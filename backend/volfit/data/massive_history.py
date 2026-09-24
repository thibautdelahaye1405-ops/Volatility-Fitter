"""Massive/Polygon HISTORICAL NBBO chains — the two-sided past.

A past-day chain used to be MARKS only (bid = ask = an aggregate close off the
flat files) because the whole-market ``quotes_v1`` tick file takes hours to
scan. But the REST ``/v3/quotes/{O:…}`` endpoint answers ONE contract's last
NBBO at-or-before any instant in one call, so a chain at a past instant — the
official close of a day, or "n minutes before close" — is N such calls on the
pooled client, run CONCURRENTLY: real bid/ask history, interactively.

    eod (a past day)      -> NBBO at-or-before that session's close
    intraday (a past ts)  -> NBBO at-or-before ts

Budget: the selected expiries' contracts, nearest-the-money first (ranked by
|ln(K/S)| / sqrt(T), so every expiry keeps its belly and a long expiry a wider
one) up to ``NBBO_MAX_CONTRACTS``; progress narrated per contract through
volfit.data.progress (the status-bar gauge reads "312 / 1500 contracts").

Concurrency (2026-09-24): an AIMD window over a pool of ``NBBO_POOL`` workers.
It opens at ``NBBO_CONCURRENCY`` in flight, widens by ``NBBO_WINDOW_STEP``
after every ``NBBO_WINDOW_CLEAN`` clean calls up to the pool size, halves on a
retried rate-limit / timeout / 5xx event (``MassiveHttp.get``'s ``on_retry``
hook) and never drops under ``NBBO_WINDOW_FLOOR``. The backtest's client
sustained 40 in flight on this key with no 429; the app starts where it used
to run and earns the rest. ``_nbbo_window`` keeps the last frame's window for
diagnostics.

Degradation is PER FRAME, not per session (2026-09-24 — until then ONE
rate-limit body gated every later past chain to marks): only an entitlement
answer (``MassiveEntitlement``) sets the session gate. A rate-limited call is
retried with backoff inside ``_get``; still failing, that contract is SKIPPED
and the frame completes with what it got (``quote_kind="quotes"``, the gauge
reads "… · throttled: n skipped"); a frame that ends with ZERO quotes falls
back to marks as before, but the next frame tries the quotes again.

Entitlement: historical quotes sit a tier above aggregates. The FIRST contract
is fetched synchronously as the probe; ``NOT_AUTHORIZED`` gates the path for
the session — the provider then falls back to the aggregate MARKS (flat files,
else per-contract minute bars) and says so (``historical_quote_kind`` ->
"marks", ``nbbo_history_gate`` -> the reason). Spot at the instant: the
underlying's own NBBO mid, else its minute aggregate (each a separate Massive
product), else put-call parity on the reconstructed chain — so an options-only
plan works.
"""

from __future__ import annotations

import math
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from volfit.data import progress
from volfit.data.fieldmap import price_or_none
from volfit.data.massive_http import MassiveEntitlement, MassiveError
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

#: The AIMD window's opening size — where the path used to run flat.
NBBO_CONCURRENCY = 12
#: The worker pool = the window's cap (the backtest's proven ceiling).
NBBO_POOL = 40
#: Additive step after every ``NBBO_WINDOW_CLEAN`` clean calls; the floor after halving.
NBBO_WINDOW_STEP = 4
NBBO_WINDOW_CLEAN = 50
NBBO_WINDOW_FLOOR = 4
#: Contracts per historical chain — nearest-the-money first across the selected
#: expiries. ~1500 × ~100 ms with 12 in flight ≈ 12 s worst case.
NBBO_MAX_CONTRACTS = 1500


class AdaptiveWindow:
    """A bounded in-flight window over a fixed thread pool: additive increase,
    multiplicative decrease. ``acquire`` blocks while ``in_flight >= limit``;
    ``release(ok)`` counts clean calls toward the next widening; ``throttle``
    halves the limit (floored) — the ``on_retry`` hook of every request."""

    def __init__(
        self,
        start: int = NBBO_CONCURRENCY,
        floor: int = NBBO_WINDOW_FLOOR,
        cap: int = NBBO_POOL,
        step: int = NBBO_WINDOW_STEP,
        clean_runs: int = NBBO_WINDOW_CLEAN,
    ) -> None:
        self.floor, self.cap, self.step, self.clean_runs = floor, cap, step, clean_runs
        self.limit = max(min(start, cap), floor)
        self.in_flight = 0
        self.clean = 0
        self.throttles = 0
        self.peak = 0  # the most ever in flight (a test's invariant)
        self._cond = threading.Condition()

    def acquire(self) -> None:
        with self._cond:
            while self.in_flight >= self.limit:
                self._cond.wait()
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)

    def release(self, ok: bool = True) -> None:
        with self._cond:
            self.in_flight -= 1
            if ok:
                self.clean += 1
                if self.clean >= self.clean_runs:
                    self.limit = min(self.cap, self.limit + self.step)
                    self.clean = 0
            self._cond.notify_all()

    def throttle(self, kind: str = "") -> None:
        with self._cond:
            self.limit = max(self.floor, self.limit // 2)
            self.clean = 0
            self.throttles += 1


def _ns(ts: datetime) -> int:
    """Nanoseconds since the epoch of a UTC-naive instant (the API's clock)."""
    return int(ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _short(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[-1][:120] if text else "historical quotes unavailable"


def budget_contracts(
    contracts: list[dict], spot: float | None, day: date, cap: int
) -> list[dict]:
    """The contracts worth a request: all of them under ``cap``, else the
    nearest-the-money first — ranked by |ln(K/S)| / sqrt(T) (T at least one
    day), so a long expiry keeps a wider belly and a weekly a tight one.
    Without a spot the nearest expiry's median strike stands in (listings are
    centred on the spot at listing time). Returned in (expiry, strike, C/P)
    order so the chain is deterministic whatever the completion order."""
    if len(contracts) <= cap:
        return contracts
    if spot is None or spot <= 0.0:
        nearest = min(c["expiry"] for c in contracts)
        strikes = sorted(c["strike"] for c in contracts if c["expiry"] == nearest)
        spot = strikes[len(strikes) // 2]

    def rank(c: dict) -> float:
        t = max((c["expiry"] - day).days, 1) / 365.0
        return abs(math.log(c["strike"] / spot)) / math.sqrt(t)

    kept = sorted(contracts, key=rank)[:cap]
    return sorted(kept, key=lambda c: (c["expiry"], c["strike"], c["call_put"]))


class MassiveHistoryMixin:
    """Historical NBBO chains for ``MassiveProvider`` (a mixin: it uses the
    host's ``_intraday_contracts`` / ``_quote_le`` / ``_spot_at`` /
    ``_agg_bar_le`` / ``_underlying`` / ``_spot_from_quotes`` and the
    ``hist_nbbo`` switch + ``_hist_nbbo_gate`` memory the host initialises)."""

    api_key: str
    hist_nbbo: bool
    _hist_nbbo_gate: str | None
    #: The last frame's AIMD window (diagnostics / tests); None before any frame.
    _nbbo_window: AdaptiveWindow | None = None
    #: The stock NBBO answered NOT_AUTHORIZED this session (an options-only plan).
    _stock_nbbo_gated: bool = False

    def nbbo_history_available(self) -> bool:
        """Whether past chains are served as real two-sided NBBO: a key, the
        path switched on, and no entitlement / rate-limit gate seen this session."""
        return bool(self.api_key) and self.hist_nbbo and self._hist_nbbo_gate is None

    def nbbo_history_gate(self) -> str | None:
        """Why the NBBO history path is off (None while it works)."""
        if not self.hist_nbbo:
            return "historical NBBO disabled (VOLFIT_MASSIVE_HIST_NBBO=0)"
        return self._hist_nbbo_gate

    def _fetch_nbbo_chain(
        self, ticker: str, expiries: list[date] | None, ts: datetime
    ) -> ChainSnapshot | None:
        """The chain at ``ts`` from per-contract historical NBBO; None when the
        path is gated (the caller falls back to marks), nothing is listed, or
        no contract had a quote by then (a pre-open instant)."""
        if not self.nbbo_history_available():
            return None
        contracts = self._intraday_contracts(ticker, expiries)
        if not contracts:
            return None
        ns = _ns(ts)
        window = AdaptiveWindow()
        self._nbbo_window = window
        probe = contracts[len(contracts) // 2]  # mid-listing: near the money, inside any budget
        answered: dict[str, dict | None] = {}
        try:  # the probe: one synchronous quote proves the entitlement
            answered[probe["ticker"]] = self._quote_le(probe["ticker"], ns, on_retry=window.throttle)
        except MassiveEntitlement as exc:
            self._hist_nbbo_gate = _short(exc)
            return None
        except Exception:  # noqa: BLE001 — throttled / failed even after the retries: the crawl decides
            answered[probe["ticker"]] = None
        spot_hint = self._spot_hint(ticker, ts, ns)
        chosen = budget_contracts(contracts, spot_hint, ts.date(), NBBO_MAX_CONTRACTS)
        n = len(chosen)

        def _one(c: dict) -> tuple[dict, dict, bool]:
            """(contract, quote or {}, throttled?) — never raises but for entitlement."""
            if c["ticker"] in answered:  # the probe is not re-fetched
                q = answered[c["ticker"]]
                return c, (q or {}), q is None
            window.acquire()
            ok = True
            try:
                return c, self._quote_le(c["ticker"], ns, on_retry=window.throttle), False
            except MassiveEntitlement:
                ok = False
                raise  # a mid-chain entitlement answer: abort, gate the session
            except MassiveError:  # rate / 5xx / transport still failing after the retries
                ok = False
                return c, {}, True
            except Exception:  # noqa: BLE001 — a malformed answer skips, never aborts
                return c, {}, False
            finally:
                window.release(ok)

        quotes: list[OptionQuote] = []
        styles: list[str] = []
        throttled = 0
        pool = ThreadPoolExecutor(max_workers=NBBO_POOL, thread_name_prefix="volfit-nbbo")
        try:
            futures = [pool.submit(_one, c) for c in chosen]
            for i, fut in enumerate(futures, 1):
                c, q, skipped = fut.result()
                throttled += int(skipped)
                label = f"{i} / {n} contracts" + (f" · throttled: {throttled} skipped" if throttled else "")
                progress.report(i, n, label)
                bid, ask = price_or_none(q.get("bid_price")), price_or_none(q.get("ask_price"))
                if bid is None and ask is None:
                    continue
                quotes.append(
                    OptionQuote(
                        ticker=ticker.upper(), expiry=c["expiry"], strike=c["strike"],
                        call_put=c["call_put"], bid=bid, ask=ask, last=None, volume=None,
                        open_interest=None, timestamp=ts,
                    )
                )
                if c["style"] in ("american", "european"):
                    styles.append(c["style"])
        except MassiveEntitlement as exc:
            self._hist_nbbo_gate = _short(exc)
            return None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if not quotes:
            return None  # all throttled / nothing quoted by then: marks for THIS frame only
        spot = spot_hint if spot_hint else self._spot_from_quotes(quotes)
        if spot is None:
            raise RuntimeError(
                f"Massive: no spot for {ticker!r} at {ts.isoformat()} (no underlying quote, no parity)"
            )
        from volfit.data.massive import _resolve_style, _settlement_for

        return ChainSnapshot(
            ticker=ticker.upper(), spot=spot, timestamp=ts, quotes=quotes,
            exercise_style=_resolve_style(styles), tick_size=US_OPTION_TICK,
            settlement=_settlement_for(quotes, ticker), quote_kind="quotes",
        )

    def _spot_hint(self, ticker: str, ts: datetime, ns: int) -> float | None:
        """The underlying at the instant, best-effort: its NBBO mid, else its
        minute-aggregate close — each a separate Massive product, so an
        options-only plan gets neither and the caller relies on parity. A
        NOT_AUTHORIZED answer from the stock NBBO is remembered for the
        session (``_stock_nbbo_gated``): one call and one meter error per
        frame fewer on an options-only plan."""
        if not self._stock_nbbo_gated:
            try:
                return float(self._spot_at(ticker, ns))
            except MassiveEntitlement:  # a separate product: don't ask again this session
                self._stock_nbbo_gated = True
            except Exception:  # noqa: BLE001 — no quote / throttled: try the bar
                pass
        try:
            ms = int(ts.replace(tzinfo=timezone.utc).timestamp() * 1000)
            bar = self._agg_bar_le(self._underlying(ticker), ts.date(), ms)
            return price_or_none(bar.get("c")) if bar else None
        except Exception:  # noqa: BLE001 — parity is the last resort
            return None

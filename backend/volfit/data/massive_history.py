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
one) up to ``NBBO_MAX_CONTRACTS``; ``NBBO_CONCURRENCY`` requests in flight;
progress narrated per contract through volfit.data.progress (the status-bar
gauge reads "312 / 1500 contracts").

Entitlement: historical quotes sit a tier above aggregates. The FIRST contract
is fetched synchronously as the probe; ``NOT_AUTHORIZED`` (or a rate-limit
``ERROR`` body at any point) gates the path for the session — the provider then
falls back to the aggregate MARKS (flat files, else per-contract minute bars)
and says so (``historical_quote_kind`` -> "marks", ``nbbo_history_gate`` -> the
reason). Spot at the instant: the underlying's own NBBO mid, else its minute
aggregate (each a separate Massive product), else put-call parity on the
reconstructed chain — so an options-only plan works.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from volfit.data import progress
from volfit.data.fieldmap import price_or_none
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

#: Concurrent per-contract quote requests (the pooled httpx client is thread-safe).
NBBO_CONCURRENCY = 12
#: Contracts per historical chain — nearest-the-money first across the selected
#: expiries. ~1500 × ~100 ms with 12 in flight ≈ 12 s worst case.
NBBO_MAX_CONTRACTS = 1500


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
        probe = contracts[len(contracts) // 2]  # mid-listing: near the money, inside any budget
        try:  # the probe: one synchronous quote proves the entitlement
            first = self._quote_le(probe["ticker"], ns)
        except RuntimeError as exc:
            self._hist_nbbo_gate = _short(exc)
            return None
        spot_hint = self._spot_hint(ticker, ts, ns)
        chosen = budget_contracts(contracts, spot_hint, ts.date(), NBBO_MAX_CONTRACTS)
        n = len(chosen)
        answered = {probe["ticker"]: first}  # the probe is not re-fetched

        def _one(c: dict) -> tuple[dict, dict]:
            if c["ticker"] in answered:
                return c, answered[c["ticker"]]
            try:
                return c, self._quote_le(c["ticker"], ns)
            except RuntimeError:
                raise  # entitlement / rate limit: abort the whole reconstruction
            except Exception:  # noqa: BLE001 — a slow/failed contract skips, never aborts
                return c, {}

        quotes: list[OptionQuote] = []
        styles: list[str] = []
        pool = ThreadPoolExecutor(max_workers=NBBO_CONCURRENCY, thread_name_prefix="volfit-nbbo")
        try:
            futures = [pool.submit(_one, c) for c in chosen]
            for i, fut in enumerate(futures, 1):
                c, q = fut.result()
                progress.report(i, n, f"{i} / {n} contracts")
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
        except RuntimeError as exc:
            self._hist_nbbo_gate = _short(exc)
            return None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if not quotes:
            return None
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
        options-only plan gets neither and the caller relies on parity."""
        try:
            return float(self._spot_at(ticker, ns))
        except Exception:  # noqa: BLE001 — not entitled / no quote: try the bar
            pass
        try:
            ms = int(ts.replace(tzinfo=timezone.utc).timestamp() * 1000)
            bar = self._agg_bar_le(self._underlying(ticker), ts.date(), ms)
            return price_or_none(bar.get("c")) if bar else None
        except Exception:  # noqa: BLE001 — parity is the last resort
            return None

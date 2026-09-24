"""The read side of the Massive live book — the merge, the REST memory and
the health model (the second half of volfit.data.massive_stream, split out
on 2026-09-24 to keep each module under the 400-line policy).

``MassiveStreamReadsMixin`` is mixed into ``MassiveStreamMixin`` and expects
its state (``_live_book``, ``_stats``, ``_sockets``, ``_requested``,
``_stream_dropped``, ``_stream_index``, ``_ticker_plans``, ``stream_cap``,
``stream_connections``, ``_session_open``, ``_ws_urls``) plus the host
provider's ``_intraday_contracts``, ``_note_spot``, ``_snapshot_results`` and
``_rest_chain``. See the massive_stream module docstring for the design (why
the book is capped, what the merge fills, what "served" means per ticker).
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime, timezone

from volfit.data.massive_book import ns_to_utc_naive
from volfit.data.stream_allocation import normalize_focus
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

log = logging.getLogger("volfit.massive_ws")

#: How often the streaming branch refreshes a streaming ticker's REST memory
#: (the default; env ``VOLFIT_MASSIVE_REST_SECONDS`` overrides, floored at 15).
STREAM_REST_SECONDS = 60.0
REST_SECONDS_ENV = "VOLFIT_MASSIVE_REST_SECONDS"
REST_SECONDS_FLOOR = 15.0
#: Outside the session, a stream whose last MESSAGE is older than this reads idle.
_IDLE_SECONDS = 60.0


def cluster_kind(url: str | None) -> str | None:
    if not url:
        return None
    return "delayed" if "delayed" in url else "realtime"


def rest_seconds_setting(value: float | None = None) -> float:
    """The REST cadence behind the book: ``value`` when given, else the env
    knob, else the default — never under ``REST_SECONDS_FLOOR`` (one windowed
    snapshot per ticker per 15 s is the most the REST budget should carry;
    a malformed value falls back to the default)."""
    if value is None:
        raw = os.environ.get(REST_SECONDS_ENV, "").strip()
        try:
            value = float(raw) if raw else STREAM_REST_SECONDS
        except ValueError:
            value = STREAM_REST_SECONDS
    return max(REST_SECONDS_FLOOR, float(value))


class MassiveStreamReadsMixin:
    """The merge (``_chain_from_book``), the REST memory, the focus / tier
    readings and the health readings."""

    # ----------------------------------------------------------- focus, tier
    def set_stream_focus(self, nodes) -> bool:
        """Hold the on-screen nodes ``{(TICKER, expiry ISO)}`` for the next
        plan; True when they CHANGED (the caller then re-plans in place),
        False on every tick where nothing moved — never a re-plan for nothing."""
        new = normalize_focus(nodes)
        if new == self._focus:
            return False
        self._focus = new
        return True

    def stream_tier(self, ticker: str, expiry: date) -> str:
        """How the node is served: ``"live"`` when EVERY planned contract of
        (ticker, expiry) is on a connection (the focus, or a universe that
        fits the budget), ``"rest"`` when the belly ticks and the rest comes
        from the REST memory — or nothing of the node is planned (beyond the
        window: its quotes are the memory's) — ``"none"`` when the ticker is
        not served at all."""
        if not self.is_streaming_ticker(ticker):
            return "none"
        index = self._stream_index
        mine = [c for c in self._ticker_plans.get(ticker.upper(), []) if index[c][1]["expiry"] == expiry]
        if not mine:
            return "rest"
        live = set(self._live_set())
        return "live" if all(c in live for c in mine) else "rest"

    @property
    def rest_seconds(self) -> float:
        """The REST cadence (s) behind the live book (the SSE badge's reading)."""
        return self._rest_seconds

    def _allocation_line(self) -> str:
        """One log line of the last allocation: per-ticker live / requested."""
        alloc = self._allocation
        if alloc is None:
            return "no allocation"
        parts = [f"{t} {s.live}/{s.requested}" + (f" (focus {s.focus})" if s.focus else "")
                 for t, s in sorted(alloc.shares.items())]
        focus = ", ".join(f"{t}|{e}" for t, e in alloc.focus) or "none"
        return f"{'; '.join(parts) or 'nothing planned'} · focus {focus} · floor {self._floor}"

    # ---------------------------------------------------------------- reads
    def _spot_from_quotes(self, quotes: list[OptionQuote]) -> float | None:
        """Parity forward (spot proxy) from already-built two-sided quotes."""
        from volfit.data.massive import _parity_forward

        by_exp: dict[date, dict[float, dict[str, float]]] = {}
        for q in quotes:
            if q.bid is None or q.ask is None or q.ask < q.bid:
                continue
            by_exp.setdefault(q.expiry, {}).setdefault(q.strike, {})[q.call_put] = 0.5 * (q.bid + q.ask)
        return _parity_forward(by_exp)

    def _book_parity_spot(self, ticker: str, expiries: list[date] | None = None) -> float | None:
        """The parity forward of the BOOKED ticks (the nearest selected expiry,
        else the plan's nearest expiry with enough pairs); never a request."""
        book = self._live_book
        if book is None:
            return None
        if expiries:
            rows = self._intraday_contracts(ticker, sorted(expiries)[:1])
        else:
            rows = [self._stream_index[c][1] for c in self._ticker_plans.get(ticker.upper(), []) if c in self._stream_index]
        quotes: list[OptionQuote] = []
        for row in rows:
            tick = book.quote(row["ticker"])
            if tick is None:
                continue
            quotes.append(OptionQuote(
                ticker=ticker.upper(), expiry=row["expiry"], strike=row["strike"],
                call_put=row["call_put"], bid=tick.bid, ask=tick.ask, last=None,
                volume=None, open_interest=None, timestamp=None,
            ))
        return self._spot_from_quotes(quotes) if quotes else None

    def book_spot(self, ticker: str, expiries: list[date] | None = None) -> float | None:
        """Book-only spot (the nearest selected expiry's parity forward off the
        streamed ticks); None when not streaming or the book cannot imply one."""
        return self._book_parity_spot(ticker, expiries) if self._live_book is not None else None

    def live_chain(self, ticker: str, expiries: list[date] | None) -> ChainSnapshot | None:
        """BOOK-ONLY live chain (no request, ever): the merged chain for the
        selected expiries, or None when not streaming / nothing booked yet. The
        live quote-table tick stream polls this at 1 Hz."""
        if self._live_book is None:
            return None
        return self._chain_from_book(ticker, expiries)

    def _chain_from_book(self, ticker: str, expiries: list[date] | None) -> ChainSnapshot | None:
        """The live chain: every listed contract of the selection — booked ones
        with their tick (stamped at the provider tick time), the rest from the
        last REST snapshot (its own stamps), else unquoted. None until at least
        one tick is booked and a forward can be implied (the caller then
        REST-fetches the first frame)."""
        from volfit.data.massive import _resolve_style, _settlement_for

        book = self._live_book
        rows = self._intraday_contracts(ticker, expiries)
        if book is None or not rows:
            return None
        key = ticker.upper()
        rest = self._last_rest_chain.get(key)
        rest_by = {(q.expiry, q.strike, q.call_put): q for q in rest.quotes} if rest is not None else {}
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        newest: datetime | None = None
        quotes: list[OptionQuote] = []
        booked: list[OptionQuote] = []
        styles: list[str] = []
        for row in rows:
            tick = book.quote(row["ticker"])
            if tick is not None:
                ts = ns_to_utc_naive(tick.ts)
                if ts is not None and (newest is None or ts > newest):
                    newest = ts
                quote = OptionQuote(
                    ticker=key, expiry=row["expiry"], strike=row["strike"], call_put=row["call_put"],
                    bid=tick.bid, ask=tick.ask, last=None, volume=None, open_interest=None,
                    timestamp=ts or now,
                )
                booked.append(quote)
            else:
                filler = rest_by.get((row["expiry"], row["strike"], row["call_put"]))
                if filler is not None:
                    quote = OptionQuote(
                        ticker=key, expiry=row["expiry"], strike=row["strike"], call_put=row["call_put"],
                        bid=filler.bid, ask=filler.ask, last=filler.last, volume=filler.volume,
                        open_interest=filler.open_interest, timestamp=filler.timestamp,
                    )
                else:
                    quote = OptionQuote(
                        ticker=key, expiry=row["expiry"], strike=row["strike"], call_put=row["call_put"],
                        bid=None, ask=None, last=None, volume=None, open_interest=None, timestamp=now,
                    )
            quotes.append(quote)
            if row["style"] in ("american", "european"):
                styles.append(row["style"])
        if not booked:
            return None
        spot = self._spot_from_quotes(booked) or self._spot_from_quotes(quotes)
        if spot is None:
            return None
        self._note_spot(key, spot)
        return ChainSnapshot(
            ticker=key, spot=spot, timestamp=newest or now, quotes=quotes,
            exercise_style=_resolve_style(styles), tick_size=US_OPTION_TICK,
            settlement=_settlement_for(quotes, ticker),
        )

    # ------------------------------------------------------- the REST memory
    def refresh_stream_rest(self, ticker: str, expiries: list[date] | None, block: bool = False) -> Future | ChainSnapshot | None:
        """Refresh the ticker's REST memory (the wings the book does not carry)
        at most every ``rest_seconds`` (60 by default) — one windowed snapshot
        per ticker per cadence, on a background worker unless ``block``. Every
        ordinary REST ``fetch_chain`` refreshes it too."""
        key = ticker.upper()
        if not self._sockets:
            return None
        now = time.monotonic()
        last = self._last_rest_at.get(key)
        if last is not None and now - last < self._rest_seconds:
            return None
        if key in self._rest_inflight:
            return None
        self._rest_inflight.add(key)
        if block:
            return self._pull_stream_rest(key, expiries)
        if self._rest_pool is None:
            self._rest_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="massive-rest")
        return self._rest_pool.submit(self._pull_stream_rest, key, expiries)

    def _pull_stream_rest(self, key: str, expiries: list[date] | None) -> ChainSnapshot | None:
        try:
            results = self._snapshot_results(key, expiries)
            stamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
            return self._rest_chain(key, results, stamp, prev_close=False)
        except Exception as exc:  # noqa: BLE001 — the memory keeps its last snapshot
            log.warning("massive stream: %s REST refresh failed: %s", key, exc)
            return None
        finally:
            self._last_rest_at[key] = time.monotonic()
            self._rest_inflight.discard(key)

    def _remember_rest_chain(self, chain: ChainSnapshot) -> None:
        """Called by the REST chain builder for a LIVE two-sided chain."""
        self._last_rest_chain[chain.ticker.upper()] = chain
        self._last_rest_at[chain.ticker.upper()] = time.monotonic()

    # ---------------------------------------------------------------- health
    def _socket_counts(self) -> tuple[int, int, int, bool]:
        """``(subscribed, acknowledged, refused, any running)`` across connections."""
        sub = ack = ref = 0
        running = False
        for socket in self._sockets:
            counter = getattr(socket, "counts", None)
            if counter is not None:
                a, b, c = counter()
                sub, ack, ref = sub + a, ack + b, ref + c
            else:
                sub += len(socket.contracts)
            running = running or bool(socket.is_running())
        return sub, ack, ref, running

    def _stream_status(self) -> tuple[str, str] | None:
        """``(level, detail)`` for the Data Source light while streaming (None
        otherwise), computed live: red on a dead / refused / unauthenticated
        stream, amber while connecting / warming / idle / on the delayed
        cluster, green when the real-time cluster is delivering quotes."""
        if not self._sockets or self._stats is None:
            return None
        snap = self._stats.snapshot()
        sub, ack, ref, running = self._socket_counts()
        if not running:
            return ("red", f"stream dead · reconnecting ({snap['reconnects']})")
        if snap["authFailed"]:
            return ("red", f"stream {snap['lastError'] or 'auth failed'}")
        if ref:
            text = (snap["lastError"] or "subscription refused").split(" · ")[0]
            return ("red", f"stream refused: {text[:60]} · {len(self._requested):,} requested / {self.stream_cap:,} cap")
        if not snap["connected"]:
            more = f" · reconnecting ({snap['reconnects']})" if snap["reconnects"] else ""
            return ("amber", f"stream connecting · {sub:,} subscribed{more}")
        extra = f" · {len(self._stream_dropped):,} over cap" if self._stream_dropped else ""
        if ack == 0:
            return ("amber", f"stream warming · {sub:,} subscribed, 0 acked{extra}")
        age = snap["lastMessageAge"]
        if age is None or (not self._session_open() and age > _IDLE_SECONDS):
            since = snap["lastMessageUtc"]
            when = f" since {since[11:16]} UTC" if since else ""
            return ("amber", f"stream idle{when} · closed session · {ack:,} acked{extra}")
        detail = f"streaming {ack:,} · {snap['rate']:.0f} msg/s · last {age:.0f} s{extra}"
        fresh_quote = snap["lastQuoteAge"] is not None and snap["lastQuoteAge"] < _IDLE_SECONDS
        level = "green" if cluster_kind(snap["url"]) == "realtime" and fresh_quote else "amber"
        return (level, detail)

    def stream_stats(self) -> dict | None:
        """The plain health dict the ``/datasources`` payload carries (None when
        not streaming): the shared counters plus the subscription counts, the
        cap, the per-ticker served flags and the light's own reading."""
        if not self._sockets or self._stats is None:
            return None
        snap = self._stats.snapshot()
        sub, ack, ref, running = self._socket_counts()
        status = self._stream_status() or ("amber", "")
        alloc = self._allocation
        snap.update({
            "running": running,
            "cluster": cluster_kind(snap["url"] or self._ws_urls()[0]),
            "subscribed": sub,
            "acknowledged": ack,
            "refused": ref,
            "overCap": len(self._stream_dropped),
            "requested": len(self._requested),
            "cap": self.stream_cap,
            "connections": self.stream_connections,
            "sessionOpen": self._session_open(),
            "tickers": {t: self.is_streaming_ticker(t) for t in sorted(self._ticker_plans)},
            # the allocation (volfit.data.stream_allocation): per-ticker live /
            # requested / focus counts, the focus nodes, the floor, the REST cadence
            "allocation": alloc.as_dict()["tickers"] if alloc is not None else {},
            "focus": [f"{t}|{e}" for t, e in sorted(self._focus)],
            "floor": self._floor,
            "restSeconds": self._rest_seconds,
            "level": status[0],
            "detail": status[1],
        })
        return snap

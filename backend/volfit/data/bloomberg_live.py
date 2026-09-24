"""Streaming half of the Bloomberg provider — the live ``//blp/mktdata`` book.

``BloombergStreamingMixin`` gives ``BloombergProvider`` (volfit.data.bloomberg)
the same duck-typed streaming contract the Massive provider exposes, so
``AppState.sync_streaming`` and the scheduler's throttled refit drive it with no
changes (volfit/api/state.py, volfit/api/scheduler.py):

    option_tickers(ticker, expiries) -> [security, ...]   what to subscribe
    start_streaming(contracts) / stop_streaming()
    update_streaming(contracts)   INCREMENTAL universe edit (same session)
    is_streaming() / streaming_contracts()

While streaming, ``fetch_chain(live)`` and ``spot()`` are served from the
``BbgBook`` (volfit.data.bloomberg_stream) — no ``bdp`` at all: the real-time
spot poll and every chain refresh stop touching the metered reference-data
quota. The underlying is subscribed alongside its contracts so spot comes off
the stream too. Reference data still needed (and still metered, once per
ticker): the ``OPT_CHAIN`` listing (``bds``) and ONE ``PX_LAST`` to centre the
strike window before the stream exists.

Subscription budget: the Desktop API caps concurrent real-time subscriptions
per Terminal, so contracts are (1) windowed by the provider's ``strike_window``
(the shared PER-EXPIRY rule of volfit.data.strike_window by default — a 2-day
rung costs a few percent of the ladder, a 1-year rung the wide band) around a
HYSTERESIS-held spot centre (re-centred only after a > ``RECENTER_PCT`` move —
otherwise a spot wobbling across a strike boundary would restart the stream
every tick) and (2) capped at ``max_subscriptions`` by the shared allocation
policy (volfit.data.bloomberg_plan / stream_allocation: the focus nodes'
whole rungs, every ticker's floor, a fair share of the remainder — since
2026-09-24; nearest-the-money within each ticker). The same plan sets each
security's conflation ``interval``: the focus tickers (or, without a focus,
every ticker's nearest two rungs) and the underlyings at ``stream_interval``
(1 s), the rest at the slow tier (``VOLFIT_BBG_STREAM_INTERVAL_SLOW``, 5 s);
a focus change re-subscribes ONLY the securities whose interval changed.
``streaming_contracts`` reports the REQUESTED set (pre-cap) so the scheduler's
universe diff stays stable; ``feed_status`` surfaces the dropped count.

Book first: ``fetch_chain(live)`` calls ``_chain_from_book_first``, which waits
up to the provider's ``book_first_wait`` for the underlying's paint AND the
selection's coverage (a selection edit is resubscribed on the next scheduler
tick) before the metered fallback is even considered; any paint read off the
book clears a stale reference refusal from the status light.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

from volfit.data.bloomberg_parse import ParsedOption
from volfit.data.bloomberg_plan import BloombergPlanMixin, slow_interval_setting
from volfit.data.bloomberg_stream import BbgBook, BloombergSubscription
from volfit.data.stream_allocation import Allocation, ticker_floor
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

#: Re-centre the strike window only after the spot moves this far from the
#: centre used for the current subscription (fraction of spot).
RECENTER_PCT = 0.05
#: Retry a failed (metered) centring spot hit at most this often.
_SPOT_RETRY_SECONDS = 60.0
#: Seconds a book read waits for the underlying's INITPAINT after a fresh start
#: before falling back to the metered reference path.
_WARMUP_WAIT = 2.0
#: A stream whose newest stamp is older than this is reported idle (pre-market,
#: closed session) — the book retains each contract's last tick across quiet spells.
_IDLE_SECONDS = 20 * 60.0


class BloombergStreamingMixin(BloombergPlanMixin):
    """Streaming contract for ``BloombergProvider`` (expects the host class to
    provide ``_security``, ``_select_contracts``, ``_window_contracts``,
    ``_spot``, ``strike_window``; the plan / allocation / conflation tiers in
    volfit.data.bloomberg_plan)."""

    # ---------------------------------------------------------------- init
    def _init_streaming(
        self,
        stream_interval: float | None = 1.0,
        max_subscriptions: int = 3000,
        stream_session_factory=None,
        stream_host: str | None = None,
        stream_port: int | None = None,
        stream_interval_slow: float | None = None,
        stream_floor: int | None = None,
    ) -> None:
        self._stream_interval = stream_interval
        #: The slow conflation tier (None = env VOLFIT_BBG_STREAM_INTERVAL_SLOW,
        #: 5 s) and the per-ticker floor of the allocation (None = env
        #: VOLFIT_MASSIVE_WS_FLOOR, 60 — shared with the Massive book).
        self._slow_interval = slow_interval_setting(stream_interval_slow)
        self._floor = ticker_floor() if stream_floor is None else max(0, int(stream_floor))
        self._focus: set[tuple[str, str]] = set()  # (TICKER, expiry ISO) on screen
        self._allocation: Allocation | None = None
        self._max_subscriptions = max(1, int(max_subscriptions))
        self._stream_factory = stream_session_factory
        self._stream_host, self._stream_port = stream_host, stream_port
        self._book: BbgBook | None = None
        self._sub: BloombergSubscription | None = None
        self._requested: list[str] = []  # option securities AppState asked for
        self._stream_dropped: set[str] = set()  # requested but over the cap
        self._stream_tickers: set[str] = set()  # underlyings in the current stream
        self._stream_index: dict[str, tuple[str, ParsedOption]] = {}  # sec -> (ticker, contract)
        self._stream_center: dict[str, float] = {}  # ticker -> spot the window is centred on
        self._center_failed_at: dict[str, float] = {}
        # ``_oi_cache`` / ``_style_cache`` (the reference-only facts a streamed
        # chain reports) are owned by BloombergReferenceMixin._init_reference.

    # ------------------------------------------------------- what to stream
    def _window_center(self, ticker: str) -> float | None:
        """Spot to centre the strike window on: the live book spot once a
        > RECENTER_PCT move is seen, else the held centre, else ONE metered
        PX_LAST (retried at most every minute); None when none is obtainable."""
        key = ticker.upper()
        held = self._stream_center.get(key)
        live = self._book_spot(ticker, wait=0.0) if self.is_streaming() else None
        if live is not None and (held is None or abs(live / held - 1.0) > RECENTER_PCT):
            self._stream_center[key] = held = live
        if held is not None:
            return held
        last_fail = self._center_failed_at.get(key)
        if last_fail is not None and time.monotonic() - last_fail < _SPOT_RETRY_SECONDS:
            return None
        try:
            self._stream_center[key] = held = float(self._spot(ticker))
        except Exception:  # noqa: BLE001 — no Terminal / refused: back off
            self._center_failed_at[key] = time.monotonic()
            return None
        return held

    def _stream_plan(self, ticker: str, expiries: list[date] | None) -> list[ParsedOption]:
        """The windowed contracts of ``ticker``'s selection (what the stream should
        carry). Raises ValueError (via ``_select_contracts``) when nothing is listed;
        a missing centre means 'cannot plan yet' -> empty."""
        contracts = self._select_contracts(ticker, expiries)
        center = self._window_center(ticker)
        if center is None:
            return []
        return self._window_contracts(contracts, center)

    def option_tickers(self, ticker: str, expiries: list[date] | None) -> list[str]:
        """Securities the active universe wants streamed for ``ticker`` (cheap once
        the OPT_CHAIN listing + window centre are cached — called every tick)."""
        plan = self._stream_plan(ticker, expiries)
        key = ticker.upper()
        for c in plan:
            self._stream_index[c.security] = (key, c)
        return [c.security for c in plan]

    # ------------------------------------------------------------ lifecycle
    def start_streaming(self, contracts: list[str]) -> None:
        """Subscribe the underlyings + ``contracts`` (the allocation's live set,
        each at its tier's conflation interval) on a fresh session and serve
        live reads from the book. Replaces any stream."""
        self.stop_streaming()
        securities = self._plan_subscriptions(contracts)
        self._book = BbgBook()
        kwargs = {
            "interval": self._stream_interval, "session_factory": self._stream_factory,
            "intervals": self._interval_map(securities),
        }
        if self._stream_host:
            kwargs["host"] = self._stream_host
        if self._stream_port:
            kwargs["port"] = int(self._stream_port)
        self._sub = BloombergSubscription(securities, self._book, **kwargs)
        self._sub.start()

    def update_streaming(self, contracts: list[str]) -> tuple[list[str], list[str]]:
        """INCREMENTAL universe edit: re-plan for ``contracts`` and diff against the
        live subscription — subscribe only the new securities, unsubscribe only
        the gone ones, move only the ones whose conflation tier changed, on the
        SAME session (no restart, no repaint of the rest, no warming gap).
        Covers ticker/expiry edits, a strike-window re-centre, cap re-ranking
        and a focus change alike. Starts a stream when none is running; stops
        it when the universe empties. Returns ``(added, removed)``."""
        if not self.is_streaming() or self._sub is None:
            self.start_streaming(contracts)
            return (list(self._sub.securities) if self._sub else [], [])
        if not contracts:
            self.stop_streaming()
            return ([], [])
        wanted = self._plan_subscriptions(contracts)
        have = set(self._sub.securities)
        added = self._sub.subscribe([s for s in wanted if s not in have])
        removed = self._sub.unsubscribe([s for s in have if s not in set(wanted)])
        self._sub.set_intervals(self._interval_map(wanted))  # the tiers of the kept ones
        return (added, removed)

    def stop_streaming(self) -> None:
        if self._sub is not None:
            self._sub.stop()
            self._sub = None
        self._book = None
        self._requested = []
        self._stream_dropped = set()
        self._stream_tickers = set()

    def is_streaming(self) -> bool:
        return self._sub is not None and self._sub.is_running()

    def streaming_contracts(self) -> set[str]:
        """The REQUESTED set (pre-cap) — the scheduler diffs this against the
        universe to decide a resubscribe, so it must echo what it asked for."""
        return set(self._requested) if self._sub is not None else set()

    def live_chain(self, ticker: str, expiries: list[date] | None) -> ChainSnapshot | None:
        """BOOK-ONLY live chain (never a metered request): the streamed chain for
        the selected expiries, or None when not streaming / not painted / not
        covered. The live quote-table tick stream (volfit.api.table_stream) polls
        this at 1 Hz — unlike ``fetch_chain`` it must never fall back to ``bdp``."""
        return self._chain_from_book(ticker, expiries)

    # -------------------------------------------------------------- reads
    def _book_spot(self, ticker: str, wait: float = _WARMUP_WAIT) -> float | None:
        """Underlying spot off the stream (last, else NBBO mid); waits up to
        ``wait`` s for the INITPAINT right after a start. None if unavailable."""
        if self._book is None:
            return None
        sec = self._security(ticker)
        tick = self._book.wait_for(sec, wait) if wait > 0.0 else self._book.quote(sec)
        if tick is None:
            return None
        value = tick.last
        if value is None and tick.bid is not None and tick.ask is not None:
            value = 0.5 * (tick.bid + tick.ask)
        if value is not None:
            # A subscription paint is a request Bloomberg answered: a refusal the
            # light still shows from an earlier reference call is stale.
            self._last_error = None
        return value

    def _chain_from_book_first(self, ticker: str, expiries: list[date] | None) -> ChainSnapshot | None:
        """BOOK FIRST: the book's chain, waiting up to ``book_first_wait`` s for
        the underlying's paint and the selection's coverage (polled every 0.1 s
        — the scheduler resubscribes an edited selection within a tick). None
        once the budget is spent, or at once when the underlying was refused
        (nothing to wait for) or the stream stopped."""
        deadline = time.monotonic() + float(getattr(self, "book_first_wait", _WARMUP_WAIT))
        while True:
            if not self.is_streaming() or self._book is None:
                return None
            if self._security(ticker) in self._book.failures():
                return None
            remaining = deadline - time.monotonic()
            snap = self._chain_from_book(ticker, expiries, wait=max(remaining, 0.0))
            if snap is not None:
                return snap
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return None
            time.sleep(min(0.1, remaining))

    def _chain_from_book(
        self, ticker: str, expiries: list[date] | None, wait: float = _WARMUP_WAIT
    ) -> ChainSnapshot | None:
        """The live chain for ``ticker``'s selection built from the book.

        None (caller falls back to the metered reference fetch) when not streaming,
        when the underlying has not painted within ``wait`` s, or when the
        selection is not fully covered by the subscription (a selection edit the
        scheduler has not resubscribed for yet) — an explicit fetch must never
        silently miss contracts. Over-cap contracts are the exception: they are
        carried unquoted. Quotes are stamped with the PROVIDER tick times (the
        honest staleness signal across quiet periods), the chain with the newest
        of them."""
        if not self.is_streaming() or self._book is None or self._sub is None:
            return None
        spot = self._book_spot(ticker, wait=wait)
        if spot is None:
            return None
        plan = self._stream_plan(ticker, expiries)
        subscribed = set(self._sub.securities)
        if not plan or any(
            c.security not in subscribed and c.security not in self._stream_dropped for c in plan
        ):
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        key = ticker.upper()
        ticks = [(c, self._book.quote(c.security)) for c in plan]
        stamps = [t.ts for _, t in ticks if t is not None and t.ts is not None]
        under = self._book.quote(self._security(ticker))
        if under is not None and under.ts is not None:
            stamps.append(under.ts)
        # INITPAINT summaries carry no per-side stamp: an un-stamped quote is at
        # most as fresh as the newest stamped tick of the chain (on a delayed feed
        # that is 15 min behind the clock — 'now' would overstate its freshness).
        newest = max(stamps) if stamps else None
        quotes: list[OptionQuote] = []
        for c, tick in ticks:
            quotes.append(
                OptionQuote(
                    ticker=key,
                    expiry=c.expiry,
                    strike=c.strike,
                    call_put=c.call_put,
                    bid=tick.bid if tick else None,
                    ask=tick.ask if tick else None,
                    last=tick.last if tick else None,
                    volume=tick.volume if tick else None,
                    open_interest=self._oi_cache.get(c.security),
                    timestamp=(tick.ts if tick else None) or newest or now,
                )
            )
        style = self._style_cache.get(key) or (
            "european" if self._security(ticker).endswith(" Index") else "american"
        )
        return ChainSnapshot(
            ticker=key,
            spot=spot,
            timestamp=newest or now,
            quotes=quotes,
            exercise_style=style,
            tick_size=US_OPTION_TICK,
            settlement=self._settlement(key, {q.expiry for q in quotes}),  # the kept root per date
        )

    # ------------------------------------------------------------- status
    def _stream_status(self) -> tuple[str, str] | None:
        """``(level, detail)`` for the Data Source light while streaming (None
        otherwise) — quota-free, read off the book: red on a session error or a
        refused underlying, amber while connecting / on a delayed stream / idle,
        green once real-time ticks flow. Mentions over-cap + refused counts."""
        if not self.is_streaming() or self._book is None or self._sub is None:
            return None
        if self._sub.last_error:
            return ("red", f"stream: {self._sub.last_error}")
        failures = self._book.failures()
        underlyings = [self._security(t) for t in sorted(self._stream_tickers)]
        for sec in underlyings:
            if sec in failures:
                return ("red", f"stream: {failures[sec]}")
        started = self._book.started()
        if started == 0:
            return ("amber", "stream connecting")
        extras = []
        if self._stream_dropped:
            extras.append(f"{len(self._stream_dropped)} over cap")
        refused = [s for s in failures if s not in underlyings]
        if refused:
            extras.append(f"{len(refused)} refused")
        suffix = "".join(f" · {e}" for e in extras)
        newest = self._book.newest_ts()
        if newest is None:
            if self._book.size() == 0:
                return ("amber", f"stream warming · {started} subscribed{suffix}")
            # Painted (INITPAINT last-known values) but no stamped tick yet — the
            # signature of a session opened outside trading hours: the book is
            # serving, just not moving. Say so rather than "warming" forever.
            return ("amber", f"streaming {started} · no tick stamp yet{suffix}")
        age = (datetime.now(timezone.utc).replace(tzinfo=None) - newest).total_seconds()
        if age > _IDLE_SECONDS:
            return ("amber", f"stream idle since {newest:%H:%M} UTC · {started} subscribed{suffix}")
        slow = [t for t in sorted(self._stream_tickers) if self._book.delayed([self._security(t)])]
        if slow:
            which = "" if len(slow) == len(underlyings) else f" ({', '.join(slow)})"
            return ("amber", f"streaming {started} · delayed feed{which}{suffix}")
        return ("green", f"streaming {started} · real-time{suffix}")

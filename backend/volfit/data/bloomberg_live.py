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

Bucket rotation (2026-09-24, volfit.data.bloomberg_rotation — the WHY is
there): over the cap a worker cycles the over-cap contracts through
``rotation_slots`` reserved slots into a paint memory, and ``_chain_from_book``
serves those paints with their own stamp and spot beside the live ticks.
``update_streaming`` diffs the LIVE set only, under the worker's lock: a
bucket in flight is never touched by a re-plan. Health: bloomberg_health.
"""

from __future__ import annotations

import time
from contextlib import nullcontext
from datetime import date, datetime, timezone

from volfit.data.bloomberg_health import BloombergHealthMixin
from volfit.data.bloomberg_parse import ParsedOption
from volfit.data.bloomberg_plan import BloombergPlanMixin, slow_interval_setting
from volfit.data.bloomberg_rotation import (
    BUCKET_WAIT_S,
    POLL_S,
    RotationWorker,
    paint_stamp,
    rotation_slots_setting,
)
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


class BloombergStreamingMixin(BloombergHealthMixin, BloombergPlanMixin):
    """Streaming contract for ``BloombergProvider`` (expects the host class to
    provide ``_security``, ``_select_contracts``, ``_window_contracts``,
    ``_spot``, ``strike_window``; plan / tiers: bloomberg_plan, light /
    health: bloomberg_health)."""

    #: The rotation worker's book poll and bucket wait (tests shorten them).
    _rotation_poll = POLL_S
    _rotation_wait = BUCKET_WAIT_S

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
        rotation_slots: int | None = None,
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
        #: Bucket rotation: R (0 = off), the plan's pool + the slots it engaged
        #: (bloomberg_plan writes them), the worker while one runs.
        self._rotation_slots = rotation_slots_setting(rotation_slots, self._max_subscriptions)
        self._rotation_pool: list[str] = []
        self._rotation_active = 0
        self._rotation: RotationWorker | None = None
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
        self._sync_rotation()

    def update_streaming(self, contracts: list[str]) -> tuple[list[str], list[str]]:
        """INCREMENTAL universe edit: re-plan for ``contracts`` and diff against the
        LIVE set of the subscription — subscribe only the new securities,
        unsubscribe only the gone ones, move only the ones whose conflation tier
        changed, on the SAME session (no restart, no repaint of the rest, no
        warming gap). Covers ticker/expiry edits, a strike-window re-centre, cap
        re-ranking and a focus change alike. Starts a stream when none is
        running; stops it when the universe empties. Returns ``(added, removed)``.
        The rotation's bucket in flight is the worker's, not the diff's: under
        the worker's lock, the owned securities are left out of "have" (never
        unsubscribed here) and the ones the new plan wants live are handed over."""
        if not self.is_streaming() or self._sub is None:
            self.start_streaming(contracts)
            return (list(self._sub.securities) if self._sub else [], [])
        if not contracts:
            self.stop_streaming()
            return ([], [])
        worker = self._rotation
        with (worker.hold() if worker is not None else nullcontext()):
            wanted = self._plan_subscriptions(contracts)
            owned = worker.owned() if worker is not None else set()
            have = set(self._sub.securities) - owned
            handed = worker.release([s for s in wanted if s in owned]) if owned else []
            added = self._sub.subscribe([s for s in wanted if s not in have]) + handed
            removed = self._sub.unsubscribe([s for s in have if s not in set(wanted)])
            self._sub.set_intervals(self._interval_map(wanted))  # the tiers of the kept ones
        self._sync_rotation()
        return (added, removed)

    def _sync_rotation(self) -> None:
        """Start / re-pool / stop the worker for the plan's pool + slots."""
        pool, slots = self._rotation_pool, self._rotation_active
        if not slots or not pool or self._sub is None or self._book is None:
            if self._rotation is not None:
                self._rotation.stop()
                self._rotation = None
            return
        if self._rotation is None:
            self._rotation = RotationWorker(
                self._sub, self._book, self._paint_spot, slots,
                bucket_wait=self._rotation_wait, poll=self._rotation_poll,
            )
            self._rotation.start()
        self._rotation.set_pool(pool)

    def _paint_spot(self, sec: str) -> float | None:
        """The underlying's current book value — the spot a paint is taken at."""
        entry = self._stream_index.get(sec)
        return self._book_spot(entry[0], wait=0.0) if entry is not None else None

    def stop_streaming(self) -> None:
        if self._rotation is not None:
            self._rotation.stop()
            self._rotation = None
        if self._sub is not None:
            self._sub.stop()
            self._sub = None
        self._book = None
        self._requested = []
        self._stream_dropped = set()
        self._stream_tickers = set()
        self._rotation_pool, self._rotation_active = [], 0

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
        silently miss contracts. Over-cap contracts are the exception: the
        rotation's paint memory quotes them at the paint's own stamp and spot
        (the quote synchronisation transports them), and only a contract never
        painted is carried unquoted. Quotes are stamped with the PROVIDER tick
        times (the honest staleness signal across quiet periods), the chain
        with the newest of them; every live quote carries the underlying's paint
        as its own spot (``OptionQuote.spot``) so the quote synchronisation
        (volfit.api.quote_sync) ages each tick against the chain's stamp."""
        if not self.is_streaming() or self._book is None or self._sub is None:
            return None
        spot = self._book_spot(ticker, wait=wait)
        if spot is None:
            return None
        plan = self._stream_plan(ticker, expiries)
        subscribed = set(self._sub.securities)
        dropped = self._stream_dropped
        if not plan or any(c.security not in subscribed and c.security not in dropped for c in plan):
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        key = ticker.upper()
        memory = self._rotation.memory if self._rotation is not None else None
        rows = []  # (contract, live tick | None, rotated paint | None)
        stamps = []
        for c in plan:
            if c.security in dropped:
                paint = memory.get(c.security) if memory is not None else None
                rows.append((c, None, paint))
                if paint is not None and paint.ts is not None:
                    stamps.append(paint.ts)
            else:
                tick = self._book.quote(c.security)
                rows.append((c, tick, None))
                if tick is not None and tick.ts is not None:
                    stamps.append(tick.ts)
        under = self._book.quote(self._security(ticker))
        if under is not None and under.ts is not None:
            stamps.append(under.ts)
        # INITPAINT summaries carry no per-side stamp: an un-stamped quote is at
        # most as fresh as the newest stamped tick of the chain (on a delayed feed
        # that is 15 min behind the clock — 'now' would overstate its freshness);
        # a rotated paint is dated by its age (bloomberg_rotation.paint_stamp).
        newest = max(stamps) if stamps else None
        wall = datetime.now(timezone.utc).replace(tzinfo=None)
        quotes: list[OptionQuote] = []
        for c, tick, paint in rows:
            if paint is not None:
                tick, stamp = paint, paint_stamp(paint, newest, wall)
                quoted_at = paint.spot if paint.spot is not None else spot
            else:
                stamp = (tick.ts if tick else None) or newest or now
                quoted_at = spot  # the underlying's paint: the spot every live tick is quoted against
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
                    timestamp=stamp,
                    spot=quoted_at,
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

    # The light + the health block (_stream_status / stream_stats): bloomberg_health.

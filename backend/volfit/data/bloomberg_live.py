"""Streaming half of the Bloomberg provider — the live ``//blp/mktdata`` book.

``BloombergStreamingMixin`` gives ``BloombergProvider`` (volfit.data.bloomberg)
the same duck-typed streaming contract the Massive provider exposes, so
``AppState.sync_streaming`` and the scheduler's throttled refit drive it with no
changes (volfit/api/state.py, volfit/api/scheduler.py):

    option_tickers(ticker, expiries) -> [security, ...]   what to subscribe
    start_streaming(contracts) / stop_streaming()
    is_streaming() / streaming_contracts()

While streaming, ``fetch_chain(live)`` and ``spot()`` are served from the
``BbgBook`` (volfit.data.bloomberg_stream) — no ``bdp`` at all: the real-time
spot poll and every chain refresh stop touching the metered reference-data
quota. The underlying is subscribed alongside its contracts so spot comes off
the stream too. Reference data still needed (and still metered, once per
ticker): the ``OPT_CHAIN`` listing (``bds``) and ONE ``PX_LAST`` to centre the
strike window before the stream exists.

Subscription budget: the Desktop API caps concurrent real-time subscriptions
per Terminal, so contracts are (1) windowed to ``strike_window`` around a
HYSTERESIS-held spot centre (re-centred only after a > ``RECENTER_PCT`` move —
otherwise a spot wobbling across a strike boundary would restart the stream
every tick) and (2) capped at ``max_subscriptions`` by nearest-the-money first.
``streaming_contracts`` reports the REQUESTED set (pre-cap) so the scheduler's
universe diff stays stable; ``feed_status`` surfaces the dropped count.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timezone

from volfit.data.bloomberg_parse import ParsedOption
from volfit.data.bloomberg_stream import BbgBook, BloombergSubscription
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


class BloombergStreamingMixin:
    """Streaming contract for ``BloombergProvider`` (expects the host class to
    provide ``_security``, ``_select_contracts``, ``_window_contracts``,
    ``_spot``, ``strike_window``)."""

    # ---------------------------------------------------------------- init
    def _init_streaming(
        self,
        stream_interval: float | None = 1.0,
        max_subscriptions: int = 3000,
        stream_session_factory=None,
        stream_host: str | None = None,
        stream_port: int | None = None,
    ) -> None:
        self._stream_interval = stream_interval
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
        #: Reference-only fields the stream cannot carry, remembered from the last
        #: metered chain fetch so a streamed chain still reports them.
        self._oi_cache: dict[str, int] = {}
        self._style_cache: dict[str, str] = {}

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
        """Subscribe the underlyings + ``contracts`` (capped nearest-the-money) on a
        fresh session and serve live reads from the book. Replaces any stream."""
        self.stop_streaming()
        self._requested = list(dict.fromkeys(contracts))
        self._stream_tickers = {
            self._stream_index[s][0] for s in self._requested if s in self._stream_index
        }
        underlyings = [self._security(t) for t in sorted(self._stream_tickers)]
        kept, dropped = self._cap(self._requested, self._max_subscriptions - len(underlyings))
        self._stream_dropped = set(dropped)
        self._book = BbgBook()
        kwargs = {"interval": self._stream_interval, "session_factory": self._stream_factory}
        if self._stream_host:
            kwargs["host"] = self._stream_host
        if self._stream_port:
            kwargs["port"] = int(self._stream_port)
        self._sub = BloombergSubscription(underlyings + kept, self._book, **kwargs)
        self._sub.start()

    def _cap(self, contracts: list[str], budget: int) -> tuple[list[str], list[str]]:
        """Keep at most ``budget`` contracts, nearest-the-money first (by
        |log(K/centre)|; unknown contracts rank last). Order of the kept list is
        the input order, so a no-op cap leaves the request untouched."""
        if len(contracts) <= budget:
            return list(contracts), []

        def distance(sec: str) -> float:
            entry = self._stream_index.get(sec)
            if entry is None:
                return math.inf
            ticker, c = entry
            center = self._stream_center.get(ticker)
            if not center or c.strike <= 0.0:
                return math.inf
            return abs(math.log(c.strike / center))

        ranked = sorted(contracts, key=distance)
        keep = set(ranked[: max(budget, 0)])
        return [s for s in contracts if s in keep], [s for s in contracts if s not in keep]

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
        if tick.last is not None:
            return tick.last
        if tick.bid is not None and tick.ask is not None:
            return 0.5 * (tick.bid + tick.ask)
        return None

    def _chain_from_book(self, ticker: str, expiries: list[date] | None) -> ChainSnapshot | None:
        """The live chain for ``ticker``'s selection built from the book.

        None (caller falls back to the metered reference fetch) when not streaming,
        when the underlying has not painted yet, or when the selection is not fully
        covered by the subscription (a selection edit the scheduler has not
        resubscribed for yet) — an explicit fetch must never silently miss
        contracts. Over-cap contracts are the exception: they are carried unquoted.
        Quotes are stamped with the PROVIDER tick times (the honest staleness
        signal across quiet periods), the chain with the newest of them."""
        if not self.is_streaming() or self._book is None or self._sub is None:
            return None
        spot = self._book_spot(ticker)
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
        from volfit.data.expiry_time import settlement_map

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
            settlement=settlement_map({q.expiry for q in quotes}, root=key),
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
            return ("amber", f"stream warming · {started} subscribed{suffix}")
        age = (datetime.now(timezone.utc).replace(tzinfo=None) - newest).total_seconds()
        if age > _IDLE_SECONDS:
            return ("amber", f"stream idle since {newest:%H:%M} UTC · {started} subscribed{suffix}")
        slow = [t for t in sorted(self._stream_tickers) if self._book.delayed([self._security(t)])]
        if slow:
            which = "" if len(slow) == len(underlyings) else f" ({', '.join(slow)})"
            return ("amber", f"streaming {started} · delayed feed{which}{suffix}")
        return ("green", f"streaming {started} · real-time{suffix}")

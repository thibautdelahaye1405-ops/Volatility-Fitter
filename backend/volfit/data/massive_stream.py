"""Streaming half of the Massive provider — the windowed, capped, acknowledged
live book (moved out of volfit.data.massive on 2026-09-24).

``MassiveStreamMixin`` gives ``MassiveProvider`` the duck-typed streaming
contract ``AppState.sync_streaming`` and the scheduler drive (the same one
volfit.data.bloomberg_live exposes):

    option_tickers(ticker, expiries) -> [contract, ...]   the PLAN (pre-cap)
    start_streaming(contracts) / update_streaming(contracts) / stop_streaming()
    is_streaming() / streaming_contracts() / is_streaming_ticker(ticker)
    live_chain(ticker, expiries) / book_spot(ticker) / stream_stats()

Why (the 2026-09-23 finding, verified live): the quotes socket allows about
1,000 contracts per connection and refuses an over-limit frame in full; the
old provider subscribed EVERY listed contract of every selected expiry (SPY
26 expiries = 10,560; NVDA 9 = 1,866) in one frame, so the book never served
and the light said "stream warming" for five days while a REST probe fed the
spot. Throughput was never the problem (parse + apply 264k–473k events/s).

The plan (``option_tickers``): the listed contracts of the selection inside
the shared per-expiry strike window (volfit.data.strike_window — the band
the quote prep keeps, so nothing a fit would see is left out) around a
HYSTERESIS-held centre (re-centred after a > ``RECENTER_PCT`` move: the book's
parity spot when serving, else the last REST spot, else ONE nearest-expiry
snapshot page retried at most every minute; no centre = no plan yet), ranked
nearest-the-money by |ln K/centre| / sqrt(T). ``streaming_contracts`` echoes
the REQUESTED (pre-cap) set so the scheduler's universe diff stays stable.

The cap (``_plan_subscriptions``): across ALL its tickers the provider
subscribes at most ``stream_cap`` × ``stream_connections`` contracts, split
by the allocation POLICY (volfit.data.stream_allocation, 2026-09-24): the
focus nodes' whole planned rungs first (the nodes with an open tick-stream
SSE, handed over by ``AppState.sync_streaming`` through ``set_stream_focus``),
then every ticker's floor (``VOLFIT_MASSIVE_WS_FLOOR``, 60), then a fair
share of the remainder — no longer the global nearest-the-money rank that
gave SPY 874 of 950 slots and NVDA 76. The remainder is remembered in
``_stream_dropped`` and shown in the light. The live list is in PRIORITY
order and split into groups of ≤ ``stream_cap``, one ``MassiveWebSocket``
per group, all feeding ONE ``LiveBook``; a re-plan keeps a contract on the
connection it already has and fills the new ones where there is room.

The merge (``_chain_from_book``): every listed contract of the selection is
emitted — booked ones with their tick, the rest (over cap, beyond the window,
not yet acknowledged) from the ticker's LAST REST snapshot with that
snapshot's own stamps (``refresh_stream_rest`` refreshes it every
``rest_seconds`` — ``VOLFIT_MASSIVE_REST_SECONDS``, 60, floor 15 — per
streaming ticker, off the scheduler's streaming branch), else unquoted.
The chain's stamp is the newest booked tick; the spot is the parity forward
of the BOOKED quotes (the belly ticks), so a stale wing never moves it.
``stream_tier(ticker, expiry)`` tells the per-node SSE which tier a node is
on: "live" when its whole planned rung is on the socket, else "rest".

Honesty (``is_streaming_ticker``): a ticker is served iff a connection runs,
at least one of its planned contracts is acknowledged, and at least one of
them is booked — an unserved ticker stays on the request path (Auto-update
keeps working, the SSE says not streaming). ``is_streaming`` itself stays
"the stream is wanted" for start / stop; a dead thread is revived in place
(the book and the live set kept), counted as a reconnect and logged.

Health (``_stream_status`` / ``stream_stats``): the light's stream suffix and
the ``/datasources`` ``stream`` block, computed live on every call from the
shared ``StreamStats`` and the connections' acknowledgement counts.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from volfit.data.massive_book import LiveBook, StreamStats
from volfit.data.massive_stream_plan import RECENTER_PCT, MassiveStreamPlanMixin
from volfit.data.massive_stream_reads import (
    STREAM_REST_SECONDS,
    MassiveStreamReadsMixin,
    cluster_kind,
    rest_seconds_setting,
)
from volfit.data.stream_allocation import Allocation, allocate, ticker_floor
from volfit.data.types import ChainSnapshot

log = logging.getLogger("volfit.massive_ws")

#: The live subscription budget per connection (the server allows ~1,000).
DEFAULT_STREAM_CAP = 950
DEFAULT_STREAM_CONNECTIONS = 1
#: A dead connection thread is restarted at most this often.
_REVIVE_SECONDS = 5.0
#: The delayed cluster (a delayed-tier key is served here, not on socket.*).
DELAYED_WS_URL = "wss://delayed.polygon.io/options"


class MassiveStreamMixin(MassiveStreamPlanMixin, MassiveStreamReadsMixin):
    """Streaming contract for ``MassiveProvider`` (the cap and the lifecycle
    here; the plan in volfit.data.massive_stream_plan; the merge, the REST
    memory, the focus / tier and the health readings in
    volfit.data.massive_stream_reads; expects the host to provide
    ``_intraday_contracts``, ``available_expiries``, ``last_spot`` /
    ``_note_spot``, ``_get``, ``base_url``, ``_underlying``,
    ``_spot_from_parity``, ``_snapshot_results``, ``_rest_chain``,
    ``api_key``, ``window_vol``)."""

    # ---------------------------------------------------------------- init
    def _init_streaming(
        self,
        ws_url: str | None = None,
        stream_cap: int = DEFAULT_STREAM_CAP,
        stream_connections: int = DEFAULT_STREAM_CONNECTIONS,
        ws_connect=None,
        session_open=None,
        quote_grace: float = 6.0,
        stream_floor: int | None = None,
        stream_rest_seconds: float | None = None,
    ) -> None:
        self._ws_url_override = ws_url
        self.stream_cap = max(1, int(stream_cap))
        self.stream_connections = max(1, int(stream_connections))
        #: The allocation knobs (volfit.data.stream_allocation): the per-ticker
        #: floor (None = env VOLFIT_MASSIVE_WS_FLOOR, 60) and the REST cadence
        #: behind the book (None = env VOLFIT_MASSIVE_REST_SECONDS, 60, floor 15).
        self._floor = ticker_floor() if stream_floor is None else max(0, int(stream_floor))
        self._rest_seconds = rest_seconds_setting(stream_rest_seconds)
        self._focus: set[tuple[str, str]] = set()  # (TICKER, expiry ISO) on screen
        self._allocation: Allocation | None = None  # the last policy answer
        self._ws_connect = ws_connect
        self._session_open_fn = session_open
        self._quote_grace = quote_grace
        self._live_book: LiveBook | None = None
        self._stats: StreamStats | None = None
        self._sockets: list = []
        self._requested: list[str] = []  # the pre-cap plan AppState asked for
        self._stream_dropped: set[str] = set()  # requested but over the budget
        self._stream_index: dict[str, tuple[str, dict, float]] = {}  # contract -> (ticker, row, rank)
        self._ticker_plans: dict[str, list[str]] = {}  # ticker -> its last plan (rank order)
        self._stream_center: dict[str, float] = {}
        self._center_failed_at: dict[str, float] = {}
        self._plan_cache: dict[tuple, list[tuple[str, dict, float]]] = {}
        self._last_rest_chain: dict[str, ChainSnapshot] = {}
        self._last_rest_at: dict[str, float] = {}
        self._rest_inflight: set[str] = set()
        self._rest_pool: ThreadPoolExecutor | None = None
        self._last_revive = 0.0

    def _session_open(self) -> bool:
        if self._session_open_fn is not None:
            return bool(self._session_open_fn())
        from volfit.data.expiry_time import session_open_now

        return session_open_now()

    @property
    def _ws(self):
        """The first connection (the pre-2026-09-24 single-socket name)."""
        return self._sockets[0] if self._sockets else None

    @_ws.setter
    def _ws(self, socket) -> None:
        self._sockets = [socket] if socket is not None else []

    # ------------------------------------------------------------ clusters
    def _ws_url(self) -> str:
        """Real-time options-cluster WS endpoint derived from the REST host."""
        host = self.base_url.split("://")[-1].rstrip("/").replace("api.", "socket.")
        return f"wss://{host}/options"

    def _ws_urls(self) -> list[str]:
        """Candidate clusters, tried in order: the explicit override
        (``VOLFIT_MASSIVE_WS_URL``) or the real-time cluster derived from the
        REST host, then the delayed cluster as the auto-fallback (a delayed-tier
        key auths on the real-time cluster but is served no quote there)."""
        primary = self._ws_url_override or self._ws_url()
        candidates = [primary]
        if DELAYED_WS_URL not in candidates:
            candidates.append(DELAYED_WS_URL)
        return candidates

    # -------------------------------------------------------------- the cap
    def _plan_subscriptions(self, contracts: list[str]) -> list[str]:
        """Record the requested set; return the live set the allocation policy
        keeps within ``stream_cap × stream_connections`` — in PRIORITY order
        (focus, floors, fair-share rounds: the chunks a refusal trims from the
        far end). Each ticker's plan goes in by its own rank; contracts the
        index does not know (a caller's raw list) go in under one pseudo
        ticker in input order, so they are capped as a prefix."""
        self._requested = list(dict.fromkeys(contracts))
        plans: dict[str, list[str]] = {}
        for contract in self._requested:
            entry = self._stream_index.get(contract)
            plans.setdefault(entry[0] if entry is not None else "", []).append(contract)
        for ticker, mine in plans.items():
            if ticker:
                mine.sort(key=lambda c: self._stream_index[c][2])
        index = self._stream_index
        alloc = allocate(
            plans, self._focus, self.stream_cap * self.stream_connections, self._floor,
            expiry_of=lambda c: index[c][1]["expiry"].isoformat() if c in index else None,
        )
        self._allocation = alloc
        self._stream_dropped = set(alloc.dropped)
        return list(alloc.live)

    # ------------------------------------------------------------ lifecycle
    def start_streaming(self, contracts: list[str]) -> None:
        """Open the connection(s) and stream NBBO for the capped plan into ONE
        live book; ``fetch_chain(live)`` then serves from it. Replaces any stream."""
        from volfit.data.massive_ws import MassiveWebSocket

        self.stop_streaming()
        kept = self._plan_subscriptions(contracts)
        self._live_book = LiveBook()
        self._stats = StreamStats()
        self._stats.sockets = self.stream_connections
        cap = self.stream_cap
        for i in range(self.stream_connections):
            group = kept[i * cap : (i + 1) * cap]
            socket = MassiveWebSocket(
                self.api_key, group, self._live_book, urls=self._ws_urls(),
                connect=self._ws_connect, stats=self._stats, quote_grace=self._quote_grace,
                session_open=self._session_open, name=f"ws{i + 1}",
            )
            self._sockets.append(socket)
            socket.start()
        log.info(
            "massive stream: %d requested, %d subscribed on %d connection(s) (cap %d), %d over cap · %s",
            len(self._requested), len(kept), self.stream_connections, cap, len(self._stream_dropped),
            self._allocation_line(),
        )

    def update_streaming(self, contracts: list[str]) -> tuple[list[str], list[str]]:
        """INCREMENTAL universe edit: re-plan for ``contracts``, diff against the
        live connections — subscribe only the new contracts (where there is
        room), unsubscribe only the gone ones; no reconnect, the rest keeps
        ticking. Starts a stream when none runs, stops on an empty universe.
        Returns ``(added, removed)``."""
        if not self.is_streaming():
            self.start_streaming(contracts)
            return (self._live_set(), [])
        if not contracts:
            self.stop_streaming()
            return ([], [])
        kept = self._plan_subscriptions(contracts)
        wanted = set(kept)
        removed: list[str] = []
        for socket in self._sockets:
            removed += socket.unsubscribe([c for c in socket.contracts if c not in wanted])
        have = set(self._live_set())
        new = [c for c in kept if c not in have]
        added: list[str] = []
        for socket in self._sockets:
            if not new:
                break
            room = self.stream_cap - len(socket.contracts)
            if room <= 0:
                continue
            take, new = new[:room], new[room:]
            added += socket.subscribe(take)
        if new:  # cannot happen (budget = connections × cap) — never silently
            log.warning("massive stream: %d planned contracts found no connection with room", len(new))
        if added or removed:
            log.info("massive stream: re-planned — +%d / -%d (%d over cap) · %s",
                     len(added), len(removed), len(self._stream_dropped), self._allocation_line())
        return (added, removed)

    def _live_set(self) -> list[str]:
        out: list[str] = []
        for socket in self._sockets:
            out += socket.contracts
        return out

    def stop_streaming(self) -> None:
        """Tear down the connection(s) and drop the live book (back to REST live)."""
        for socket in self._sockets:
            socket.stop()
        self._sockets = []
        self._live_book = None
        self._stats = None
        self._requested = []
        self._stream_dropped = set()

    def _revive(self) -> None:
        """A connection whose thread died while wanted is restarted in place —
        the book and the live set kept — counted as a reconnect and logged."""
        for socket in self._sockets:
            if socket.is_running() or getattr(socket, "stopped", False):
                continue
            now = time.monotonic()
            if now - self._last_revive < _REVIVE_SECONDS:
                continue
            self._last_revive = now
            socket.start()
            if self._stats is not None:
                self._stats.note_reconnect()
            log.warning("massive stream: a connection thread was dead — restarted (reconnect #%d)",
                        self._stats.reconnects if self._stats else 0)

    def is_streaming(self) -> bool:
        """The stream is WANTED (connections exist) — the start / stop predicate."""
        self._revive()
        return bool(self._sockets)

    def streaming_contracts(self) -> set[str]:
        """The REQUESTED set (pre-cap) — the scheduler diffs this against the
        universe to decide a resubscribe, so it must echo what it asked for."""
        return set(self._requested) if self._sockets else set()

    def is_streaming_ticker(self, ticker: str) -> bool:
        """Served, not merely wanted: a connection runs, one of the ticker's
        planned contracts is acknowledged, and one of them is booked."""
        if not self._sockets or self._live_book is None:
            return False
        if not any(s.is_running() for s in self._sockets):
            return False
        mine = self._ticker_plans.get(ticker.upper())
        if not mine:
            return False
        acked = False
        for socket in self._sockets:
            confirmed = getattr(socket, "acked", None)
            if confirmed and any(c in confirmed for c in mine):
                acked = True
                break
        return acked and self._live_book.any_of(mine)


__all__ = [
    "DEFAULT_STREAM_CAP", "DEFAULT_STREAM_CONNECTIONS", "MassiveStreamMixin",
    "RECENTER_PCT", "STREAM_REST_SECONDS", "cluster_kind", "MassiveStreamReadsMixin",
    "rest_seconds_setting",
]

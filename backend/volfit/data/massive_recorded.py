"""The recorded book — the API process reads the tick recorder's book instead
of opening a Massive websocket of its own (TICK RECORDER, 2026-09-24).

WHY: the key allows ONE quotes socket; a second ``/options`` connection is
refused and disturbs the first. With the recorder (volfit.data.tick_recorder)
owning that socket in its own process, the API must serve the live chain
from what the recorder writes — the ``latest`` table of the day's tick store
(volfit.data.tick_store) — through the very same read path the in-process
book used: ``_chain_from_book`` calls ``book.quote(contract)``, the honesty
test calls ``book.any_of(...)``. So ``RecordedBook`` exposes the ``LiveBook``
READ interface over the store, cached for one second per read burst (the
per-node SSE polls at 1 Hz; a chain read touches ~10,000 contracts and must
not run 10,000 queries).

``MassiveRecordedMixin`` sits ahead of ``MassiveStreamMixin`` in the
provider's MRO: with a recorded book configured (``book_source=
"recorder:<file or directory>"``, env ``VOLFIT_MASSIVE_BOOK`` in serve.py) the
streaming lifecycle ATTACHES the reader instead of opening sockets — the plan
is still computed (the merge needs the requested set and the over-cap count
for the light) — and the health readings answer from the recorder's
heartbeat and stats: a heartbeat older than ``STALE_S`` reads "recorder
stale" (red), and no ticker is served then. Without a recorded book every
method defers to the socket path unchanged.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from pathlib import Path

from volfit.data.massive_book import QuoteTick
from volfit.data.tick_store import TickStore, daily_path

log = logging.getLogger("volfit.massive_ws")

#: A recorder whose heartbeat is older than this is not serving.
STALE_S = 10.0
#: The reader re-reads ``latest`` at most this often (one read per SSE poll).
READ_TTL_S = 1.0
#: The ``book_source`` spelling: ``recorder:<path>`` (a file or the directory
#: of daily files, where today's exchange day is picked).
PREFIX = "recorder:"


class RecordedBook:
    """``LiveBook``'s read interface over the tick store's ``latest`` table.

    ``source`` is the daily file or the directory of daily files (the day's
    file is re-resolved on every refresh, so the reader follows the day roll
    without a restart). ``clock`` (monotonic) gates the read cache, ``wall``
    (epoch seconds) ages the recorder's heartbeat — both injectable."""

    def __init__(
        self, source, ttl_s: float = READ_TTL_S, stale_s: float = STALE_S,
        clock=time.monotonic, wall=time.time,
    ) -> None:
        self._source = Path(source)
        self._ttl = float(ttl_s)
        self._stale = float(stale_s)
        self._clock = clock
        self._wall = wall
        self._store: TickStore | None = None
        self._store_path: Path | None = None
        self._quotes: dict[str, QuoteTick] = {}
        self._meta: dict[str, str] = {}
        self._read_at: float | None = None
        self._warned = False
        #: ``LiveBook.connected``'s counterpart: the recorder is alive.
        self.connected = False

    # ---------------------------------------------------------------- files
    def path(self) -> Path:
        """The file read now: the source itself, or the day's file in it."""
        return daily_path(self._source) if self._source.is_dir() else self._source

    def _open(self, path: Path) -> TickStore | None:
        if self._store is not None and self._store_path == path:
            return self._store
        if self._store is not None:
            self._store.close()
            self._store, self._store_path = None, None
        if not path.is_file():
            return None
        self._store, self._store_path = TickStore(path), path
        log.info("massive recorded book: reading %s", path)
        return self._store

    def _refresh(self, force: bool = False) -> None:
        now = self._clock()
        if not force and self._read_at is not None and now - self._read_at < self._ttl:
            return
        self._read_at = now
        store = self._open(self.path())
        if store is None:
            self._quotes, self._meta = {}, {}
            self.connected = False
            return
        try:
            book = store.latest_book()
            meta = store.meta()
        except sqlite3.Error as exc:  # a checkpoint / a locked file: keep the last read
            if not self._warned:
                log.warning("massive recorded book: read failed (%s); serving the last read", exc)
                self._warned = True
            return
        self._warned = False
        self._quotes = {c: QuoteTick(bid=b, ask=a, ts=t) for c, (b, a, t) in book.items()}
        self._meta = meta
        self.connected = self.alive()

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store, self._store_path = None, None

    # ------------------------------------------------------- the book reads
    def quote(self, contract: str) -> QuoteTick | None:
        self._refresh()
        return self._quotes.get(contract)

    def any_of(self, contracts) -> bool:
        self._refresh()
        quotes = self._quotes
        return any(c in quotes for c in contracts)

    def newest_ts(self) -> int | None:
        self._refresh()
        stamps = [t.ts for t in self._quotes.values() if t.ts is not None]
        return max(stamps) if stamps else None

    def size(self) -> int:
        self._refresh()
        return len(self._quotes)

    def items(self) -> list[tuple[str, QuoteTick]]:
        self._refresh()
        return list(self._quotes.items())

    def remove(self, contracts) -> None:
        """The recorder owns the subscription: a reader never forgets a tick."""

    def clear(self) -> None:
        """Same: the store is the recorder's, not the reader's to clear."""

    # ---------------------------------------------------------- the health
    def _meta_json(self, key: str) -> dict | None:
        import json

        raw = self._meta.get(key)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def stats(self) -> dict | None:
        """The recorder's last ``stream_stats()`` (with ``ackedByTicker``)."""
        self._refresh()
        return self._meta_json("stats")

    def plan(self) -> dict | None:
        self._refresh()
        return self._meta_json("plan")

    def pid(self) -> int | None:
        self._refresh()
        try:
            return int(self._meta["pid"])
        except (KeyError, ValueError):
            return None

    def heartbeat_age_s(self) -> float | None:
        """Seconds since the recorder's heartbeat (None: no recorder wrote here)."""
        self._refresh()
        raw = self._meta.get("heartbeat")
        if raw is None:
            return None
        try:
            return max(0.0, self._wall() - float(raw))
        except ValueError:
            return None

    def alive(self) -> bool:
        age = self.heartbeat_age_s()
        return age is not None and age < self._stale


class StaticBook(RecordedBook):
    """A frozen book — the store's ``book_at(instant)`` — for the replay
    command: the same read interface, always 'alive', nothing to refresh."""

    def __init__(self, quotes: dict[str, tuple[float | None, float | None, int]]) -> None:
        super().__init__(".")
        self._quotes = {c: QuoteTick(bid=b, ask=a, ts=t) for c, (b, a, t) in quotes.items()}
        self.connected = True

    def _refresh(self, force: bool = False) -> None:  # noqa: D401 — frozen
        return

    def heartbeat_age_s(self) -> float | None:
        return 0.0

    def stats(self) -> dict | None:
        return None


def resolve_book_source(source) -> RecordedBook | None:
    """``book_source`` -> a reader: None, a ready reader, or ``recorder:<path>``."""
    if source is None or source == "":
        return None
    if isinstance(source, RecordedBook):
        return source
    text = str(source).strip()
    if text.lower().startswith(PREFIX):
        text = text[len(PREFIX):].strip()
    if not text:
        raise ValueError("book_source: 'recorder:<file or directory>' expected")
    return RecordedBook(text)


class MassiveRecordedMixin:
    """The recorded-book overrides of the streaming lifecycle and health
    (ahead of ``MassiveStreamMixin`` in the MRO; every method defers to the
    socket path when no recorded book is configured)."""

    def _init_recorded(self, book_source=None) -> None:
        self._recorded: RecordedBook | None = resolve_book_source(book_source)

    def use_recorded_book(self, book: RecordedBook | None) -> None:
        """Switch the book source (the replay command hands a frozen book)."""
        self.stop_streaming()
        self._recorded = book

    @property
    def recorded_mode(self) -> bool:
        return self._recorded is not None

    # ------------------------------------------------------------ lifecycle
    def start_streaming(self, contracts: list[str]) -> None:
        if self._recorded is None:
            return super().start_streaming(contracts)
        self._sockets, self._stats = [], None  # never a MassiveWebSocket here
        kept = self._plan_subscriptions(contracts)  # the merge + the light need the plan
        self._live_book = self._recorded
        log.info(
            "massive recorded book: attached %s (%d requested, %d in plan, %d over cap)",
            self._recorded.path() if hasattr(self._recorded, "path") else "book",
            len(self._requested), len(kept), len(self._stream_dropped),
        )

    def update_streaming(self, contracts: list[str]) -> tuple[list[str], list[str]]:
        if self._recorded is None:
            return super().update_streaming(contracts)
        if self._live_book is None:
            self.start_streaming(contracts)
        elif not contracts:
            self.stop_streaming()
        else:
            self._plan_subscriptions(contracts)
        return ([], [])

    def stop_streaming(self) -> None:
        if self._recorded is None:
            return super().stop_streaming()
        self._live_book = None
        self._sockets, self._stats = [], None
        self._requested, self._stream_dropped = [], set()

    def is_streaming(self) -> bool:
        if self._recorded is None:
            return super().is_streaming()
        return self._live_book is not None and self._recorded.alive()

    def streaming_contracts(self) -> set[str]:
        if self._recorded is None:
            return super().streaming_contracts()
        return set(self._requested) if self._live_book is not None else set()

    def is_streaming_ticker(self, ticker: str) -> bool:
        """Served iff the recorder is alive, its stats say the ticker's planned
        contracts are acknowledged on ITS socket, and one of them is booked."""
        if self._recorded is None:
            return super().is_streaming_ticker(ticker)
        if self._live_book is None or not self._recorded.alive():
            return False
        key = ticker.upper()
        mine = self._ticker_plans.get(key)
        if not mine:
            return False
        stats = self._recorded.stats() or {}
        by_ticker = stats.get("ackedByTicker")
        acked = (by_ticker.get(key, 0) > 0) if isinstance(by_ticker, dict) else bool((stats.get("tickers") or {}).get(key))
        return acked and self._recorded.any_of(mine)

    # ------------------------------------------------------ the REST memory
    def refresh_stream_rest(self, ticker: str, expiries: list[date] | None, block: bool = False) -> Future | object | None:
        """The socket path gates the memory refresh on an open socket; with a
        recorded book the wings still come from the per-minute REST snapshot,
        so the same throttle runs keyed on the attached reader instead."""
        if self._recorded is None:
            return super().refresh_stream_rest(ticker, expiries, block=block)
        key = ticker.upper()
        if self._live_book is None:
            return None
        from volfit.data.massive_stream_reads import STREAM_REST_SECONDS

        cadence = getattr(self, "_rest_seconds", STREAM_REST_SECONDS)  # the provider's own knob
        now = time.monotonic()
        last = self._last_rest_at.get(key)
        if (last is not None and now - last < cadence) or key in self._rest_inflight:
            return None
        self._rest_inflight.add(key)
        if block:
            return self._pull_stream_rest(key, expiries)
        if self._rest_pool is None:
            self._rest_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="massive-rest")
        return self._rest_pool.submit(self._pull_stream_rest, key, expiries)

    # ---------------------------------------------------------------- health
    def _recorded_tick_age(self, stats: dict, beat: float) -> float | None:
        """Age of the newest quote: the recorder's own reading plus the time
        since it wrote it, else the newest booked stamp against the wall."""
        age = stats.get("lastQuoteAge")
        if isinstance(age, (int, float)):
            return float(age) + beat
        newest = self._recorded.newest_ts()
        if newest is None:
            return None
        from volfit.data.tick_store import to_ns

        return max(0.0, time.time() - to_ns(newest) / 1e9)

    def _stream_status(self) -> tuple[str, str] | None:
        if self._recorded is None:
            return super()._stream_status()
        if self._live_book is None:
            return None
        beat = self._recorded.heartbeat_age_s()
        if beat is None:
            return ("red", "recorded book · no recorder heartbeat")
        if beat >= self._recorded._stale:
            return ("red", f"recorder stale ({beat:.0f} s)")
        stats = self._recorded.stats() or {}
        if stats.get("level") == "red" and stats.get("detail"):
            return ("red", f"recorded book · {stats['detail']}")
        acked = int(stats.get("acknowledged") or 0)
        age = self._recorded_tick_age(stats, beat)
        last = f"last tick {age:.0f} s" if age is not None else "no tick yet"
        extra = f" · {len(self._stream_dropped):,} over cap" if self._stream_dropped else ""
        level = "green" if stats.get("level") == "green" else "amber"
        return (level, f"recorded book · {acked:,} acked · {last}{extra} · recorder alive")

    def stream_stats(self) -> dict | None:
        if self._recorded is None:
            return super().stream_stats()
        if self._live_book is None:
            return None
        snap = dict(self._recorded.stats() or {})
        status = self._stream_status() or ("amber", "")
        alive = self._recorded.alive()
        snap.setdefault("connected", alive)
        snap.update({
            "source": "recorder",
            "heartbeatAge": self._recorded.heartbeat_age_s(),
            "running": alive,
            "requested": len(self._requested),
            "overCap": len(self._stream_dropped),
            "cap": self.stream_cap,
            "connections": self.stream_connections,
            "sessionOpen": self._session_open(),
            "tickers": {t: self.is_streaming_ticker(t) for t in sorted(self._ticker_plans)},
            "level": status[0],
            "detail": status[1],
        })
        return snap


__all__ = ["PREFIX", "READ_TTL_S", "STALE_S", "MassiveRecordedMixin", "RecordedBook", "StaticBook", "resolve_book_source"]

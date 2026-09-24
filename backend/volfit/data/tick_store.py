"""The tick store — one SQLite file per exchange day holding the recorded
Massive book (TICK RECORDER, 2026-09-24).

WHY a store of ticks: the app's live book (volfit.data.massive_book.LiveBook)
is a memory of the LATEST quote per contract inside the API process — it dies
with the process, cannot be replayed, and needs the one Massive websocket the
key allows. The tick recorder (volfit.data.tick_recorder) is a separate
process that owns the socket and writes what the book saw into this store;
the API process then READS the book from here (volfit.data.massive_recorded)
and never opens a socket of its own, and any instant of the day can be
rebuilt from the ticks (``book_at``) after the fact.

Layout (WAL so the recorder writes while the API reads; a busy timeout so a
checkpoint never raises on either side):

* ``ticks(contract, ts_ns, bid, ask, seen_at)`` — APPEND-ONLY, one row per
  CHANGE of a contract's (bid, ask, ts): the socket re-sends unchanged NBBOs
  on every book fold, and writing those would multiply the file by the fold
  rate for no information. ``ts_ns`` is the provider's tick time normalised
  to nanoseconds (the feed has shipped ms too — ``to_ns`` infers the unit),
  the wall clock (``seen_at``) when the feed sent none. Indexed on
  ``(contract, ts_ns)`` so ``book_at`` is one indexed group-by.
* ``latest(contract PRIMARY KEY, ts_ns, bid, ask, seen_at)`` — the book as
  it stands, upserted on every change: the API's ``RecordedBook`` reads this
  table alone at 1 Hz, never the tick log.
* ``meta(key PRIMARY KEY, value)`` — the recorder's identity and health:
  ``pid``, ``startedAt``, ``heartbeat`` (epoch seconds, rewritten every
  fold), ``stats`` (the provider's ``stream_stats()`` JSON plus the per-
  ticker acknowledged counts), ``plan`` (tickers, expiries, requested / live
  / over-cap / refused counts), ``stop`` (the stop request the launcher
  posts) and ``stoppedAt``.

A DAILY file (``ticks_<YYYY-MM-DD>.sqlite``, the New York exchange day) makes
a session one replayable unit and keeps any single file bounded.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

from volfit.data.massive_listing import exchange_day

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    contract TEXT    NOT NULL,
    ts_ns    INTEGER NOT NULL,
    bid      REAL,
    ask      REAL,
    seen_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ticks_contract_ts ON ticks (contract, ts_ns);
CREATE TABLE IF NOT EXISTS latest (
    contract TEXT PRIMARY KEY,
    ts_ns    INTEGER NOT NULL,
    bid      REAL,
    ask      REAL,
    seen_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

#: The daily file name pattern.
FILE_PATTERN = "ticks_{day}.sqlite"


def to_ns(value) -> int | None:
    """A provider epoch stamp in ANY unit -> nanoseconds (None for no stamp).
    The unit is inferred from the magnitude exactly like
    ``massive_book.ns_to_utc_naive``: < 1e10 seconds, < 1e13 milliseconds,
    < 1e16 microseconds, else nanoseconds — integer arithmetic throughout,
    a float would lose the low digits of a nanosecond stamp."""
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    if v < 10**10:
        return v * 10**9
    if v < 10**13:
        return v * 10**6
    if v < 10**16:
        return v * 10**3
    return v


def ns_of(ts: datetime) -> int:
    """A UTC-naive datetime (the codebase's stored form) -> epoch nanoseconds."""
    aware = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    return int(aware.timestamp()) * 10**9 + aware.microsecond * 1000


def daily_path(out_dir, day: date | None = None) -> Path:
    """The day's file under ``out_dir`` (today's New York exchange day by default)."""
    return Path(out_dir) / FILE_PATTERN.format(day=(day or exchange_day()).isoformat())


class TickStore:
    """The daily tick file: the recorder's writer and the API's reader share
    this class (WAL; every statement under one re-entrant lock because the
    API reads from several request threads on one connection)."""

    def __init__(self, path, busy_timeout_s: float = 5.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(
            str(self.path), timeout=busy_timeout_s, check_same_thread=False, isolation_level=None
        )
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(_SCHEMA)
        #: The dedupe memory: contract -> (bid, ask, ts_ns) as last written,
        #: seeded from ``latest`` so a restarted recorder does not re-append
        #: the whole book it already holds (a direct query: ``latest_book`` is
        #: the reader's call and its cache is measured).
        with self._lock:
            rows = self.conn.execute("SELECT contract, bid, ask, ts_ns FROM latest").fetchall()
        self._last: dict[str, tuple] = {c: (b, a, int(t)) for c, b, a, t in rows}

    # ------------------------------------------------------------ lifecycle
    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def __enter__(self) -> "TickStore":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # -------------------------------------------------------------- writes
    def fold(self, ticks, seen_at: float | None = None) -> int:
        """Append the CHANGED ticks of ``ticks`` (``(contract, bid, ask, ts)``
        tuples, ``ts`` in any epoch unit or None) and upsert ``latest``.
        Returns how many rows were written. One transaction per fold."""
        now_ns = int((seen_at if seen_at is not None else time.time()) * 1e9)
        rows: list[tuple] = []
        for contract, bid, ask, ts in ticks:
            ts_ns = to_ns(ts)
            if ts_ns is None:
                ts_ns = now_ns
            key = (bid, ask, ts_ns)
            if self._last.get(contract) == key:
                continue
            self._last[contract] = key
            rows.append((contract, ts_ns, bid, ask, now_ns))
        if not rows:
            return 0
        with self._lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.executemany(
                    "INSERT INTO ticks (contract, ts_ns, bid, ask, seen_at) VALUES (?, ?, ?, ?, ?)", rows
                )
                self.conn.executemany(
                    "INSERT INTO latest (contract, ts_ns, bid, ask, seen_at) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(contract) DO UPDATE SET ts_ns = excluded.ts_ns, bid = excluded.bid, "
                    "ask = excluded.ask, seen_at = excluded.seen_at",
                    rows,
                )
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return len(rows)

    def set_meta(self, key: str, value) -> None:
        """Store a meta value (a non-string is stored as JSON)."""
        text = value if isinstance(value, str) else json.dumps(value)
        with self._lock:
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, text),
            )

    def delete_meta(self, key: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM meta WHERE key = ?", (key,))

    def heartbeat(self, now: float | None = None) -> None:
        """Stamp the recorder's liveness (epoch seconds)."""
        self.set_meta("heartbeat", repr(float(now if now is not None else time.time())))

    # --------------------------------------------------------------- reads
    def latest_book(self) -> dict[str, tuple[float | None, float | None, int]]:
        """The book as it stands: contract -> (bid, ask, ts_ns)."""
        with self._lock:
            rows = self.conn.execute("SELECT contract, bid, ask, ts_ns FROM latest").fetchall()
        return {c: (b, a, int(t)) for c, b, a, t in rows}

    def book_at(self, ts) -> dict[str, tuple[float | None, float | None, int]]:
        """The book at an instant: the last tick at-or-before ``ts`` (a
        UTC-naive datetime or epoch nanoseconds) per contract. SQLite's
        bare-column rule with ``MAX(ts_ns)`` picks that row's bid/ask, and
        the ``(contract, ts_ns)`` index serves the group-by."""
        limit = ns_of(ts) if isinstance(ts, datetime) else int(ts)
        with self._lock:
            rows = self.conn.execute(
                "SELECT contract, bid, ask, MAX(ts_ns) FROM ticks WHERE ts_ns <= ? GROUP BY contract",
                (limit,),
            ).fetchall()
        return {c: (b, a, int(t)) for c, b, a, t in rows}

    def meta(self) -> dict[str, str]:
        with self._lock:
            return dict(self.conn.execute("SELECT key, value FROM meta").fetchall())

    def get_meta(self, key: str, default=None):
        with self._lock:
            row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def _json_meta(self, key: str) -> dict | None:
        raw = self.get_meta(key)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def stats(self) -> dict | None:
        """The recorder's last ``stream_stats()`` dict (None before the first fold)."""
        return self._json_meta("stats")

    def plan(self) -> dict | None:
        """What the recorder streams (tickers, expiries, the counts)."""
        return self._json_meta("plan")

    def heartbeat_age_s(self, now: float | None = None) -> float | None:
        """Seconds since the recorder's last heartbeat (None: never stamped)."""
        raw = self.get_meta("heartbeat")
        if raw is None:
            return None
        try:
            stamp = float(raw)
        except ValueError:
            return None
        return max(0.0, (now if now is not None else time.time()) - stamp)

    def tick_count(self) -> int:
        with self._lock:
            return int(self.conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0])

    def latest_count(self) -> int:
        with self._lock:
            return int(self.conn.execute("SELECT COUNT(*) FROM latest").fetchone()[0])

    def newest_ts_ns(self) -> int | None:
        """The newest tick time in the book (None when empty)."""
        with self._lock:
            row = self.conn.execute("SELECT MAX(ts_ns) FROM latest").fetchone()
        return None if row is None or row[0] is None else int(row[0])


__all__ = ["FILE_PATTERN", "TickStore", "daily_path", "ns_of", "to_ns"]

"""The Bloomberg live book — the pure, thread-safe ``{security -> BbgTick}``
store the ``//blp/mktdata`` subscription feeds (split out of
volfit.data.bloomberg_stream on 2026-09-24 to keep the transport under the
400-line policy, the way volfit.data.massive_book sits beside massive_ws).

Bloomberg sends DELTAS (a message carries only the fields that changed,
after an initial ``INITPAINT`` summary), so ``apply`` MERGES each record onto
the security's current tick. The book also tracks subscription status
(started / failed + reason), the ``IS_DELAYED_STREAM`` flag, and the newest
provider stamp (freshness); ``wait_for`` lets the first fetch after a start
wait for a paint instead of paying a metered reference hit.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime

from volfit.data.bloomberg_decode import flag, int_or_none, price_or_none


@dataclass(frozen=True)
class BbgTick:
    """Latest known state of one streamed security (merged across deltas)."""

    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int | None = None
    ts: datetime | None = None  # newest provider stamp seen (UTC-naive)
    delayed: bool = False  # IS_DELAYED_STREAM reported true on this security


class BbgBook:
    """Thread-safe live book fed by decoded subscription records (see
    volfit.data.bloomberg_decode for the record shapes). A field present with
    value ``None`` means Bloomberg sent a NULL (side withdrawn) and clears it;
    an absent field keeps the previous value (delta semantics)."""

    def __init__(self) -> None:
        self._ticks: dict[str, BbgTick] = {}
        self._started: set[str] = set()
        self._failed: dict[str, str] = {}
        self._lock = threading.Lock()
        self._ready = threading.Condition(self._lock)
        #: True once any subscription has been acknowledged (session alive).
        self.connected = False

    # ------------------------------------------------------------ ingest
    def apply(self, records: list[dict]) -> None:
        with self._lock:
            for rec in records:
                kind = rec.get("kind")
                if kind == "data":
                    self._apply_data(rec)
                elif kind == "started":
                    self._started.add(rec["sec"])
                    self._failed.pop(rec["sec"], None)
                    self.connected = True
                elif kind == "failure":
                    self._failed[rec["sec"]] = rec.get("reason") or "subscription failed"
                elif kind == "terminated":
                    self._started.discard(rec["sec"])
                elif kind == "session_down":
                    self.connected = False
            self._ready.notify_all()

    def _apply_data(self, rec: dict) -> None:
        sec, fields = rec.get("sec"), rec.get("fields") or {}
        if not sec:
            return
        tick = self._ticks.get(sec, BbgTick())
        updates: dict = {}
        if "BID" in fields:
            updates["bid"] = price_or_none(fields["BID"])
        if "ASK" in fields:
            updates["ask"] = price_or_none(fields["ASK"])
        if "LAST_PRICE" in fields:
            updates["last"] = price_or_none(fields["LAST_PRICE"])
        if "VOLUME" in fields:
            updates["volume"] = int_or_none(fields["VOLUME"])
        if "IS_DELAYED_STREAM" in fields:
            updates["delayed"] = flag(fields["IS_DELAYED_STREAM"])
        stamp = rec.get("ts")
        if stamp is not None and (tick.ts is None or stamp > tick.ts):
            updates["ts"] = stamp
        self._ticks[sec] = replace(tick, **updates) if updates else tick

    # -------------------------------------------------------------- reads
    def quote(self, sec: str) -> BbgTick | None:
        with self._lock:
            return self._ticks.get(sec)

    def size(self) -> int:
        with self._lock:
            return len(self._ticks)

    def started(self) -> int:
        with self._lock:
            return len(self._started)

    def failures(self) -> dict[str, str]:
        with self._lock:
            return dict(self._failed)

    def newest_ts(self) -> datetime | None:
        """Newest provider stamp across the book (the freshness signal)."""
        with self._lock:
            stamps = [t.ts for t in self._ticks.values() if t.ts is not None]
        return max(stamps) if stamps else None

    def delayed(self, secs: list[str] | None = None) -> bool:
        """Whether the stream is delayed — judged on ``secs`` (e.g. the
        underlyings) or, when None, on any booked security."""
        with self._lock:
            pool = [self._ticks.get(s) for s in secs] if secs is not None else list(self._ticks.values())
        return any(t is not None and t.delayed for t in pool)

    def wait_for(self, sec: str, timeout: float) -> BbgTick | None:
        """Block up to ``timeout`` s for ``sec`` to have a price (its INITPAINT
        lands within ~1 s of subscribing), so the first fetch after a stream
        start can be served from the book instead of a metered reference hit."""
        deadline = time.monotonic() + timeout
        with self._lock:
            while True:
                tick = self._ticks.get(sec)
                if tick is not None and (tick.last is not None or tick.bid is not None):
                    return tick
                remaining = deadline - time.monotonic()
                if remaining <= 0.0 or sec in self._failed:
                    return tick
                self._ready.wait(remaining)

    def remove(self, secs: list[str]) -> None:
        """Forget securities that were unsubscribed (ticks, status) so a stale
        last tick can never be served for a contract the universe dropped."""
        with self._lock:
            for s in secs:
                self._ticks.pop(s, None)
                self._started.discard(s)
                self._failed.pop(s, None)

    def clear(self) -> None:
        with self._lock:
            self._ticks.clear()
            self._started.clear()
            self._failed.clear()
            self.connected = False


__all__ = ["BbgBook", "BbgTick"]

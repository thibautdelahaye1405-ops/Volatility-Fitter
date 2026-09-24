"""The Massive options live book, its health counters and the frame parser.

Split out of ``volfit.data.massive_ws`` on 2026-09-24 so the transport (one
asyncio connection: auth, chunked subscribe, acknowledgements, reconnects)
and the pure, synchronous state it feeds live apart and stay under the
400-line policy each:

* ``LiveBook`` — thread-safe ``{option_ticker -> QuoteTick}``; ``apply`` folds
  a parsed frame and RETURNS what the transport must act on (the number of
  quotes, the status events) — the 2026-09-23 finding was that the old
  ``apply`` swallowed ``status: "error"`` frames ("Subscription limit reached
  for feed…"), so a refused subscription looked like a warming book for
  five days;
* ``StreamStats`` — the health counters the Data Source light and the
  ``/datasources`` payload read: connections, cluster, message and quote
  rates over a 10-second sliding window, ages, reconnects, the last error
  and when it happened. Monotonic stamps for ages, a wall stamp for the
  "idle since HH:MM" reading;
* ``parse_frame`` / ``ns_to_utc_naive`` — the frame decoder and the
  provider-timestamp conversion (the WS ``t`` is nominally nanoseconds but
  Polygon channels have shipped milliseconds too, so the unit is inferred).
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

#: The message-rate window (seconds) of ``StreamStats.rate``.
RATE_WINDOW_S = 10.0


@dataclass(frozen=True)
class QuoteTick:
    """The latest streamed NBBO for one option contract (prices may be None)."""

    bid: float | None
    ask: float | None
    ts: int | None  # provider nanosecond timestamp


def _num(value) -> float | None:
    """A positive float, or None (a 0/blank NBBO side is 'no quote')."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0.0 else None


def parse_frame(raw) -> list[dict]:
    """Decode a WS text frame to a list of event dicts (tolerant of a single
    object or malformed JSON)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def ns_to_utc_naive(ns) -> datetime | None:
    """Provider epoch timestamp -> UTC-naive datetime (the stored form).

    The unit is inferred from magnitude (ns -> us -> ms -> s); values outside
    2001..2286 (epoch 1e9..1e10 seconds) return None rather than stamping a
    chain with a nonsense date (callers then fall back to the wall clock)."""
    if ns is None:
        return None
    try:
        seconds = float(ns)
    except (TypeError, ValueError):
        return None
    while seconds >= 1e10:  # ns -> us -> ms -> s, whichever the feed sent
        seconds /= 1e3
    if not 1e9 <= seconds < 1e10:
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None, microsecond=0)


class LiveBook:
    """Thread-safe ``{option_ticker -> QuoteTick}`` updated from WS messages.

    Pure of any transport: ``apply`` ingests a parsed message (a list of event
    dicts in the Polygon shape — ``{"ev":"Q","sym":"O:…","bp":bid,"ap":ask,
    "t":ns}``) and ``quote`` reads one back, both under a lock so the WS thread
    and the request threads never race. One book may be fed by SEVERAL
    connections (the multi-connection plan): every writer shares the lock.
    """

    def __init__(self) -> None:
        self._quotes: dict[str, QuoteTick] = {}
        self._lock = threading.Lock()
        #: Set once auth + the first subscription have been acknowledged, so the
        #: provider can tell "book warming up" from "book genuinely empty".
        self.connected = False

    def apply(self, events: list[dict]) -> tuple[int, list[dict]]:
        """Fold a batch of WS events into the book. Quotes update the book;
        ``auth_success`` / ``success`` statuses flip ``connected``. Returns
        ``(quotes folded, the status events)`` so the transport can count
        acknowledgements and act on refusals — never silently dropped."""
        quotes = 0
        statuses: list[dict] = []
        with self._lock:
            for ev in events:
                kind = ev.get("ev")
                if kind == "Q":
                    sym = ev.get("sym")
                    if sym:
                        self._quotes[sym] = QuoteTick(
                            bid=_num(ev.get("bp")), ask=_num(ev.get("ap")), ts=ev.get("t")
                        )
                        quotes += 1
                elif kind == "status":
                    if ev.get("status") in ("auth_success", "success"):
                        self.connected = True
                    statuses.append(ev)
        return quotes, statuses

    def quote(self, contract: str) -> QuoteTick | None:
        with self._lock:
            return self._quotes.get(contract)

    def any_of(self, contracts) -> bool:
        """Whether at least one of ``contracts`` has a booked tick (the
        per-ticker "served" test of ``is_streaming_ticker``; short-circuits)."""
        with self._lock:
            quotes = self._quotes
            return any(c in quotes for c in contracts)

    def items(self) -> list[tuple[str, QuoteTick]]:
        """A consistent copy of the whole book under ONE lock acquisition —
        the tick recorder (volfit.data.tick_recorder) folds it into its store
        once a second; a read per contract would take the lock ~1,000 times
        against the writer thread for the same snapshot."""
        with self._lock:
            return list(self._quotes.items())

    def newest_ts(self) -> int | None:
        """Largest provider timestamp across the booked ticks (None when the
        book is empty or the feed sends no timestamps)."""
        with self._lock:
            stamps = [t.ts for t in self._quotes.values() if t.ts is not None]
        return max(stamps) if stamps else None

    def size(self) -> int:
        with self._lock:
            return len(self._quotes)

    def remove(self, contracts: list[str]) -> None:
        """Forget unsubscribed contracts so a stale last tick can never be served
        for an option the universe dropped."""
        with self._lock:
            for c in contracts:
                self._quotes.pop(c, None)

    def clear(self) -> None:
        with self._lock:
            self._quotes.clear()
            self.connected = False


class StreamStats:
    """Thread-safe health counters of one stream (shared by its connections).

    ``rate()`` is messages per second over the last ``RATE_WINDOW_S`` (per-
    second buckets); ages are read off monotonic stamps so a clock change
    never fakes freshness; ``last_message_wall`` gives the "idle since HH:MM"
    reading. ``snapshot()`` is the plain dict the API serialises."""

    def __init__(self, clock=time.monotonic) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self.sockets = 0  # connections configured
        self.connected = 0  # connections currently authenticated
        self.url: str | None = None  # the cluster of the latest connection
        self.messages = 0
        self.quotes = 0
        self._buckets: deque[tuple[int, int]] = deque()  # (second, messages)
        self.last_message_at: float | None = None
        self.last_quote_at: float | None = None
        self.last_message_wall: datetime | None = None
        self.reconnects = 0
        self.last_error: str | None = None
        self.last_error_at: float | None = None
        self.auth_failed = False

    # ------------------------------------------------------------ writers
    def note_message(self, quotes: int) -> None:
        now = self._clock()
        with self._lock:
            self.messages += 1
            self.quotes += quotes
            self.last_message_at = now
            self.last_message_wall = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
            if quotes:
                self.last_quote_at = now
            sec = int(now)
            if self._buckets and self._buckets[-1][0] == sec:
                self._buckets[-1] = (sec, self._buckets[-1][1] + 1)
            else:
                self._buckets.append((sec, 1))
            self._trim(now)

    def note_connected(self, url: str) -> None:
        with self._lock:
            self.connected += 1
            self.url = url
            self.auth_failed = False

    def note_disconnected(self) -> None:
        with self._lock:
            self.connected = max(0, self.connected - 1)

    def note_reconnect(self) -> None:
        with self._lock:
            self.reconnects += 1

    def note_error(self, text: str) -> None:
        with self._lock:
            self.last_error = str(text)[:240]
            self.last_error_at = self._clock()

    def note_auth_failed(self, text: str) -> None:
        self.note_error(text)
        with self._lock:
            self.auth_failed = True

    # ------------------------------------------------------------ readers
    def _trim(self, now: float) -> None:
        floor = int(now - RATE_WINDOW_S)
        while self._buckets and self._buckets[0][0] < floor:
            self._buckets.popleft()

    def rate(self) -> float:
        with self._lock:
            self._trim(self._clock())
            return sum(n for _, n in self._buckets) / RATE_WINDOW_S

    def _age(self, stamp: float | None) -> float | None:
        return None if stamp is None else max(0.0, self._clock() - stamp)

    def message_age(self) -> float | None:
        with self._lock:
            return self._age(self.last_message_at)

    def quote_age(self) -> float | None:
        with self._lock:
            return self._age(self.last_quote_at)

    def snapshot(self) -> dict:
        with self._lock:
            self._trim(self._clock())
            return {
                "connected": self.connected > 0,
                "connections": self.sockets,
                "connectedCount": self.connected,
                "url": self.url,
                "messages": self.messages,
                "quotes": self.quotes,
                "rate": round(sum(n for _, n in self._buckets) / RATE_WINDOW_S, 2),
                "lastMessageAge": self._age(self.last_message_at),
                "lastQuoteAge": self._age(self.last_quote_at),
                "lastMessageUtc": self.last_message_wall.isoformat() if self.last_message_wall else None,
                "reconnects": self.reconnects,
                "lastError": self.last_error,
                "lastErrorAge": self._age(self.last_error_at),
                "authFailed": self.auth_failed,
            }

"""Bloomberg real-time subscriptions (``//blp/mktdata``) — a live quote book.

Why: every ``bdp``/``bds`` reference-data request is METERED against the
Terminal's daily quota, so polling a chain (hundreds–thousands of contracts)
every few seconds is both slow and self-limiting. The Desktop API also offers a
genuine PUSH channel: the ``//blp/mktdata`` *subscription* service. One
``subscribe()`` per security, then Bloomberg streams field updates as they
happen (optionally conflated with ``interval=N`` seconds) — a websocket-like
feed that does not consume the reference-data quota. The Bloomberg provider
serves ``fetch_chain(live)`` and ``spot()`` straight from this book while it
streams (volfit.data.bloomberg_live), exactly as the Massive provider does from
its WebSocket book (volfit.data.massive_ws).

Two layers, mirroring massive_ws:

* ``BbgBook`` — a pure, thread-safe ``{security -> BbgTick}`` store. Bloomberg
  sends DELTAS (a message carries only the fields that changed, after an initial
  ``INITPAINT`` summary), so ``apply`` MERGES each record onto the security's
  current tick. Also tracks subscription status (started / failed + reason),
  the ``IS_DELAYED_STREAM`` flag, and the newest provider stamp (freshness).
* ``BloombergSubscription`` — a daemon thread owning a blpapi session: start →
  open ``//blp/mktdata`` → subscribe (in batches) → ``nextEvent`` loop →
  ``decode_event`` (volfit.data.bloomberg_decode) → ``book.apply``; reconnects
  with capped backoff on a session drop. The session is injectable
  (``session_factory``) and ``decode_event`` passes pre-decoded record lists
  through, so tests drive the loop offline.

Wire facts confirmed live against the Terminal (2026-08-20): SPX streams
real-time, US equities + their options are flagged ``IS_DELAYED_STREAM`` (15 min)
on a non-entitled exchange; ``interval=1.0`` conflation is honoured; a bad
security yields ``SubscriptionFailure``; OPEN_INT is not subscribable.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime

from volfit.data.bloomberg_decode import (
    STREAM_FIELDS,
    decode_event,
    flag,
    int_or_none,
    price_or_none,
)

#: Securities per ``subscribe()`` call — keeps each request modest and lets the
#: SubscriptionStarted statuses (and INITPAINTs) interleave with the next batch.
SUBSCRIBE_BATCH = 200

#: Default Desktop API endpoint (the local bbcomm of the logged-in Terminal).
DEFAULT_HOST, DEFAULT_PORT = "localhost", 8194


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


# ------------------------------------------------------------- transport
class BloombergSubscription:
    """Daemon thread streaming ``securities`` from ``//blp/mktdata`` into ``book``.

    Parameters
    ----------
    securities      : full Bloomberg security strings to subscribe to.
    book            : the ``BbgBook`` to update.
    fields          : subscribed fields (``STREAM_FIELDS``).
    interval        : conflation interval in seconds (``interval=N`` subscription
                      option; None = every tick). 1 s keeps a 2k-contract chain
                      to ~2k updates/s worst case — plenty for a 5 s refit loop.
    session_factory : zero-arg callable returning a started session-like object
                      with ``openService(name)``, ``subscribe(list)``,
                      ``nextEvent(timeout_ms)`` and ``stop()``, plus a
                      ``subscription_list(items)`` builder — injected by tests;
                      defaults to a real blpapi session (``host``/``port``).
    """

    SERVICE = "//blp/mktdata"

    def __init__(
        self,
        securities: list[str],
        book: BbgBook,
        fields: tuple[str, ...] = STREAM_FIELDS,
        interval: float | None = 1.0,
        session_factory=None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        max_backoff: float = 30.0,
    ) -> None:
        self._securities = list(dict.fromkeys(securities))  # dedupe, keep order
        self._book = book
        self._fields = tuple(fields)
        self._interval = interval
        self._factory = session_factory
        self._host, self._port = host, port
        self._max_backoff = max_backoff
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        #: Incremental (un)subscribe ops from other threads, applied by the
        #: worker (which owns the session) between ``nextEvent`` calls — a
        #: universe edit never restarts the session. ``_securities`` is the
        #: LIVE set (updated on enqueue) and is what a reconnect resubscribes.
        self._ops: queue.Queue[tuple[str, list[str]]] = queue.Queue()
        self._lock = threading.Lock()

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="bbg-mktdata", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._book.clear()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def securities(self) -> list[str]:
        """The LIVE subscribed set (pending ops included)."""
        with self._lock:
            return list(self._securities)

    # ------------------------------------------------ incremental updates
    def subscribe(self, securities: list[str]) -> list[str]:
        """Add securities to the live stream without restarting the session
        (applied by the worker within ~0.5 s). Returns the ones actually new."""
        with self._lock:
            have = set(self._securities)
            new = [s for s in dict.fromkeys(securities) if s not in have]
            self._securities.extend(new)
        if new:
            self._ops.put(("sub", new))
        return new

    def unsubscribe(self, securities: list[str]) -> list[str]:
        """Drop securities from the live stream (and the book) without a restart.
        Returns the ones actually removed."""
        with self._lock:
            drop = set(securities)
            gone = [s for s in self._securities if s in drop]
            self._securities = [s for s in self._securities if s not in drop]
        if gone:
            self._book.remove(gone)
            self._ops.put(("unsub", gone))
        return gone

    # ---------------------------------------------------------------- loop
    def _run(self) -> None:
        """Reconnect until ``stop()`` with capped backoff; never raises."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                streamed = self._session_pass()
            except Exception as exc:  # noqa: BLE001 — session error: retry
                text = str(exc).strip()
                self.last_error = text.splitlines()[-1][:120] if text else "session error"
                streamed = False
            if self._stop.is_set():
                return
            backoff = 1.0 if streamed else min(backoff * 2.0, self._max_backoff)
            self._stop.wait(backoff)

    def _session_pass(self) -> bool:
        """One start → open → subscribe → consume pass. Returns whether any data
        record was booked (so the loop resets its backoff)."""
        session = self._factory() if self._factory is not None else self._blpapi_session()
        got_data = False
        try:
            if not session.openService(self.SERVICE):
                raise RuntimeError(f"could not open {self.SERVICE}")
            self.last_error = None
            self._discard_ops()  # the live set already reflects them: resubscribe it whole
            self._subscribe_all(session)
            while not self._stop.is_set():
                event = session.nextEvent(500)
                self._drain_ops(session)  # incremental (un)subscribes, ≤ 0.5 s latency
                if event is None:
                    continue
                records = decode_event(event)
                if not records:
                    continue
                self._book.apply(records)
                got_data = got_data or any(r.get("kind") == "data" for r in records)
                if any(r.get("kind") == "session_down" for r in records):
                    break  # reconnect
        finally:
            try:
                session.stop()
            except Exception:  # noqa: BLE001
                pass
        return got_data

    def _items(self, securities: list[str]) -> list[tuple[str, str, str]]:
        options = f"interval={self._interval:g}" if self._interval else ""
        fields = ",".join(self._fields)
        return [(s, fields, options) for s in securities]

    def _subscribe_all(self, session) -> None:
        with self._lock:
            securities = list(self._securities)
        for start in range(0, len(securities), SUBSCRIBE_BATCH):
            batch = securities[start : start + SUBSCRIBE_BATCH]
            session.subscribe(session.subscription_list(self._items(batch)))
            if self._stop.is_set():
                return

    def _discard_ops(self) -> None:
        while True:
            try:
                self._ops.get_nowait()
            except queue.Empty:
                return

    def _drain_ops(self, session) -> None:
        """Apply queued incremental ops on the worker's session (batched)."""
        while True:
            try:
                kind, secs = self._ops.get_nowait()
            except queue.Empty:
                return
            for start in range(0, len(secs), SUBSCRIBE_BATCH):
                batch = session.subscription_list(self._items(secs[start : start + SUBSCRIBE_BATCH]))
                if kind == "sub":
                    session.subscribe(batch)
                else:
                    session.unsubscribe(batch)

    def _blpapi_session(self):
        """A started real blpapi session wrapped with the small interface the loop
        uses (so the fake session in tests only has to mimic that interface)."""
        import blpapi

        opts = blpapi.SessionOptions()
        opts.setServerHost(self._host)
        opts.setServerPort(self._port)
        opts.setAutoRestartOnDisconnection(True)
        session = blpapi.Session(opts)
        if not session.start():
            raise RuntimeError(f"blpapi session failed to start ({self._host}:{self._port})")
        return _BlpapiSession(session, blpapi)


class _BlpapiSession:
    """Thin adapter over ``blpapi.Session`` exposing the loop's interface."""

    def __init__(self, session, blpapi) -> None:
        self._s = session
        self._blpapi = blpapi

    def openService(self, name: str) -> bool:  # noqa: N802 — blpapi naming
        return bool(self._s.openService(name))

    def subscription_list(self, items: list[tuple[str, str, str]]):
        subs = self._blpapi.SubscriptionList()
        for sec, fields, options in items:
            subs.add(sec, fields, options, self._blpapi.CorrelationId(sec))
        return subs

    def subscribe(self, subs) -> None:
        self._s.subscribe(subs)

    def unsubscribe(self, subs) -> None:
        # blpapi matches on CorrelationId VALUE, so a fresh CorrelationId(sec)
        # identifies the original subscription of that security.
        self._s.unsubscribe(subs)

    def nextEvent(self, timeout_ms: int):  # noqa: N802 — blpapi naming
        event = self._s.nextEvent(timeout_ms)
        return None if event.eventType() == self._blpapi.Event.TIMEOUT else event

    def stop(self) -> None:
        self._s.stop()

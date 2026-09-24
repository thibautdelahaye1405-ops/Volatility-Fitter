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

* ``BbgBook`` (volfit.data.bloomberg_book, re-exported here) — a pure,
  thread-safe ``{security -> BbgTick}`` store that MERGES Bloomberg's deltas
  and tracks subscription status, the delayed flag and the newest stamp.
* ``BloombergSubscription`` — a daemon thread owning a blpapi session: start →
  open ``//blp/mktdata`` → subscribe (in batches) → ``nextEvent`` loop →
  ``decode_event`` (volfit.data.bloomberg_decode) → ``book.apply``; reconnects
  with capped backoff on a session drop. The session is injectable
  (``session_factory``; the real one is volfit.data.bloomberg_session) and
  ``decode_event`` passes pre-decoded record lists through, so tests drive
  the loop offline.

Wire facts confirmed live against the Terminal (2026-08-20): SPX streams
real-time, US equities + their options are flagged ``IS_DELAYED_STREAM`` (15 min)
on a non-entitled exchange; ``interval=1.0`` conflation is honoured; a bad
security yields ``SubscriptionFailure``; OPEN_INT is not subscribable.

Conflation is PER SECURITY (2026-09-24, the tiered-cadence layer): each item
carries its own ``interval=N`` option (``intervals`` overrides the default
``interval``), and ``set_intervals`` moves live securities between tiers
with the SDK's ``resubscribe`` (an unsubscribe + subscribe on the same
session when the session lacks it) — only the securities whose interval
changed are touched, so a focus change never repaints the rest.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Mapping

from volfit.data.bloomberg_book import BbgBook, BbgTick  # noqa: F401 — re-exported
from volfit.data.bloomberg_decode import STREAM_FIELDS, decode_event

__all__ = ["BbgBook", "BbgTick", "BloombergSubscription", "DEFAULT_HOST", "DEFAULT_PORT", "SUBSCRIBE_BATCH"]

#: Securities per ``subscribe()`` call — keeps each request modest and lets the
#: SubscriptionStarted statuses (and INITPAINTs) interleave with the next batch.
SUBSCRIBE_BATCH = 200

#: Default Desktop API endpoint (the local bbcomm of the logged-in Terminal).
DEFAULT_HOST, DEFAULT_PORT = "localhost", 8194


# ------------------------------------------------------------- transport
class BloombergSubscription:
    """Daemon thread streaming ``securities`` from ``//blp/mktdata`` into ``book``.

    Parameters
    ----------
    securities      : full Bloomberg security strings to subscribe to.
    book            : the ``BbgBook`` to update.
    fields          : subscribed fields (``STREAM_FIELDS``).
    interval        : the DEFAULT conflation interval in seconds (``interval=N``
                      subscription option; None = every tick). 1 s keeps a
                      2k-contract chain to ~2k updates/s worst case — plenty
                      for a 5 s refit loop.
    intervals       : per-security overrides of ``interval`` (sec -> seconds
                      or None) — the fast / slow tiers of the provider's plan.
    session_factory : zero-arg callable returning a started session-like object
                      with ``openService(name)``, ``subscribe(list)``,
                      ``unsubscribe(list)``, ``nextEvent(timeout_ms)`` and
                      ``stop()``, plus a ``subscription_list(items)`` builder
                      and (optionally) ``resubscribe(list)`` — injected by
                      tests; defaults to a real blpapi session (``host``/``port``).
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
        intervals: Mapping[str, float | None] | None = None,
    ) -> None:
        self._securities = list(dict.fromkeys(securities))  # dedupe, keep order
        self._book = book
        self._fields = tuple(fields)
        self._interval = interval
        self._intervals: dict[str, float | None] = dict(intervals or {})
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

    def interval_of(self, sec: str) -> float | None:
        """The conflation interval ``sec`` is (or will be) subscribed at."""
        with self._lock:
            return self._intervals.get(sec, self._interval)

    def set_intervals(self, intervals: Mapping[str, float | None]) -> list[str]:
        """Adopt a new per-security interval map; the LIVE securities whose
        interval changes are re-subscribed on the same session (a ``resub``
        op: ``resubscribe`` when the session has it, else unsubscribe +
        subscribe). Returns them — an unchanged map moves nothing."""
        new = dict(intervals)
        with self._lock:
            changed = [
                s for s in self._securities
                if self._intervals.get(s, self._interval) != new.get(s, self._interval)
            ]
            self._intervals = new
        if changed:
            self._ops.put(("resub", changed))
        return changed

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
        if self._factory is not None:
            session = self._factory()
        else:
            from volfit.data.bloomberg_session import blpapi_session

            session = blpapi_session(self._host, self._port)
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
        """``(security, fields, options)`` per item — the options string carries
        the security's OWN conflation interval (``interval=N``, empty = every
        tick), so one batch can mix the fast and slow tiers."""
        fields = ",".join(self._fields)
        with self._lock:
            intervals = {s: self._intervals.get(s, self._interval) for s in securities}
        return [(s, fields, f"interval={iv:g}" if iv else "") for s, iv in intervals.items()]

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
        """Apply queued incremental ops on the worker's session (batched).
        ``resub`` (an interval change) uses the session's ``resubscribe`` —
        the SDK primitive that swaps a live subscription's options in place —
        and falls back to unsubscribe + subscribe on a session without it."""
        resubscribe = getattr(session, "resubscribe", None)
        while True:
            try:
                kind, secs = self._ops.get_nowait()
            except queue.Empty:
                return
            for start in range(0, len(secs), SUBSCRIBE_BATCH):
                batch = session.subscription_list(self._items(secs[start : start + SUBSCRIBE_BATCH]))
                if kind == "sub":
                    session.subscribe(batch)
                elif kind == "unsub":
                    session.unsubscribe(batch)
                elif resubscribe is not None:
                    resubscribe(batch)
                else:
                    session.unsubscribe(batch)
                    session.subscribe(batch)

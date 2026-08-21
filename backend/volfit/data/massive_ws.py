"""Massive/Polygon options WebSocket — a live NBBO book for real-time chains.

A background thread runs an asyncio client that connects to the options cluster
(``wss://socket.massive.com/options``), authenticates with the API key,
subscribes to the quote channels (``Q.O:…``) of the active universe's contracts,
and keeps an in-memory ``LiveBook`` of the latest bid/ask per contract. The
Massive provider then serves ``fetch_chain(live)`` straight from that book — no
REST snapshot poll — so the surface refits (on the workflow's throttle) off a
real-time, unlimited feed.

The message parsing / book update is a pure, synchronous ``LiveBook`` (fully
unit-testable); the transport is a thin asyncio loop with an injectable
``connect`` factory so tests drive it with a fake connection and never open a
socket. Reconnects with capped backoff; a daemon thread so it never blocks exit.

Universe edits are INCREMENTAL: ``subscribe`` / ``unsubscribe`` (thread-safe,
callable from the scheduler) update the live contract set and post an op the
session coroutine turns into a ``{"action": "subscribe"|"unsubscribe"}`` frame
on the open connection — no reconnect, no repaint of the rest. The live set is
what a reconnect (re)subscribes whole, so an op lost to a dropping connection
is never lost for long; the book forgets unsubscribed contracts at once.
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass

#: Default options-cluster WebSocket endpoint (polygon.io host also works).
DEFAULT_WS_URL = "wss://socket.massive.com/options"


@dataclass(frozen=True)
class QuoteTick:
    """The latest streamed NBBO for one option contract (prices may be None)."""

    bid: float | None
    ask: float | None
    ts: int | None  # provider nanosecond timestamp


class LiveBook:
    """Thread-safe ``{option_ticker -> QuoteTick}`` updated from WS messages.

    Pure of any transport: ``apply`` ingests a parsed message (a list of event
    dicts in the Polygon shape — ``{"ev":"Q","sym":"O:…","bp":bid,"ap":ask,
    "t":ns}``) and ``quote`` reads one back, both under a lock so the WS thread
    and the request threads never race.
    """

    def __init__(self) -> None:
        self._quotes: dict[str, QuoteTick] = {}
        self._lock = threading.Lock()
        #: Set once auth + the first subscription have been acknowledged, so the
        #: provider can tell "book warming up" from "book genuinely empty".
        self.connected = False

    def apply(self, events: list[dict]) -> None:
        """Fold a batch of WS events into the book (quotes update; status events
        flip ``connected``). Unknown event types are ignored."""
        with self._lock:
            for ev in events:
                kind = ev.get("ev")
                if kind == "Q":
                    sym = ev.get("sym")
                    if sym:
                        self._quotes[sym] = QuoteTick(
                            bid=_num(ev.get("bp")), ask=_num(ev.get("ap")), ts=ev.get("t")
                        )
                elif kind == "status" and ev.get("status") in ("auth_success", "success"):
                    self.connected = True

    def quote(self, contract: str) -> QuoteTick | None:
        with self._lock:
            return self._quotes.get(contract)

    def newest_ts(self) -> int | None:
        """Largest provider timestamp across the booked ticks (None when the
        book is empty or the feed sends no timestamps) — the freshness signal
        the Data Source selector shows ('stream idle since …')."""
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


def _num(value) -> float | None:
    """A positive float, or None (a 0/blank NBBO side is 'no quote')."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0.0 else None


class MassiveWebSocket:
    """Background asyncio WS client feeding a ``LiveBook``.

    Parameters
    ----------
    api_key   : Massive/Polygon key (sent in the auth frame).
    contracts : option tickers to subscribe to (``"O:SPY…"``); the client
                prefixes each with the quote channel ``Q.``.
    book      : the ``LiveBook`` to update.
    url/urls  : cluster endpoint(s). Pass a single ``url`` or a ``urls`` list of
                CANDIDATE clusters tried in order — the client locks onto the
                first that actually streams quotes and advances past any cluster
                that connects + auths but stays SILENT (the signature of a feed
                whose real-time quote channels aren't entitled; a delayed-tier key
                is served on a ``delayed.*`` cluster instead).
    connect   : optional ``(url) -> async-context-manager`` (or zero-arg) yielding
                a connection with ``send(str)`` and async iteration over text
                frames — injected by tests; defaults to ``websockets.connect``.
    quote_grace : seconds to wait for the first quote on a freshly-connected
                cluster before deciding it is silent and trying the next candidate.
    """

    def __init__(
        self,
        api_key: str,
        contracts: list[str],
        book: LiveBook,
        url: str = DEFAULT_WS_URL,
        urls: list[str] | None = None,
        connect=None,
        max_backoff: float = 30.0,
        quote_grace: float = 6.0,
    ) -> None:
        self._key = api_key
        self._contracts = list(dict.fromkeys(contracts))
        self._lock = threading.Lock()
        self._book = book
        self._urls = list(urls) if urls else [url]
        self._idx = 0
        self._connect = connect
        self._max_backoff = max_backoff
        self._quote_grace = quote_grace
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: Published by the running session: its loop + op queue, so
        #: ``subscribe``/``unsubscribe`` from other threads can hand it frames.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ops: asyncio.Queue | None = None

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="massive-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._book.clear()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def contracts(self) -> list[str]:
        """The LIVE subscribed set (for resubscribe diffing; pending ops included)."""
        with self._lock:
            return list(self._contracts)

    # ------------------------------------------------ incremental updates
    def subscribe(self, contracts: list[str]) -> list[str]:
        """Add contracts to the live stream without reconnecting (a subscribe
        frame on the open connection). Returns the ones actually new."""
        with self._lock:
            have = set(self._contracts)
            new = [c for c in dict.fromkeys(contracts) if c not in have]
            self._contracts.extend(new)
        if new:
            self._post(("subscribe", new))
        return new

    def unsubscribe(self, contracts: list[str]) -> list[str]:
        """Drop contracts from the live stream (and the book) without reconnecting.
        Returns the ones actually removed."""
        with self._lock:
            drop = set(contracts)
            gone = [c for c in self._contracts if c in drop]
            self._contracts = [c for c in self._contracts if c not in drop]
        if gone:
            self._book.remove(gone)
            self._post(("unsubscribe", gone))
        return gone

    def _post(self, op: tuple[str, list[str]]) -> None:
        """Hand an op to the live session (no-op without one: the next session
        subscribes the whole live set, which already reflects the op)."""
        loop, queue = self._loop, self._ops
        if loop is None or queue is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, op)
        except RuntimeError:  # loop shutting down between sessions
            pass

    # --------------------------------------------------------------- loop
    def _run(self) -> None:
        try:
            asyncio.run(self._consume_loop())
        except Exception:  # noqa: BLE001 — the WS thread must never crash the app
            pass

    async def _consume_loop(self) -> None:
        """Reconnect until ``stop()``, rotating through the candidate clusters.

        A session that streamed quotes keeps reconnecting to the SAME cluster on a
        drop (``got`` True → idx unchanged). A silent/errored session advances to
        the next candidate; once a full sweep finds nothing, back off (capped) so a
        wholly-unentitled key doesn't busy-loop."""
        backoff = 1.0
        while not self._stop.is_set():
            url = self._urls[self._idx]
            try:
                got = await self._session(url)
            except Exception:  # noqa: BLE001 — drop/auth error: try the next cluster
                got = False
            if self._stop.is_set():
                return
            if got:
                backoff = 1.0
                continue  # working cluster: reconnect here on the next drop
            self._idx = (self._idx + 1) % len(self._urls)
            if self._idx == 0:  # swept every candidate without a quote: back off
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, self._max_backoff)

    @staticmethod
    def _frame(action: str, contracts: list[str]) -> str:
        return json.dumps({"action": action, "params": ",".join(f"Q.{c}" for c in contracts)})

    async def _session(self, url: str | None = None) -> bool:
        """One connect → auth → subscribe → consume pass against ``url``. Returns
        whether any quote arrived (so the loop can tell a serving cluster from a
        silent one). Incremental ops posted meanwhile are sent on this
        connection as they arrive (``asyncio.wait`` over the next frame and the
        next op), with the quote-grace timeout still policing a silent cluster."""
        url = url or self._urls[self._idx]
        connect = self._connect or (lambda: self._default_connect(url))
        got_data = False
        ops: asyncio.Queue = asyncio.Queue()  # fresh per session: the live set carries history
        self._loop, self._ops = asyncio.get_running_loop(), ops
        try:
            async with connect() as conn:
                await conn.send(json.dumps({"action": "auth", "params": self._key}))
                contracts = self.contracts
                if contracts:
                    await conn.send(self._frame("subscribe", contracts))
                aiter = conn.__aiter__()
                recv = asyncio.ensure_future(aiter.__anext__())
                try:
                    while not self._stop.is_set():
                        op_task = asyncio.ensure_future(ops.get())
                        done, _pending = await asyncio.wait(
                            {recv, op_task},
                            timeout=self._quote_grace,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if op_task in done:
                            action, items = op_task.result()
                            if items:
                                await conn.send(self._frame(action, items))
                        else:
                            op_task.cancel()
                        if recv in done:
                            try:
                                raw = recv.result()
                            except (StopAsyncIteration, RuntimeError):
                                break  # connection closed / iterator exhausted → reconnect
                            events = _parse(raw)
                            self._book.apply(events)
                            if any(ev.get("ev") == "Q" for ev in events):
                                got_data = True
                            recv = asyncio.ensure_future(aiter.__anext__())
                        elif not done:
                            if got_data:
                                continue  # a quiet moment on a working cluster — keep waiting
                            break  # silent since connect → this cluster isn't serving us
                finally:
                    recv.cancel()
        finally:
            self._loop, self._ops = None, None
        return got_data

    def _default_connect(self, url: str):
        import websockets

        return websockets.connect(url, max_size=None, ping_interval=20)


def _parse(raw) -> list[dict]:
    """Decode a WS text frame to a list of event dicts (tolerant of a single
    object or malformed JSON)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []

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

    def size(self) -> int:
        with self._lock:
            return len(self._quotes)

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
    url       : cluster endpoint (default options cluster).
    connect   : optional ``() -> async-context-manager`` yielding a connection
                with ``send(str)`` and async iteration over text frames —
                injected by tests; defaults to ``websockets.connect``.
    """

    def __init__(
        self,
        api_key: str,
        contracts: list[str],
        book: LiveBook,
        url: str = DEFAULT_WS_URL,
        connect=None,
        max_backoff: float = 30.0,
    ) -> None:
        self._key = api_key
        self._contracts = list(contracts)
        self._book = book
        self._url = url
        self._connect = connect
        self._max_backoff = max_backoff
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

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
        """The contract set this client is subscribed to (for resubscribe diffing)."""
        return list(self._contracts)

    # --------------------------------------------------------------- loop
    def _run(self) -> None:
        try:
            asyncio.run(self._consume_loop())
        except Exception:  # noqa: BLE001 — the WS thread must never crash the app
            pass

    async def _consume_loop(self) -> None:
        """Reconnect with capped exponential backoff until ``stop()``."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._session()
                backoff = 1.0  # a clean session ended (e.g. server close): retry fast
            except Exception:  # noqa: BLE001 — drop/auth error: back off and retry
                if self._stop.is_set():
                    return
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, self._max_backoff)

    async def _session(self) -> None:
        """One connect → auth → subscribe → consume pass."""
        connect = self._connect or self._default_connect
        async with connect() as conn:
            await conn.send(json.dumps({"action": "auth", "params": self._key}))
            if self._contracts:
                params = ",".join(f"Q.{c}" for c in self._contracts)
                await conn.send(json.dumps({"action": "subscribe", "params": params}))
            async for raw in conn:
                if self._stop.is_set():
                    return
                self._book.apply(_parse(raw))

    def _default_connect(self):
        import websockets

        return websockets.connect(self._url, max_size=None, ping_interval=20)


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

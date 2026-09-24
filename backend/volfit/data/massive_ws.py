"""Massive/Polygon options WebSocket transport — one connection, a chunked and
ACKNOWLEDGED subscription, session-aware reconnects (reworked 2026-09-24).

Why this shape (the 2026-09-23 finding, verified live): Massive's options
QUOTES socket allows about 1,000 contracts per connection; a subscribe frame
that would cross the limit is refused IN FULL ("Subscription limit reached
for feed. Please remove some subscriptions and try again."), the count is
cumulative on the connection, one connection per cluster per plan. The old
client sent EVERY contract of the selection in ONE frame (SPY 26 expiries =
10,560), dropped ``status: "error"`` frames silently and reported "streaming"
whenever its thread was alive — so the app showed "stream warming" for five
days while the book never served. Also: a 6-second "silent cluster" rule
against a single delayed URL reconnected every 6–36 s all night, unlogged.

What the client does now:
* subscribes in CHUNKS of ``SUBSCRIBE_BATCH`` (200) contracts, the initial
  set after auth included; every chunk is a PENDING record until the server
  acknowledges it ("subscribed to: Q.O:…" status per contract, or a quote
  arriving for a contract — the implicit acknowledgement);
* PARSES status frames: "Subscription limit reached" pairs the refusal with
  the pending chunk it answers (FIFO — the server answers frames in order;
  when no acknowledgement has parsed yet on the connection, the LAST chunk
  sent), drops the farther half of that chunk (chunks are ranked nearest-
  the-money first by the provider's plan) into ``refused`` and re-sends the
  nearer half, until the acknowledged count sits under the server's limit;
  ``auth_failed`` records the error and backs off (no busy loop); any other
  error is recorded and logged;
* keeps a connected socket OUTSIDE the US session (silence is expected there
  — no rotation, no reconnect churn); INSIDE the session a first connection
  with no quote for ``quote_grace`` rotates to the next candidate cluster,
  and a serving connection with no message at all for
  ``SILENCE_RECONNECT_S`` reconnects;
* logs every connect / auth / acknowledgement count / error / drop /
  reconnect on ``volfit.massive_ws`` — never silent.

Universe edits stay INCREMENTAL (``subscribe`` / ``unsubscribe`` from any
thread post chunked ops the session sends on the open connection); the live
set is what a reconnect (re)subscribes whole. ``LiveBook`` / ``StreamStats``
live in volfit.data.massive_book and are re-exported here for readers of the
old module.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading

from volfit.data.massive_book import LiveBook, QuoteTick, StreamStats, parse_frame
from volfit.data.massive_ws_acks import LIMIT_TEXT, AckMixin

__all__ = ["DEFAULT_WS_URL", "LIMIT_TEXT", "LiveBook", "MassiveWebSocket", "QuoteTick", "StreamStats"]

#: Default options-cluster WebSocket endpoint (polygon.io host also works).
DEFAULT_WS_URL = "wss://socket.massive.com/options"
#: Contracts per subscribe / unsubscribe frame.
SUBSCRIBE_BATCH = 200
#: In-session: seconds without ANY message on a serving connection → reconnect.
SILENCE_RECONNECT_S = 30.0

log = logging.getLogger("volfit.massive_ws")
_parse = parse_frame  # the old private name


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _default_session_open() -> bool:
    from volfit.data.expiry_time import session_open_now

    return session_open_now()


class MassiveWebSocket(AckMixin):
    """Background asyncio WS client feeding a ``LiveBook`` (one connection).

    Parameters
    ----------
    api_key   : Massive/Polygon key (sent in the auth frame).
    contracts : option tickers to subscribe to (``"O:SPY…"``), NEAREST-THE-
                MONEY FIRST (a refusal drops the tail of a chunk); the client
                prefixes each with the quote channel ``Q.``.
    book      : the ``LiveBook`` to update (shared across connections).
    url/urls  : cluster endpoint(s): a single ``url`` or a ``urls`` list of
                CANDIDATE clusters tried in order (a delayed-tier key auths on
                the real-time cluster but is served no quote there).
    connect   : optional ``(url) -> async-context-manager`` (or zero-arg)
                yielding a connection with ``send(str)`` and async iteration
                over text frames — injected by tests; defaults to
                ``websockets.connect``.
    quote_grace : in-session seconds a FIRST connection may stay quote-less
                before the next candidate cluster is tried.
    stats     : the shared ``StreamStats`` (one is made when omitted).
    session_open : ``() -> bool`` — whether the US options session is open now
                (default: 09:30–16:15 ET on a trading day); injectable clock.
    silence_s : in-session seconds without any message before a reconnect.
    name      : a label for the log lines ("ws1", "ws2" — the connection index).
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
        stats: StreamStats | None = None,
        batch: int = SUBSCRIBE_BATCH,
        session_open=None,
        silence_s: float = SILENCE_RECONNECT_S,
        name: str = "ws",
    ) -> None:
        self._key = api_key
        self._contracts = list(dict.fromkeys(contracts))
        self._lock = threading.Lock()
        self._book = book
        self._stats = stats or StreamStats()
        self._urls = list(urls) if urls else [url]
        self._idx = 0
        self._connect = connect
        self._max_backoff = max_backoff
        self._quote_grace = quote_grace
        self._batch = max(1, int(batch))
        self._session_open = session_open or _default_session_open
        self._silence_s = silence_s
        self._name = name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        #: Published by the running session: its loop + op queue, so
        #: ``subscribe``/``unsubscribe`` from other threads can hand it frames.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ops: asyncio.Queue | None = None
        #: Acknowledgement state of the CURRENT connection: contracts the
        #: server confirmed (by status or by a quote), the chunks sent and not
        #: yet fully confirmed (in send order), and the contracts a refusal
        #: dropped (they leave the live set until the provider re-plans).
        self._acked: set[str] = set()
        self._pending: list[dict] = []
        self._pending_syms: set[str] = set()
        self._refused: list[str] = []
        self._acks_parsed = 0  # status acknowledgements parsed this connection

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name=f"massive-{self._name}", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._book.clear()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def contracts(self) -> list[str]:
        """The LIVE subscribed set (for resubscribe diffing; pending ops included,
        refused contracts excluded)."""
        with self._lock:
            return list(self._contracts)

    @property
    def acked(self) -> set[str]:
        with self._lock:
            return set(self._acked)

    @property
    def refused(self) -> list[str]:
        with self._lock:
            return list(self._refused)

    def counts(self) -> tuple[int, int, int]:
        """``(subscribed, acknowledged, refused)`` of this connection."""
        with self._lock:
            return (len(self._contracts), len(self._acked), len(self._refused))

    # ------------------------------------------------ incremental updates
    def subscribe(self, contracts: list[str]) -> list[str]:
        """Add contracts to the live stream without reconnecting (chunked
        subscribe frames on the open connection). Returns the ones actually new."""
        with self._lock:
            have = set(self._contracts)
            new = [c for c in dict.fromkeys(contracts) if c not in have]
            self._contracts.extend(new)
            for c in new:
                if c in self._refused:
                    self._refused.remove(c)  # a re-plan retries it
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
            self._acked.difference_update(drop)
            self._refused = [c for c in self._refused if c not in drop]
            self._forget_pending(drop)
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
        except Exception as exc:  # noqa: BLE001 — the WS thread must never crash the app
            self._stats.note_error(f"thread: {type(exc).__name__}: {exc}")
            log.exception("%s: thread ended", self._name)

    async def _consume_loop(self) -> None:
        """Reconnect until ``stop()``: a serving cluster is kept (reconnect there
        after a drop, 1 s later); a SILENT first connection — in session only —
        rotates to the next candidate, backing off once every candidate was
        swept; a closed / errored session reconnects with capped backoff; a
        failed auth waits the full backoff (no busy loop)."""
        backoff = 1.0
        first = True
        while not self._stop.is_set():
            url = self._urls[self._idx]
            if not first:
                self._stats.note_reconnect()
                log.info("%s: reconnecting to %s (reconnect #%d)", self._name, url, self._stats.reconnects)
            first = False
            try:
                outcome = await self._session(url)
            except Exception as exc:  # noqa: BLE001 — drop / refused socket: retry
                outcome = "error"
                self._stats.note_error(f"{type(exc).__name__}: {exc}")
                log.warning("%s: session error on %s: %s", self._name, url, exc)
            if self._stop.is_set():
                return
            if outcome == "served":
                backoff = 1.0
                await asyncio.sleep(1.0)  # the working cluster: back here after a drop
                continue
            if outcome == "silent":
                self._idx = (self._idx + 1) % len(self._urls)
                log.info("%s: silent in session — trying %s", self._name, self._urls[self._idx])
                if self._idx == 0:  # swept every candidate without a quote: back off
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, self._max_backoff)
                continue
            if outcome == "auth_failed":
                await asyncio.sleep(self._max_backoff)
                continue
            await asyncio.sleep(backoff)  # closed / error: same cluster, capped backoff
            backoff = min(backoff * 2.0, self._max_backoff)

    @staticmethod
    def _frame(action: str, contracts: list[str]) -> str:
        return json.dumps({"action": action, "params": ",".join(f"Q.{c}" for c in contracts)})

    async def _send_subscribe(self, conn, contracts: list[str]) -> None:
        """One chunked subscribe: each frame becomes a pending record."""
        for chunk in _chunks(contracts, self._batch):
            with self._lock:
                self._pending.append({"items": list(chunk), "left": set(chunk)})
                self._pending_syms.update(chunk)
            await conn.send(self._frame("subscribe", chunk))

    async def _send_op(self, conn, action: str, items: list[str]) -> None:
        if not items:
            return
        if action == "subscribe":
            await self._send_subscribe(conn, items)
            return
        for chunk in _chunks(items, self._batch):
            await conn.send(self._frame(action, chunk))

    async def _session(self, url: str | None = None) -> str:
        """One connect → auth → chunked subscribe → consume pass against ``url``.

        Returns WHY it ended: ``"served"`` (quotes flowed — reconnect here),
        ``"silent"`` (in session, no quote within the grace — rotate),
        ``"closed"`` (the server closed it without a quote — same cluster,
        backoff), ``"auth_failed"``. Incremental ops posted meanwhile are sent
        on this connection as they arrive."""
        url = url or self._urls[self._idx]
        connect = self._connect or (lambda: self._default_connect(url))
        got_data = False
        outcome = "closed"
        ops: asyncio.Queue = asyncio.Queue()  # fresh per session: the live set carries history
        self._loop, self._ops = asyncio.get_running_loop(), ops
        with self._lock:
            self._acked.clear()
            self._pending.clear()
            self._pending_syms.clear()
            self._acks_parsed = 0
        loop = asyncio.get_running_loop()
        authed = False
        try:
            async with connect() as conn:
                log.info("%s: connecting %s (%d contracts)", self._name, url, len(self._contracts))
                await conn.send(json.dumps({"action": "auth", "params": self._key}))
                contracts = self.contracts
                if contracts:
                    await self._send_subscribe(conn, contracts)
                aiter = conn.__aiter__()
                recv = asyncio.ensure_future(aiter.__anext__())
                connected_at = last_msg = loop.time()
                wait_s = max(0.01, min(self._quote_grace, self._silence_s))
                try:
                    while not self._stop.is_set():
                        op_task = asyncio.ensure_future(ops.get())
                        done, _pending = await asyncio.wait(
                            {recv, op_task}, timeout=wait_s, return_when=asyncio.FIRST_COMPLETED
                        )
                        if op_task in done:
                            action, items = op_task.result()
                            await self._send_op(conn, action, items)
                        else:
                            op_task.cancel()
                        if recv in done:
                            try:
                                raw = recv.result()
                            except (StopAsyncIteration, RuntimeError):
                                break  # connection closed / iterator exhausted → reconnect
                            events = parse_frame(raw)
                            last_msg = loop.time()
                            quotes, statuses = self._book.apply(events)
                            self._stats.note_message(quotes)
                            if quotes:
                                got_data = True
                                self._ack_by_quotes(events)
                            failed = False
                            for ev in statuses:
                                if await self._handle_status(conn, ev, url) == "auth_failed":
                                    failed = True
                                if ev.get("status") == "auth_success":
                                    authed = True
                            if failed:
                                outcome = "auth_failed"
                                break
                            recv = asyncio.ensure_future(aiter.__anext__())
                        elif not done:
                            if not self._session_open():
                                continue  # closed session: silence is expected, keep the socket
                            now = loop.time()
                            if not got_data and now - connected_at >= self._quote_grace:
                                outcome = "silent"
                                break
                            if got_data and now - last_msg >= self._silence_s:
                                log.warning("%s: no message for %.0f s in session — reconnecting", self._name, now - last_msg)
                                break
                finally:
                    recv.cancel()
        finally:
            self._loop, self._ops = None, None
            if authed:
                self._stats.note_disconnected()
        return "served" if got_data else outcome

    def _default_connect(self, url: str):
        import websockets

        return websockets.connect(url, max_size=None, ping_interval=20)

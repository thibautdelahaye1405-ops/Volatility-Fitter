"""Incremental (un)subscribe on the Massive WebSocket (volfit.data.massive_ws) —
a universe edit sends subscribe/unsubscribe frames on the OPEN connection
instead of reconnecting; the live set is what a reconnect resubscribes; the
book forgets dropped contracts; the provider's ``update_streaming`` diffs.

Driven on the test's own asyncio loop with a slow fake connection that stays
open while ops are posted (no socket, no thread).
"""

from __future__ import annotations

import asyncio
import json

from volfit.data.massive_ws import LiveBook, MassiveWebSocket
from volfit.data.massive import MassiveProvider


class SlowConn:
    """Fake websockets conn yielding ``frames`` one per ``gap`` seconds."""

    def __init__(self, frames: list[str], gap: float = 0.03):
        self._frames, self._gap = list(frames), gap
        self.sent: list[str] = []

    async def send(self, msg: str) -> None:
        self.sent.append(msg)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def __aiter__(self):
        for f in self._frames:
            await asyncio.sleep(self._gap)
            yield f


def _q(sym: str, bid: float) -> dict:
    return {"ev": "Q", "sym": sym, "bp": bid, "ap": bid + 0.2, "t": 1}


def _sent(conn: SlowConn) -> list[dict]:
    return [json.loads(m) for m in conn.sent]


def test_ops_are_sent_on_the_live_connection_and_book_forgets_dropped():
    frames = [json.dumps([{"ev": "status", "status": "auth_success"}])]
    frames += [json.dumps([_q("O:SPY1", 1.0), _q("O:SPY2", 2.0)])] * 8  # keeps the conn open ~0.25 s
    conn = SlowConn(frames)
    book = LiveBook()
    ws = MassiveWebSocket("KEY", ["O:SPY1", "O:SPY2"], book, connect=lambda: conn, quote_grace=5.0)

    async def drive():
        session = asyncio.ensure_future(ws._session())
        await asyncio.sleep(0.08)  # auth + subscribe sent, first quotes booked
        assert ws.subscribe(["O:NEW", "O:SPY1"]) == ["O:NEW"]  # SPY1 already live
        await asyncio.sleep(0.05)
        assert book.quote("O:SPY2") is not None
        assert ws.unsubscribe(["O:SPY2", "O:NOPE"]) == ["O:SPY2"]
        assert book.quote("O:SPY2") is None  # forgotten at once (the fake keeps sending it; a real server stops)
        await session
        return session.result()

    got = asyncio.run(drive())
    assert got is True
    sent = _sent(conn)
    assert sent[0]["action"] == "auth" and sent[1] == {"action": "subscribe", "params": "Q.O:SPY1,Q.O:SPY2"}
    assert {"action": "subscribe", "params": "Q.O:NEW"} in sent
    assert {"action": "unsubscribe", "params": "Q.O:SPY2"} in sent
    assert sent.index({"action": "subscribe", "params": "Q.O:NEW"}) < sent.index({"action": "unsubscribe", "params": "Q.O:SPY2"})
    assert ws.contracts == ["O:SPY1", "O:NEW"]


def test_reconnect_subscribes_the_live_set():
    """Ops folded into the live set survive a drop: the next session subscribes
    the CURRENT set whole (no stale ops replayed)."""
    first = SlowConn([json.dumps([{"ev": "status", "status": "auth_success"}])] + [json.dumps([_q("O:A", 1.0)])] * 4)
    second = SlowConn([json.dumps([_q("O:A", 1.0)])])
    conns = [first, second]
    book = LiveBook()
    ws = MassiveWebSocket("KEY", ["O:A", "O:B"], book, connect=lambda: conns.pop(0), quote_grace=5.0)

    async def drive():
        s1 = asyncio.ensure_future(ws._session())
        await asyncio.sleep(0.05)
        ws.subscribe(["O:C"])
        ws.unsubscribe(["O:B"])
        await s1
        # no live session now: posting is a harmless no-op, the set still updates
        assert ws.subscribe(["O:D"]) == ["O:D"] and ws._loop is None
        await ws._session()

    asyncio.run(drive())
    assert _sent(second)[1] == {"action": "subscribe", "params": "Q.O:A,Q.O:C,Q.O:D"}
    assert ws.contracts == ["O:A", "O:C", "O:D"]


def test_livebook_remove():
    book = LiveBook()
    book.apply([_q("O:X", 1.0), _q("O:Y", 2.0)])
    book.remove(["O:X", "O:Z"])
    assert book.quote("O:X") is None and book.quote("O:Y").bid == 2.0 and book.size() == 1


class _FakeWs:
    def __init__(self, contracts):
        self._c = list(contracts)
        self.subs: list[list[str]] = []
        self.unsubs: list[list[str]] = []

    @property
    def contracts(self):
        return list(self._c)

    def subscribe(self, contracts):
        new = [c for c in contracts if c not in self._c]
        self._c += new
        self.subs.append(new)
        return new

    def unsubscribe(self, contracts):
        gone = [c for c in self._c if c in set(contracts)]
        self._c = [c for c in self._c if c not in set(contracts)]
        self.unsubs.append(gone)
        return gone

    def is_running(self):
        return True

    def stop(self):
        pass


def test_provider_update_streaming_diffs_on_the_live_ws():
    prov = MassiveProvider(["SPY"], api_key="k")
    prov._ws = _FakeWs(["O:A", "O:B"])  # what start_streaming() installs
    prov._live_book = LiveBook()
    assert prov.is_streaming()
    added, removed = prov.update_streaming(["O:B", "O:C", "O:C"])
    assert added == ["O:C"] and removed == ["O:A"]
    assert prov.streaming_contracts() == {"O:B", "O:C"}
    assert prov._ws.subs == [["O:C"]] and prov._ws.unsubs == [["O:A"]]
    # empty universe -> the stream stops
    prov.update_streaming([])
    assert not prov.is_streaming() and prov._live_book is None

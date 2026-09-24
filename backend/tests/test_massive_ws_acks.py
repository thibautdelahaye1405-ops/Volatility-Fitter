"""The Massive options socket after the 2026-09-24 rework (volfit.data.massive_ws
+ massive_ws_acks + massive_book): the chunked initial subscribe, per-contract
acknowledgements (by status and by a quote), a refused frame trimmed and
re-sent, auth failure, other errors recorded, the session-gated silence rule
(a closed-session socket kept for a simulated hour; an in-session silence
reconnecting), the stats' rate window and the US session clock.

Offline: fake connections driven on the test's own asyncio loop."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from volfit.data.massive_book import LiveBook, StreamStats, ns_to_utc_naive
from volfit.data.massive_ws import SUBSCRIBE_BATCH, MassiveWebSocket


# ------------------------------------------------------------ the transport

class Conn:
    """Fake websockets conn: canned frames, one per ``gap`` s; optional
    scripted replies (sent frame index -> frames to yield after it)."""

    def __init__(self, frames=None, gap: float = 0.01, hold: float = 0.0):
        self.frames, self.gap, self.hold = list(frames or []), gap, hold
        self.sent: list[dict] = []
        self.replies: list[str] = []
        self.on_send = None

    async def send(self, msg: str) -> None:
        self.sent.append(json.loads(msg))
        if self.on_send is not None:
            self.on_send(self, self.sent[-1])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def __aiter__(self):
        for f in self.frames:
            await asyncio.sleep(self.gap)
            yield f
        while self.replies or self.hold > 0.0:
            if self.replies:
                yield self.replies.pop(0)
                continue
            await asyncio.sleep(min(0.01, self.hold))
            self.hold -= 0.01


def _ack(syms) -> str:
    return json.dumps([{"ev": "status", "status": "success", "message": f"subscribed to: Q.{s}"} for s in syms])


def test_initial_subscribe_is_chunked_and_acknowledgements_are_counted():
    contracts = [f"O:C{i:04d}" for i in range(SUBSCRIBE_BATCH * 2 + 5)]
    conn = Conn([json.dumps([{"ev": "status", "status": "auth_success"}]), _ack(contracts[:SUBSCRIBE_BATCH])], hold=0.6)
    stats = StreamStats()
    ws = MassiveWebSocket("KEY", contracts, LiveBook(), connect=lambda: conn, stats=stats, session_open=lambda: True, quote_grace=0.2)
    assert asyncio.run(ws._session()) == "silent"  # acks but no quote within the grace: rotate
    subs = [m for m in conn.sent if m["action"] == "subscribe"]
    assert [len(m["params"].split(",")) for m in subs] == [SUBSCRIBE_BATCH, SUBSCRIBE_BATCH, 5]
    assert subs[0]["params"].startswith("Q.O:C0000,Q.O:C0001")
    assert ws.counts() == (len(contracts), SUBSCRIBE_BATCH, 0)
    assert stats.messages == 2 and stats.snapshot()["connected"] is False  # left the session


def test_a_quote_acknowledges_its_contract_and_refusal_trims_and_resends():
    """A "Subscription limit reached" frame: the pending chunk it answers loses
    its farther half (refused, remembered) and the nearer half is re-sent;
    nothing is unsubscribed; the error is recorded and counted."""
    contracts = [f"O:C{i:02d}" for i in range(10)]
    limit = json.dumps([{"ev": "status", "status": "error",
                         "message": "Subscription limit reached for feed. Please remove some subscriptions and try again."}])
    conn = Conn([json.dumps([{"ev": "status", "status": "auth_success"}])], hold=0.3)

    def script(c: Conn, msg: dict):
        subs = [m for m in c.sent if m["action"] == "subscribe"]
        if msg["action"] == "subscribe" and len(subs) == 1:
            c.replies.append(limit)  # the first (only) chunk is refused
        elif msg["action"] == "subscribe" and len(subs) == 2:
            names = [s[2:] for s in msg["params"].split(",")]
            c.replies.append(_ack(names))  # the halved chunk is accepted
            c.replies.append(json.dumps([{"ev": "Q", "sym": names[0], "bp": 1.0, "ap": 1.2, "t": 1}]))

    conn.on_send = script
    stats = StreamStats()
    book = LiveBook()
    ws = MassiveWebSocket("KEY", contracts, book, connect=lambda: conn, stats=stats, session_open=lambda: True, quote_grace=5.0, silence_s=5.0)
    assert asyncio.run(ws._session()) == "served"
    subs = [m for m in conn.sent if m["action"] == "subscribe"]
    assert len(subs) == 2 and subs[1]["params"] == ",".join(f"Q.{c}" for c in contracts[:5])
    assert not [m for m in conn.sent if m["action"] == "unsubscribe"]
    assert ws.refused == contracts[5:] and ws.contracts == contracts[:5]
    assert ws.counts() == (5, 5, 5)
    assert "Subscription limit reached" in (stats.last_error or "") and "5 dropped" in stats.last_error
    assert book.quote("O:C00").bid == 1.0 and stats.quotes == 1


def test_auth_failure_is_recorded_and_ends_the_session():
    conn = Conn([json.dumps([{"ev": "status", "status": "auth_failed", "message": "invalid key"}])])
    stats = StreamStats()
    ws = MassiveWebSocket("KEY", ["O:A"], LiveBook(), connect=lambda: conn, stats=stats, session_open=lambda: True)
    assert asyncio.run(ws._session()) == "auth_failed"
    assert stats.auth_failed and "invalid key" in stats.last_error


def test_other_errors_are_recorded_not_dropped():
    conn = Conn([json.dumps([{"ev": "status", "status": "error", "message": "unknown channel"}])], hold=0.05)
    stats = StreamStats()
    ws = MassiveWebSocket("KEY", ["O:A"], LiveBook(), connect=lambda: conn, stats=stats, session_open=lambda: False)
    asyncio.run(ws._session())
    assert stats.last_error == "unknown channel"


def test_closed_session_silence_keeps_the_socket_and_never_reconnects():
    """Outside the US session a connected, silent socket is kept: over a
    simulated hour (60 grace periods) the loop reconnects 0 times and the
    single connection stays open."""
    conn = Conn([json.dumps([{"ev": "status", "status": "auth_success"}])], hold=0.6)
    stats = StreamStats()
    opened = []

    def connect():
        opened.append(conn)
        return conn

    ws = MassiveWebSocket("KEY", ["O:A"], LiveBook(), connect=connect, stats=stats,
                          session_open=lambda: False, quote_grace=0.01, silence_s=0.01)

    async def drive():
        task = asyncio.ensure_future(ws._consume_loop())
        await asyncio.sleep(0.45)  # ≫ 40 grace / silence periods
        ws._stop.set()
        await asyncio.wait_for(task, 2.0)

    asyncio.run(drive())
    assert len(opened) == 1 and stats.reconnects == 0 and stats.snapshot()["connected"] is False


def test_in_session_silence_reconnects_after_the_silence_window():
    """Inside the session a serving connection with no message at all for
    ``silence_s`` reconnects (to the same cluster); the counter says so."""
    first = Conn([json.dumps([{"ev": "status", "status": "auth_success"}]),
                  json.dumps([{"ev": "Q", "sym": "O:A", "bp": 1.0, "ap": 1.1, "t": 1}])], hold=0.5)
    second = Conn([json.dumps([{"ev": "Q", "sym": "O:A", "bp": 1.0, "ap": 1.1, "t": 2}])], hold=0.5)
    conns = [first, second]
    stats = StreamStats()
    ws = MassiveWebSocket("KEY", ["O:A"], LiveBook(), urls=["wss://x", "wss://y"], connect=lambda: conns.pop(0),
                          stats=stats, session_open=lambda: True, quote_grace=5.0, silence_s=0.05)

    async def drive():
        task = asyncio.ensure_future(ws._consume_loop())
        await asyncio.sleep(1.4)
        ws._stop.set()
        await asyncio.wait_for(task, 3.0)

    asyncio.run(drive())
    assert stats.reconnects == 1 and not conns  # reconnected once, on the SAME cluster (idx 0)
    assert ws._idx == 0


def test_stream_stats_rate_window_and_ages():
    clock = {"t": 100.0}
    stats = StreamStats(clock=lambda: clock["t"])
    for _ in range(50):
        stats.note_message(2)
    assert stats.rate() == pytest.approx(5.0) and stats.quotes == 100
    clock["t"] += 3.0
    assert stats.message_age() == 3.0 and stats.quote_age() == 3.0
    clock["t"] += 20.0
    assert stats.rate() == 0.0  # the window slid past every bucket
    assert ns_to_utc_naive(1_700_000_000_000_000_000) == datetime(2023, 11, 14, 22, 13, 20)


def test_session_open_now_is_the_us_options_session():
    from volfit.data.expiry_time import ET, session_open_now

    assert session_open_now(datetime(2026, 9, 24, 10, 0, tzinfo=ET))
    assert session_open_now(datetime(2026, 9, 24, 16, 10, tzinfo=ET))  # index options to 16:15
    assert not session_open_now(datetime(2026, 9, 24, 16, 20, tzinfo=ET))
    assert not session_open_now(datetime(2026, 9, 24, 9, 0, tzinfo=ET))
    assert not session_open_now(datetime(2026, 9, 26, 12, 0, tzinfo=ET))  # Saturday
    assert session_open_now(datetime(2026, 9, 24, 15, 0, tzinfo=timezone.utc))  # 11:00 ET, an aware UTC instant
    assert not session_open_now(datetime(2026, 11, 27, 13, 30, tzinfo=ET))  # half-day: closed at 13:00

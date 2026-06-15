"""Offline tests for the Massive options WebSocket live book.

No socket: a ``FakeConn`` stands in for ``websockets.connect``, yielding canned
text frames in the Polygon shape. Verifies the pure ``LiveBook`` parsing and the
asyncio session's auth → subscribe → consume flow.
"""

from __future__ import annotations

import asyncio
import json

from volfit.data.massive_ws import LiveBook, MassiveWebSocket


def test_livebook_applies_quotes_and_status():
    book = LiveBook()
    book.apply([{"ev": "status", "status": "auth_success"}])
    assert book.connected is True
    book.apply([
        {"ev": "Q", "sym": "O:SPY260918C00500000", "bp": 9.8, "ap": 10.2, "t": 1},
        {"ev": "Q", "sym": "O:SPY260918P00500000", "bp": 0, "ap": 1.5, "t": 2},  # 0 bid -> None
        {"ev": "T", "sym": "O:SPY260918C00500000"},  # non-quote ignored
    ])
    c = book.quote("O:SPY260918C00500000")
    assert c is not None and c.bid == 9.8 and c.ask == 10.2
    p = book.quote("O:SPY260918P00500000")
    assert p.bid is None and p.ask == 1.5  # zeroed side dropped
    assert book.quote("O:UNKNOWN") is None
    assert book.size() == 2


def test_livebook_latest_wins_and_clear():
    book = LiveBook()
    book.apply([{"ev": "Q", "sym": "O:X", "bp": 1.0, "ap": 1.2, "t": 1}])
    book.apply([{"ev": "Q", "sym": "O:X", "bp": 1.1, "ap": 1.3, "t": 2}])  # newer tick wins
    assert book.quote("O:X").bid == 1.1
    book.clear()
    assert book.size() == 0 and book.connected is False


class FakeConn:
    """Async context manager + async-iterable stand-in for a websockets conn."""

    def __init__(self, frames: list[str]):
        self._frames = frames
        self.sent: list[str] = []

    async def send(self, msg: str) -> None:
        self.sent.append(msg)

    async def __aenter__(self) -> "FakeConn":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def __aiter__(self):
        for f in self._frames:
            yield f


def test_session_auths_subscribes_and_books_quotes():
    frames = [
        json.dumps([{"ev": "status", "status": "auth_success"}]),
        json.dumps([
            {"ev": "Q", "sym": "O:SPY260918C00500000", "bp": 9.8, "ap": 10.2, "t": 1},
            {"ev": "Q", "sym": "O:SPY260918C00505000", "bp": 7.0, "ap": 7.4, "t": 1},
        ]),
    ]
    conn = FakeConn(frames)
    book = LiveBook()
    ws = MassiveWebSocket(
        "KEY",
        ["O:SPY260918C00500000", "O:SPY260918C00505000"],
        book,
        connect=lambda: conn,
    )
    asyncio.run(ws._session())

    # Auth + a single batched subscribe were sent, in order.
    assert json.loads(conn.sent[0]) == {"action": "auth", "params": "KEY"}
    sub = json.loads(conn.sent[1])
    assert sub["action"] == "subscribe"
    assert sub["params"] == "Q.O:SPY260918C00500000,Q.O:SPY260918C00505000"
    # Both quotes are in the book; status flipped connected.
    assert book.connected is True and book.size() == 2
    assert book.quote("O:SPY260918C00500000").ask == 10.2


class SilentConn(FakeConn):
    """Connects + (implicitly) auths but never yields a frame — the signature of a
    cluster whose quote channels aren't entitled. Blocks past the quote grace."""

    async def __aiter__(self):
        await asyncio.sleep(0.5)  # longer than the test's quote_grace -> timeout
        return
        yield  # pragma: no cover (makes this an async generator)


def test_consume_loop_advances_past_a_silent_cluster():
    """The real-time cluster connects but streams nothing (gated); the client must
    advance to the delayed candidate and book its quotes."""
    streaming = FakeConn([
        json.dumps([{"ev": "status", "status": "auth_success"}]),
        json.dumps([{"ev": "Q", "sym": "O:SPY1", "bp": 1.0, "ap": 1.2, "t": 1}]),
    ])
    conns = [SilentConn([]), streaming]  # 1st candidate silent, 2nd streams
    book = LiveBook()
    ws = MassiveWebSocket(
        "KEY",
        ["O:SPY1"],
        book,
        urls=["wss://socket.massive.com/options", "wss://delayed.polygon.io/options"],
        connect=lambda: conns.pop(0),
        quote_grace=0.05,
    )

    async def drive():
        # One sweep: silent session returns False (advances idx), then the streaming
        # session books the quote. Stop the loop right after it locks on.
        await ws._session(ws._urls[0])  # silent -> no data
        assert book.size() == 0
        got = await ws._session(ws._urls[1])  # streaming cluster
        assert got is True and book.quote("O:SPY1").bid == 1.0

    asyncio.run(drive())


def test_sync_streaming_starts_and_stops_with_mode():
    """AppState.sync_streaming opens the stream for the active Massive source in
    realtime mode and tears it down when the mode/source no longer wants it."""
    from datetime import date

    from volfit.api.state import AppState
    from volfit.data.provider import SyntheticProvider

    class FakeStreaming(SyntheticProvider):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.started = None
            self.streaming = False

        def option_tickers(self, ticker, expiries):
            return [f"O:{ticker}1", f"O:{ticker}2"]

        def start_streaming(self, contracts):
            self.started = list(contracts)
            self.streaming = True

        def stop_streaming(self):
            self.streaming = False

        def is_streaming(self):
            return self.streaming

    ref = date(2026, 6, 15)
    prov = FakeStreaming(reference_date=ref, tickers=("ALPHA",))
    state = AppState(ref, providers={"massive": prov}, active_source="massive")

    state.sync_streaming()  # spotMode defaults to static -> no stream
    assert prov.streaming is False

    opts = state.options()
    state.set_options(opts.model_copy(update={"spotMode": "realtime"}))
    state.sync_streaming()  # realtime + active -> stream starts
    assert prov.streaming is True and prov.started == ["O:ALPHA1", "O:ALPHA2"]

    state.set_options(opts.model_copy(update={"spotMode": "static"}))
    state.sync_streaming()  # mode off -> stream stops (no leaked socket)
    assert prov.streaming is False


def test_sync_streaming_resubscribes_on_universe_change():
    """A universe change (ticker added/removed, expiry edit) while streaming
    restarts the WS on the new contract set; an unchanged universe does not."""
    from datetime import date

    from volfit.api.state import AppState
    from volfit.data.provider import SyntheticProvider

    class FakeStreaming(SyntheticProvider):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.subscribed: list[str] | None = None
            self.streaming = False
            self.starts = 0

        def option_tickers(self, ticker, expiries):
            return [f"O:{ticker}1", f"O:{ticker}2"]

        def start_streaming(self, contracts):
            self.subscribed = list(contracts)
            self.streaming = True
            self.starts += 1

        def stop_streaming(self):
            self.streaming = False
            self.subscribed = None

        def is_streaming(self):
            return self.streaming

        def streaming_contracts(self):
            return set(self.subscribed) if self.subscribed else set()

    ref = date(2026, 6, 15)
    prov = FakeStreaming(reference_date=ref, tickers=("ALPHA", "BETA"))
    state = AppState(ref, providers={"massive": prov}, active_source="massive")
    state.set_options(state.options().model_copy(update={"spotMode": "realtime"}))

    state.sync_streaming()  # initial start over ALPHA + BETA
    assert prov.streaming is True and prov.starts == 1
    assert set(prov.subscribed) == {"O:ALPHA1", "O:ALPHA2", "O:BETA1", "O:BETA2"}

    state.sync_streaming()  # unchanged universe -> no restart
    assert prov.starts == 1

    state.remove_ticker("BETA")  # universe shrank
    state.sync_streaming()  # -> resubscribe to ALPHA only
    assert prov.starts == 2
    assert set(prov.subscribed) == {"O:ALPHA1", "O:ALPHA2"}

"""The recorded book (volfit.data.massive_recorded): the API's Massive
provider serves its live chain from the tick recorder's store and opens NO
socket; honesty per ticker reads the recorder's stats; a stale heartbeat
turns the light red and un-serves every ticker; reads are cached per second.
All offline (a temp tick store, a fake HTTP layer, a socket class that
raises if ever built)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from volfit.data.massive import MassiveProvider
from volfit.data.massive_recorded import PREFIX, RecordedBook, StaticBook, resolve_book_source
from volfit.data.tick_store import TickStore, daily_path, ns_of

TODAY = date.today()
EXP = TODAY + timedelta(days=30)
SPOT = 500.0
STRIKES = (480, 490, 495, 500, 505, 510, 520)
TICK_TS = datetime(2026, 9, 18, 15, 45, 30)


def _contract(strike: int, cp: str) -> str:
    return f"O:SPY{EXP:%y%m%d}{cp}{int(strike):08d}"


def _listing() -> list[dict]:
    return [
        {"contract_type": "call" if cp == "C" else "put", "exercise_style": "american",
         "expiration_date": EXP.isoformat(), "strike_price": float(k), "ticker": _contract(k, cp),
         "underlying_ticker": "SPY"}
        for k in STRIKES for cp in ("C", "P")
    ]


class FakeHttp:
    def __call__(self, url: str, params: dict | None) -> dict:
        if "reference/options/contracts" in url:
            return {"results": _listing(), "status": "OK"}
        if "snapshot/options" in url:
            return {"results": [], "status": "OK"}
        raise AssertionError(url)


class NeverASocket:
    """The lock: in recorded mode the provider must never build a transport."""

    def __init__(self, *a, **kw):
        raise AssertionError("a MassiveWebSocket was built in recorded mode")


@pytest.fixture
def no_socket(monkeypatch):
    import volfit.data.massive_ws as ws_mod

    monkeypatch.setattr(ws_mod, "MassiveWebSocket", NeverASocket)


#: (bid, ask) per strike for calls / puts: a parity forward of 500.
PRICES = {495: (7.0, 2.0), 500: (4.0, 4.0), 505: (2.0, 7.0)}


def _write_store(path, heartbeat: float, acked_by_ticker: dict | None = None, quotes: bool = True) -> None:
    with TickStore(path) as ts:
        if quotes:
            ticks = []
            for k, (c, p) in PRICES.items():
                ticks.append((_contract(k, "C"), c, c + 0.2, ns_of(TICK_TS)))
                ticks.append((_contract(k, "P"), p, p + 0.2, ns_of(TICK_TS)))
            ts.fold(ticks, seen_at=heartbeat)
        ts.set_meta("pid", "4242")
        ts.set_meta("stats", {
            "connected": True, "acknowledged": 6, "subscribed": 6, "refused": 0, "lastQuoteAge": 2.0,
            "level": "amber", "detail": "streaming 6 · 3 msg/s · last 2 s",
            "ackedByTicker": {"SPY": 6} if acked_by_ticker is None else acked_by_ticker,
        })
        ts.heartbeat(now=heartbeat)


def _provider(book: RecordedBook, **kw) -> MassiveProvider:
    p = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(), book_source=book, stream_cap=6, **kw)
    p._note_spot("SPY", SPOT)
    return p


def _book(path, wall: float) -> RecordedBook:
    clock = {"t": 0.0}
    book = RecordedBook(path, clock=lambda: clock["t"], wall=lambda: wall)
    book._test_clock = clock  # type: ignore[attr-defined]
    return book


def test_recorded_mode_serves_the_chain_and_never_builds_a_socket(no_socket, tmp_path):
    path = tmp_path / "ticks.sqlite"
    _write_store(path, heartbeat=1000.0)
    p = _provider(_book(path, wall=1000.0))
    assert p.recorded_mode and not p.is_streaming()
    plan = p.option_tickers("SPY", [EXP])
    p.start_streaming(plan)  # NeverASocket would raise here on the socket path
    assert p._sockets == [] and p.is_streaming() and p.is_streaming_ticker("SPY")
    assert p.streaming_contracts() == set(plan)
    chain = p.live_chain("SPY", [EXP])
    assert chain is not None and chain.timestamp == TICK_TS and chain.spot == pytest.approx(500.0, abs=0.2)
    booked = {(q.strike, q.call_put): (q.bid, q.ask) for q in chain.quotes if q.bid is not None}
    assert booked[(495.0, "C")] == (7.0, 7.2) and booked[(505.0, "P")] == (7.0, 7.2) and len(booked) == 6
    assert p.fetch_chain("SPY", [EXP]).timestamp == TICK_TS  # the live fetch is the book read
    assert p.spot("SPY", [EXP]) == pytest.approx(500.0, abs=0.2)
    p.update_streaming(plan)  # a re-plan in recorded mode: still no socket
    assert p._sockets == []
    p.stop_streaming()
    assert p._live_book is None and not p.is_streaming() and p.streaming_contracts() == set()


def test_stream_stats_and_light_read_the_recorder(no_socket, tmp_path):
    from volfit.api.routers.datasource import StreamHealth

    path = tmp_path / "ticks.sqlite"
    _write_store(path, heartbeat=1000.0)
    p = _provider(_book(path, wall=1000.0), status_ttl_s=0.0)
    assert p.stream_stats() is None and p._stream_status() is None  # not attached yet
    p.start_streaming(p.option_tickers("SPY", [EXP]))
    stats = p.stream_stats()
    assert stats["source"] == "recorder" and stats["heartbeatAge"] == 0.0 and stats["running"] is True
    assert stats["acknowledged"] == 6 and stats["tickers"] == {"SPY": True} and stats["ackedByTicker"] == {"SPY": 6}
    assert stats["requested"] == 14 and stats["overCap"] == 8 and stats["cap"] == 6
    assert StreamHealth(**stats).detail == stats["detail"]  # the /datasources block validates
    level, detail = p._stream_status()
    assert level == "amber" and detail == "recorded book · 6 acked · last tick 2 s · 8 over cap · recorder alive"
    colour, text = p.feed_status()
    assert colour == "amber" and "delayed feed · recorded book · 6 acked" in text
    p.stop_streaming()


def test_a_stale_recorder_un_serves_and_reads_red(no_socket, tmp_path):
    path = tmp_path / "ticks.sqlite"
    _write_store(path, heartbeat=1000.0)
    wall = {"t": 1000.0}
    book = RecordedBook(path, clock=lambda: 0.0, wall=lambda: wall["t"])
    p = _provider(book)
    p.start_streaming(p.option_tickers("SPY", [EXP]))
    assert p.is_streaming_ticker("SPY")
    wall["t"] = 1042.0  # the recorder stopped writing 42 s ago
    book._read_at = None  # past the read cache
    assert not p.is_streaming() and not p.is_streaming_ticker("SPY")
    assert p._stream_status() == ("red", "recorder stale (42 s)")
    assert p.stream_stats()["running"] is False and p.stream_stats()["tickers"] == {"SPY": False}
    assert p.live_chain("SPY", [EXP]) is not None  # the last book still reads (the caller decides)
    p.stop_streaming()


def test_honesty_needs_the_recorder_acks_and_a_booked_quote(no_socket, tmp_path):
    unacked = tmp_path / "unacked.sqlite"
    _write_store(unacked, heartbeat=1000.0, acked_by_ticker={"SPY": 0})
    p = _provider(_book(unacked, wall=1000.0))
    p.start_streaming(p.option_tickers("SPY", [EXP]))
    assert p.is_streaming() and not p.is_streaming_ticker("SPY")  # nothing acknowledged on the recorder
    assert not p.is_streaming_ticker("QQQ")  # never planned
    p.stop_streaming()

    empty = tmp_path / "empty.sqlite"
    _write_store(empty, heartbeat=1000.0, quotes=False)  # acked per the stats, nothing booked
    q = _provider(_book(empty, wall=1000.0))
    q.start_streaming(q.option_tickers("SPY", [EXP]))
    assert not q.is_streaming_ticker("SPY") and q.live_chain("SPY", [EXP]) is None
    q.stop_streaming()


def test_reads_are_cached_for_a_second_and_a_directory_picks_the_day(no_socket, tmp_path, monkeypatch):
    path = daily_path(tmp_path)  # today's file in the directory
    _write_store(path, heartbeat=1000.0)
    calls = {"n": 0}
    real = TickStore.latest_book

    def counted(self):
        calls["n"] += 1
        return real(self)

    monkeypatch.setattr(TickStore, "latest_book", counted)
    clock = {"t": 0.0}
    book = RecordedBook(tmp_path, clock=lambda: clock["t"], wall=lambda: 1000.0)
    assert book.path() == path
    assert book.quote(_contract(500, "C")).bid == 4.0
    assert book.any_of([_contract(495, "P")]) and book.size() == 6 and book.newest_ts() == ns_of(TICK_TS)
    assert calls["n"] == 1  # one read burst
    clock["t"] = 1.5
    assert book.quote(_contract(500, "P")).ask == 4.2 and calls["n"] == 2
    assert book.pid() == 4242 and book.alive() and book.stats()["acknowledged"] == 6
    book.close()


def test_book_source_spellings_and_the_serve_env(tmp_path, no_socket):
    assert resolve_book_source(None) is None and resolve_book_source("") is None
    book = resolve_book_source(f"{PREFIX}{tmp_path}")
    assert isinstance(book, RecordedBook) and book._source == tmp_path
    assert resolve_book_source(book) is book
    with pytest.raises(ValueError):
        resolve_book_source("recorder:")
    p = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(), book_source=f"recorder:{tmp_path}")
    assert p.recorded_mode
    assert not p.is_streaming()  # no file yet: nothing served, nothing opened
    plain = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp())
    assert not plain.recorded_mode and plain._recorded is None


def test_state_sync_streaming_attaches_the_recorded_book(no_socket, tmp_path):
    """AppState's streaming sync sees a served ticker through the reader —
    the scheduler's streaming branch and the SSE work unchanged."""
    from volfit.api.state import AppState

    path = tmp_path / "ticks.sqlite"
    _write_store(path, heartbeat=1000.0)
    p = _provider(_book(path, wall=1000.0))
    state = AppState(TODAY, providers={"massive": p}, active_source="massive")
    state._available["SPY"] = [EXP]
    state._selected["SPY"] = [EXP]
    state.sync_streaming()
    assert p.is_streaming() and p._sockets == []
    assert state.streaming_tickers() == ["SPY"] and state.request_tickers() == []
    state.sync_streaming()  # idempotent
    assert p.streaming_contracts() == set(p.option_tickers("SPY", [EXP]))
    p.stop_streaming()


def test_static_book_is_a_frozen_read(tmp_path):
    book = StaticBook({_contract(500, "C"): (4.0, 4.2, ns_of(TICK_TS))})
    assert book.alive() and book.size() == 1 and book.quote(_contract(500, "C")).ask == 4.2
    assert book.stats() is None and book.newest_ts() == ns_of(TICK_TS)
    p = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp())
    p.use_recorded_book(book)
    assert p.recorded_mode
    p.start_streaming([])
    assert p.is_streaming() and p._live_book is book
    p.use_recorded_book(None)
    assert not p.recorded_mode and p._live_book is None

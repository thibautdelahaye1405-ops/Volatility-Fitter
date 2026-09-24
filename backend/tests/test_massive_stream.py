"""The Massive live book after the 2026-09-24 rework (volfit.data.massive_stream
+ massive_ws + massive_book): the windowed, capped, nearest-the-money plan; the
chunked, acknowledged subscription; a refused frame trimmed and re-sent; several
connections feeding one book; the book + REST merge; the stream-health model;
per-ticker honesty; the session-gated silence rule; a dead thread revived.

All offline: a fake HTTP layer for the listing / snapshot pages and fake
connections for the socket (no thread unless the test starts one; every
started stream is stopped)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from volfit.data.massive import MassiveProvider
from volfit.data.massive_book import LiveBook, StreamStats
from volfit.data.massive_stream import STREAM_REST_SECONDS
from volfit.data.strike_window import strike_bounds

TODAY = date.today()
SPOT = 500.0


def _exp(days: int) -> date:
    return TODAY + timedelta(days=days)


def _row(strike: float, days: int, cp: str = "call") -> dict:
    return {
        "contract_type": cp, "exercise_style": "american",
        "expiration_date": _exp(days).isoformat(), "strike_price": strike,
        "ticker": f"O:SPY{_exp(days):%y%m%d}{cp[0].upper()}{int(strike):08d}", "underlying_ticker": "SPY",
    }


def _ladder(days: int, strikes) -> list[dict]:
    return [_row(k, days, cp) for k in strikes for cp in ("call", "put")]


class FakeHttp:
    """Contracts listing + snapshot pages by path; records every call."""

    def __init__(self, listing: list[dict], snapshot: list[dict] | None = None):
        self.listing, self.snapshot = listing, snapshot or []
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url: str, params: dict | None) -> dict:
        self.calls.append((url, params))
        if "reference/options/contracts" in url:
            return {"results": self.listing, "status": "OK"}
        if "snapshot/options" in url:
            return {"results": self.snapshot, "status": "OK"}
        raise AssertionError(url)


def _snap(strike: float, days: int, cp: str, bid: float, ask: float) -> dict:
    return {
        "details": {"contract_type": cp, "expiration_date": _exp(days).isoformat(),
                    "strike_price": strike, "exercise_style": "american"},
        "last_quote": {"bid": bid, "ask": ask}, "day": {"close": 0.5 * (bid + ask)},
        "open_interest": 7, "underlying_asset": {"price": SPOT},
    }


def _provider(listing, snapshot=None, **kw) -> MassiveProvider:
    return MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(listing, snapshot), **kw)


# ------------------------------------------------------------------ the plan

def test_plan_is_windowed_ranked_nearest_the_money_and_needs_a_centre():
    """A 2-day rung keeps a narrow band, a 1-year rung the wide one; the plan
    is ordered by |ln K/S| / sqrt(T); no centre = no plan (never the whole
    ladder — the 2026-09-23 finding)."""
    strikes = [k for k in range(300, 701, 5)]
    listing = _ladder(2, strikes) + _ladder(365, strikes)
    p = _provider(listing)
    http = p._http_get
    assert p.option_tickers("SPY", [_exp(2), _exp(365)]) == []  # no spot anywhere
    assert any("snapshot/options" in u for u, _ in http.calls)  # ONE centring page was tried
    tried = len(http.calls)
    p.option_tickers("SPY", [_exp(2)])
    assert len(http.calls) == tried  # the failed probe is not retried within the minute

    p._note_spot("SPY", SPOT)
    plan = p.option_tickers("SPY", [_exp(2), _exp(365)])
    lo2, hi2 = strike_bounds(SPOT, _exp(2), TODAY)
    lo1, hi1 = strike_bounds(SPOT, _exp(365), TODAY)
    short = [c for c in plan if p._stream_index[c][1]["expiry"] == _exp(2)]
    long = [c for c in plan if p._stream_index[c][1]["expiry"] == _exp(365)]
    assert short and long and len(short) < len(long)
    assert all(lo2 <= p._stream_index[c][1]["strike"] <= hi2 for c in short)
    assert all(lo1 <= p._stream_index[c][1]["strike"] <= hi1 for c in long)
    ranks = [p._stream_index[c][2] for c in plan]
    assert ranks == sorted(ranks)
    assert p._stream_index[plan[0]][1]["strike"] == SPOT  # the ATM contract first
    assert p.streaming_contracts() == set()  # not streaming yet


def test_window_centre_holds_until_a_five_percent_move():
    """Hysteresis: the centre moves only after a > 5 % spot move — otherwise a
    spot wobbling across a strike boundary would re-plan every tick."""
    p = _provider(_ladder(30, range(400, 601, 5)))
    p._note_spot("SPY", 500.0)
    p.option_tickers("SPY", [_exp(30)])
    assert p._stream_center["SPY"] == 500.0
    p._note_spot("SPY", 510.0)  # +2 %: held
    p.option_tickers("SPY", [_exp(30)])
    assert p._stream_center["SPY"] == 500.0
    p._note_spot("SPY", 540.0)  # +8 %: re-centred
    p.option_tickers("SPY", [_exp(30)])
    assert p._stream_center["SPY"] == 540.0


def test_centre_probe_reads_one_nearest_expiry_page():
    """With no spot memory the plan takes ONE snapshot page of the nearest
    expiry (limit 250, that expiry only) and uses its underlying price."""
    p = _provider(_ladder(30, [495, 500, 505]), snapshot=[_snap(500, 30, "call", 4.0, 4.2)])
    plan = p.option_tickers("SPY", [_exp(30)])
    assert len(plan) == 6 and p._stream_center["SPY"] == SPOT
    pages = [(u, q) for u, q in p._http_get.calls if "snapshot/options" in u]
    assert len(pages) == 1 and pages[0][1]["expiration_date"] == _exp(30).isoformat()
    assert pages[0][1]["limit"] == 250 and "cursor" not in pages[0][0]


# ------------------------------------------------------------------- the cap

class _Ws:
    """A stand-in connection: records subscribe/unsubscribe, never a thread."""

    def __init__(self, api_key, contracts, book, **kw):
        self._c = list(contracts)
        self.kw = kw
        self.subs: list[list[str]] = []
        self.unsubs: list[list[str]] = []
        self.running = True
        self.stopped = False
        self._acked: set[str] = set()
        self._refused: list[str] = []

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
        self.stopped = True

    def is_running(self):
        return self.running

    @property
    def contracts(self):
        return list(self._c)

    @property
    def acked(self):
        return set(self._acked)

    @property
    def refused(self):
        return list(self._refused)

    def counts(self):
        return (len(self._c), len(self._acked), len(self._refused))

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


@pytest.fixture
def fake_ws(monkeypatch):
    import volfit.data.massive_ws as ws_mod

    monkeypatch.setattr(ws_mod, "MassiveWebSocket", _Ws)
    return _Ws


def test_cap_is_a_fair_share_across_tickers_each_by_its_own_rank(fake_ws):
    """Two tickers, a budget of 12: the live set is a FAIR SHARE — six of
    each ticker's plan, each a nearest-the-money prefix of its own rank (the
    allocation policy, 2026-09-24; no longer the 12 nearest across both,
    which starved the second name); the rest is remembered as over cap; the
    requested (pre-cap) set is what the scheduler diffs against."""
    p = MassiveProvider(["SPY", "QQQ"], api_key="k", http_get=FakeHttp([]), stream_cap=12)
    rows_spy = [dict(_row(k, 30), underlying_ticker="SPY") for k in range(480, 521, 5)]
    rows_qqq = [dict(_row(k, 30), ticker=f"O:QQQ{k}", underlying_ticker="QQQ") for k in range(380, 421, 5)]
    p._contracts_cache[("SPY", frozenset([_exp(30)]), TODAY)] = [
        {"ticker": r["ticker"], "expiry": _exp(30), "strike": r["strike_price"], "call_put": "C", "style": "american"} for r in rows_spy
    ]
    p._contracts_cache[("QQQ", frozenset([_exp(30)]), TODAY)] = [
        {"ticker": r["ticker"], "expiry": _exp(30), "strike": r["strike_price"], "call_put": "C", "style": "american"} for r in rows_qqq
    ]
    p._note_spot("SPY", 500.0)
    p._note_spot("QQQ", 400.0)
    plan = p.option_tickers("SPY", [_exp(30)]) + p.option_tickers("QQQ", [_exp(30)])
    assert len(plan) == 18
    p.start_streaming(plan)
    live = p._sockets[0].contracts
    assert len(live) == 12 and len(p._stream_dropped) == 6
    assert p.streaming_contracts() == set(plan)  # REQUESTED, pre-cap
    for ticker in ("SPY", "QQQ"):
        mine = [c for c in live if p._stream_index[c][0] == ticker]
        assert mine == p._ticker_plans[ticker][:6]  # six each, a rank prefix of its OWN plan
        gone = [c for c in p._stream_dropped if p._stream_index[c][0] == ticker]
        assert max(p._stream_index[c][2] for c in mine) <= min(p._stream_index[c][2] for c in gone)
    assert live[:2] == [p._ticker_plans["QQQ"][0], p._ticker_plans["SPY"][0]]  # priority order: the round-robin
    stats = p.stream_stats()
    assert stats["allocation"] == {"QQQ": {"requested": 9, "live": 6, "focus": 0}, "SPY": {"requested": 9, "live": 6, "focus": 0}}
    assert stats["focus"] == [] and stats["floor"] == 60 and stats["restSeconds"] == 60.0
    p.stop_streaming()
    assert p.streaming_contracts() == set() and p._live_book is None


def test_update_streaming_diffs_in_place_and_fills_where_there_is_room(fake_ws):
    p = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp([]), stream_cap=3)
    p.start_streaming(["O:A", "O:B", "O:C", "O:D"])  # unknown ranks: input order, capped at 3
    sock = p._sockets[0]
    assert sock.contracts == ["O:A", "O:B", "O:C"] and p._stream_dropped == {"O:D"}
    added, removed = p.update_streaming(["O:B", "O:C", "O:E"])
    assert removed == ["O:A"] and added == ["O:E"]
    assert sock.contracts == ["O:B", "O:C", "O:E"] and p._stream_dropped == set()
    assert p.update_streaming(["O:B", "O:C", "O:E"]) == ([], [])  # unchanged: no frame
    p.update_streaming([])
    assert not p.is_streaming()


def test_multi_connection_splits_the_capped_plan_and_shares_one_book(fake_ws):
    p = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp([]), stream_cap=2, stream_connections=2)
    p.start_streaming(["O:A", "O:B", "O:C", "O:D", "O:E"])
    assert [s.contracts for s in p._sockets] == [["O:A", "O:B"], ["O:C", "O:D"]]
    assert p._stream_dropped == {"O:E"}
    assert all(s.kw["stats"] is p._stats for s in p._sockets)
    assert {id(s.kw.get("name")) for s in p._sockets} and [s.kw["name"] for s in p._sockets] == ["ws1", "ws2"]
    p.update_streaming(["O:A", "O:C", "O:D", "O:E"])  # B gone -> room on ws1 for E
    assert [s.contracts for s in p._sockets] == [["O:A", "O:E"], ["O:C", "O:D"]]
    p.stop_streaming()


# ----------------------------------------------------------------- the merge

def _stream_provider(**kw) -> tuple[MassiveProvider, LiveBook]:
    listing = _ladder(30, [480, 490, 495, 500, 505, 510, 520])
    snapshot = [_snap(k, 30, cp, 4.0, 4.4) for k in (480, 490, 495, 500, 505, 510, 520) for cp in ("call", "put")]
    p = _provider(listing, snapshot, **kw)
    p._note_spot("SPY", SPOT)
    return p, LiveBook()


def test_chain_from_book_merges_the_ticking_belly_with_rest_wings(fake_ws):
    """A capped book: the belly ticks (fresh stamps), the wings come from the
    last REST snapshot with its older stamp, the chain is stamped at the newest
    tick and the spot is the parity forward of the BOOKED quotes."""
    p, _ = _stream_provider(stream_cap=6)
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    book = p._live_book
    live = p._sockets[0].contracts
    assert len(live) == 6 and {p._stream_index[c][1]["strike"] for c in live} == {495, 500, 505}
    # the first live fetch falls through to REST (nothing booked) and seeds the memory
    rest = p.fetch_chain("SPY", [_exp(30)])
    assert p._last_rest_chain["SPY"] is rest and len(rest.quotes) == 14
    old = rest.timestamp
    tick_ts = datetime(2030, 1, 1, 15, 0, tzinfo=timezone.utc)
    ns = int(tick_ts.timestamp() * 1e9)
    prices = {495: (7.0, 2.0), 500: (4.0, 4.0), 505: (2.0, 7.0)}  # forward 500
    for k, (c, pv) in prices.items():
        for cp, px in (("C", c), ("P", pv)):
            sym = next(x for x in live if p._stream_index[x][1]["strike"] == k and p._stream_index[x][1]["call_put"] == cp)
            book.apply([{"ev": "Q", "sym": sym, "bp": px, "ap": px + 0.2, "t": ns}])
    chain = p.live_chain("SPY", [_exp(30)])
    assert chain is not None and len(chain.quotes) == 14
    belly = [q for q in chain.quotes if q.strike in prices]
    wings = [q for q in chain.quotes if q.strike not in prices]
    assert all(q.timestamp == tick_ts.replace(tzinfo=None) for q in belly)
    assert all(q.timestamp == old and q.bid == 4.0 and q.ask == 4.4 and q.open_interest == 7 for q in wings)
    assert chain.timestamp == tick_ts.replace(tzinfo=None)
    assert chain.spot == pytest.approx(500.0, abs=0.2)
    # QUOTE SYNC: booked ticks carry the book's spot at read time (the chain's);
    # a flat 4.0 / 4.4 REST layer implies no parity forward, so its fillers carry
    # no spot of their own (read as synchronous — no correction over a wrong one).
    assert all(q.spot == chain.spot for q in belly)
    assert all(q.spot is None for q in wings)
    p.stop_streaming()


def test_chain_from_book_layers_carry_their_own_spots_on_one_basis(fake_ws):
    """QUOTE SYNC (2026-09-24): booked ticks carry the book's spot (the chain's),
    REST fillers the REST layer's parity forward of the SAME expiry — not
    Massive's underlying price (``rest.spot``), which sits a carry basis away
    from a front-expiry parity forward — so the quote synchronisation reads the
    true spot move between the layers (here 500 vs 499)."""
    strikes = (480, 490, 495, 500, 505, 510, 520)
    f_rest = 499.0
    snapshot = []
    for k in strikes:
        for cp in ("call", "put"):
            mid = (max(f_rest - k, 0.0) if cp == "call" else max(k - f_rest, 0.0)) + 2.0
            snapshot.append(_snap(k, 30, cp, mid - 0.2, mid + 0.2))  # parity at F = 499, D = 1
    p = _provider(_ladder(30, strikes), snapshot, stream_cap=6)
    p._note_spot("SPY", SPOT)
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    book, live = p._live_book, p._sockets[0].contracts
    rest = p.fetch_chain("SPY", [_exp(30)])  # seeds the REST memory
    assert rest.spot == SPOT  # the REST chain's own spot IS the underlying price (500)
    ns = int(datetime(2030, 1, 1, 15, 0, tzinfo=timezone.utc).timestamp() * 1e9)
    for k, (c, pv) in {495: (7.0, 2.0), 500: (4.0, 4.0), 505: (2.0, 7.0)}.items():  # parity F = 500
        for cp, px in (("C", c), ("P", pv)):
            sym = next(x for x in live if p._stream_index[x][1]["strike"] == k and p._stream_index[x][1]["call_put"] == cp)
            book.apply([{"ev": "Q", "sym": sym, "bp": px - 0.1, "ap": px + 0.1, "t": ns}])
    chain = p.live_chain("SPY", [_exp(30)])
    belly = [q for q in chain.quotes if q.strike in (495, 500, 505)]
    wings = [q for q in chain.quotes if q.strike not in (495, 500, 505)]
    assert chain.spot == pytest.approx(500.0, abs=1e-6)
    assert all(q.spot == chain.spot for q in belly)
    assert all(q.spot == pytest.approx(f_rest, abs=1e-6) for q in wings)  # same-basis REST spot
    p.stop_streaming()


def test_chain_from_book_without_a_tick_is_none_and_unquoted_beyond_the_memory(fake_ws):
    p, _ = _stream_provider(stream_cap=6)
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    assert p.live_chain("SPY", [_exp(30)]) is None  # nothing booked yet: the caller REST-fetches
    live = p._sockets[0].contracts
    for sym in live:
        px = 4.0 if p._stream_index[sym][1]["strike"] == 500 else (7.0 if p._stream_index[sym][1]["call_put"] == ("C" if p._stream_index[sym][1]["strike"] < 500 else "P") else 2.0)
        p._live_book.apply([{"ev": "Q", "sym": sym, "bp": px, "ap": px + 0.2, "t": 1}])
    chain = p.live_chain("SPY", [_exp(30)])  # no REST memory: wings unquoted
    assert chain is not None
    assert all(q.bid is None and q.ask is None for q in chain.quotes if q.strike not in (495, 500, 505))
    p.stop_streaming()


def test_refresh_stream_rest_pulls_one_windowed_snapshot_per_minute(fake_ws, monkeypatch):
    p, _ = _stream_provider(stream_cap=6)
    http = p._http_get
    assert p.refresh_stream_rest("SPY", [_exp(30)], block=True) is None  # not streaming: nothing
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    before = len(http.calls)
    chain = p.refresh_stream_rest("SPY", [_exp(30)], block=True)
    assert chain is not None and p._last_rest_chain["SPY"] is chain
    assert len(http.calls) == before + 1  # one snapshot stream (a single expiry)
    assert p.refresh_stream_rest("SPY", [_exp(30)], block=True) is None  # throttled
    import time

    import volfit.data.massive_stream as ms

    clock = {"t": time.monotonic() + STREAM_REST_SECONDS + 1.0}  # a minute later
    monkeypatch.setattr(ms.time, "monotonic", lambda: clock["t"])
    assert p.refresh_stream_rest("SPY", [_exp(30)], block=True) is not None  # due again
    p.stop_streaming()


# ---------------------------------------------------------------- honesty

def test_is_streaming_ticker_needs_acks_and_a_booked_quote(fake_ws):
    p, _ = _stream_provider(stream_cap=6)
    plan = p.option_tickers("SPY", [_exp(30)])
    p.start_streaming(plan)
    sock = p._sockets[0]
    assert p.is_streaming() and not p.is_streaming_ticker("SPY")  # wanted, not served
    sock._acked.update(sock.contracts[:2])
    assert not p.is_streaming_ticker("SPY")  # acked, nothing booked
    p._live_book.apply([{"ev": "Q", "sym": sock.contracts[0], "bp": 1.0, "ap": 1.2, "t": 1}])
    assert p.is_streaming_ticker("SPY")
    assert not p.is_streaming_ticker("QQQ")  # never planned
    sock.running = False
    assert not p.is_streaming_ticker("SPY")  # the thread died: not served
    p.stop_streaming()


def test_state_uses_per_ticker_honesty(fake_ws):
    """An unserved Massive ticker stays on the request path; a served one moves
    to the streaming branch (volfit.api.state_sources.is_streaming)."""
    from volfit.api.state import AppState

    p, _ = _stream_provider(stream_cap=6)
    state = AppState(TODAY, providers={"massive": p}, active_source="massive")
    state._available["SPY"] = [_exp(30)]
    state._selected["SPY"] = [_exp(30)]
    state.sync_streaming()
    assert p.is_streaming() and state.request_tickers() == ["SPY"] and state.streaming_tickers() == []
    sock = p._sockets[0]
    sock._acked.update(sock.contracts)
    p._live_book.apply([{"ev": "Q", "sym": sock.contracts[0], "bp": 1.0, "ap": 1.2, "t": 1}])
    assert state.streaming_tickers() == ["SPY"] and state.request_tickers() == []
    state.sync_streaming()  # unchanged plan: no re-plan frame
    assert sock.subs == [] and sock.unsubs == []
    p.stop_streaming()


def test_dead_thread_is_revived_in_place_and_counted(fake_ws, monkeypatch):
    p, _ = _stream_provider(stream_cap=6)
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    sock = p._sockets[0]
    book = p._live_book
    sock.running = False  # the thread died (not stopped)
    assert p.is_streaming()  # still WANTED: sync_streaming must not restart with an empty book
    assert sock.running and p._live_book is book and p._stats.reconnects == 1
    p.stop_streaming()


# ----------------------------------------------------------------- health

def test_stream_status_lines_and_colours(fake_ws):
    p, _ = _stream_provider(stream_cap=6, session_open=lambda: True)
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    sock, stats = p._sockets[0], p._stats
    assert p._stream_status() == ("amber", "stream connecting · 6 subscribed")
    stats.note_connected("wss://delayed.polygon.io/options")
    level, detail = p._stream_status()
    assert (level, detail) == ("amber", "stream warming · 6 subscribed, 0 acked · 8 over cap")
    sock._acked.update(sock.contracts)
    stats.note_message(3)
    level, detail = p._stream_status()
    assert level == "amber" and detail.startswith("streaming 6 · 0 msg/s · last 0 s · 8 over cap")
    stats.url = "wss://socket.massive.com/options"
    assert p._stream_status()[0] == "green"  # the real-time cluster delivering quotes
    sock._refused.append("O:X")
    stats.note_error("Subscription limit reached for feed. Please remove some subscriptions and try again. · 1 dropped")
    level, detail = p._stream_status()
    assert level == "red" and detail.startswith("stream refused: Subscription limit reached") and "14 requested / 6 cap" in detail
    sock._refused.clear()
    stats.note_auth_failed("auth failed: invalid key")
    assert p._stream_status() == ("red", "stream auth failed: invalid key")
    sock.running = False
    p._last_revive = 10 ** 12  # keep the revive from restarting it
    assert p._stream_status() == ("red", "stream dead · reconnecting (0)")
    p.stop_streaming()
    assert p._stream_status() is None


def test_stream_status_idle_outside_the_session_keys_on_the_last_message(fake_ws, monkeypatch):
    p, _ = _stream_provider(stream_cap=6, session_open=lambda: False)
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    sock, stats = p._sockets[0], p._stats
    clock = {"t": 1000.0}
    stats._clock = lambda: clock["t"]
    stats.note_connected("wss://delayed.polygon.io/options")
    sock._acked.update(sock.contracts)
    stats.note_message(0)
    assert p._stream_status()[1].startswith("streaming 6")
    clock["t"] += 120.0
    level, detail = p._stream_status()
    assert level == "amber" and detail.startswith("stream idle since ") and "closed session · 6 acked" in detail
    p.stop_streaming()


def test_feed_status_colour_follows_the_stream(fake_ws):
    p, _ = _stream_provider(stream_cap=6, status_ttl_s=0.0, session_open=lambda: True)
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    p._sockets[0]._refused.append("O:X")
    p._stats.note_error("Subscription limit reached for feed.")
    level, detail = p.feed_status()
    assert level == "red" and "delayed feed · stream refused" in detail
    p.stop_streaming()
    assert p.feed_status()[0] == "amber"


def test_stream_stats_is_a_plain_dict_for_the_api(fake_ws):
    p, _ = _stream_provider(stream_cap=6, session_open=lambda: False)
    assert p.stream_stats() is None
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    d = p.stream_stats()
    assert d["subscribed"] == 6 and d["requested"] == 14 and d["overCap"] == 8 and d["cap"] == 6
    assert d["acknowledged"] == 0 and d["refused"] == 0 and d["connections"] == 1
    assert d["cluster"] in ("realtime", "delayed") and d["sessionOpen"] is False
    assert d["tickers"] == {"SPY": False} and d["level"] == "amber" and d["detail"]
    assert d["allocation"] == {"SPY": {"requested": 14, "live": 6, "focus": 0}}
    assert d["focus"] == [] and d["floor"] == 60 and d["restSeconds"] == 60.0
    json.dumps(d)  # serialisable
    p.stop_streaming()


# ------------------------------------------------- focus, tier, cadence

def _two_rung_provider(**kw) -> MassiveProvider:
    """SPY with a 30-day and a 60-day rung of 7 strikes (14 contracts each)."""
    strikes = [480, 490, 495, 500, 505, 510, 520]
    listing = _ladder(30, strikes) + _ladder(60, strikes)
    p = _provider(listing, **kw)
    p._note_spot("SPY", SPOT)
    return p


def test_focus_puts_the_whole_rung_live_and_replans_only_on_a_change(fake_ws):
    """With a budget of 16 for 28 planned contracts the belly of BOTH rungs is
    live and each node reads "rest"; focusing the 60-day node puts its whole
    planned rung on the socket (the node reads "live", the other stays
    "rest"), the re-plan is in place (a diff, no restart); the same focus
    again is a no-op; an empty focus goes back to the fair share."""
    p = _two_rung_provider(stream_cap=16)
    near, far = _exp(30), _exp(60)
    plan = p.option_tickers("SPY", [near, far])
    assert len(plan) == 28
    p.start_streaming(plan)
    sock, book = p._sockets[0], p._live_book
    sock._acked.update(sock.contracts)
    book.apply([{"ev": "Q", "sym": sock.contracts[0], "bp": 1.0, "ap": 1.2, "t": 1}])
    assert len(sock.contracts) == 16 and p.stream_tier("SPY", near) == "rest" and p.stream_tier("SPY", far) == "rest"
    assert p.set_stream_focus({("spy", far.isoformat())}) is True
    assert p.set_stream_focus({("SPY", far.isoformat())}) is False  # unchanged: no re-plan
    added, removed = p.update_streaming(plan)  # same universe, new focus: an in-place diff
    assert p._sockets[0] is sock and p._live_book is book and added and removed and len(added) == len(removed)
    far_rung = [c for c in plan if p._stream_index[c][1]["expiry"] == far]
    assert set(far_rung) <= set(sock.contracts)
    assert p._allocation.live[:14] == far_rung  # the focus first, in rank order (the socket appends the diff)
    assert p.stream_tier("SPY", far) == "live" and p.stream_tier("SPY", near) == "rest"
    assert p.stream_stats()["focus"] == [f"SPY|{far.isoformat()}"]
    assert p.stream_stats()["allocation"]["SPY"] == {"requested": 28, "live": 16, "focus": 14}
    assert p.update_streaming(plan) == ([], [])  # steady: no frame
    assert p.set_stream_focus(set()) is True
    p.update_streaming(plan)
    assert p.stream_tier("SPY", far) == "rest"
    sock.running = False
    p._last_revive = 10 ** 12
    assert p.stream_tier("SPY", far) == "none"  # unserved: no tier at all
    p.stop_streaming()


def test_state_sync_replans_on_a_focus_change_without_a_universe_change(fake_ws):
    """AppState hands the focus to the provider every sync: a node coming on
    screen (the SSE's focus_open) re-plans the live set IN PLACE on the next
    tick, the tick after that is silent, and closing the SSE re-plans once
    more — never a restart, never a frame when nothing changed."""
    from volfit.api.state import AppState

    p = _two_rung_provider(stream_cap=16)
    near, far = _exp(30), _exp(60)
    state = AppState(TODAY, providers={"massive": p}, active_source="massive")
    state._available["SPY"] = [near, far]
    state._selected["SPY"] = [near, far]
    state.sync_streaming()
    sock = p._sockets[0]
    state.sync_streaming()
    assert sock.subs == [] and sock.unsubs == []  # steady
    node = state.focus_open("spy", far.isoformat())
    assert node == ("SPY", far.isoformat()) and state.stream_focus() == {node}
    state.sync_streaming()
    assert p._sockets[0] is sock and len(sock.subs) == 1 and len(sock.unsubs) == 1  # re-planned in place
    far_rung = {c for c in p._ticker_plans["SPY"] if p._stream_index[c][1]["expiry"] == far}
    assert far_rung <= set(sock.contracts)
    state.sync_streaming()
    assert len(sock.subs) == 1 and len(sock.unsubs) == 1  # nothing changed: no re-plan
    state.focus_close(node)
    state.sync_streaming()
    assert len(sock.subs) == 2 and len(sock.unsubs) == 2  # back to the fair share
    p.stop_streaming()


def test_rest_cadence_knob_and_floor_knob(fake_ws, monkeypatch):
    """``VOLFIT_MASSIVE_REST_SECONDS`` sets the REST memory's cadence (floored
    at 15 s; a bad value keeps 60), ``VOLFIT_MASSIVE_WS_FLOOR`` the per-ticker
    floor; the throttle in ``refresh_stream_rest`` follows the cadence."""
    import time

    from volfit.data.massive_stream import rest_seconds_setting

    assert rest_seconds_setting(None) == 60.0 and rest_seconds_setting(5) == 15.0 and rest_seconds_setting(90) == 90.0
    monkeypatch.setenv("VOLFIT_MASSIVE_REST_SECONDS", "20")
    monkeypatch.setenv("VOLFIT_MASSIVE_WS_FLOOR", "3")
    p, _ = _stream_provider(stream_cap=6)
    assert p.rest_seconds == 20.0 and p._floor == 3
    monkeypatch.setenv("VOLFIT_MASSIVE_REST_SECONDS", "junk")
    assert _stream_provider(stream_cap=6)[0].rest_seconds == 60.0
    p.start_streaming(p.option_tickers("SPY", [_exp(30)]))
    assert p.refresh_stream_rest("SPY", [_exp(30)], block=True) is not None
    assert p.refresh_stream_rest("SPY", [_exp(30)], block=True) is None  # throttled
    clock = {"t": time.monotonic() + 21.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["t"])
    assert p.refresh_stream_rest("SPY", [_exp(30)], block=True) is not None  # 20 s later: due
    assert p.stream_stats()["restSeconds"] == 20.0 and p.stream_stats()["floor"] == 3
    p.stop_streaming()

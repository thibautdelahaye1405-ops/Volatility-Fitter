"""The tick recorder (volfit.data.tick_recorder): the loop driven offline over
a real MassiveProvider with a fake listing and a fake connection — ticks
land in the tick store (changed only), the heartbeat / stats / plan meta are
written, a chain FRAME is saved into a VolStore under the as-of tag and the
app's store-first as-of serves it with zero provider calls; ``replay``
rebuilds the same chain from the ticks; the expiry rule; a clean stop
through the store; the status lines. No socket, no thread."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone

import pytest

from volfit.api.state import AppState, AsOfSelection
from volfit.data.expiry_time import latest_completed_session
from volfit.data.massive import MassiveProvider
from volfit.data.provider import SyntheticProvider
from volfit.data.store import ASOF_CACHE_TAG, VolStore
from volfit.data.tick_recorder import STOP_KEY, Recorder, frame_instant, select_expiries
from volfit.data.tick_recorder_cli import replay, status_lines, stop_recorder
from volfit.data.tick_store import TickStore, daily_path, ns_of

TODAY = date.today()
EXP = TODAY + timedelta(days=30)
SPOT = 500.0
STRIKES = (480, 490, 495, 500, 505, 510, 520)
#: A FINAL instant (the last completed session, mid-day UTC) so the as-of
#: layer consults the store — today's instant is served live, never cached.
DAY = latest_completed_session(datetime.now(timezone.utc).replace(tzinfo=None))
T_A = datetime.combine(DAY, time(15, 45, 30))
T_B = datetime.combine(DAY, time(15, 46, 10))
PRICES = {495: (7.0, 2.0), 500: (4.0, 4.0), 505: (2.0, 7.0)}  # a parity forward of 500


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
    def __init__(self):
        self.calls = 0

    def __call__(self, url: str, params: dict | None) -> dict:
        self.calls += 1
        if "reference/options/contracts" in url:
            return {"results": _listing(), "status": "OK"}
        if "snapshot/options" in url:
            return {"results": [], "status": "OK"}
        raise AssertionError(url)


class _Ws:
    """A stand-in connection: no thread; acknowledgements set by the test."""

    def __init__(self, api_key, contracts, book, **kw):
        self._c = list(contracts)
        self.running, self.stopped = True, False
        self._acked: set[str] = set()
        self._refused: list[str] = []

    def start(self):
        self.running = True

    def stop(self):
        self.running, self.stopped = False, True

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
        return new

    def unsubscribe(self, contracts):
        gone = [c for c in self._c if c in set(contracts)]
        self._c = [c for c in self._c if c not in set(contracts)]
        return gone


@pytest.fixture
def fake_ws(monkeypatch):
    import volfit.data.massive_ws as ws_mod

    monkeypatch.setattr(ws_mod, "MassiveWebSocket", _Ws)
    return _Ws


def _provider() -> MassiveProvider:
    p = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(), stream_cap=6)
    p._note_spot("SPY", SPOT)
    return p


def _apply(book, ts: datetime, bump: float = 0.0) -> None:
    ns = ns_of(ts)
    for k, (c, pv) in PRICES.items():
        book.apply([
            {"ev": "Q", "sym": _contract(k, "C"), "bp": c + bump, "ap": c + bump + 0.2, "t": ns},
            {"ev": "Q", "sym": _contract(k, "P"), "bp": pv + bump, "ap": pv + bump + 0.2, "t": ns},
        ])


class Counting(SyntheticProvider):
    """The app-side Massive stand-in for the as-of read: history-capable,
    counts its chain fetches (the store must answer with zero)."""

    def __init__(self):
        super().__init__(reference_date=TODAY, tickers=("SPY",))
        self.calls = 0

    def historical_modes(self):
        return {"live", "prev_close", "eod", "intraday"}

    def intraday_capable(self):
        return True

    def historical_quote_kind(self):
        return "quotes"

    def fetch_chain(self, ticker, expiries=None, as_of=None):
        self.calls += 1
        return super().fetch_chain(ticker, expiries, None)


def _quotes(chain):
    return sorted((q.expiry, q.strike, q.call_put, q.bid, q.ask) for q in chain.quotes)


# ------------------------------------------------------------ the rule

def test_select_expiries_rules():
    ladder = [date(2026, 10, 2), date(2026, 10, 9), date(2026, 10, 16), date(2026, 10, 21), date(2026, 11, 20)]
    assert select_expiries(ladder, "all") == ladder
    assert select_expiries(ladder, "monthly") == [date(2026, 10, 16), date(2026, 11, 20)]  # third Fridays
    assert select_expiries(ladder, "weekly") == [date(2026, 10, 2), date(2026, 10, 9), date(2026, 10, 16), date(2026, 11, 20)]
    assert select_expiries(ladder, "2026-10-21, 2026-12-18") == [date(2026, 10, 21)]  # ∩ listed
    assert frame_instant(datetime(2026, 9, 24, 15, 47, 31), 1) == datetime(2026, 9, 24, 15, 47)
    assert frame_instant(datetime(2026, 9, 24, 15, 47, 31), 5) == datetime(2026, 9, 24, 15, 45)


# ------------------------------------------------------------ the loop

def test_loop_records_ticks_health_and_frames_the_asof_layer_serves(fake_ws, tmp_path):
    ticks_dir, db = tmp_path / "ticks", tmp_path / "volfit.sqlite"
    prov = _provider()
    clock = {"t": 1000.0}
    rec = Recorder(prov, {"SPY": [EXP]}, ticks_dir, store_path=db, frame_minutes=1, interval=1.0,
                   rest_memory=False, clock=lambda: clock["t"])
    rec.start()
    assert prov.is_streaming() and rec.store is not None and rec.store.path == daily_path(ticks_dir)
    plan = rec.store.plan()
    assert plan["tickers"] == ["SPY"] and plan["expiries"] == {"SPY": [EXP.isoformat()]} and plan["requested"] == 14
    sock = prov._sockets[0]
    sock._acked.update(sock.contracts)

    # an empty book: the heartbeat and stats are still written, no frame
    out = rec.tick(clock["t"])
    assert out == {"ticks": 0, "frames": 0}
    assert rec.store.heartbeat_age_s(now=1000.0) == 0.0 and rec.store.get_meta("pid") is not None
    assert rec.store.stats()["ackedByTicker"] == {"SPY": 6} and rec.store.stats()["framesSaved"] == 0

    # ticks land; the frame is saved at the floored tick minute under the as-of tag
    _apply(prov._live_book, T_A)
    clock["t"] = 1061.0  # a frame minute later
    out = rec.tick(clock["t"])
    assert out == {"ticks": 6, "frames": 1} and rec.store.tick_count() == 6
    assert rec.store.latest_book()[_contract(500, "C")] == (4.0, 4.2, ns_of(T_A))
    with VolStore(db) as vs:
        rows = vs.conn.execute("SELECT ticker, ts, source, series_id, quote_kind, request_json FROM snapshots").fetchall()
    assert rows == [("SPY", T_A.replace(second=0).isoformat(), "massive", ASOF_CACHE_TAG, "quotes", f'["{EXP.isoformat()}"]')]

    # the same book a minute later: no new tick, no duplicate frame; the same ticks are not re-appended
    clock["t"] = 1122.0
    assert rec.tick(clock["t"]) == {"ticks": 0, "frames": 0}
    # new ticks in the next minute: a second frame
    _apply(prov._live_book, T_B, bump=0.1)
    clock["t"] = 1183.0
    assert rec.tick(clock["t"]) == {"ticks": 6, "frames": 1} and rec.frames_saved == 2
    assert rec.store.stats()["ticksWritten"] == 12

    # the app's store-first as-of serves the frame's instant with ZERO provider calls
    counting = Counting()
    state = AppState(TODAY, providers={"massive": counting}, active_source="massive", store_path=str(db))
    state._available["SPY"] = [EXP]
    state._selected["SPY"] = [EXP]
    state.set_as_of(AsOfSelection(mode="intraday", ts=T_A.replace(second=0)))
    chain = state.snapshot("SPY")
    assert counting.calls == 0 and chain.quote_kind == "quotes" and len(chain.quotes) == 6
    assert {(q.strike, q.call_put): (q.bid, q.ask) for q in chain.quotes}[(495.0, "C")] == (7.0, 7.2)
    assert chain.spot == pytest.approx(500.0, abs=0.2)

    rec.shutdown()
    assert not prov.is_streaming() and rec.store is None
    with TickStore(daily_path(ticks_dir)) as ts:
        assert ts.get_meta("stoppedAt") is not None and ts.tick_count() == 12


def test_replay_rebuilds_the_same_chain_from_the_ticks(fake_ws, tmp_path):
    ticks_dir, db, db2 = tmp_path / "ticks", tmp_path / "volfit.sqlite", tmp_path / "replay.sqlite"
    prov = _provider()
    rec = Recorder(prov, {"SPY": [EXP]}, ticks_dir, store_path=db, rest_memory=False, clock=lambda: 1000.0)
    rec.start()
    _apply(prov._live_book, T_A)
    rec.tick(1000.0)
    _apply(prov._live_book, T_B, bump=0.1)
    rec.tick(1061.0)
    rec.shutdown()
    with VolStore(db) as vs:
        frames = {vs.load_snapshot(sid).timestamp: vs.load_snapshot(sid) for _t, sid, _ts in vs.list_snapshots(["SPY"], include_series=True)}
    assert set(frames) == {T_A.replace(second=0), T_B.replace(second=0)}

    fresh = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp())  # no socket, no memory
    at = T_A + timedelta(seconds=20)  # between the two tick bursts
    chain = replay(daily_path(ticks_dir), "SPY", at, "all", store_path=db2, provider=fresh)
    assert chain.timestamp == at and _quotes(chain) == _quotes(frames[T_A.replace(second=0)])
    assert not fresh.is_streaming()
    with VolStore(db2) as vs:
        meta = vs.snapshot_meta_at("SPY", at, source="massive", include_series=True, exact=True)
        assert meta is not None and meta.series_id == ASOF_CACHE_TAG and meta.request == [EXP]
    later = replay(daily_path(ticks_dir), "SPY", T_B, "all", provider=fresh)  # the newer ticks
    assert _quotes(later) == _quotes(frames[T_B.replace(second=0)])
    with pytest.raises(SystemExit):
        replay(daily_path(ticks_dir), "SPY", T_A - timedelta(hours=1), "all", provider=fresh)  # nothing yet


def test_run_stops_cleanly_on_the_store_request_and_status_reads_the_meta(fake_ws, tmp_path, capsys):
    ticks_dir = tmp_path / "ticks"
    prov = _provider()
    rec = Recorder(prov, {"SPY": [EXP]}, ticks_dir, store_path=None, interval=0.0, clock=lambda: 1000.0)
    ticks_dir.mkdir()
    with TickStore(daily_path(ticks_dir)) as ts:
        ts.set_meta(STOP_KEY, "1")  # a stop posted before the run: cleared at start, the loop runs
    original = rec.tick

    def tick_then_stop(now=None):
        out = original(now)
        with TickStore(daily_path(ticks_dir)) as other:  # the launcher's request, from another handle
            other.set_meta(STOP_KEY, "1")
        return out

    rec.tick = tick_then_stop  # type: ignore[method-assign]
    rec.run()
    assert not prov.is_streaming() and rec.store is None
    lines = status_lines(daily_path(ticks_dir))
    assert lines[0].startswith("store") and "stopped" in lines[1] and "heartbeat" in lines[2]
    assert status_lines(tmp_path / "nope.sqlite") == [f"no tick store at {tmp_path / 'nope.sqlite'}"]
    # stop_recorder on an already-stopped store answers at once (stoppedAt is set)
    assert stop_recorder(daily_path(ticks_dir), grace_s=1.0)
    assert "stopped cleanly" in capsys.readouterr().out
    assert not stop_recorder(tmp_path / "nope.sqlite")


def test_frames_wait_for_a_booked_forward_and_survive_a_store_failure(fake_ws, tmp_path, monkeypatch):
    ticks_dir, db = tmp_path / "ticks", tmp_path / "volfit.sqlite"
    prov = _provider()
    rec = Recorder(prov, {"SPY": [EXP], "QQQ": []}, ticks_dir, store_path=db, rest_memory=False, clock=lambda: 1000.0)
    rec.start()
    prov._live_book.apply([{"ev": "Q", "sym": _contract(500, "C"), "bp": 4.0, "ap": 4.2, "t": ns_of(T_A)}])
    assert rec.tick(1000.0) == {"ticks": 1, "frames": 0}  # one leg: no parity forward, no frame
    _apply(prov._live_book, T_A)
    monkeypatch.setattr(VolStore, "save_snapshot", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert rec.tick(1061.0)["frames"] == 0 and rec.frames_saved == 0  # logged, the loop goes on
    rec.shutdown()

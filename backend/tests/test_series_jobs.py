"""SERIES ARC S2 — create, harvest and the job slot (+ the S2 routes).

Locks: create resolves the instants, fills the pinned ladder from the
universe selection, freezes the base settings and writes pending / skipped
frames (422-class errors on an unknown ticker, no instant, nothing
servable); a historical run harvests every frame AS OF its instant through
the provider's as-of path into series-owned rows the as-of picker never
lists; a failing instant is recorded on its frame and the run ends done;
pause mid-run checkpoints and resume continues at the next frame; cancel;
the queue (a second start waits, then runs); recover() flips a running
status to paused; a live series harvests due frames through the app's
refresh (data version bumped, the live chain refreshed); the routes.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.asof import asof_payload
from volfit.api.schemas_series import LaneSpec, SeriesClock, SeriesLadder, SeriesSpec
from volfit.api.series_create import SeriesSpecError, create_series, estimate
from volfit.api.series_jobs import SeriesJobs, series_jobs_of
from volfit.api.series_store import SeriesStore
from volfit.api.state import AppState
from volfit.data.provider import AsOf, SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 13)
NOW = datetime(2026, 6, 12, 18, 0)  # Friday 14:00 ET


class HistoryProvider(SyntheticProvider):
    """A synthetic source with intraday history: the chain AS OF ``ts`` is
    the synthetic chain stamped at ``ts``; ``fail_at`` instants raise; a
    ``gate`` event blocks each fetch until released (pause / cancel tests)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fail_at: set[datetime] = set()
        self.gate: threading.Event | None = None
        self.calls: list[datetime | None] = []

    def intraday_capable(self):
        return True

    def historical_modes(self):
        return {"live", "prev_close", "eod"}

    def fetch_chain(self, ticker, expiries=None, as_of: AsOf | None = None):
        if self.gate is not None:
            self.gate.wait(5.0)
        ts = as_of.ts if as_of is not None and as_of.mode == "intraday" else None
        self.calls.append(ts)
        if ts is not None and ts in self.fail_at:
            raise RuntimeError("feed gap")
        chain = super().fetch_chain(ticker, expiries)
        return dataclasses.replace(chain, timestamp=ts) if ts is not None else chain


def _state(db, cls=HistoryProvider, source="massive") -> AppState:
    prov = cls(reference_date=REF, tickers=("ALPHA",))
    state = AppState(REF, providers={source: prov}, active_source=source, store_path=str(db))
    return state


def _spec(**over) -> SeriesSpec:
    base = dict(name="alpha", ticker="ALPHA", mode="historical",
                clock=SeriesClock(step="15m", count=3),
                lanes=[LaneSpec(id="free", name="free")])
    base.update(over)
    return SeriesSpec(**base)


def _wait(jobs: SeriesJobs, timeout=10.0):
    jobs.join(timeout)
    deadline = time.time() + timeout
    while jobs.is_running() and time.time() < deadline:
        time.sleep(0.02)


def _doc(state, sid):
    with VolStore(state.store_path) as store:
        return SeriesStore(store).get(sid)


# ------------------------------------------------------------------ create

def test_create_resolves_instants_ladder_and_base(tmp_path):
    state = _state(tmp_path / "a.sqlite")
    est = estimate(state, _spec(), NOW)
    assert est.nFrames == 3 and est.servable == [True] * 3 and est.harvestSeconds == 42.0
    res = create_series(state, _spec(), NOW)
    doc = _doc(state, res.id)
    assert doc is not None and res.estimate == est
    assert [f.ts for f in doc.frames] == [(NOW - timedelta(minutes=15 * k)).isoformat()
                                          for k in (2, 1, 0)]
    assert all(f.status == "pending" for f in doc.frames)
    assert doc.spec.source == "massive" and doc.spec.ladder.policy == "pinned"
    assert doc.spec.ladder.expiries == [e.isoformat() for e in state.selected_expiries("ALPHA")]
    assert doc.baseFit == state.fit_settings() and doc.baseOptions == state.options()
    assert doc.progress.status == "draft" and doc.progress.framesTotal == 3
    assert [e["action"] for e in state._event_tail][-1] == "series_create"


def test_create_refuses_bad_specs(tmp_path):
    state = _state(tmp_path / "b.sqlite")
    with pytest.raises(SeriesSpecError, match="not in the universe"):
        create_series(state, _spec(ticker="ZZZ"), NOW)
    with pytest.raises(SeriesSpecError, match="import-store"):
        create_series(state, _spec(mode="import"), NOW)
    live_only = _state(tmp_path / "c.sqlite", cls=SyntheticProvider, source="cboe")
    with pytest.raises(SeriesSpecError, match="no instant can be served"):
        create_series(live_only, _spec(), NOW)
    # a mixed clock: the future instants are written as skipped frames
    future = _spec(clock=SeriesClock(step="15m", start=NOW - timedelta(minutes=15), count=3))
    doc = _doc(state, create_series(state, future, NOW).id)
    assert [f.status for f in doc.frames] == ["pending", "pending", "skipped"]
    assert doc.frames[2].error == "in the future"


# ----------------------------------------------------------------- harvest

def test_historical_run_harvests_every_frame_as_of_its_instant(tmp_path):
    state = _state(tmp_path / "h.sqlite")
    sid = create_series(state, _spec(ladder=SeriesLadder(maxExpiries=2)), NOW).id
    jobs = series_jobs_of(state)
    assert jobs.start(sid) == "started"
    assert jobs.start(sid) == "already"
    _wait(jobs)
    doc = _doc(state, sid)
    assert doc.progress.status == "done" and doc.progress.framesReady == 3
    assert doc.progress.current is None and doc.progress.error is None
    prov = state.provider
    assert prov.calls == [datetime.fromisoformat(f.ts) for f in doc.frames]
    with VolStore(state.store_path) as store:
        for f in doc.frames:
            assert f.status == "ready" and f.snapshotId is not None
            chain = store.load_snapshot(f.snapshotId)
            assert chain.timestamp.isoformat() == f.ts
            assert len(f.expiries) == 2 and len(chain.expiries()) == 2  # cropped to the ladder
            assert f.nQuotes == len(chain.quotes) and f.quoteKind == "quotes"
            assert store.conn.execute("SELECT series_id FROM snapshots WHERE id = ?",
                                      (f.snapshotId,)).fetchone()[0] == sid
        assert store.list_snapshots(["ALPHA"], source="massive") == []
    assert [d for d in asof_payload(state)["days"] if d["hasCaptures"]] == []
    assert jobs.status(sid).running is None and jobs.status(sid).progress.status == "done"
    # startedTs reads the store's local clock like harvestedTs / updatedTs
    # (it was UTC until 2026-09-11: every run read an hour long on a UTC+1 desk).
    started = datetime.fromisoformat(doc.progress.startedTs)
    harvested = datetime.fromisoformat(doc.frames[0].harvestedTs)
    updated = datetime.fromisoformat(doc.progress.updatedTs)
    assert abs((harvested - started).total_seconds()) < 120
    assert abs((updated - started).total_seconds()) < 120


def test_frame_budget_field_defaults_and_bounds():
    """SeriesSpec.frameBudgetSeconds: 300 s by default, None = unlimited,
    at least 5 s."""
    from pydantic import ValidationError

    assert _spec().frameBudgetSeconds == 300
    assert _spec(frameBudgetSeconds=None).frameBudgetSeconds is None
    with pytest.raises(ValidationError):
        _spec(frameBudgetSeconds=2)


def test_failed_frame_is_recorded_and_the_run_ends_done(tmp_path):
    state = _state(tmp_path / "f.sqlite")
    sid = create_series(state, _spec(), NOW).id
    state.provider.fail_at = {NOW - timedelta(minutes=15)}
    jobs = series_jobs_of(state)
    jobs.start(sid)
    _wait(jobs)
    doc = _doc(state, sid)
    assert [f.status for f in doc.frames] == ["ready", "failed", "ready"]
    assert doc.frames[1].error == "feed gap" and doc.frames[1].snapshotId is None
    assert doc.progress.status == "done" and doc.progress.framesReady == 2
    assert doc.progress.error == "feed gap"
    # a re-start retries the failed frame only
    state.provider.fail_at = set()
    state.provider.calls = []
    jobs.start(sid)
    _wait(jobs)
    doc = _doc(state, sid)
    assert state.provider.calls == [NOW - timedelta(minutes=15)]
    assert [f.status for f in doc.frames] == ["ready"] * 3 and doc.progress.error is None


def test_pause_resume_cancel_and_the_queue(tmp_path):
    state = _state(tmp_path / "p.sqlite")
    prov = state.provider
    sid = create_series(state, _spec(), NOW).id
    other = create_series(state, _spec(name="other"), NOW).id
    jobs = series_jobs_of(state)
    prov.gate = threading.Event()  # every fetch blocks until released
    assert jobs.start(sid) == "started"
    assert jobs.start(other) == "queued"
    assert _doc(state, other).progress.status == "queued"
    assert jobs.status(sid).running == sid and jobs.status(sid).queue == [other]
    time.sleep(0.2)
    assert _doc(state, sid).progress.status == "harvesting"
    assert jobs.pause(sid) is True
    prov.gate.set()  # the in-flight frame lands, the loop sees the pause
    _wait(jobs)
    doc = _doc(state, sid)
    assert doc.progress.status == "paused" and doc.progress.framesReady == 1
    assert [f.status for f in doc.frames] == ["ready", "pending", "pending"]
    # the queue advanced: the other series ran to completion
    _wait(jobs)
    assert _doc(state, other).progress.status == "done"
    # resume continues at the next frame
    prov.calls = []
    assert jobs.resume(sid) == "started"
    _wait(jobs)
    assert prov.calls == [NOW - timedelta(minutes=15), NOW]
    assert _doc(state, sid).progress.status == "done"
    # cancel a queued series
    third = create_series(state, _spec(name="third"), NOW).id
    prov.gate = threading.Event()
    jobs.start(sid)  # re-run (frames all ready: ends at once, but holds the slot briefly)
    jobs.start(third)
    jobs.cancel(third)
    prov.gate.set()
    _wait(jobs)
    assert _doc(state, third).progress.status in ("cancelled", "draft")
    # cancel the running series
    prov.gate = threading.Event()
    fourth = create_series(state, _spec(name="fourth"), NOW).id
    jobs.start(fourth)
    time.sleep(0.2)
    assert jobs.cancel(fourth) is True
    prov.gate.set()
    _wait(jobs)
    assert _doc(state, fourth).progress.status == "cancelled"
    assert jobs.start(fourth) == "started"  # a cancelled series can run again
    prov.gate.set()
    _wait(jobs)


def test_recover_pauses_a_series_left_running(tmp_path):
    state = _state(tmp_path / "r.sqlite")
    sid = create_series(state, _spec(), NOW).id
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        series.set_progress(sid, series.get(sid).progress.model_copy(update={"status": "harvesting"}))
    jobs = SeriesJobs(state)
    assert jobs.recover() == [sid]
    doc = _doc(state, sid)
    assert doc.progress.status == "paused" and doc.progress.current == "recovered after a restart"
    assert jobs.recover() == []
    assert jobs.start(sid) == "started"
    _wait(jobs)
    assert _doc(state, sid).progress.status == "done"


def test_live_series_harvests_due_frames_through_the_app_refresh(tmp_path):
    state = _state(tmp_path / "l.sqlite", cls=SyntheticProvider, source="cboe")
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)  # the runner's clock
    spec = _spec(mode="live", clock=SeriesClock(step="1m", start=now - timedelta(minutes=5),
                                                 count=5, sessionOnly=False))
    sid = create_series(state, spec).id
    before = state.data_version("ALPHA") if hasattr(state, "data_version") else None
    jobs = SeriesJobs(state)
    jobs.start(sid)
    _wait(jobs)
    doc = _doc(state, sid)
    assert doc.progress.status == "done" and doc.progress.framesReady == 5
    assert all(f.status == "ready" and f.snapshotId is not None for f in doc.frames)
    stamps = [datetime.fromisoformat(f.ts) for f in doc.frames]
    assert stamps == sorted(stamps)  # stamped when taken
    assert state.snapshot("ALPHA").quotes  # the live chain is warm (refreshed by the run)
    if before is not None:
        assert state.data_version("ALPHA") > before


def test_wait_until_honours_the_clock_and_interruptions(tmp_path):
    state = _state(tmp_path / "w.sqlite")
    ticks = iter([NOW, NOW, NOW + timedelta(seconds=2)])
    jobs = SeriesJobs(state, now=lambda: next(ticks))
    assert jobs._wait_until("x", NOW + timedelta(seconds=1)) is None  # became due on the third tick
    jobs._cancel.add("x")
    assert jobs._wait_until("x", NOW + timedelta(hours=1)) == "cancelled"


# ------------------------------------------------------------------ routes

def _app(db):
    prov = HistoryProvider(reference_date=REF, tickers=("ALPHA",))
    return create_app(reference_date=REF, providers={"massive": prov}, active_source="massive",
                      store_path=str(db))


def test_series_routes_estimate_create_start_status(tmp_path):
    with TestClient(_app(tmp_path / "app.sqlite")) as c:
        spec = {"name": "alpha", "ticker": "alpha", "mode": "historical",
                "clock": {"step": "15m", "start": "2026-06-12T13:30:00-04:00", "count": 2},
                "lanes": [{"id": "free", "name": "free"}]}
        est = c.post("/series/estimate", json=spec)
        assert est.status_code == 200, est.text
        assert est.json()["nFrames"] == 2 and est.json()["servable"] == [True, True]
        assert est.json()["instants"] == ["2026-06-12T17:30:00", "2026-06-12T17:45:00"]
        bad = c.post("/series/estimate", json={**spec, "ticker": "ZZZ"})
        assert bad.status_code == 422 and "universe" in bad.json()["detail"]

        r = c.post("/series", json=spec)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        assert r.json()["estimate"]["nFrames"] == 2
        assert c.get(f"/series/{sid}/status").json()["progress"]["status"] == "draft"
        st = c.post(f"/series/{sid}/start")
        assert st.status_code == 200 and st.json()["seriesId"] == sid
        jobs = c.app.state.volfit.series_jobs
        _wait(jobs)
        status = c.get(f"/series/{sid}/status").json()
        assert status["running"] is None and status["progress"]["status"] == "done"
        doc = c.get(f"/series/{sid}").json()
        assert [f["status"] for f in doc["frames"]] == ["ready", "ready"]
        assert c.post(f"/series/{sid}/pause").status_code == 200  # idle: a no-op
        assert c.post("/series/nope/start").status_code == 404
        assert c.get("/series/nope/status").status_code == 404
        # delete stops and removes
        assert c.delete(f"/series/{sid}").json()["deleted"] is True
        actions = [e["action"] for e in c.app.state.volfit._event_tail]
        assert "series_create" in actions and "series_start" in actions

"""SERIES ARC S3 — lane calibration on detached states (roadmap §3.3).

The three locks of D11 plus the mechanics: (1) a FREE lane's fits are
byte-identical to the desk's per-ticker Calibrate on the same chain under
the same settings; (2) a PRIOR lane's frame-1 fit equals a manual roll
(calibrate frame 0, capture the snapshot, activate it, calibrate frame 1);
(3) a FILTER lane reproduces ``backtest.filter_replay`` on the same store
(the ring, step by step). Then: the carry doc round-trips and a pause →
resume run stores exactly the fits of an uninterrupted run; an LV lane
stores the surface row and carries an LV prior; the pull columns read
against the free reference; failed frames are skipped; the metrics shape.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta

import numpy as np

from volfit.api import priors, workflow
from volfit.api.schemas_series import LaneSpec, SeriesLadder
from volfit.api.series_import import ImportSource, SeriesImportRequest, import_series
from volfit.api.series_jobs import SeriesJobs
from volfit.api.series_lanes import (
    LaneCarry,
    SeriesChains,
    alive_expiries,
    calibrate_frame,
    lane_options,
    lane_state,
    run_lanes,
)
from volfit.api.series_store import SeriesStore
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 13)
T0 = datetime(2026, 6, 12, 17, 30)  # Friday 13:30 ET


def _chain(minutes: int = 0):
    chain = SyntheticProvider(reference_date=REF, tickers=("ALPHA",)).fetch_chain("ALPHA")
    return dataclasses.replace(chain, timestamp=T0 + timedelta(minutes=minutes))


def _campaign(path, minutes=(0, 15, 30)) -> str:
    with VolStore(path) as vs:
        for m in minutes:
            vs.save_snapshot(_chain(m))
    return str(path)


def _state(db) -> AppState:
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return AppState(REF, providers={"cboe": prov}, active_source="cboe", store_path=str(db))


def _series(state, campaign, lanes, ladder=None, name="s"):
    return import_series(state, SeriesImportRequest(
        name=name, ticker="ALPHA", source=ImportSource(kind="store", path=campaign),
        lanes=lanes, ladder=ladder or SeriesLadder(maxExpiries=2),
    ))


class _Opened:
    """A SeriesStore over a store kept open for the test's lifetime."""

    def __init__(self, state):
        self._store = VolStore(state.store_path)
        self.series = SeriesStore(self._store)

    def __getattr__(self, name):
        return getattr(self.series, name)


def _run(state, sid):
    jobs = SeriesJobs(state)
    assert jobs.start(sid) == "started"
    jobs.join(120)
    series = _Opened(state)
    return series.get(sid), series


def _params(fit):
    p = fit.params
    return (p["L"], p["R"], tuple(p["a"]), p["alphaL"], p["alphaR"])


FREE = LaneSpec(id="free", name="free", patchOptions={"priorPersistenceMode": "off",
                                                       "observationFilterMode": "off"})
PRIOR = LaneSpec(id="prior", name="prior", patchOptions={"priorPersistenceMode": "hybrid",
                                                          "observationFilterMode": "off"})


# ------------------------------------------------------- lock 1: free lane

def test_free_lane_is_byte_identical_to_the_live_calibrate(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0, 15))
    state = _state(tmp_path / "app.sqlite")
    doc = _series(state, campaign, [FREE]).model_copy()
    doc, series = _run(state, doc.id)
    assert doc.progress.status == "done"
    assert doc.progress.fitsTotal == doc.progress.fitsDone == 4  # 2 frames × 2 expiries
    for frame in doc.frames:
        chain = series.frame_chain(doc.id, frame.idx)
        # the desk's Calibrate on a state holding exactly this chain, these settings
        live = AppState(chain.timestamp.date(), providers={"x": SeriesChains({"ALPHA": chain})},
                        active_source="x")
        live.set_fit_settings(doc.baseFit)
        live.set_options(lane_options(doc, FREE))  # the same options the lane ran under
        live.set_expiries("ALPHA", [date.fromisoformat(e) for e in frame.expiries])
        workflow.calibrate_ticker(live, "ALPHA", "mid")
        stored = {f.expiry: f for f in series.fits(doc.id, idx=frame.idx, lane_id="free")}
        assert set(stored) == set(frame.expiries)
        for iso, fit in stored.items():
            ptr = live.get_calibrated_ptr("ALPHA", iso, "mid")
            rec = live.get_fit(ptr[0])
            p = rec.result.params
            assert fit.params["L"] == float(p.L) and fit.params["R"] == float(p.R)
            assert np.array_equal(np.asarray(fit.params["a"]), np.asarray(p.a, dtype=float))
            assert fit.diagnostics["cost"] == float(rec.result.cost)
            assert fit.status == "done" and fit.model == "lqd" and fit.fitMs is not None
            assert fit.metrics["rmsBp"] >= 0.0 and fit.metrics["nQuotes"] == rec.prepared.k.size
            assert "pullAtmBp" not in fit.metrics  # the free lane has no reference but itself


# ------------------------------------------------------ lock 2: prior lane

def test_prior_lane_equals_a_manual_roll(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0, 15))
    state = _state(tmp_path / "app.sqlite")
    doc = _series(state, campaign, [FREE, PRIOR])
    doc, series = _run(state, doc.id)
    assert doc.progress.status == "done"
    c0, c1 = series.frame_chain(doc.id, 0), series.frame_chain(doc.id, 1)
    frames = doc.frames

    def _live(chain, frame, prior=None):
        st = lane_state(doc, PRIOR, frame, chain, LaneCarry(prior=prior))
        workflow.calibrate_ticker(st, "ALPHA", "mid")
        return st

    s0 = _live(c0, frames[0])
    snap = priors.capture_snapshot(s0, "ALPHA", "mid", lv=False)
    assert snap is not None and len(snap.nodes) == 2
    s1 = _live(c1, frames[1], prior=snap)
    lane1 = {f.expiry: f for f in series.fits(doc.id, idx=1, lane_id="prior")}
    free1 = {f.expiry: f for f in series.fits(doc.id, idx=1, lane_id="free")}
    for iso, fit in lane1.items():
        rec = s1.get_fit(s1.get_calibrated_ptr("ALPHA", iso, "mid")[0])
        assert np.array_equal(np.asarray(fit.params["a"]), np.asarray(rec.result.params.a, dtype=float))
        assert fit.metrics["pullAtmBp"] == round((fit.metrics["atmVol"] - free1[iso].metrics["atmVol"]) * 1e4, 2)
        assert "pullSkew" in fit.metrics
    # the carry doc holds the frame-1 snapshot (prior for a frame 2) and round-trips
    carry = LaneCarry.from_doc(series.lane_filter(doc.id, "prior"))
    assert carry.last_idx == 1 and carry.prior is not None and len(carry.prior.nodes) == 2
    assert LaneCarry.from_doc(carry.to_doc()).to_doc() == carry.to_doc()
    assert series.lane_filter(doc.id, "free")["prior"] is None  # a free lane carries nothing


# ----------------------------------------------------- lock 3: filter lane

def test_filter_lane_reproduces_the_offline_filter_replay(tmp_path):
    from backtest.filter_replay import replay_day

    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0, 15, 30))
    state = _state(tmp_path / "app.sqlite")
    lane = LaneSpec(id="filt", name="filter", patchOptions={
        "observationFilterMode": "overlay", "priorPersistenceMode": "off",
        "intradayClock": True, "enforceCalendar": False,
    })
    doc = _series(state, campaign, [lane], ladder=SeriesLadder(maxExpiries=1))
    doc, series = _run(state, doc.id)
    assert doc.progress.status == "done"
    iso = doc.frames[0].expiries[0]
    carry = LaneCarry.from_doc(series.lane_filter(doc.id, "filt"))
    ring = carry.filter_history[("ALPHA", iso, "mid")]
    lane_steps = [dict(s) for s in
                  __import__("volfit.api.filter_history", fromlist=["history_docs"])
                  .history_docs({("ALPHA", iso, "mid"): ring})[0]["steps"]]
    with VolStore(campaign) as store:
        instants = sorted(ts for _t, _s, ts in store.list_snapshots(["ALPHA"]))
        part = replay_day(store, "ALPHA", instants[0].date(), instants, max_expiries=1)
    assert part["nodes"][iso] == lane_steps
    assert len(lane_steps) == 3 and lane_steps[0]["resetReason"] is not None
    # the per-frame metrics carry the filter's step
    fits = series.fits(doc.id, lane_id="filt")
    assert [f.metrics.get("filterReset") is not None for f in fits] == [True, False, False]
    assert all("zeta" in f.metrics and "gain" in f.metrics for f in fits)
    assert [f.metrics.get("filterProvenance") for f in fits][1:] == ["update", "update"]


# ------------------------------------------------------- pause and resume

def test_pause_then_resume_stores_the_uninterrupted_fits(tmp_path, monkeypatch):
    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0, 15, 30))
    straight = _state(tmp_path / "a.sqlite")
    ref_doc, ref_series = _run(straight, _series(straight, campaign, [FREE, PRIOR]).id)
    ref = {(f.laneId, f.idx, f.expiry): _params(f) for f in ref_series.fits(ref_doc.id)}
    assert len(ref) == 12  # 3 frames × 2 lanes × 2 expiries

    state = _state(tmp_path / "b.sqlite")
    sid = _series(state, campaign, [FREE, PRIOR]).id
    jobs = SeriesJobs(state)
    import volfit.api.series_lanes as lanes_mod
    real = lanes_mod.calibrate_frame
    calls = {"n": 0}

    def pausing(*a, **kw):
        out = real(*a, **kw)
        calls["n"] += 1
        if calls["n"] == 3:  # after frame 0 (both lanes) and frame 1 (free): pause
            jobs.pause(sid)
        return out

    monkeypatch.setattr(lanes_mod, "calibrate_frame", pausing)
    jobs.start(sid)
    jobs.join(120)
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(sid)
        assert doc.progress.status == "paused"
        assert series.count_fits(sid) == 6  # frame 0 ×2 lanes + frame 1 free
        assert LaneCarry.from_doc(series.lane_filter(sid, "prior")).last_idx == 0
    monkeypatch.setattr(lanes_mod, "calibrate_frame", real)
    assert jobs.resume(sid) == "started"
    jobs.join(120)
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(sid)
        assert doc.progress.status == "done" and doc.progress.fitsDone == 12
        got = {(f.laneId, f.idx, f.expiry): _params(f) for f in series.fits(sid)}
    assert got == ref  # the carry doc gave the resumed prior lane its exact chain state


# ---------------------------------------------------------------- LV lane

def test_lv_lane_stores_the_surface_row_and_carries_an_lv_prior(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0, 15))
    state = _state(tmp_path / "app.sqlite")
    lv = LaneSpec(id="lv", name="lv", family="lv", patchOptions={"priorPersistenceMode": "hybrid"})
    doc = _series(state, campaign, [lv], ladder=SeriesLadder(maxExpiries=3))
    doc, series = _run(state, doc.id)
    assert doc.progress.status == "done", doc.progress.error
    fits = series.fits(doc.id, idx=0, lane_id="lv")
    surface = [f for f in fits if f.expiry is None]
    assert len(surface) == 1 and surface[0].model == "affine" and surface[0].status == "done"
    p = surface[0].params
    assert len(p["theta"]) == len(p["tNodes"]) and len(p["theta"][0]) == len(p["xNodes"])
    assert surface[0].metrics["rmsBp"] >= 0.0 and "arbitrageFree" in surface[0].metrics
    assert len([f for f in fits if f.expiry]) == 3  # the slices ride along
    carry = LaneCarry.from_doc(series.lane_filter(doc.id, "lv"))
    assert carry.prior is not None and carry.prior.lvSurface is not None
    assert doc.progress.fitsTotal == 2 * (3 + 1)


# ------------------------------------------------------------- mechanics

def test_failed_frames_are_skipped_and_expected_counts_exclude_them(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0, 15))
    state = _state(tmp_path / "app.sqlite")
    doc = _series(state, campaign, [FREE])
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        f1 = doc.frames[1].model_copy(update={"status": "failed", "error": "gap", "snapshotId": None})
        series.put_frame(doc.id, f1)
    jobs = SeriesJobs(state)
    jobs.calibrate_hook = run_lanes
    jobs.start(doc.id)
    jobs.join(120)
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        got = series.get(doc.id)
        # the runner retried the failed frame (import chains have no source: stays failed)
        assert [f.status for f in got.frames][0] == "ready"
        assert all(f.idx == 0 for f in series.fits(doc.id))


def test_calibrate_frame_reference_and_metrics_shape(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0,))
    state = _state(tmp_path / "app.sqlite")
    doc = _series(state, campaign, [FREE, PRIOR])
    with VolStore(state.store_path) as store:
        chain = SeriesStore(store).frame_chain(doc.id, 0)
    free_fits, free_carry = calibrate_frame(doc, FREE, doc.frames[0], chain, LaneCarry())
    assert free_carry.prior is None and free_carry.filter_states == {}
    ref = {f.expiry: f for f in free_fits}
    prior_fits, prior_carry = calibrate_frame(doc, PRIOR, doc.frames[0], chain, LaneCarry(), ref)
    assert prior_carry.prior is not None and prior_carry.last_idx == 0
    for f in prior_fits:
        assert f.metrics["pullAtmBp"] == 0.0 and f.metrics["pullSkew"] == 0.0  # cold frame = free
        for key in ("rmsBp", "maxIvBp", "nQuotes", "atmVol", "skew", "leeLeft", "leeRight"):
            assert key in f.metrics
        for key in ("t", "forward", "discount", "varSwapVol", "cost", "kMin", "kMax"):
            assert key in f.diagnostics


def test_alive_expiries_at_the_instant():
    chain = _chain(0)  # 2026-06-12 17:30 UTC
    isos = ["2026-06-12", "2026-06-19", "2026-07-17"]
    # calendar clock: the same-day rung is degenerate and dropped
    assert alive_expiries(chain, isos, intraday=False) == [date(2026, 6, 19), date(2026, 7, 17)]
    # intraday clock without settlement records: alive through its day
    assert alive_expiries(chain, isos, intraday=True)[0] == date(2026, 6, 12)
    # with a settlement record the rung dies at its settlement instant
    from volfit.data.expiry_time import settlement_map
    stamped = dataclasses.replace(chain, settlement=settlement_map([date(2026, 6, 12)]))
    assert date(2026, 6, 12) in alive_expiries(stamped, isos, intraday=True)  # settles 20:00 UTC
    late = dataclasses.replace(stamped, timestamp=datetime(2026, 6, 12, 20, 0))
    assert date(2026, 6, 12) not in alive_expiries(late, isos, intraday=True)


def test_a_dying_calendar_repair_keeps_the_phase_a_fits(tmp_path, monkeypatch):
    import volfit.api.surface_symmetric as sym

    def boom(*a, **kw):
        raise RuntimeError("repair died")

    monkeypatch.setattr(sym, "phase_b_repair", boom)
    campaign = _campaign(tmp_path / "c.sqlite", minutes=(0,))
    state = _state(tmp_path / "app.sqlite")
    lv = LaneSpec(id="lv", name="lv", family="lv")
    doc = _series(state, campaign, [FREE, lv])
    with VolStore(state.store_path) as store:
        chain = SeriesStore(store).frame_chain(doc.id, 0)
    fits, _carry = calibrate_frame(doc, FREE, doc.frames[0], chain, LaneCarry())
    assert [f.status for f in fits] == ["done", "done"]  # phase A committed before the repair
    assert all(f.metrics["calendarRepair"] == "RuntimeError: repair died" for f in fits)
    lv_fits, _c = calibrate_frame(doc, lv, doc.frames[0], chain, LaneCarry())
    surface = [f for f in lv_fits if f.expiry is None]
    assert surface[0].status == "failed" and "repair died" in surface[0].error


def test_creation_warns_about_the_active_filter_under_calendar_coupling(tmp_path):
    from volfit.api.series_create import lane_warnings
    from volfit.api.schemas_series import SeriesClock, SeriesSpec

    state = _state(tmp_path / "app.sqlite")
    active = LaneSpec(id="a", name="+ filter", patchOptions={"observationFilterMode": "active"})
    spec = SeriesSpec(name="x", ticker="ALPHA", clock=SeriesClock(step="15m", count=3),
                      lanes=[FREE, active])
    warn = lane_warnings(state, spec)
    assert len(warn) == 1 and "+ filter" in warn[0] and "active filter" in warn[0]
    daily = spec.model_copy(update={"clock": SeriesClock(step="daily", count=3)})
    assert lane_warnings(state, daily) == []
    # calendar coupling off does not lift it: the MAP block itself is the finding
    relaxed = active.model_copy(update={"patchOptions": {"observationFilterMode": "active",
                                                          "enforceCalendar": False}})
    assert len(lane_warnings(state, spec.model_copy(update={"lanes": [relaxed]}))) == 1
    overlay = active.model_copy(update={"patchOptions": {"observationFilterMode": "overlay"}})
    assert lane_warnings(state, spec.model_copy(update={"lanes": [overlay]})) == []

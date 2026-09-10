"""SERIES ARC S7 — the determinism certification locks.

A series is REPLAYABLE lineage: (1) two fresh runs of the same series spec
over the same campaign store produce byte-identical fits (params, cost,
metrics) for every (lane, frame, expiry), free and prior lanes alike; (2) a
stored series whose fits are dropped (``SeriesStore.reset_fits``) and re-run
reproduces them, carries included; (3) the certification registry names the
case and its locks exist.
"""

from __future__ import annotations

import dataclasses
import os
from datetime import date, datetime, timedelta

from volfit.api.schemas_series import LaneSpec, SeriesLadder
from volfit.api.series_import import ImportSource, SeriesImportRequest, import_series
from volfit.api.series_jobs import SeriesJobs
from volfit.api.series_store import SeriesStore
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 13)
T0 = datetime(2026, 6, 12, 17, 30)
FREE = LaneSpec(id="free", name="free", patchOptions={"priorPersistenceMode": "off"})
PRIOR = LaneSpec(id="prior", name="prior", patchOptions={"priorPersistenceMode": "hybrid"})
FILT = LaneSpec(id="filt", name="filter", patchOptions={
    "priorPersistenceMode": "off", "observationFilterMode": "overlay", "enforceCalendar": False,
})


def _chain(minutes: int = 0):
    chain = SyntheticProvider(reference_date=REF, tickers=("ALPHA",)).fetch_chain("ALPHA")
    return dataclasses.replace(chain, timestamp=T0 + timedelta(minutes=minutes))


def _campaign(path, minutes=(0, 15, 30)) -> str:
    with VolStore(path) as vs:
        for m in minutes:
            vs.save_snapshot(_chain(m))
    return str(path)


def _run(db, campaign, lanes):
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    state = AppState(REF, providers={"cboe": prov}, active_source="cboe", store_path=str(db))
    doc = import_series(state, SeriesImportRequest(
        name="s", ticker="ALPHA", source=ImportSource(kind="store", path=campaign),
        lanes=lanes, ladder=SeriesLadder(maxExpiries=2),
    ))
    jobs = SeriesJobs(state)
    assert jobs.start(doc.id) == "started"
    jobs.join(180)
    return state, doc.id


def _fits(state, sid):
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(sid)
        assert doc is not None and doc.progress.status == "done", doc.progress
        rows = {}
        for f in series.fits(sid):
            rows[(f.laneId, f.idx, f.expiry)] = (
                f.params, f.diagnostics.get("cost"), f.metrics.get("rmsBp"),
                f.metrics.get("atmVol"), f.status,
            )
        carries = {lane.id: series.lane_filter(sid, lane.id) for lane in doc.spec.lanes}
        return rows, carries


def test_two_fresh_runs_are_byte_identical(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite")
    a_state, a_id = _run(tmp_path / "a.sqlite", campaign, [FREE, PRIOR, FILT])
    b_state, b_id = _run(tmp_path / "b.sqlite", campaign, [FREE, PRIOR, FILT])
    a_rows, a_carries = _fits(a_state, a_id)
    b_rows, b_carries = _fits(b_state, b_id)
    assert len(a_rows) == 3 * 3 * 2 and set(a_rows) == set(b_rows)
    for key in a_rows:
        assert a_rows[key] == b_rows[key], key
    # the carried prior surfaces agree node by node; the rings step by step
    for lane in ("prior", "filt"):
        ca, cb = a_carries[lane], b_carries[lane]
        assert (ca.get("prior") or {}).get("nodes") == (cb.get("prior") or {}).get("nodes")
        assert ca.get("filterHistory") == cb.get("filterHistory")


def test_a_stored_series_rerun_reproduces_its_fits(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite")
    state, sid = _run(tmp_path / "a.sqlite", campaign, [FREE, PRIOR])
    before, carries_before = _fits(state, sid)
    with VolStore(state.store_path) as store:
        dropped = SeriesStore(store).reset_fits(sid)
        assert dropped == 2 * 3 * 2
        assert SeriesStore(store).count_fits(sid) == 0
        assert SeriesStore(store).lane_filter(sid, "prior") is None
        assert SeriesStore(store).get(sid).progress.status == "draft"
    jobs = SeriesJobs(state)
    assert jobs.start(sid) == "started"
    jobs.join(180)
    after, carries_after = _fits(state, sid)
    assert after == before
    assert (carries_after["prior"].get("prior") or {}).get("nodes") == (
        (carries_before["prior"].get("prior") or {}).get("nodes"))


def test_certification_registry_names_the_case():
    from backtest.certification import CASES

    case = next(c for c in CASES if c.key == "series_replay_determinism")
    assert case.dimension == "model_stress"
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for lock in case.locks:
        assert os.path.exists(os.path.join(here, lock.split("::")[0])), lock

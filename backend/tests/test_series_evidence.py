"""SERIES ARC S5 — the Lanes stage's evidence + the lane filter rings.

Locks: the evidence is derived from the strip (means, the worst frame, the
handle-path roughness = mean |Δ| between consecutive frames — checked by
hand against the strip —, the pull means, the fit time, the ζ spread); a
free lane has no pull; the strip carries skew and curvature; a filter
lane's ring index lists its expiries and the ring's steps are the live
wire dicts (the first step a seed), a free lane has an empty index; the
routes (200 / 404 series / 404 lane).
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.schemas_series import LaneSpec, SeriesLadder
from volfit.api.series_evidence import evidence_payload, lane_filter_index, lane_filter_ring
from volfit.api.series_import import ImportSource, SeriesImportRequest, import_series
from volfit.api.series_jobs import SeriesJobs
from volfit.api.series_payload import STRIP_METRICS, strip_payload
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 13)
T0 = datetime(2026, 6, 12, 17, 30)


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


FREE = LaneSpec(id="free", name="free", patchOptions={"priorPersistenceMode": "off"})
PRIOR = LaneSpec(id="prior", name="prior", patchOptions={"priorPersistenceMode": "hybrid"})
FILT = LaneSpec(id="filt", name="filter", patchOptions={
    "priorPersistenceMode": "off", "observationFilterMode": "overlay", "enforceCalendar": False,
})


def _calibrated(tmp_path, lanes, minutes=(0, 15, 30)):
    campaign = _campaign(tmp_path / "c.sqlite", minutes)
    state = _state(tmp_path / "app.sqlite")
    doc = import_series(state, SeriesImportRequest(
        name="s", ticker="ALPHA", source=ImportSource(kind="store", path=campaign),
        lanes=lanes, ladder=SeriesLadder(maxExpiries=2),
    ))
    jobs = SeriesJobs(state)
    assert jobs.start(doc.id) == "started"
    jobs.join(120)
    return state, doc


def test_evidence_matches_the_strip_by_hand(tmp_path):
    state, doc = _calibrated(tmp_path, [FREE, PRIOR])
    strip = strip_payload(state, doc.id)
    assert set(strip.lanes["free"]) == set(STRIP_METRICS)
    assert all(v is not None for v in strip.lanes["free"]["skew"])
    assert all(v is not None for v in strip.lanes["free"]["curvature"])
    ev = evidence_payload(state, doc.id)
    assert ev.seriesId == doc.id and ev.expiry == doc.frames[0].expiries[0]
    assert set(ev.lanes) == {"free", "prior"}
    free = ev.lanes["free"]
    assert free.nFrames == 3 and free.nFailed == 0
    rms = strip.lanes["free"]["rmsBp"]
    assert free.meanRmsBp == round(float(np.mean(rms)), 4)
    worst_i = int(np.argmax(rms))
    assert free.worstFrame is not None and free.worstFrame.idx == strip.idx[worst_i]
    assert free.worstFrame.rmsBp == rms[worst_i] and free.worstFrame.ts == strip.ts[worst_i]
    atm = strip.atmVol["free"]
    rough = np.mean([abs(b - a) * 1e4 for a, b in zip(atm, atm[1:])])
    assert free.roughnessAtmBp == round(float(rough), 4)
    skew = strip.lanes["free"]["skew"]
    assert free.roughnessSkew == round(float(np.mean([abs(b - a) for a, b in zip(skew, skew[1:])])), 4)
    assert free.meanPullAtmBp is None and free.meanAbsPullAtmBp is None  # the reference
    assert free.meanFitMs is not None and free.meanFitMs > 0
    assert free.zetaAtmStd is None  # no filter on this lane
    prior = ev.lanes["prior"]
    assert prior.meanAbsPullAtmBp is not None and prior.meanAbsPullAtmBp >= 0.0
    assert prior.meanPullAtmBp == round(float(np.mean(strip.lanes["prior"]["pullAtmBp"])), 4)
    only = evidence_payload(state, doc.id, ["prior"], expiry=doc.frames[0].expiries[1])
    assert set(only.lanes) == {"prior"} and only.expiry == doc.frames[0].expiries[1]


def test_filter_rings_index_and_steps(tmp_path):
    state, doc = _calibrated(tmp_path, [FREE, FILT])
    assert lane_filter_index(state, doc.id, "free").expiries == []
    index = lane_filter_index(state, doc.id, "filt")
    assert index.laneId == "filt" and index.expiries == doc.frames[0].expiries
    ring = lane_filter_ring(state, doc.id, "filt", index.expiries[0])
    assert ring.expiry == index.expiries[0] and len(ring.steps) == 3
    first, last = ring.steps[0], ring.steps[-1]
    assert first["resetReason"] is not None and last["provenance"] == "update"
    assert {"ts", "dtDays", "prediction", "posterior", "gain"} <= set(last)
    # a step's ts is the app's local-clock epoch of the naive snapshot stamp
    stamps = [datetime.fromtimestamp(s["ts"]) for s in ring.steps]
    assert stamps == [datetime.fromisoformat(f.ts) for f in doc.frames]
    assert ring.frameIdx == [f.idx for f in doc.frames]  # matched by order, never by clock
    assert lane_filter_ring(state, doc.id, "filt", "2099-01-01").steps == []
    ev = evidence_payload(state, doc.id, ["filt"])
    assert ev.lanes["filt"].zetaAtmStd is not None


def test_evidence_and_filter_routes(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite")
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    app = create_app(reference_date=REF, providers={"cboe": prov}, active_source="cboe",
                     store_path=str(tmp_path / "app.sqlite"))
    with TestClient(app) as c:
        doc = c.post("/series/import-store", json={
            "name": "alpha", "ticker": "ALPHA",
            "source": {"kind": "store", "path": campaign},
            "lanes": [FREE.model_dump(), FILT.model_dump()],
            "ladder": {"policy": "pinned", "expiries": [], "maxExpiries": 1},
        }).json()
        sid = doc["id"]
        c.post(f"/series/{sid}/start")
        c.app.state.volfit.series_jobs.join(120)
        ev = c.get(f"/series/{sid}/evidence", params={"lanes": "free,filt"})
        assert ev.status_code == 200, ev.text
        assert set(ev.json()["lanes"]) == {"free", "filt"}
        assert ev.json()["lanes"]["free"]["nFrames"] == 3
        assert c.get("/series/nope/evidence").status_code == 404
        idx = c.get(f"/series/{sid}/lanes/filt/filter").json()
        assert idx["expiries"] == doc["frames"][0]["expiries"]
        ring = c.get(f"/series/{sid}/lanes/filt/filter/{idx['expiries'][0]}").json()
        assert len(ring["steps"]) == 3 and ring["frameIdx"] == [0, 1, 2]
        assert c.get(f"/series/{sid}/lanes/nope/filter").status_code == 404
        assert c.get("/series/nope/lanes/filt/filter").status_code == 404

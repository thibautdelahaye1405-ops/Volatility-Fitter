"""SERIES ARC S4 — the frame / strip payloads and the presets route.

Locks: a frame payload carries the market per expiry (quote bands with
strikes and the fit-target edges), every requested lane's curves sampled
from the STORED params (finite, dense, the k range of the model curve),
the σ(k, τ) grid, the term points and the lane metrics; a lane filter;
the LV lane's surface metrics; the memo returns the same object until a
fit lands; a pending frame yields an empty market; the strip has one
value per ready frame per lane per metric and picks the shown expiry;
the routes (200 / 404) and the presets route (eight lanes, before the id
routes).
"""

from __future__ import annotations

import dataclasses
import math
from datetime import date, datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.schemas_series import LaneSpec, SeriesLadder
from volfit.api.series_import import ImportSource, SeriesImportRequest, import_series
from volfit.api.series_jobs import SeriesJobs
from volfit.api.series_payload import STRIP_METRICS, frame_payload, strip_payload
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 13)
T0 = datetime(2026, 6, 12, 17, 30)


def _chain(minutes: int = 0):
    chain = SyntheticProvider(reference_date=REF, tickers=("ALPHA",)).fetch_chain("ALPHA")
    return dataclasses.replace(chain, timestamp=T0 + timedelta(minutes=minutes))


def _campaign(path, minutes=(0, 15)) -> str:
    with VolStore(path) as vs:
        for m in minutes:
            vs.save_snapshot(_chain(m))
    return str(path)


def _state(db) -> AppState:
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return AppState(REF, providers={"cboe": prov}, active_source="cboe", store_path=str(db))


FREE = LaneSpec(id="free", name="free", patchOptions={"priorPersistenceMode": "off"})
PRIOR = LaneSpec(id="prior", name="prior", patchOptions={"priorPersistenceMode": "hybrid"})
LV = LaneSpec(id="lv", name="lv", family="lv")


def _calibrated(tmp_path, lanes, minutes=(0, 15), max_expiries=2):
    campaign = _campaign(tmp_path / "c.sqlite", minutes)
    state = _state(tmp_path / "app.sqlite")
    doc = import_series(state, SeriesImportRequest(
        name="s", ticker="ALPHA", source=ImportSource(kind="store", path=campaign),
        lanes=lanes, ladder=SeriesLadder(maxExpiries=max_expiries),
    ))
    jobs = SeriesJobs(state)
    assert jobs.start(doc.id) == "started"
    jobs.join(120)
    return state, doc


# ------------------------------------------------------------------ frame

def test_frame_payload_market_lanes_surface_term(tmp_path):
    state, doc = _calibrated(tmp_path, [FREE, PRIOR])
    p = frame_payload(state, doc.id, 1)
    assert p.seriesId == doc.id and p.idx == 1 and p.ts == doc.frames[1].ts
    assert p.quoteKind == "quotes" and p.spot == doc.frames[1].spot
    assert p.expiries == doc.frames[1].expiries and set(p.market) == set(p.expiries)
    m = p.market[p.expiries[0]]
    assert m["forward"] > 0 and m["tau"] > 0 and m["t"] > 0 and m["spot"] == p.spot
    q = m["quotes"]
    assert len(q) > 5 and all(qq["strike"] > 0 for qq in q)
    assert all(math.isclose(qq["k"], math.log(qq["strike"] / m["forward"]), rel_tol=1e-9) for qq in q)
    assert all(qq["bid"] <= qq["mid"] <= qq["ask"] for qq in q)
    assert q[0]["targetLo"] is None  # fit mode mid: no band edges
    assert p.forwards[p.expiries[0]] == m["forward"]
    assert set(p.lanes) == {"free", "prior"}
    free = p.lanes["free"]
    assert free.status == "done" and [s.expiry for s in free.slices] == p.expiries
    s0 = free.slices[0]
    assert len(s0.k) == len(s0.iv) > 100 and all(np.isfinite(s0.iv)) and min(s0.k) <= -1.4
    assert s0.atmVol is not None and s0.metrics["rmsBp"] >= 0.0
    assert free.surface is not None
    assert free.surface.expiries == p.expiries and len(free.surface.sigma) == 2
    assert len(free.surface.sigma[0]) == len(free.surface.k) == 61
    assert all(np.isfinite(np.asarray(free.surface.sigma)).ravel())
    assert [t["expiry"] for t in free.term] == p.expiries and free.term[0]["atmVol"] is not None
    assert free.metrics["nSlices"] == 2 and free.metrics["rmsBp"] is not None
    prior = p.lanes["prior"]
    assert "pullAtmBp" in prior.slices[0].metrics
    only = frame_payload(state, doc.id, 1, ["prior"])
    assert set(only.lanes) == {"prior"} and only.market == p.market


def test_frame_payload_memo_and_pending_frame(tmp_path):
    state, doc = _calibrated(tmp_path, [FREE], minutes=(0,))
    a = frame_payload(state, doc.id, 0)
    b = frame_payload(state, doc.id, 0)
    assert a is b  # the memo
    with VolStore(state.store_path) as store:
        from volfit.api.schemas_series import FrameDoc
        from volfit.api.series_store import SeriesStore
        SeriesStore(store).put_frame(doc.id, FrameDoc(idx=7, ts="2026-06-12T18:00:00"))
    pending = frame_payload(state, doc.id, 7)
    assert pending.market == {} and pending.lanes == {} and pending.spot is None


def test_lv_lane_carries_the_surface_metrics(tmp_path):
    state, doc = _calibrated(tmp_path, [LV], minutes=(0,), max_expiries=3)
    p = frame_payload(state, doc.id, 0)
    lv = p.lanes["lv"]
    assert lv.metrics["surface"]["status"] == "done" and "rmsBp" in lv.metrics["surface"]
    assert len(lv.slices) == 3 and lv.surface is not None and len(lv.surface.sigma) == 3


# ------------------------------------------------------------------ strip

def test_strip_payload_one_value_per_frame_per_lane(tmp_path):
    state, doc = _calibrated(tmp_path, [FREE, PRIOR], minutes=(0, 15, 30))
    s = strip_payload(state, doc.id)
    assert s.idx == [0, 1, 2] and s.ts == [f.ts for f in doc.frames]
    assert s.spot == [f.spot for f in doc.frames]
    assert set(s.atmVol) == {"free", "prior"} and len(s.atmVol["free"]) == 3
    assert all(v is not None and v > 0 for v in s.atmVol["free"])
    for lane in ("free", "prior"):
        assert set(s.lanes[lane]) == set(STRIP_METRICS)
        assert all(len(v) == 3 for v in s.lanes[lane].values())
        assert all(v is not None for v in s.lanes[lane]["rmsBp"])
    assert all(v is None for v in s.lanes["free"]["pullAtmBp"])  # the reference lane
    assert all(v is not None for v in s.lanes["prior"]["pullAtmBp"])
    second = doc.frames[0].expiries[1]
    shown = strip_payload(state, doc.id, ["free"], expiry=second)
    assert set(shown.atmVol) == {"free"} and shown.atmVol["free"] != s.atmVol["free"]


# ----------------------------------------------------------------- routes

def _app(db):
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return create_app(reference_date=REF, providers={"cboe": prov}, active_source="cboe",
                      store_path=str(db))


def test_frame_strip_and_presets_routes(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite")
    with TestClient(_app(tmp_path / "app.sqlite")) as c:
        presets = c.get("/series/presets")
        assert presets.status_code == 200 and len(presets.json()) == 8
        assert [p["id"] for p in presets.json()][:3] == ["lqd_free", "lqd_prior", "lqd_prior_filter"]
        assert presets.json()[0]["patchFit"]["nOrder"] == c.get("/settings/fit").json()["nOrder"]
        doc = c.post("/series/import-store", json={
            "name": "alpha", "ticker": "ALPHA",
            "source": {"kind": "store", "path": campaign},
            "presets": ["lqd_free"], "ladder": {"policy": "pinned", "expiries": [], "maxExpiries": 2},
        }).json()
        sid = doc["id"]
        c.post(f"/series/{sid}/start")
        c.app.state.volfit.series_jobs.join(120)
        r = c.get(f"/series/{sid}/frame/0", params={"lanes": "lqd_free"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body["lanes"]) == {"lqd_free"} and len(body["market"]) == 2
        assert c.get(f"/series/{sid}/frame/9").status_code == 404
        assert c.get("/series/nope/frame/0").status_code == 404
        strip = c.get(f"/series/{sid}/strip", params={"expiry": body["expiries"][0]}).json()
        assert strip["idx"] == [0, 1] and len(strip["atmVol"]["lqd_free"]) == 2
        assert c.get("/series/nope/strip").status_code == 404

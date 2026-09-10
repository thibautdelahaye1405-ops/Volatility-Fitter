"""SERIES ARC S6 — series files + Adopt as prior.

Locks: export → delete → import round-trips byte-identically on everything
the store keeps (the spec and base settings, the frame index, every
chain's quotes, every fit, the carries) under the SAME id; an import of an
id already present is a no-op returning the existing document; envelope
errors are 422-class; Adopt as prior turns one lane's fits at one frame
into the ticker's ACTIVE prior (save = activate: the anchoring axis reports
the + Prior cell as production on the live smile), carries the LV surface
of an LV lane, logs the event, and refuses a lane / frame with no fit; the
routes.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.schemas_series import LaneSpec, SeriesLadder
from volfit.api.series_adopt import AdoptError, AdoptPriorRequest, adopt_prior
from volfit.api.series_files import SeriesFormatError, export_series, import_series_file
from volfit.api.series_import import ImportSource, SeriesImportRequest, import_series
from volfit.api.series_jobs import SeriesJobs
from volfit.api.series_store import SeriesStore
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


def _snapshot(state, series_id):
    """Everything the store keeps of a series, as comparable JSON."""
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(series_id)
        chains = {f.idx: store.load_snapshot(f.snapshotId) for f in doc.frames if f.snapshotId}
        return {
            "doc": doc.model_copy(update={"frames": [f.model_copy(update={"snapshotId": None})
                                                    for f in doc.frames]}).model_dump(mode="json"),
            "chains": {i: (c.spot, c.timestamp.isoformat(), c.exercise_style, c.tick_size,
                           [(q.expiry, q.strike, q.call_put, q.bid, q.ask) for q in c.quotes])
                       for i, c in chains.items()},
            "fits": [f.model_dump(mode="json") for f in series.fits(series_id)],
            "carries": {lane.id: series.lane_filter(series_id, lane.id) for lane in doc.spec.lanes},
        }


# ---------------------------------------------------------------- files

def test_export_delete_import_round_trips_byte_identically(tmp_path):
    state, doc = _calibrated(tmp_path, [FREE, PRIOR])
    before = _snapshot(state, doc.id)
    bundle = export_series(state, doc.id)
    assert bundle["schema"] == "volfit-series/1" and bundle["series"]["id"] == doc.id
    assert len(bundle["chains"]) == 2 and len(bundle["fits"]) == 8  # 2 frames × 2 lanes × 2 expiries
    assert set(bundle["carries"]) == {"free", "prior"}
    with VolStore(state.store_path) as store:
        assert SeriesStore(store).delete(doc.id)
        assert store.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
    again = import_series_file(state, bundle)
    assert again.id == doc.id and again.spec == doc.spec
    assert [f.status for f in again.frames] == ["ready", "ready"]
    assert _snapshot(state, doc.id) == before
    # idempotent: a second import returns the stored document, adds nothing
    twice = import_series_file(state, bundle)
    assert twice == again
    with VolStore(state.store_path) as store:
        assert store.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2
        assert store.list_snapshots(["ALPHA"]) == []  # owned frames, never captures


def test_import_refuses_bad_envelopes(tmp_path):
    state = _state(tmp_path / "app.sqlite")
    for bad, msg in (([], "not a JSON object"), ({}, "schema"),
                     ({"schema": "volfit-snapshot/1"}, "not a series file"),
                     ({"schema": "volfit-series/2"}, "unsupported"),
                     ({"schema": "volfit-series/1"}, "no series document"),
                     ({"schema": "volfit-series/1", "series": {"id": "x"}}, "malformed")):
        with pytest.raises(SeriesFormatError, match=msg):
            import_series_file(state, bad)


# ---------------------------------------------------------------- adopt

def test_adopt_prior_activates_the_lane_frame_as_the_live_prior(tmp_path):
    state, doc = _calibrated(tmp_path, [FREE, LV], max_expiries=3)
    assert state.active_prior("ALPHA") is None
    with pytest.raises(AdoptError, match="not a ready frame"):
        adopt_prior(state, doc.id, AdoptPriorRequest(idx=9))
    with pytest.raises(AdoptError, match="unknown lane"):
        adopt_prior(state, doc.id, AdoptPriorRequest(laneId="nope", idx=0))
    res = adopt_prior(state, doc.id, AdoptPriorRequest(idx=1))  # the production lane
    assert res.laneId == "free" and res.idx == 1 and res.nodes == 3 and not res.lvSurface
    assert res.persisted is True and res.dataTs == doc.frames[1].ts
    snap = state.active_prior("ALPHA")
    assert snap is not None and [n.expiry for n in snap.nodes] == doc.frames[1].expiries
    with VolStore(state.store_path) as store:
        fit = [f for f in SeriesStore(store).fits(doc.id, idx=1, lane_id="free") if f.expiry][0]
    node = next(n for n in snap.nodes if n.expiry == fit.expiry)
    assert set(fit.params["a"]) <= set(node.lqd)  # the frame's backbone coefficients, verbatim
    assert [e["action"] for e in state._event_tail][-1] == "series_adopt_prior"
    lv = adopt_prior(state, doc.id, AdoptPriorRequest(laneId="lv", idx=0))
    assert lv.lvSurface is True and state.active_prior("ALPHA").lvSurface is not None


def test_series_file_and_adopt_routes(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite")
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    app = create_app(reference_date=REF, providers={"cboe": prov}, active_source="cboe",
                     store_path=str(tmp_path / "app.sqlite"))
    with TestClient(app) as c:
        doc = c.post("/series/import-store", json={
            "name": "alpha", "ticker": "ALPHA",
            "source": {"kind": "store", "path": campaign},
            "presets": ["lqd_free"], "ladder": {"policy": "pinned", "expiries": [], "maxExpiries": 2},
        }).json()
        sid = doc["id"]
        c.post(f"/series/{sid}/start")
        c.app.state.volfit.series_jobs.join(120)
        r = c.post(f"/series/{sid}/export")
        assert r.status_code == 200 and r.headers["content-disposition"].endswith('.volfit-series.json"')
        bundle = r.json()
        assert c.post("/series/nope/export").status_code == 404
        assert c.delete(f"/series/{sid}").json()["deleted"]
        back = c.post("/series/import", json=bundle)
        assert back.status_code == 200 and back.json()["id"] == sid
        assert len(back.json()["frames"]) == 2
        assert c.post("/series/import", json={"schema": "volfit-snapshot/1"}).status_code == 422

        iso = doc["frames"][0]["expiries"][0]
        before = c.get(f"/smiles/ALPHA/{iso}").json()
        assert before["anchoring"]["production"] != "prior"
        res = c.post(f"/series/{sid}/adopt-prior", json={"idx": 0})
        assert res.status_code == 200, res.text
        assert res.json()["nodes"] == 2 and res.json()["laneId"] == "lqd_free"
        after = c.get(f"/smiles/ALPHA/{iso}").json()
        assert after["anchoring"]["production"] == "prior"  # the + Prior cell lights
        assert c.post(f"/series/{sid}/adopt-prior", json={"idx": 7}).status_code == 422
        assert c.post("/series/nope/adopt-prior", json={"idx": 0}).status_code == 404

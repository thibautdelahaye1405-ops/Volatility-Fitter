"""SERIES ARC S1 — import stored snapshots as a series + the read router.

Locks: the three sources through ONE loader — the app's captures (frames
REFERENCE the capture rows; delete keeps them), another VolStore file (chains
copied as series-OWNED rows; clock derived; ladder = the union, cropped by
maxExpiries; start / end / maxFrames bounds), fixture files in both capture
shapes (the intraday SPY 0DTE fixture, a daily-shape file, a directory
mixing them with a foreign ticker); presets resolve; the failure modes
(bad path, no match, unknown preset, no store); and the router (list / get /
delete / import-store, 404 / 422 / 409).
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.schemas_series import LaneSpec, SeriesLadder
from volfit.api.series_import import (
    ImportError_,
    ImportSource,
    SeriesImportRequest,
    derive_clock,
    import_series,
    quote_kind_of,
)
from volfit.api.series_store import SeriesStore
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 13)
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "intraday_spy_0dte.json")


def _chain(minutes: int = 0, ticker: str = "ALPHA"):
    chain = SyntheticProvider(reference_date=REF, tickers=(ticker,)).fetch_chain(ticker)
    if minutes:
        chain = dataclasses.replace(chain, timestamp=chain.timestamp + timedelta(minutes=minutes))
    return chain


def _state(db) -> AppState:
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return AppState(REF, providers={"cboe": prov}, active_source="cboe", store_path=str(db))


def _campaign_store(path, minutes=(0, 1, 2)) -> str:
    with VolStore(path) as vs:
        for m in minutes:
            vs.save_snapshot(_chain(m))
    return str(path)


def _req(kind: str, **over) -> SeriesImportRequest:
    src = {k: over.pop(k) for k in ("path", "start", "end", "maxFrames") if k in over}
    base = dict(name="alpha series", ticker="ALPHA", source=ImportSource(kind=kind, **src))
    base.update(over)
    return SeriesImportRequest(**base)


# ---------------------------------------------------------------- captures

def test_captures_import_references_the_capture_rows(tmp_path):
    db = tmp_path / "app.sqlite"
    state = _state(db)
    chain = state.snapshot("ALPHA")  # live fetch -> auto-captured under cboe
    doc = import_series(state, _req("captures"))
    assert doc.spec.mode == "import" and doc.spec.source == "cboe"
    assert len(doc.frames) == 1 and doc.frames[0].ts == chain.timestamp.isoformat()
    assert doc.frames[0].status == "ready" and doc.frames[0].nQuotes == len(chain.quotes)
    assert doc.frames[0].quoteKind == "quotes" and doc.frames[0].spot == chain.spot
    assert doc.spec.lanes[0].id == "current" and doc.spec.lanes[0].production
    assert doc.spec.fitMode == state.options().fitMode
    assert doc.progress.framesTotal == doc.progress.framesReady == 1
    with VolStore(db) as store:
        sid = doc.frames[0].snapshotId
        assert store.conn.execute(
            "SELECT series_id FROM snapshots WHERE id = ?", (sid,)
        ).fetchone()[0] is None  # referenced, not owned
        assert SeriesStore(store).delete(doc.id)
        assert store.load_snapshot(sid).ticker == "ALPHA"  # the capture survives


# ------------------------------------------------------------------- store

def test_store_import_copies_chains_as_owned_frames_and_derives_the_clock(tmp_path):
    campaign = _campaign_store(tmp_path / "campaign.sqlite")
    state = _state(tmp_path / "app.sqlite")
    doc = import_series(state, _req("store", path=campaign, presets=["lqd_free", "lv_prior"]))
    assert [f.idx for f in doc.frames] == [0, 1, 2]
    assert doc.spec.clock.step == "1m" and doc.spec.clock.count == 3
    assert doc.spec.clock.start == _chain(0).timestamp and not doc.spec.clock.sessionOnly
    assert doc.spec.source == "import:campaign.sqlite"
    assert [lane.id for lane in doc.spec.lanes] == ["lqd_free", "lv_prior"]
    # the ladder = the union of the frames' expiries; every frame carries them all
    union = [e.isoformat() for e in _chain(0).expiries()]
    assert doc.spec.ladder.policy == "pinned" and doc.spec.ladder.expiries == union
    assert all(f.expiries == union for f in doc.frames)
    with VolStore(state.store_path) as store:
        owned = [r[0] for r in store.conn.execute(
            "SELECT id FROM snapshots WHERE series_id = ?", (doc.id,)
        )]
        assert sorted(owned) == sorted(f.snapshotId for f in doc.frames)
        assert store.list_snapshots(["ALPHA"]) == []  # never listed as captures
        chain = SeriesStore(store).frame_chain(doc.id, 2)
        assert chain is not None and chain.timestamp == _chain(2).timestamp


def test_store_import_bounds_and_ladder_crop(tmp_path):
    campaign = _campaign_store(tmp_path / "campaign.sqlite", minutes=(0, 5, 10, 15))
    state = _state(tmp_path / "app.sqlite")
    t0 = _chain(0).timestamp
    doc = import_series(state, _req(
        "store", path=campaign, start=t0 + timedelta(minutes=4), end=t0 + timedelta(minutes=12),
        ladder=SeriesLadder(maxExpiries=2),
    ))
    assert [f.ts for f in doc.frames] == [(t0 + timedelta(minutes=m)).isoformat() for m in (5, 10)]
    assert doc.spec.clock.step == "5m"
    assert all(len(f.expiries) == 2 for f in doc.frames)
    assert doc.frames[0].expiries == doc.spec.ladder.expiries[:2]  # nearest first
    first = import_series(state, _req("store", path=campaign, maxFrames=1))
    assert len(first.frames) == 1 and first.frames[0].ts == t0.isoformat()
    pinned = import_series(state, _req(
        "store", path=campaign, ladder=SeriesLadder(expiries=[doc.spec.ladder.expiries[1]]),
    ))
    assert all(f.expiries == [doc.spec.ladder.expiries[1]] for f in pinned.frames)


def test_derive_clock_steps():
    t0 = datetime(2026, 9, 8, 10, 0)
    assert derive_clock([t0]).step == "15m"
    assert derive_clock([t0 + timedelta(minutes=30 * i) for i in range(4)]).step == "30m"
    assert derive_clock([t0 + timedelta(days=i) for i in range(3)]).step == "daily"
    assert derive_clock([t0 + timedelta(days=7 * i) for i in range(3)]).step == "weekly"
    assert derive_clock([t0, t0 + timedelta(minutes=4)]).step == "5m"  # nearest step


# ---------------------------------------------------------------- fixtures

def _daily_fixture(path, chain, asset="ALPHA"):
    doc = {
        "asset": asset, "as_of": chain.timestamp.date().isoformat(),
        "snapshot_ts_utc": chain.timestamp.isoformat(), "exercise_style": "american",
        "spot": chain.spot, "expiries": [e.isoformat() for e in chain.expiries()],
        "forwards": {},
        "quotes": [{"expiry": q.expiry.isoformat(), "strike": q.strike, "cp": q.call_put,
                    "bid": q.bid, "ask": q.ask, "ask_size": 3} for q in chain.quotes],
    }
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_intraday_fixture_file_imports_one_frame_stamped_like_a_capture(tmp_path):
    state = _state(tmp_path / "app.sqlite")
    doc = import_series(state, _req("fixtures", path=FIXTURE, ticker="SPY", presets=["lqd_free"]))
    assert doc.spec.ticker == "SPY" and len(doc.frames) == 1
    f = doc.frames[0]
    assert f.ts == "2026-07-10T16:30:00" and f.nQuotes == 862 and f.quoteKind == "quotes"
    assert f.expiries and f.expiries[0] == "2026-07-10"  # alive on the day: the 0DTE rung
    with VolStore(state.store_path) as store:
        chain = SeriesStore(store).frame_chain(doc.id, 0)
    assert chain is not None and chain.tick_size == 0.01 and chain.exercise_style == "american"
    assert chain.settlement is not None and date(2026, 7, 10) in chain.settlement
    assert chain.quotes[0].open_interest == 45  # fixture "size" -> open interest


def test_fixture_directory_mixes_both_shapes_and_skips_other_tickers(tmp_path):
    fx = tmp_path / "fx"
    (fx / "intraday").mkdir(parents=True)
    (fx / "daily" / "2026-06-13").mkdir(parents=True)
    intraday = {
        "asset": "ALPHA", "day": REF.isoformat(), "exercise_style": "american",
        "expiries": [e.isoformat() for e in _chain(0).expiries()],
        "snapshots": [
            {"ts": _chain(m).timestamp.isoformat(), "spot": _chain(m).spot,
             "quotes": [{"expiry": q.expiry.isoformat(), "strike": q.strike, "cp": q.call_put,
                         "bid": q.bid, "ask": q.ask, "size": 1} for q in _chain(m).quotes]}
            for m in (0, 15)
        ],
    }
    (fx / "intraday" / "ALPHA_2026-06-13.json").write_text(json.dumps(intraday), encoding="utf-8")
    _daily_fixture(fx / "daily" / "2026-06-13" / "ALPHA.json", _chain(60 * 6))
    _daily_fixture(fx / "daily" / "2026-06-13" / "BETA.json", _chain(60 * 6, "BETA"), asset="BETA")
    (fx / "daily" / "notes.json").write_text("[1, 2]", encoding="utf-8")  # unknown shape
    state = _state(tmp_path / "app.sqlite")
    doc = import_series(state, _req("fixtures", path=str(fx)))
    assert [f.ts for f in doc.frames] == [_chain(m).timestamp.isoformat() for m in (0, 15, 360)]
    assert doc.spec.source == "import:fx"


def test_quote_kind_marks_detection():
    chain = _chain(0)
    assert quote_kind_of(chain) == "quotes"
    marks = dataclasses.replace(
        chain, quotes=[dataclasses.replace(q, ask=q.bid) for q in chain.quotes if q.bid is not None]
    )
    assert quote_kind_of(marks) == "marks"
    assert quote_kind_of(dataclasses.replace(chain, quote_kind="marks")) == "marks"


# ---------------------------------------------------------------- failures

def test_import_failure_modes(tmp_path):
    state = _state(tmp_path / "app.sqlite")
    with pytest.raises(ImportError_, match="store file not found"):
        import_series(state, _req("store", path=str(tmp_path / "missing.sqlite")))
    with pytest.raises(ImportError_, match="fixture path not found"):
        import_series(state, _req("fixtures", path=str(tmp_path / "nope")))
    with pytest.raises(ImportError_, match="no stored snapshots"):
        import_series(state, _req("captures"))
    campaign = _campaign_store(tmp_path / "campaign.sqlite")
    with pytest.raises(ImportError_, match="unknown lane preset"):
        import_series(state, _req("store", path=campaign, presets=["nope"]))
    explicit = import_series(state, _req(
        "store", path=campaign, lanes=[LaneSpec(id="x", name="x", family="svi")],
    ))
    assert explicit.spec.lanes[0].family == "svi"
    no_store = AppState(REF, providers={"cboe": SyntheticProvider(reference_date=REF,
                                                                  tickers=("ALPHA",))})
    with pytest.raises(RuntimeError, match="VOLFIT_DB"):
        import_series(no_store, _req("store", path=campaign))


# ------------------------------------------------------------------ router

def _app(db):
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return create_app(reference_date=REF, providers={"cboe": prov}, active_source="cboe",
                      store_path=str(db))


def test_series_routes_list_get_delete_import(tmp_path):
    campaign = _campaign_store(tmp_path / "campaign.sqlite")
    with TestClient(_app(tmp_path / "app.sqlite")) as c:
        assert c.get("/series").json() == {"series": []}
        r = c.post("/series/import-store", json={
            "name": "alpha", "ticker": "alpha",
            "source": {"kind": "store", "path": campaign},
            "presets": ["lqd_free", "lqd_prior_filter"],
        })
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["spec"]["ticker"] == "ALPHA" and len(doc["frames"]) == 3
        assert [lane["id"] for lane in doc["spec"]["lanes"]] == ["lqd_free", "lqd_prior_filter"]
        assert doc["baseFit"]["nOrder"] == c.get("/settings/fit").json()["nOrder"]

        rows = c.get("/series", params={"ticker": "ALPHA"}).json()["series"]
        assert len(rows) == 1 and rows[0]["id"] == doc["id"] and rows[0]["nFrames"] == 3
        assert c.get("/series", params={"ticker": "BETA"}).json()["series"] == []
        assert c.get(f"/series/{doc['id']}").json()["frames"] == doc["frames"]
        assert c.get("/series/nope").status_code == 404

        bad = c.post("/series/import-store", json={
            "name": "x", "ticker": "ALPHA",
            "source": {"kind": "store", "path": str(tmp_path / "missing.sqlite")},
        })
        assert bad.status_code == 422 and "not found" in bad.json()["detail"]

        assert c.delete(f"/series/{doc['id']}").json() == {"deleted": True, "id": doc["id"]}
        assert c.delete(f"/series/{doc['id']}").status_code == 404
        assert c.get("/series").json() == {"series": []}
        actions = [e["action"] for e in c.app.state.volfit._event_tail]
        assert actions.count("series_import") == 1 and actions.count("series_delete") == 1


def test_series_routes_409_without_a_store():
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    with TestClient(create_app(reference_date=REF, providers={"cboe": prov},
                               active_source="cboe")) as c:
        assert c.get("/series").status_code == 409
        assert "VOLFIT_DB" in c.get("/series").json()["detail"]

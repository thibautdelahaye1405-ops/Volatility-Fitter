"""Prior framework — Phase A: full calibration snapshot, persistence, status.

'Save all' freezes every active ticker's calibrated surface (per-expiry model +
LQD backbone + market state + LV grid) into a PriorSurfaceSnapshot, persists it to
the store (history kept), and survives a restart. The snapshot must reproduce the
exact modelled prices (the LQD backbone vector rebuilds the same slice).
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors, service
from volfit.api.state import AppState
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import build_slice

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


@pytest.fixture()
def db_path() -> str:
    return str(Path(tempfile.mkdtemp()) / "priors.sqlite")


@pytest.fixture()
def client(db_path):
    with TestClient(create_app(reference_date=REF_DATE, store_path=db_path)) as c:
        c.get("/universe")  # warm the universe
        yield c


def _first_iso(client) -> str:
    return client.get("/universe").json()["expiries"][TICKER][1]["expiry"]


def test_save_all_captures_nodes_lv_and_market(client):
    client.get(f"/smiles/{TICKER}/{_first_iso(client)}")  # bootstrap a calibration
    result = client.post("/priors/save-all").json()
    assert TICKER in result["tickers"]
    assert result["nodes"] >= 1
    assert result["persisted"] is True

    status = {t["ticker"]: t for t in client.get("/priors").json()["tickers"]}
    alpha = status[TICKER]
    assert alpha["nodeCount"] >= 1
    assert alpha["hasLvSurface"] is True  # synthetic ALPHA has >= 2 expiries
    assert alpha["dataTs"] is not None and alpha["savedTs"] is not None


def test_snapshot_reproduces_modelled_prices():
    """The stored LQD backbone vector rebuilds the exact same priced slice."""
    state = AppState(REF_DATE)
    iso = [e.isoformat() for e in sorted(state.forwards(TICKER))][1]
    record = service.displayed_base(state, TICKER, iso, "mid")

    snap = priors.capture_snapshot(state, TICKER, "mid")
    assert snap is not None
    node = next(n for n in snap.nodes if n.expiry == iso)

    rebuilt = build_slice(LQDParams.from_vector(np.array(node.lqd)))
    k = np.linspace(-0.3, 0.3, 25)
    assert np.allclose(rebuilt.implied_w(k), record.result.slice.implied_w(k))
    # Market state is captured for exact reproduction / transport.
    assert node.forward == pytest.approx(record.prepared.forward)
    assert node.tau == pytest.approx(record.prepared.tau)
    assert snap.refSpot == pytest.approx(state.anchor_spot(TICKER))


def test_lv_surface_snapshot_roundtrips(client):
    client.get(f"/smiles/{TICKER}/{_first_iso(client)}")
    client.post("/priors/save-all")
    state = client.app.state.volfit
    snap = state.latest_prior_snapshot(TICKER)
    assert snap.lvSurface is not None
    lv = snap.lvSurface
    assert len(lv.theta) == len(lv.tNodes)
    assert all(len(row) == len(lv.xNodes) for row in lv.theta)
    assert all(v > 0.0 for row in lv.theta for v in row)  # nodal variances positive


def test_priors_persist_across_restart(db_path):
    with TestClient(create_app(reference_date=REF_DATE, store_path=db_path)) as c:
        c.get(f"/smiles/{TICKER}/{_first_iso(c)}")
        c.post("/priors/save-all")
        before = {t["ticker"]: t for t in c.get("/priors").json()["tickers"]}[TICKER]

    # Fresh app on the same DB: the saved prior is loaded from the store.
    with TestClient(create_app(reference_date=REF_DATE, store_path=db_path)) as c2:
        c2.get("/universe")
        after = {t["ticker"]: t for t in c2.get("/priors").json()["tickers"]}[TICKER]
    assert after["savedTs"] == before["savedTs"]
    assert after["nodeCount"] == before["nodeCount"]
    assert after["hasLvSurface"] == before["hasLvSurface"]


def test_save_all_without_store_is_memory_only():
    """No store configured: status still works in-memory, persisted=False."""
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        c.get(f"/smiles/{TICKER}/{_first_iso(c)}")
        result = c.post("/priors/save-all").json()
        assert result["persisted"] is False
        status = {t["ticker"]: t for t in c.get("/priors").json()["tickers"]}
        assert status[TICKER]["nodeCount"] >= 1  # cached in-memory this session


# ----------------------------------------------------- Phase B: fetch + display
def test_fetch_uses_fresh_saved_prior_and_marks_overlay(client):
    """A prior saved this session (data moment after the previous close) is fresh,
    so Fetch uses it directly and the smile overlay becomes the dotted, spot-updated
    (transported) prior."""
    iso = _first_iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")
    client.post("/priors/save-all")

    fetched = {t["ticker"]: t for t in client.post("/priors/fetch").json()["tickers"]}
    assert fetched[TICKER]["source"] == "saved"
    assert fetched[TICKER]["nodeCount"] >= 1

    smile = client.get(f"/smiles/{TICKER}/{iso}").json()
    assert smile["priorTransported"] is True
    assert len(smile["prior"]) == len(smile["model"])  # sampled on the model grid


def test_is_fresh_ladder_decision():
    """The saved-vs-recalibrate decision keys on the data moment vs prev close."""
    from datetime import datetime, timedelta

    from volfit.api.priors import _is_fresh
    from volfit.api.schemas_prior import PriorSurfaceSnapshot

    prev_close = datetime(2026, 6, 9, 20, 0)  # ~16:00 ET prev session

    def snap(dt: datetime) -> PriorSurfaceSnapshot:
        return PriorSurfaceSnapshot(
            ticker=TICKER, dataTs=dt.isoformat(), savedTs=dt.isoformat(),
            asOfLabel="x", refSpot=100.0, market={}, nodes=[
                # one minimal node so the model validates
                {"expiry": "2026-07-10", "tCal": 0.1, "tau": 0.1, "forward": 100.0,
                 "discount": 1.0, "model": "lqd", "lqd": [0.0, 0.0], "atmVol": 0.2, "skew": 0.0}
            ],
        )

    assert _is_fresh(snap(prev_close + timedelta(hours=1)), prev_close) is True
    assert _is_fresh(snap(prev_close - timedelta(hours=1)), prev_close) is False
    assert _is_fresh(None, prev_close) is False


def test_transported_prior_identity_and_shift():
    """The transported prior curve is the prior shape at h=0 and shifts with the
    forward (sticky-strike R=1: a higher forward lowers vol at fixed k for a skew)."""
    import numpy as np

    from volfit.api.prior_transport import prior_lqd_slice, transported_prior_points
    from volfit.api.schemas_prior import PriorNode

    state = AppState(REF_DATE)
    iso = [e.isoformat() for e in sorted(state.forwards(TICKER))][1]
    snap = priors.capture_snapshot(state, TICKER, "mid")
    pnode: PriorNode = next(n for n in snap.nodes if n.expiry == iso)

    grid = np.linspace(-0.2, 0.2, 11)
    base = prior_lqd_slice(pnode)
    # h = 0 (current forward == prior forward): identity, prior's own vols.
    identity = transported_prior_points(pnode, pnode.forward, "sticky_moneyness", grid)
    expect = np.sqrt(base.implied_w(grid) / pnode.tau)
    assert np.allclose([p.vol for p in identity], expect)
    # A forward move changes the curve (transport actually moved it).
    moved = transported_prior_points(pnode, pnode.forward * 1.05, "sticky_strike", grid)
    assert not np.allclose([p.vol for p in moved], expect)

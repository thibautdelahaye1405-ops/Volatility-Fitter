"""Project the graph-extrapolated smile onto an affine Local-Vol surface
(plan Phase 9 / Amendment G).

LV has no cheap 3-param transport, so the graph-extrapolated parametric smile is
the projection TARGET and a standard affine LV calibration runs against it. The
resulting surface is arb-free (Dupire density >= 0) and reproduces the extrapolated
smiles (ATM level matches the propagated handle).
"""

from datetime import date

import numpy as np
import pytest

from volfit.api import graph_lv
from volfit.api.graph_extrapolation import solve
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


@pytest.fixture(scope="module")
def projected():
    """One affine LV projection of a ticker's graph-extrapolated surface (slow;
    the affine calibration runs once for the module)."""
    state = AppState(REF_DATE)
    tk = state.active_tickers()[0]
    for iso in [e.isoformat() for e in sorted(state.forwards(tk))]:
        state.forwards(tk)  # warm the chain
    resp = graph_lv.project_to_lv(state, tk, AffineFitRequest(fitMode="mid"))
    return state, tk, resp


def _atm(curve) -> float:
    ks = np.array([p.k for p in curve])
    vols = np.array([p.vol for p in curve])
    return float(np.interp(0.0, ks, vols))


def test_projection_builds_an_lv_surface(projected):
    _, _, resp = projected
    assert resp.hasFit
    assert len(resp.smiles) >= 2
    assert len(resp.xNodes) > 0 and len(resp.tNodes) > 0


def test_projected_surface_is_arbitrage_free(projected):
    """The Dupire PDE keeps the reconstructed surface arbitrage-free."""
    _, _, resp = projected
    assert resp.arbitrageFree is True


def test_projection_reproduces_graph_atm(projected):
    """Each LV-reconstructed smile's ATM vol matches the propagated graph handle."""
    state, tk, resp = projected
    sol = solve(state, GraphExtrapolateRequest())
    assert sol is not None
    for sm in resp.smiles:
        i = sol.universe.node_index((tk, sm.expiry))
        post_atm = float(sol.field.mean[i, 0])
        assert _atm(sm.model) == pytest.approx(post_atm, abs=8e-3)


def test_route_lv_projection_smoke():
    from fastapi.testclient import TestClient

    from volfit.api import create_app

    with TestClient(create_app(reference_date=REF_DATE)) as client:
        resp = client.post("/graph/extrapolate/lv/ALPHA", json={"fitMode": "mid"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["hasFit"] is True
        assert len(body["smiles"]) >= 2

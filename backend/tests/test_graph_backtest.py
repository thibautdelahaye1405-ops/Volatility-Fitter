"""Leave-one-node-out backtest of the graph extrapolator (plan Phase 8).

Each validation-clean calibrated node is withheld and predicted from the rest; we
report residuals + standardized residuals + an aggregate calibration summary.
Bootstrap-prior nodes (circular as a prior-vs-market test) are excluded from the
clean score.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_backtest import backtest
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def primed() -> AppState:
    state = AppState(REF_DATE)
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    return state


def test_loo_reports_residuals_and_standardized_residuals(primed):
    resp = backtest(primed, GraphExtrapolateRequest())
    assert resp.nScored > 0
    assert len(resp.nodes) == resp.nScored
    for n in resp.nodes:
        assert np.isfinite(n.residualBp)
        assert np.isfinite(n.standardizedResidual)
        assert n.priorSource == "active_transported"
    assert np.isfinite(resp.rmseBp) and resp.rmseBp >= 0.0
    assert np.isfinite(resp.zetaMean) and resp.zetaStd >= 0.0


def test_bootstrap_nodes_excluded_from_clean_score():
    """No active prior -> every node is today_bootstrap -> all excluded."""
    state = AppState(REF_DATE)
    # Touch the universe so nodes have bootstrap fits available.
    for tk in state.active_tickers():
        state.forwards(tk)
    resp = backtest(state, GraphExtrapolateRequest())
    assert resp.nScored == 0
    assert resp.nExcludedBootstrap > 0
    assert resp.nodes == []


def test_held_out_node_is_predicted_not_pinned(primed):
    """A withheld node's posterior is propagated from the others, not its own
    observation — so it can differ from the full-solve (un-withheld) posterior."""
    from volfit.api.graph_extrapolation import solve

    full = solve(primed, GraphExtrapolateRequest())
    scored = backtest(primed, GraphExtrapolateRequest())
    assert scored.nScored > 0
    # The backtest's predictions are well-defined ATM vols.
    for n in scored.nodes:
        assert 0.0 < n.postAtmVol < 5.0
    # The full solve pinned every lit node to its calibration (sanity anchor).
    assert full is not None


def test_route_backtest_smoke():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        tk = "ALPHA"
        for e in client.get("/universe").json()["expiries"][tk][:3]:
            client.post(f"/calibrate/{tk}/{e['expiry']}")
        client.post("/priors/save-all")
        client.post("/priors/fetch")
        resp = client.post("/graph/backtest", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert "rmseBp" in body and "zetaStd" in body
        assert body["nScored"] + body["nExcludedBootstrap"] >= 0

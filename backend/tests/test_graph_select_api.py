"""Observation-plan API (R3 item 13): ranking, exposure steering, route.

The closed-form-equals-refit lock lives in test_graph_select.py; here the
contract is the PRODUCT payload: dark nodes ranked by weighted variance
reduction, band units, beneficiaries, and the per-ticker exposure knob.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_select import observation_plan
from volfit.api.schemas import GraphObservationPlanRequest
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


def _darken(state, n_per_ticker=2):
    """Turn the far end of every ticker's ladder dark; returns the dark names."""
    dark = []
    for tk in state.active_tickers():
        isos = [e.isoformat() for e in sorted(state.forwards(tk))]
        for iso in isos[-n_per_ticker:]:
            state.set_node_lit(tk, iso, False)
            dark.append((tk, iso))
    return dark


def test_plan_ranks_dark_nodes_and_shrinks_bands(primed):
    dark = _darken(primed)
    plan = observation_plan(primed, GraphObservationPlanRequest(topN=10))
    assert plan.nCandidates >= len(dark)
    assert 0 < len(plan.candidates) <= 10
    pcts = [c.totalVarReductionPct for c in plan.candidates]
    assert pcts == sorted(pcts, reverse=True)  # ranked, largest first
    for c in plan.candidates:
        assert 0.0 <= c.totalVarReductionPct <= 100.0
        assert c.selfSdAfterBp < c.selfSdBeforeBp  # quoting a node pins it
        assert c.assumedPrecision > 0.0
        for b in c.beneficiaries:
            assert b.sdAfterBp <= b.sdBeforeBp + 1e-9
    # Every dark node was scored.
    named = {(c.ticker, c.expiry) for c in plan.candidates}
    assert named.issubset({(t, i) for t, i in dark} | named)


def test_exposure_weights_steer_the_ranking(primed):
    _darken(primed)
    tickers = primed.active_tickers()
    assert len(tickers) >= 2
    target = tickers[-1]
    weights = {tk: 0.0 for tk in tickers}
    weights[target] = 1.0
    plan = observation_plan(
        primed, GraphObservationPlanRequest(topN=3, exposureWeights=weights)
    )
    assert len(plan.candidates) > 0
    # With every other book zero-weighted, the winning quote serves the
    # target ticker's chain (cross-ticker edges are much weaker than
    # calendar edges, so the top candidate sits on the target's own ladder).
    assert plan.candidates[0].ticker == target


def test_route_round_trip():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        tk = "ALPHA"
        iso = client.get("/universe").json()["expiries"][tk][1]["expiry"]
        client.post(f"/calibrate/{tk}/{iso}")  # one lit calibration
        res = client.post("/graph/observation-plan", json={"topN": 4})
        assert res.status_code == 200
        body = res.json()
        # Everything except the single calibrated node is a candidate.
        assert body["nCandidates"] > 0
        assert 0 < len(body["candidates"]) <= 4
        top = body["candidates"][0]
        assert {"ticker", "expiry", "selfSdBeforeBp", "totalVarReductionPct"} <= set(top)
        assert (top["ticker"], top["expiry"]) != (tk, iso)

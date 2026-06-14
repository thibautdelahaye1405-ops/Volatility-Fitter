"""HTTP API tests: graph extrapolation and SSR scenario endpoints.

Separate module-scoped app from test_api.py so the graph universe is built
from clean mid fits (the universe is 3 tickers x 4 expiries = 12 nodes).
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
VOL_SHIFT = 0.02  # +2 ATM vol points observed on one node


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def universe(client):
    return client.get("/universe").json()


@pytest.fixture(scope="module")
def solved(client, universe):
    """One observation: ALPHA 6M ATM vol +2 pts; everything extrapolated."""
    expiry_6m = universe["expiries"]["ALPHA"][2]["expiry"]
    response = client.post(
        "/graph/solve",
        json={"observations": [{"ticker": "ALPHA", "expiry": expiry_6m, "dAtmVol": VOL_SHIFT}]},
    )
    assert response.status_code == 200
    nodes = {(n["ticker"], n["expiry"]): n for n in response.json()["nodes"]}
    return expiry_6m, nodes


# -- graph nodes (baseline lattice) ------------------------------------------


def test_graph_nodes_serves_baseline_lattice(client, universe):
    nodes = client.get("/graph/nodes").json()["nodes"]
    assert len(nodes) == 12  # 3 tickers x 4 expiries
    by_name = {(n["ticker"], n["expiry"]): n for n in nodes}
    for ticker, ladder in universe["expiries"].items():
        for rung in ladder:
            node = by_name[(ticker, rung["expiry"])]
            assert node["t"] == pytest.approx(rung["t"])
            assert 0.15 < node["atmVol"] < 0.30
            assert node["skew"] < 0  # equity-like synthetic smiles
            assert np.isfinite(node["curvature"])


# -- graph solve -------------------------------------------------------------


def test_graph_covers_full_universe(universe, solved):
    _, nodes = solved
    assert len(nodes) == 12  # 3 tickers x 4 expiries
    for (ticker, expiry), node in nodes.items():
        assert node["t"] > 0
        assert 0.15 < node["baseAtmVol"] < 0.30
        assert node["bandLo"] < node["postAtmVol"] < node["bandHi"]
        assert node["sd"] >= 0
        assert node["shiftBp"] == pytest.approx(
            (node["postAtmVol"] - node["baseAtmVol"]) * 1e4, abs=1e-9
        )


def test_observed_node_takes_most_of_the_shift(solved):
    expiry_6m, nodes = solved
    observed = nodes[("ALPHA", expiry_6m)]
    assert observed["observed"] is True
    assert 150 <= observed["shiftBp"] <= 210
    assert sum(node["observed"] for node in nodes.values()) == 1


def test_signal_propagates_along_ticker_more_than_across(universe, solved):
    expiry_6m, nodes = solved
    ladder = [e["expiry"] for e in universe["expiries"]["ALPHA"]]
    # Same-ticker neighbors (strong calendar edges) move materially...
    for expiry in ladder:
        if expiry != expiry_6m:
            assert nodes[("ALPHA", expiry)]["shiftBp"] > 20
    # ...cross-ticker nodes move too, but less than the observed ticker.
    for ticker in ("BETA", "GAMMA"):
        assert 0 < nodes[(ticker, expiry_6m)]["shiftBp"] < nodes[("ALPHA", expiry_6m)]["shiftBp"]


def test_graph_unknown_observation_is_404(client, universe):
    expiry = universe["expiries"]["ALPHA"][0]["expiry"]
    bad_ticker = {"observations": [{"ticker": "NOPE", "expiry": expiry, "dAtmVol": 0.01}]}
    assert client.post("/graph/solve", json=bad_ticker).status_code == 404
    bad_expiry = {"observations": [{"ticker": "ALPHA", "expiry": "2030-01-01", "dAtmVol": 0.01}]}
    assert client.post("/graph/solve", json=bad_expiry).status_code == 404


# -- solver hyperparameters --------------------------------------------------


def _solve_nodes(client, observations, **params) -> dict:
    """POST /graph/solve with extra solver params; return name -> node dict."""
    response = client.post("/graph/solve", json={"observations": observations, **params})
    assert response.status_code == 200, response.text
    return {(n["ticker"], n["expiry"]): n for n in response.json()["nodes"]}


def _alpha_6m_observation(universe) -> tuple[str, list[dict]]:
    expiry_6m = universe["expiries"]["ALPHA"][2]["expiry"]
    return expiry_6m, [{"ticker": "ALPHA", "expiry": expiry_6m, "dAtmVol": VOL_SHIFT}]


def test_higher_eta_propagates_more(client, universe):
    """Larger directed-smoothness reach moves a same-ticker neighbor further."""
    _, obs = _alpha_6m_observation(universe)
    near = universe["expiries"]["ALPHA"][0]["expiry"]
    low = _solve_nodes(client, obs, etaScale=0.25)
    high = _solve_nodes(client, obs, etaScale=4.0)
    assert high[("ALPHA", near)]["shiftBp"] > low[("ALPHA", near)]["shiftBp"]


def test_higher_kappa_stiffens_toward_baseline(client, universe):
    """Larger local precision shrinks increments: neighbors move less."""
    _, obs = _alpha_6m_observation(universe)
    near = universe["expiries"]["ALPHA"][1]["expiry"]
    soft = _solve_nodes(client, obs, kappaScale=0.25)
    stiff = _solve_nodes(client, obs, kappaScale=4.0)
    assert stiff[("ALPHA", near)]["shiftBp"] < soft[("ALPHA", near)]["shiftBp"]


def test_cross_weight_override_increases_cross_propagation(client, universe):
    """Heavier cross-ticker edges carry more signal to the other tickers."""
    expiry_6m, obs = _alpha_6m_observation(universe)
    base = _solve_nodes(client, obs)
    boosted = _solve_nodes(client, obs, crossWeight=20.0)
    for ticker in ("BETA", "GAMMA"):
        assert boosted[(ticker, expiry_6m)]["shiftBp"] > base[(ticker, expiry_6m)]["shiftBp"]


def test_ot_term_runs_and_stays_calibrated(client, universe):
    """Enabling the OT flux term (lambdaScale > 0) yields a valid field."""
    expiry_6m, obs = _alpha_6m_observation(universe)
    nodes = _solve_nodes(client, obs, lambdaScale=1.0, nu=0.2)
    observed = nodes[("ALPHA", expiry_6m)]
    assert observed["observed"] is True
    assert observed["shiftBp"] > 100  # still absorbs most of its own shift
    for node in nodes.values():
        assert node["bandLo"] < node["postAtmVol"] < node["bandHi"]
        assert node["sd"] >= 0


def test_invalid_solver_params_rejected(client, universe):
    _, obs = _alpha_6m_observation(universe)
    for bad in ({"kappaScale": 0.0}, {"nu": 0.0}, {"etaScale": -1.0}, {"crossWeight": -2.0}):
        response = client.post("/graph/solve", json={"observations": obs, **bad})
        assert response.status_code == 422, bad


# -- auto-tune ---------------------------------------------------------------


def test_autotune_picks_grid_minimizer(client, universe):
    a6 = universe["expiries"]["ALPHA"][2]["expiry"]
    b6 = universe["expiries"]["BETA"][2]["expiry"]
    obs = [
        {"ticker": "ALPHA", "expiry": a6, "dAtmVol": 0.02},
        {"ticker": "BETA", "expiry": b6, "dAtmVol": 0.015},
    ]
    response = client.post("/graph/autotune", json={"observations": obs})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["etaScale"] for c in body["candidates"]] == [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0]
    assert all(np.isfinite(c["rmseBp"]) for c in body["candidates"])
    best = min(body["candidates"], key=lambda c: c["rmseBp"])
    assert body["etaScale"] == best["etaScale"]
    assert body["rmseBp"] == pytest.approx(best["rmseBp"])


def test_autotune_requires_two_observations(client, universe):
    a6 = universe["expiries"]["ALPHA"][2]["expiry"]
    one = [{"ticker": "ALPHA", "expiry": a6, "dAtmVol": 0.02}]
    assert client.post("/graph/autotune", json={"observations": one}).status_code == 422


# -- ssr scenario ------------------------------------------------------------


def atm_shift(data) -> float:
    """Shifted-minus-base implied vol interpolated at k = 0."""
    k = np.array(data["k"])
    diff = np.array(data["shiftedVol"]) - np.array(data["baseVol"])
    return float(np.interp(0.0, k, diff))


def scenario(client, expiry: str, regime) -> dict:
    response = client.post(
        "/scenario/ssr",
        json={"ticker": "BETA", "expiry": expiry, "spotReturn": 0.01, "regime": regime},
    )
    assert response.status_code == 200
    return response.json()


def test_sticky_strike_realizes_the_skew(client, universe):
    expiry = universe["expiries"]["BETA"][2]["expiry"]
    skew = client.get(f"/smiles/BETA/{expiry}").json()["diagnostics"]["skew"]

    data = scenario(client, expiry, "sticky_strike")
    assert data["ssr"] == 1.0
    assert data["regime"] == "sticky_strike"
    assert len(data["k"]) == len(data["baseVol"]) == len(data["shiftedVol"]) == 241

    # SSR = 1: d sigma_atm = skew * d ln F (negative skew, spot up -> vol down).
    expected = skew * np.log1p(0.01)
    assert atm_shift(data) == pytest.approx(expected, rel=0.2)


def test_sticky_moneyness_leaves_atm_unchanged(client, universe):
    expiry = universe["expiries"]["BETA"][2]["expiry"]
    skew = client.get(f"/smiles/BETA/{expiry}").json()["diagnostics"]["skew"]

    data = scenario(client, expiry, "sticky_moneyness")
    assert data["ssr"] == 0.0
    # SSR = 0: the ATM shift is second order (curvature * delta^2).
    assert abs(atm_shift(data)) < 0.2 * abs(skew * np.log1p(0.01))


def test_custom_numeric_ssr(client, universe):
    expiry = universe["expiries"]["BETA"][2]["expiry"]
    data = scenario(client, expiry, 1.5)
    assert data["ssr"] == 1.5
    assert data["regime"] == "1.5"

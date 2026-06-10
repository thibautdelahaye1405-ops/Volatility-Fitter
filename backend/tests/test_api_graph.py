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
    assert len(data["k"]) == len(data["baseVol"]) == len(data["shiftedVol"]) == 161

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

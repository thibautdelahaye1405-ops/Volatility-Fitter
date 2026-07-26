"""HTTP API tests: graph chart baseline, production solver knobs, autotune, SSR.

P6 re-point (sandbox retirement): POST /graph/solve is gone. GET /graph/nodes
serves the SELECTED universe at transported-prior baselines (the
zero-observation production solve), the solver-knob semantics that were locked
through the sandbox are re-locked THROUGH POST /graph/extrapolate via
synthetic what-if pulses, and POST /graph/autotune LOO-tunes the smooth-field
reach eta on the production solve (same body Run ships; smooth-field only).

Module-scoped app with an active prior primed per ticker (captured from
today's fits), so every node resolves ``active_transported`` — validation-clean,
which the production autotune requires — and pulse innovations are measured
against genuine prior baselines.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors

REF_DATE = date(2026, 6, 10)
PULSE = 0.02  # +2 ATM vol points pulsed on one node


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        # Prime an active prior per ticker (captured from today's fits): nodes
        # resolve active_transported (validation-clean), and today's calibrated
        # handles round-trip the prior exactly (innovation == 0 by construction).
        state = c.app.state.volfit
        for tk in state.active_tickers():
            snap = priors.capture_snapshot(state, tk, "mid")
            if snap is not None:
                state.set_active_prior(tk, snap, "saved")
        yield c


@pytest.fixture(scope="module")
def universe(client):
    return client.get("/universe").json()


def _extrapolate(client, pulses, **params) -> dict:
    """POST /graph/extrapolate with what-if pulses; name -> node dict."""
    response = client.post(
        "/graph/extrapolate", json={"syntheticObservations": pulses, **params}
    )
    assert response.status_code == 200, response.text
    return {(n["ticker"], n["expiry"]): n for n in response.json()["nodes"]}


def _alpha_6m_pulse(universe) -> tuple[str, list[dict]]:
    expiry_6m = universe["expiries"]["ALPHA"][2]["expiry"]
    return expiry_6m, [{"ticker": "ALPHA", "expiry": expiry_6m, "dAtmVol": PULSE}]


# -- graph nodes (chart baseline = zero-observation production solve) ---------


def test_graph_nodes_serves_selected_prior_lattice(client, universe):
    nodes = client.get("/graph/nodes").json()["nodes"]
    assert len(nodes) == 12  # 3 tickers x 4 selected expiries
    by_name = {(n["ticker"], n["expiry"]): n for n in nodes}
    for ticker, ladder in universe["expiries"].items():
        for rung in ladder:
            node = by_name[(ticker, rung["expiry"])]
            # /universe counts days/365, graph payloads days/365.25.
            assert node["t"] == pytest.approx(rung["t"], rel=2e-3)
            assert 0.15 < node["atmVol"] < 0.30
            assert node["skew"] < 0  # equity-like synthetic smiles
            assert np.isfinite(node["curvature"])
            assert node["lit"] is True  # every node lit by default


def test_graph_nodes_baseline_matches_extrapolate_priors(client):
    """The canvas and the results table agree by construction: /graph/nodes
    handles ARE the production solve's prior columns (same resolution)."""
    nodes = {(n["ticker"], n["expiry"]): n for n in client.get("/graph/nodes").json()["nodes"]}
    solved = client.post("/graph/extrapolate", json={}).json()["nodes"]
    assert len(solved) == len(nodes)
    for row in solved:
        base = nodes[(row["ticker"], row["expiry"])]
        assert base["atmVol"] == pytest.approx(row["priorAtmVol"], abs=1e-12)
        assert base["skew"] == pytest.approx(row["priorSkew"], abs=1e-12)
        assert base["curvature"] == pytest.approx(row["priorCurv"], abs=1e-12)
        assert base["t"] == pytest.approx(row["t"], abs=1e-12)
        assert base["lit"] == row["lit"]


def test_dropped_pulse_leaves_the_zero_observation_prior(client, universe):
    """A pulse naming a node outside the selection is DROPPED (legacy pulse
    contract), leaving the pure zero-observation predictive prior: every mean
    exactly at its baseline, bands from the prior marginal alone."""
    expiry = universe["expiries"]["ALPHA"][0]["expiry"]
    nodes = _extrapolate(
        client, [{"ticker": "NOPE", "expiry": expiry, "dAtmVol": 0.01}]
    )
    assert len(nodes) == 12
    for node in nodes.values():
        assert node["shiftBp"] == pytest.approx(0.0, abs=1e-9)
        assert not node["calibrated"]
        assert node["sd"] > 0


# -- production solve via what-if pulses --------------------------------------


def test_pulse_covers_full_universe(client, universe):
    _, pulse = _alpha_6m_pulse(universe)
    nodes = _extrapolate(client, pulse)
    assert len(nodes) == 12
    for node in nodes.values():
        assert node["t"] > 0
        assert 0.15 < node["priorAtmVol"] < 0.30
        assert node["bandLo"] < node["postAtmVol"] < node["bandHi"]
        assert node["sd"] >= 0
        assert node["shiftBp"] == pytest.approx(
            (node["postAtmVol"] - node["priorAtmVol"]) * 1e4, abs=1e-9
        )


def test_pulsed_node_absorbs_the_pulse(client, universe):
    expiry_6m, pulse = _alpha_6m_pulse(universe)
    nodes = _extrapolate(client, pulse)
    pulsed = nodes[("ALPHA", expiry_6m)]
    assert pulsed["calibrated"] is True
    assert pulsed["innovationBp"] == pytest.approx(PULSE * 1e4)  # firm pulse
    assert 190 <= pulsed["shiftBp"] <= 210  # near-full absorption
    assert sum(node["calibrated"] for node in nodes.values()) == 1


def test_signal_propagates_along_ticker_more_than_across(client, universe):
    expiry_6m, pulse = _alpha_6m_pulse(universe)
    nodes = _extrapolate(client, pulse)
    ladder = [e["expiry"] for e in universe["expiries"]["ALPHA"]]
    # Same-ticker neighbors (strong calendar edges) move materially...
    for expiry in ladder:
        if expiry != expiry_6m:
            assert nodes[("ALPHA", expiry)]["shiftBp"] > 20
    # ...cross-ticker nodes move too, but less than the pulsed ticker.
    for ticker in ("BETA", "GAMMA"):
        assert 0 < nodes[(ticker, expiry_6m)]["shiftBp"] < nodes[("ALPHA", expiry_6m)]["shiftBp"]


# -- solver hyperparameters through the production endpoint -------------------


def test_higher_eta_propagates_more(client, universe):
    """Larger directed-smoothness reach moves a same-ticker neighbor further."""
    _, pulse = _alpha_6m_pulse(universe)
    near = universe["expiries"]["ALPHA"][0]["expiry"]
    low = _extrapolate(client, pulse, etaScale=0.25)
    high = _extrapolate(client, pulse, etaScale=4.0)
    assert high[("ALPHA", near)]["shiftBp"] > low[("ALPHA", near)]["shiftBp"]


def test_higher_kappa_stiffens_toward_baseline(client, universe):
    """Larger local precision shrinks increments: neighbors move less."""
    _, pulse = _alpha_6m_pulse(universe)
    near = universe["expiries"]["ALPHA"][1]["expiry"]
    soft = _extrapolate(client, pulse, kappaScale=0.25)
    stiff = _extrapolate(client, pulse, kappaScale=4.0)
    assert stiff[("ALPHA", near)]["shiftBp"] < soft[("ALPHA", near)]["shiftBp"]


def test_cross_weight_override_increases_cross_propagation(client, universe):
    """Heavier cross-ticker edges carry more signal to the other tickers."""
    expiry_6m, pulse = _alpha_6m_pulse(universe)
    base = _extrapolate(client, pulse)
    boosted = _extrapolate(client, pulse, crossWeight=20.0)
    for ticker in ("BETA", "GAMMA"):
        assert boosted[(ticker, expiry_6m)]["shiftBp"] > base[(ticker, expiry_6m)]["shiftBp"]


def test_ot_term_runs_and_stays_calibrated(client, universe):
    """Enabling the OT flux term (lambdaScale > 0) yields a valid field —
    the API translation ot_weight = lambdaScale / s^2 runs end to end."""
    expiry_6m, pulse = _alpha_6m_pulse(universe)
    nodes = _extrapolate(client, pulse, lambdaScale=1.0, nu=0.2)
    pulsed = nodes[("ALPHA", expiry_6m)]
    assert pulsed["calibrated"] is True
    assert pulsed["shiftBp"] > 100  # still absorbs most of its own pulse
    for node in nodes.values():
        assert node["bandLo"] < node["postAtmVol"] < node["bandHi"]
        assert node["sd"] >= 0


def test_invalid_solver_params_rejected(client, universe):
    _, pulse = _alpha_6m_pulse(universe)
    for bad in ({"kappaScale": 0.0}, {"nu": 0.0}, {"etaScale": -1.0}, {"crossWeight": -2.0}):
        response = client.post(
            "/graph/extrapolate", json={"syntheticObservations": pulse, **bad}
        )
        assert response.status_code == 422, bad


# -- auto-tune (production LOO) ----------------------------------------------


def test_autotune_rides_the_production_solve(client):
    """Grid contract + argmin agreement. With priors captured from today's own
    fits the innovations are the sub-bp capture residual, so every held-out
    node is predicted by its transported prior to within a few bp at EVERY
    reach — the LOO genuinely rides prior-anchored production solves (a
    today-fit baseline would score 0 only circularly; a broken prior would
    score tens of bp)."""
    response = client.post("/graph/autotune", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["etaScale"] for c in body["candidates"]] == [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0]
    for candidate in body["candidates"]:
        assert 0.0 <= candidate["rmseBp"] < 5.0
    best = min(body["candidates"], key=lambda c: c["rmseBp"])
    assert body["etaScale"] == best["etaScale"]
    assert body["rmseBp"] == pytest.approx(best["rmseBp"])


def test_autotune_rejects_message_mode(client):
    """eta does not exist under the message operator — 400, not a silent tune."""
    response = client.post(
        "/graph/autotune", json={"propagationMode": "precision_messages"}
    )
    assert response.status_code == 400
    assert "eta" in response.json()["detail"]


def test_autotune_rejects_what_if_pulses(client, universe):
    """A pulse is hypothesis-firm on EVERY solve — holding its node out would
    not remove the observation, so LOO over pulses is meaningless."""
    _, pulse = _alpha_6m_pulse(universe)
    response = client.post("/graph/autotune", json={"syntheticObservations": pulse})
    assert response.status_code == 400


def test_autotune_needs_validation_clean_candidates():
    """Bootstrap priors are circular as LOO targets: a state with no saved
    priors has zero validation-clean candidates and must refuse to tune."""
    from volfit.api.graph_backtest import autotune
    from volfit.api.schemas import GraphExtrapolateRequest
    from volfit.api.state import AppState

    state = AppState(REF_DATE)
    with pytest.raises(ValueError, match="validation-clean"):
        autotune(state, GraphExtrapolateRequest())


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

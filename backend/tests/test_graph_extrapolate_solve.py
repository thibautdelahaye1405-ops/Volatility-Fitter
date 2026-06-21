"""Lit-calibration innovation feed + production solve (plan Phase 3).

The propagated observation is d = calibrated_handles - transported_prior_handles
on lit nodes; the posterior increment is added back onto the prior. Dark nodes are
never observations — they only receive propagation. These tests pin the innovation
identity, the lit-node fidelity, the dark-stays-at-prior behaviour, and that a dark
node with a fit is excluded from the observation set.

Runs over the synthetic provider (ungated, so every node has a bootstrap fit).
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_extrapolation import _calibrated_handles, extrapolate
from volfit.api.graph_nodes import resolve_node_prior
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def state() -> AppState:
    return AppState(REF_DATE)


@pytest.fixture()
def primed(state):
    """Every ticker's surface captured as its active prior (prior == today)."""
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    return state


def _isos(state, ticker):
    return [e.isoformat() for e in sorted(state.forwards(ticker))]


def test_lit_innovation_equals_calibrated_minus_prior(primed):
    resp = extrapolate(primed, GraphExtrapolateRequest())
    for node in resp.nodes:
        if not node.calibrated:
            continue
        y = _calibrated_handles(primed, node.ticker, node.expiry, "mid")
        x0 = resolve_node_prior(primed, node.ticker, node.expiry).handles
        assert node.innovationBp == pytest.approx((y[0] - x0[0]) * 1e4, abs=1e-6)


def test_lit_node_lands_on_its_calibration(primed):
    """High-precision observation pins the lit node's posterior to its calibration."""
    resp = extrapolate(primed, GraphExtrapolateRequest())
    for node in resp.nodes:
        if not node.calibrated:
            continue
        y = _calibrated_handles(primed, node.ticker, node.expiry, "mid")
        assert node.postAtmVol == pytest.approx(float(y[0]), abs=5e-4)


def test_zero_innovation_keeps_dark_at_prior(primed):
    """prior == today -> ~zero innovation -> a dark node stays at its prior."""
    tk = primed.active_tickers()[0]
    dark_iso = _isos(primed, tk)[1]
    primed.set_node_lit(tk, dark_iso, False)

    resp = extrapolate(primed, GraphExtrapolateRequest())
    dark = next(n for n in resp.nodes if n.ticker == tk and n.expiry == dark_iso)
    assert dark.lit is False
    assert dark.calibrated is False
    assert dark.innovationBp is None
    assert dark.postAtmVol == pytest.approx(dark.priorAtmVol, abs=1e-3)
    assert abs(dark.shiftBp) < 30.0  # only the tiny prior-vs-today residual


def test_dark_node_with_fit_is_not_an_observation(primed):
    """A darkened node that HAS a calibration is excluded from the observations."""
    tk = primed.active_tickers()[0]
    dark_iso = _isos(primed, tk)[2]
    # The node has a bootstrap fit available...
    assert _calibrated_handles(primed, tk, dark_iso, "mid") is not None
    primed.set_node_lit(tk, dark_iso, False)

    resp = extrapolate(primed, GraphExtrapolateRequest())
    dark = next(n for n in resp.nodes if n.ticker == tk and n.expiry == dark_iso)
    assert dark.calibrated is False  # ...but it is NOT used as an observation
    assert dark.innovationBp is None
    # Observation count == number of lit nodes (all others stay lit + calibrated).
    n_obs = sum(1 for n in resp.nodes if n.calibrated)
    n_lit = sum(1 for n in resp.nodes if n.lit)
    assert n_obs == n_lit


def test_propagation_moves_a_dark_neighbour(state):
    """With flat baselines, lit innovations propagate a signed shift to a dark
    calendar neighbour (no manual typing)."""
    tk = state.active_tickers()[0]
    dark_iso = _isos(state, tk)[1]  # interior expiry: lit neighbours on both sides
    state.set_node_lit(tk, dark_iso, False)

    resp = extrapolate(state, GraphExtrapolateRequest(flatAtm=True))
    by = {(n.ticker, n.expiry): n for n in resp.nodes}
    dark = by[(tk, dark_iso)]
    # Flat baseline is 0.20 ATM vol; the lit market sits elsewhere, so the dark
    # node is pulled off the flat prior by propagation.
    assert dark.priorAtmVol == pytest.approx(0.20)
    assert abs(dark.postAtmVol - 0.20) > 1e-4
    # The shift tracks the lit neighbours' innovation sign.
    neighbours = [by[(tk, iso)] for iso in (_isos(state, tk)[0], _isos(state, tk)[2])]
    mean_innov = np.mean([n.innovationBp for n in neighbours])
    assert np.sign(dark.shiftBp) == np.sign(mean_innov)


def test_route_extrapolate_smoke():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        tk = "ALPHA"
        iso = client.get("/universe").json()["expiries"][tk][1]["expiry"]
        client.post(f"/calibrate/{tk}/{iso}")  # one lit calibration
        resp = client.post("/graph/extrapolate", json={})
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        assert len(nodes) > 0
        target = next(n for n in nodes if n["ticker"] == tk and n["expiry"] == iso)
        assert target["calibrated"] is True
        assert "priorSource" in target

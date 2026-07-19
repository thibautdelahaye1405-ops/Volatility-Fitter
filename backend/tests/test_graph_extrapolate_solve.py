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


def test_graph_nodes_empty_before_calibration():
    """GET /graph/nodes returns 200 with no nodes before anything is calibrated
    (the gated server) — never a 500 (which the browser shows as 'Failed to fetch')."""
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        resp = client.get("/graph/nodes")
        assert resp.status_code == 200
        assert resp.json()["nodes"] == []


def test_graph_nodes_appear_after_calibration_in_viewed_mode():
    """The sandbox universe rebuilds once calibrations land, in the mode the
    user is VIEWING. Regression (2026-07-09): the universe was (a) cached empty
    forever when the Graph tab was opened before the first Calibrate, and (b)
    hardcoded to mid fits — a haircut-mode session had no Manual what-if nodes
    at all even after calibrating everything."""
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        # Cache the pre-Calibrate (empty) universe, as opening the Graph tab does.
        assert client.get("/graph/nodes").json()["nodes"] == []
        tk = "ALPHA"
        iso = client.get("/universe").json()["expiries"][tk][1]["expiry"]
        # View + calibrate in a NON-mid mode (viewing records last_fit_mode).
        client.get(f"/smiles/{tk}/{iso}", params={"fit_mode": "haircut"})
        client.post(f"/calibrate/{tk}/{iso}", params={"fit_mode": "haircut"})
        nodes = client.get("/graph/nodes").json()["nodes"]
        assert (tk, iso) in {(n["ticker"], n["expiry"]) for n in nodes}


def test_graph_nodes_ignores_inactive_provider_tickers():
    """GET /graph/nodes iterates the ACTIVE universe, not the provider watchlist:
    removing a ticker from the active set (it stays in provider.list_tickers())
    must not 500 (regression: forwards() on an inactive ticker raised)."""
    with TestClient(create_app(reference_date=REF_DATE)) as client:
        st = client.app.state.volfit
        dropped = st.active_tickers()[-1]
        st.remove_ticker(dropped)
        st.universe = None  # force a rebuild over the new active set
        resp = client.get("/graph/nodes")
        assert resp.status_code == 200
        assert all(n["ticker"] != dropped for n in resp.json()["nodes"])


def test_known_ticker_accepts_active_and_provider(state):
    """A user-added ticker (in the active set, not the provider watchlist) is a
    known ticker for read-path guards — so market/history/graph don't 404 it."""
    active = state.active_tickers()
    assert state.known_ticker(active[0]) is True
    assert state.known_ticker("DEFINITELY_NOT_A_TICKER") is False
    # Simulate a user-added ticker present only in the active set.
    state._active_tickers = active + ["NVDA"]
    assert "NVDA" not in state.provider.list_tickers()
    assert state.known_ticker("NVDA") is True


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


# ------------------------------------------------ U3 unified what-if pulses
def test_synthetic_pulse_replaces_the_calibration_feed(primed):
    """A typed pulse is THE observation set: the pulsed node is pinned to
    prior + shift (hypothesis-firm), carries the typed innovation, and no
    other node is an observation — the lit-calibration feed is replaced."""
    from volfit.api.schemas import SyntheticObservation

    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[1]
    resp = extrapolate(
        primed,
        GraphExtrapolateRequest(
            syntheticObservations=[
                SyntheticObservation(ticker=tk, expiry=iso, dAtmVol=0.01)
            ]
        ),
    )
    by = {(n.ticker, n.expiry): n for n in resp.nodes}
    pulsed = by[(tk, iso)]
    assert pulsed.calibrated is True
    assert pulsed.innovationBp == pytest.approx(100.0, abs=1e-6)
    assert pulsed.postAtmVol == pytest.approx(pulsed.priorAtmVol + 0.01, abs=5e-4)
    others = [n for n in resp.nodes if (n.ticker, n.expiry) != (tk, iso)]
    assert all(not n.calibrated and n.innovationBp is None for n in others)
    # The pulse propagates: a same-ticker neighbour moves off its prior.
    neighbour = by[(tk, _isos(primed, tk)[0])]
    assert abs(neighbour.shiftBp) > 1.0


def test_synthetic_pulse_fits_nothing_and_records_nothing(primed, monkeypatch):
    """The what-if never triggers slice fits and never persists innovations —
    non-persisting by construction (P5b U3)."""
    from volfit.api import graph_extrapolation as gx
    from volfit.api.schemas import SyntheticObservation

    def _no_fit(*a, **k):
        pytest.fail("what-if must not trigger fit_or_get")

    monkeypatch.setattr(gx, "fit_or_get", _no_fit)
    monkeypatch.setattr(
        primed,
        "record_graph_innovations",
        lambda *a, **k: pytest.fail("what-if must not record innovations"),
    )
    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[0]
    resp = extrapolate(
        primed,
        GraphExtrapolateRequest(
            syntheticObservations=[
                SyntheticObservation(ticker=tk, expiry=iso, dAtmVol=0.005)
            ]
        ),
    )
    assert any(n.calibrated for n in resp.nodes)


def test_synthetic_pulse_is_mode_aware(primed):
    """The same pulse runs the ACTIVE operator: under precision messages the
    adjacent shorter expiry receives β·z with β = T_informer/T_receiver
    (αT=1, desk amplitude, consistent routes ⇒ exact transmission)."""
    from volfit.api.schemas import SyntheticObservation

    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    t = {
        iso: (date.fromisoformat(iso) - REF_DATE).days / 365.25 for iso in isos[:2]
    }
    pulse = SyntheticObservation(ticker=tk, expiry=isos[1], dAtmVol=0.01)
    resp = extrapolate(
        primed,
        GraphExtrapolateRequest(
            flatAtm=True,
            propagationMode="precision_messages",
            syntheticObservations=[pulse],
        ),
    )
    by = {(n.ticker, n.expiry): n for n in resp.nodes}
    assert by[(tk, isos[1])].shiftBp == pytest.approx(100.0, rel=1e-3)
    beta = t[isos[1]] / t[isos[0]]  # informer = the longer maturity
    assert by[(tk, isos[0])].shiftBp == pytest.approx(100.0 * beta, rel=0.02)

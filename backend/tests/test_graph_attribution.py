"""Graph attribution: the exact per-lit-node decomposition of a posterior move.

The update is linear-Gaussian, so a node's shift is literally
``sum_j K[i,j] * d[j]`` — the attribution readout must reproduce the displayed
posterior to solver precision (arithmetic, not a heuristic). Locks the
posterior seam (GraphPosterior.attribution), the drill-in payload
(GraphNodeSmile.attribution + the folded remainder), ordering/capping, the
explicit-edge beta context, and the HTTP route.
"""

from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from volfit.api import priors
from volfit.api.graph_reconstruct import node_smile
from volfit.api.schemas import GraphEdgeInput, GraphExtrapolateRequest
from volfit.api.state import AppState
from volfit.graph.posterior import posterior_update

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def primed() -> AppState:
    state = AppState(REF_DATE)
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    return state


def _isos(state, tk):
    return [e.isoformat() for e in sorted(state.forwards(tk))]


# ------------------------------------------------------------ posterior seam
def test_attribution_is_exact_on_a_small_system():
    """Every node's contributions sum to its posterior shift, and the recovered
    innovation is the raw observed-node innovation y - mu^-."""
    cov = np.array([[2.0, 0.8, 0.3], [0.8, 1.5, 0.5], [0.3, 0.5, 1.0]])
    prior = SimpleNamespace(covariance=cov)
    baseline = np.array([0.20, 0.22, 0.25])
    p0 = np.full(3, 1e4)
    observed = np.array([0, 2])
    y = np.array([0.23, 0.24])
    r = np.full(2, 50.0)
    post = posterior_update(prior, baseline, p0, observed, y, r)

    for i in range(3):
        gain, innovation, contrib = post.attribution(i)
        shift = post.mean[i] - baseline[i]
        np.testing.assert_allclose(contrib.sum(), shift, rtol=0.0, atol=1e-14)
        assert gain.shape == innovation.shape == (2,)
    np.testing.assert_allclose(innovation, y - baseline[observed], atol=1e-14)


# --------------------------------------------------------- drill-in payload
def test_dark_node_attribution_sums_to_its_shift(primed):
    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    primed.set_node_lit(tk, isos[1], False)  # the dark target
    smile = node_smile(primed, tk, isos[1], GraphExtrapolateRequest())

    assert not smile.lit and smile.attribution  # lit neighbours exist
    total = sum(e.contributionBp for e in smile.attribution) + smile.attributionOthersBp
    shift_bp = (smile.postAtmVol - smile.priorAtmVol) * 1e4
    assert abs(total - shift_bp) < 1e-6  # arithmetic identity, not a fit

    mags = [abs(e.contributionBp) for e in smile.attribution]
    assert mags == sorted(mags, reverse=True)  # largest first
    assert len(smile.attribution) <= 20
    # Every contributor is a LIT node, never the dark target itself.
    assert all((e.ticker, e.expiry) != (tk, isos[1]) for e in smile.attribution)
    for e in smile.attribution:
        assert primed.node_lit(e.ticker, e.expiry)
        assert np.isfinite(e.gain) and np.isfinite(e.innovationBp)
        assert abs(e.contributionBp - e.gain * e.innovationBp) < 1e-9


def test_lit_node_attribution_also_exact(primed):
    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[0]
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    assert smile.lit
    total = sum(e.contributionBp for e in smile.attribution) + smile.attributionOthersBp
    shift_bp = (smile.postAtmVol - smile.priorAtmVol) * 1e4
    assert abs(total - shift_bp) < 1e-6
    # A pinned lit node's own observation appears among its contributors.
    assert any((e.ticker, e.expiry) == (tk, iso) for e in smile.attribution)


def test_explicit_edge_beta_rides_as_context(primed):
    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    primed.set_node_lit(tk, isos[1], False)
    request = GraphExtrapolateRequest(
        edges=[
            GraphEdgeInput(
                fromTicker=tk, fromExpiry=isos[1], toTicker=tk, toExpiry=isos[0],
                weight=5.0, betaAtmVol=0.7,
            )
        ]
    )
    smile = node_smile(primed, tk, isos[1], request)
    by_key = {(e.ticker, e.expiry): e for e in smile.attribution}
    neighbour = by_key.get((tk, isos[0]))
    assert neighbour is not None
    assert neighbour.edgeBeta == pytest.approx(0.7)
    # Non-adjacent contributors carry no direct-edge context.
    assert all(e.edgeBeta is None for k, e in by_key.items() if k != (tk, isos[0]))


def test_attribution_over_http(primed):
    from fastapi.testclient import TestClient

    from volfit.api import create_app

    client = TestClient(create_app(reference_date=REF_DATE))
    tk = "ALPHA"
    u = client.get("/universe").json()
    iso = u["expiries"][tk][0]["expiry"]
    body = client.get(f"/graph/extrapolate/nodes/{tk}/{iso}").json()
    assert "attribution" in body and isinstance(body["attribution"], list)
    if body["attribution"]:
        entry = body["attribution"][0]
        assert set(entry) >= {"ticker", "expiry", "innovationBp", "gain", "contributionBp"}

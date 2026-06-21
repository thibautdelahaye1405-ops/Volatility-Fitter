"""Reconstructed node smiles + quote comparison (plan Phase 5).

Drilling into a node returns its full extrapolated smile (posterior curve + band),
the transported-prior and lit-calibration overlays, the market quotes, and
quote-comparison metrics. Reconstruction is arb-free by construction. Standardized
residuals are computed for quoted DARK nodes only (a lit node is pinned, not a
held-out test).
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_reconstruct import node_smile
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


def _isos(state, tk):
    return [e.isoformat() for e in sorted(state.forwards(tk))]


def test_reconstructed_lit_node_matches_its_calibration(primed):
    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[0]
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    assert smile.lit and smile.calibrated
    assert len(smile.post) > 0
    assert len(smile.litCalibration) == len(smile.post)
    # Pinned to its own calibration -> ATM residual ~ 0.
    assert abs(smile.metrics.atmResidualBp) < 30.0
    assert smile.metrics.rmsVol < 0.02


def test_reconstruction_is_arbitrage_free_and_finite(primed):
    """A non-empty post curve means build_slice accepted the retarget (A_R < 1),
    i.e. a genuine density; vols must be finite and positive."""
    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[1]
    primed.set_node_lit(tk, iso, False)  # a dark node
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    assert len(smile.post) > 0
    ks = np.array([p.k for p in smile.post])
    vols = np.array([p.vol for p in smile.post])
    assert np.all(np.isfinite(vols))
    assert np.all(vols > 0.0)
    # The level-uncertainty band straddles the posterior at the money.
    atm = int(np.argmin(np.abs(ks)))
    lo = np.array([p.vol for p in smile.postBandLo])
    hi = np.array([p.vol for p in smile.postBandHi])
    assert lo[atm] <= vols[atm] <= hi[atm]


def test_quote_metrics_present_and_bounded(primed):
    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[0]
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    m = smile.metrics
    assert m is not None
    assert m.nQuotes == len(smile.quotes) > 0
    assert m.rmsVol >= 0.0
    assert 0.0 <= m.insideSpreadHitRate <= 1.0


def test_standardized_residual_dark_only(primed):
    tk = primed.active_tickers()[0]
    lit_iso, dark_iso = _isos(primed, tk)[0], _isos(primed, tk)[2]
    primed.set_node_lit(tk, dark_iso, False)

    lit = node_smile(primed, tk, lit_iso, GraphExtrapolateRequest())
    dark = node_smile(primed, tk, dark_iso, GraphExtrapolateRequest())
    assert lit.metrics.standardizedResidual is None  # pinned, not a held-out test
    assert dark.metrics.standardizedResidual is not None
    assert np.isfinite(dark.metrics.standardizedResidual)


def test_prior_overlay_present(primed):
    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[0]
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    assert len(smile.prior) > 0
    assert smile.priorSource == "active_transported"


def test_route_node_smile_smoke():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        tk = "ALPHA"
        iso = client.get("/universe").json()["expiries"][tk][1]["expiry"]
        client.post(f"/calibrate/{tk}/{iso}")
        resp = client.get(f"/graph/extrapolate/nodes/{tk}/{iso}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == tk
        assert len(body["post"]) > 0
        assert body["metrics"]["nQuotes"] > 0
        # Unknown node -> 404.
        assert client.get(f"/graph/extrapolate/nodes/{tk}/2099-01-15").status_code == 404

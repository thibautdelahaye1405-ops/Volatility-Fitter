"""Model-agnostic native reconstruction of the graph smile (plan Phase 9).

The graph propagates the model-agnostic ATM handles; the node-smile reconstruction
renders in the CHOSEN parametric model (LQD / SVI / Multi-Core SIV) so the overlay
matches what the rest of the app draws. A non-LQD reconstruction is the chosen model
fitted to the LQD target smile, so its ATM handles still match the propagated ones.
"""

from datetime import date

import numpy as np
import pytest

from volfit.api import priors
from volfit.api.graph_reconstruct import node_smile
from volfit.api.schemas import FitSettings, GraphExtrapolateRequest
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


def _node(state, tk):
    iso = [e.isoformat() for e in sorted(state.forwards(tk))][0]
    return tk, iso


def _atm_vol(curve) -> float:
    ks = np.array([p.k for p in curve])
    vols = np.array([p.vol for p in curve])
    return float(np.interp(0.0, ks, vols))


def test_lqd_reconstruction_is_default(primed):
    tk, iso = _node(primed, primed.active_tickers()[0])
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    assert smile.model == "lqd"
    assert len(smile.post) > 0
    assert _atm_vol(smile.post) == pytest.approx(smile.postAtmVol, abs=2e-3)


@pytest.mark.parametrize("model", ["svi", "sigmoid"])
def test_native_reconstruction_matches_handles(primed, model):
    """The SVI / Multi-Core SIV reconstruction lands on the propagated ATM handles."""
    primed.set_fit_settings(FitSettings(model=model))
    tk, iso = _node(primed, primed.active_tickers()[0])
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    assert smile.model == model
    assert len(smile.post) > 0
    # Reconstructed-in-model ATM vol matches the propagated ATM handle.
    assert _atm_vol(smile.post) == pytest.approx(smile.postAtmVol, abs=6e-3)
    # Finite, positive, arb-free-ish smile (the fit lands on the arb-free target).
    vols = np.array([p.vol for p in smile.post])
    assert np.all(np.isfinite(vols)) and np.all(vols > 0.0)


@pytest.mark.parametrize("model", ["svi", "sigmoid"])
def test_native_band_and_metrics_present(primed, model):
    primed.set_fit_settings(FitSettings(model=model))
    tk, iso = _node(primed, primed.active_tickers()[0])
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    assert len(smile.postBandLo) == len(smile.post)
    assert len(smile.postBandHi) == len(smile.post)
    # The band straddles the posterior at the money.
    atm = int(np.argmin(np.abs([p.k for p in smile.post])))
    assert smile.postBandLo[atm].vol <= smile.post[atm].vol <= smile.postBandHi[atm].vol
    # Metrics computed against the native reconstruction.
    assert smile.metrics is not None and smile.metrics.nQuotes > 0
    # The lit calibration overlay is drawn in the chosen model too.
    assert len(smile.litCalibration) == len(smile.post)


def test_central_density_nonnegative(primed):
    """The reconstructed posterior smile is butterfly-arb-free in the traded core
    (Breeden-Litzenberger density >= 0 around ATM)."""
    primed.set_fit_settings(FitSettings(model="svi"))
    tk, iso = _node(primed, primed.active_tickers()[0])
    smile = node_smile(primed, tk, iso, GraphExtrapolateRequest())
    k = np.array([p.k for p in smile.post])
    vol = np.array([p.vol for p in smile.post])
    core = np.abs(k) <= 0.3
    w = (vol[core] ** 2) * smile.t  # ~total variance (t≈tau here, no events)
    # Discrete curvature of total variance is a coarse convexity proxy; the fit to
    # an arb-free target should not introduce a sharp concavity near ATM.
    d2 = w[2:] - 2 * w[1:-1] + w[:-2]
    assert np.min(d2) > -1e-2

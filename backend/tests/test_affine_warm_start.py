"""Stage 2 — warm starts for the affine local-vol calibration.

Two layers:
  * ``_seed_theta`` (pure): builds theta0 from the previous calibrated surface —
    direct reuse on a matching vertex grid, linear interpolation onto a changed
    grid, flat fallback otherwise — always clipped to the box.
  * end-to-end: a second ``calibrate_affine_surface`` warm-starts from the first
    (``seed_source`` flips flat -> prev-affine) and converges in far fewer evals,
    while the converged surface is unchanged (the seed is decoupled from
    ``theta_ref``, so it changes only the path, not the optimum).
"""

from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from volfit.api import affine_fit
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _prev(t_nodes, x_nodes, theta):
    """A minimal stand-in for the cached AffineFitResponse (localVol = sqrt θ)."""
    return SimpleNamespace(
        tNodes=list(t_nodes),
        xNodes=list(x_nodes),
        localVol=[[float(np.sqrt(v)) for v in row] for row in theta],
    )


# ------------------------------------------------------------- _seed_theta
def test_seed_theta_flat_when_no_previous():
    t = np.array([0.0, 0.5, 1.0])
    x = np.array([0.8, 1.0, 1.2])
    seed, src = affine_fit._seed_theta(None, t, x, 0.04, 0.005, 0.20)
    assert src == "flat"
    assert seed.shape == (3, 3) and np.allclose(seed, 0.04)


def test_seed_theta_reuses_matching_grid():
    t = np.array([0.0, 0.5, 1.0])
    x = np.array([0.8, 1.0, 1.2])
    theta = np.array([[0.05, 0.04, 0.045], [0.06, 0.05, 0.055], [0.07, 0.06, 0.065]])
    seed, src = affine_fit._seed_theta(_prev(t, x, theta), t, x, 0.04, 0.005, 0.20)
    assert src == "prev-affine"
    assert np.allclose(seed, theta)  # localVol -> sqrt -> square round-trips exactly


def test_seed_theta_clips_to_box():
    t = np.array([0.0, 1.0])
    x = np.array([0.8, 1.2])
    theta = np.array([[0.30, 0.001], [0.25, 0.002]])  # outside [0.005, 0.20]
    seed, src = affine_fit._seed_theta(_prev(t, x, theta), t, x, 0.04, 0.005, 0.20)
    assert src == "prev-affine"
    assert seed.max() <= 0.20 + 1e-12 and seed.min() >= 0.005 - 1e-12


def test_seed_theta_interpolates_changed_grid():
    pt = np.array([0.0, 1.0])
    px = np.array([0.8, 1.2])
    theta = np.array([[0.04, 0.06], [0.05, 0.07]])
    # New, finer grid covering the same span — interpolation, not reuse.
    t = np.array([0.0, 0.5, 1.0])
    x = np.array([0.8, 0.9, 1.0, 1.1, 1.2])
    seed, src = affine_fit._seed_theta(_prev(pt, px, theta), t, x, 0.04, 0.005, 0.20)
    assert src == "prev-affine-interp"
    assert seed.shape == (3, 5)
    # corners reproduce the source nodes; interior stays within the box
    assert seed[0, 0] == pytest.approx(0.04, abs=1e-12)
    assert seed[-1, -1] == pytest.approx(0.07, abs=1e-12)
    assert seed.min() >= 0.005 - 1e-12 and seed.max() <= 0.20 + 1e-12


def test_seed_theta_flat_on_shape_mismatch():
    t = np.array([0.0, 0.5, 1.0])
    x = np.array([0.8, 1.0, 1.2])
    bad = SimpleNamespace(tNodes=[0.0, 1.0], xNodes=[0.8, 1.2], localVol=[[0.2, 0.2, 0.2]])
    seed, src = affine_fit._seed_theta(bad, t, x, 0.04, 0.005, 0.20)
    assert src == "flat" and np.allclose(seed, 0.04)


# ------------------------------------------------------------- end-to-end
def test_recalibration_warm_starts_and_cuts_evals():
    """A second force-calibrate seeds from the first: seed_source flips, the eval
    count drops sharply, and the converged surface is unchanged."""
    state = AppState(REF_DATE)
    req = AffineFitRequest()

    r1 = affine_fit.calibrate_affine_surface(state, TICKER, req)
    d1 = affine_fit.last_affine_diagnostics(state, TICKER)
    r2 = affine_fit.calibrate_affine_surface(state, TICKER, req)
    d2 = affine_fit.last_affine_diagnostics(state, TICKER)

    assert d1.seed_source == "flat"
    assert d2.seed_source == "prev-affine"
    assert d2.nfev < d1.nfev  # warm start needs fewer optimizer evaluations
    # same optimum: warm start changes the path, not the calibrated surface
    assert np.allclose(np.array(r1.localVol), np.array(r2.localVol), atol=1e-3)

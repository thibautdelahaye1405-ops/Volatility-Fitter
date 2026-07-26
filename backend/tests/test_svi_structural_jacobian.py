"""Analytic STRUCTURAL-chart Jacobian agrees with finite differences (R3 follow-up).

Three layers, mirroring the R4 raw-chart guard (test_svi_jacobian.py):

  * the 5x5 chain matrix d(raw)/d(theta) of ``structural_chain`` matches a
    central FD of ``unpack_structural`` — including the saturation-clip
    subgradient (a clipped coordinate's column is exactly zero) and the exact
    raw-recovery identity (the chain call returns the SAME RawSVI);
  * the full gated residual Jacobian (``svi_residual_jacobian_structural``)
    matches an FD of the calibrator's residual under the structural chart for
    the mid fit, the band fit, and active calendar floor/ceiling rows;
  * the calibrator actually rides it: a structural fit converges to the same
    smile as before with the ~2-evals-per-step budget of an analytic LM
    (scipy's FD path costs 1 + P = 6 residual evals per step).
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.calib.band import BandTarget, band_residuals
from volfit.models.svi_jw.calibrate import _LEE_SLOPE_MAX, _penalties, calibrate_svi
from volfit.models.svi_jw.jacobian import svi_residual_jacobian_structural
from volfit.models.svi_jw.structural import (
    _THETA_SAT,
    pack_structural,
    structural_chain,
    unpack_structural,
)
from volfit.models.svi_jw.svi import RawSVI

T = 0.5
PW = 1e3
CAP = _LEE_SLOPE_MAX
MAW = 0.05

K = np.linspace(-0.4, 0.4, 21)
#: The structural-chart image of the admissible R4 test slice.
ADMISSIBLE = RawSVI(a=0.02, b=0.10, rho=-0.30, m=0.0, sigma=0.20)


# ------------------------------------------------------------- chain matrix
def _fd_chain(theta: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    """Central FD of unpack_structural: rows (a, b, rho, m, sigma) x cols theta."""
    fields = ("a", "b", "rho", "m", "sigma")
    j = np.empty((5, theta.size))
    for p in range(theta.size):
        d = np.zeros_like(theta)
        d[p] = eps
        hi = unpack_structural(theta + d, CAP)
        lo = unpack_structural(theta - d, CAP)
        j[:, p] = [(getattr(hi, f) - getattr(lo, f)) / (2 * eps) for f in fields]
    return j


def test_chain_matches_fd_at_generic_points():
    rng = np.random.default_rng(11)
    for _ in range(20):
        theta = rng.normal(scale=1.5, size=5)
        raw, chain = structural_chain(theta, CAP)
        np.testing.assert_allclose(chain, _fd_chain(theta), rtol=5e-5, atol=1e-8)
        # The chain call IS unpack_structural for the raw slice (exact).
        direct = unpack_structural(theta, CAP)
        for f in ("a", "b", "rho", "m", "sigma"):
            assert getattr(raw, f) == getattr(direct, f)


def test_chain_matches_fd_at_the_fitted_slice():
    theta = pack_structural(ADMISSIBLE, CAP)
    _, chain = structural_chain(theta, CAP)
    np.testing.assert_allclose(chain, _fd_chain(theta), rtol=5e-5, atol=1e-8)


def test_chain_saturation_columns_are_zero():
    """Beyond ±_THETA_SAT the lift is clipped constant — the column must be
    exactly zero (matching what an FD of the clipped unpack measures)."""
    theta = np.array([-(_THETA_SAT + 5.0), 0.3, 0.1, -0.5, _THETA_SAT + 5.0])
    _, chain = structural_chain(theta, CAP)
    assert np.all(chain[:, 0] == 0.0)  # l clipped
    assert np.all(chain[:, 4] == 0.0)  # q clipped
    assert chain[3, 2] == 1.0  # k* is never clipped
    # Unclipped columns still match FD.
    fd = _fd_chain(theta)
    np.testing.assert_allclose(chain[:, 1:4], fd[:, 1:4], rtol=5e-5, atol=1e-8)


# ------------------------------------------------- full residual Jacobian
def _residual(theta, k, w_quotes, sqrt_w, band, cal_k, cal_floor, sqrt_cal,
              ceil_k=None, ceil_w=None):
    """The gated residual under the STRUCTURAL chart, same order as calibrate.py."""
    raw = unpack_structural(theta, CAP)
    mv = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / T)
    if band is None:
        fit = sqrt_w * (mv - np.sqrt(w_quotes / T))
    else:
        fit = band_residuals(mv, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_w, MAW)
    res = np.concatenate((fit, _penalties(raw, PW, CAP)))
    if cal_k is not None:
        res = np.concatenate((res, sqrt_cal * np.maximum(cal_floor - raw.total_variance(cal_k), 0.0)))
    if ceil_k is not None:
        res = np.concatenate((res, sqrt_cal * np.maximum(raw.total_variance(ceil_k) - ceil_w, 0.0)))
    return res


def _fd_jac(theta, *args, eps=1e-6):
    base = _residual(theta, *args)
    j = np.empty((base.size, theta.size))
    for p in range(theta.size):
        d = np.zeros_like(theta)
        d[p] = eps
        j[:, p] = (_residual(theta + d, *args) - _residual(theta - d, *args)) / (2 * eps)
    return j


def _check(theta, band, cal_k, cal_floor, sqrt_cal, ceil_k=None, ceil_w=None):
    w_q = ADMISSIBLE.total_variance(K)
    sqrt_w = np.ones_like(K)
    args = (K, w_q, sqrt_w, band, cal_k, cal_floor, sqrt_cal, ceil_k, ceil_w)
    an = svi_residual_jacobian_structural(
        theta, K, T, sqrt_w, band, MAW, PW, CAP, cal_k, cal_floor, sqrt_cal,
        ceil_k, ceil_w,
    )
    fd = _fd_jac(theta, *args)
    assert an.shape == fd.shape
    np.testing.assert_allclose(an, fd, rtol=2e-4, atol=2e-6)


THETA0 = pack_structural(ADMISSIBLE, CAP)


def test_mid_fit():
    _check(THETA0, None, None, None, 0.0)


def test_band_fit():
    mid = np.sqrt(ADMISSIBLE.total_variance(K) / T)
    band = BandTarget(iv_lo=mid - 0.01, iv_mid=mid, iv_hi=mid + 0.01)
    _check(THETA0, band, None, None, 0.0)


def test_calendar_floor_active():
    cal_k = np.linspace(-0.2, 0.2, 9)
    cal_floor = ADMISSIBLE.total_variance(cal_k) + 0.01  # strictly above -> active
    _check(THETA0, None, cal_k, cal_floor, np.sqrt(1e6))


def test_calendar_ceiling_active():
    ceil_k = np.linspace(-0.2, 0.2, 9)
    ceil_w = ADMISSIBLE.total_variance(ceil_k) - 0.01  # strictly below -> active
    _check(THETA0, None, None, None, np.sqrt(1e6), ceil_k, ceil_w)


def test_penalty_rows_structurally_inert():
    """At any finite structural iterate both penalty rows are zero AND their
    Jacobian rows are zero — the fence is the chart, so there is no hinge for
    the subgradient to activate (rows N and N+1 of the mid-fit layout)."""
    rng = np.random.default_rng(3)
    for _ in range(10):
        theta = rng.normal(scale=2.0, size=5)
        raw = unpack_structural(theta, CAP)
        assert np.all(_penalties(raw, PW, CAP) == 0.0)
        an = svi_residual_jacobian_structural(
            theta, K, T, np.ones_like(K), None, MAW, PW, CAP, None, None, 0.0
        )
        assert np.all(an[K.size : K.size + 2] == 0.0)


# ------------------------------------------------------ calibrator adoption
def test_structural_fit_rides_the_analytic_jacobian():
    """Same smile as the FD era, at the analytic evaluation budget: LM with a
    supplied Jacobian costs ~2 residual evals per step, so the clean-board
    fit lands far below the FD path's 30-86 eval range (chart spot-check,
    ROADMAP 2026-07-24) while still nailing the quotes."""
    k = np.linspace(-0.35, 0.30, 25)
    lab = RawSVI(a=0.010625, b=0.07289, rho=-0.5, m=0.05831, sigma=0.10100)
    fit = calibrate_svi(k, lab.total_variance(k), 0.5, chart="structural")
    assert fit.success
    assert fit.max_iv_error * 1e4 < 0.01  # quotes reproduced to < 0.01 bp
    assert fit.n_evaluations < 30  # analytic budget (FD spot-check: 30-86)

"""Analytic SVI Jacobian agrees with finite differences (FINDINGS R4 guard).

The closed-form Jacobian (``svi_residual_jacobian``) must match a central finite-
difference of the SAME residual blocks the calibrator builds — for the mid fit, the
band fit, and the calendar floor, and for both the inactive (penalty == 0) and active
(penalty > 0) regimes of the no-arb subgradients. Tested away from the hinge kinks,
where the subgradient is the true derivative.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.band import BandTarget, band_residuals
from volfit.models.svi_jw.calibrate import _penalties, _unpack
from volfit.models.svi_jw.jacobian import svi_residual_jacobian
from volfit.models.svi_jw.svi import RawSVI

T = 0.5
PW = 1e3
LEE = 2.0
MAW = 0.05


def _residual(theta, k, w_quotes, sqrt_w, band, cal_k, cal_floor, sqrt_cal):
    """The gated residual (fit + 2 penalties + calendar), same order as calibrate.py."""
    raw = _unpack(theta)
    mv = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / T)
    if band is None:
        fit = sqrt_w * (mv - np.sqrt(w_quotes / T))
    else:
        fit = band_residuals(mv, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_w, MAW)
    res = np.concatenate((fit, _penalties(raw, PW, LEE)))
    if cal_k is not None:
        res = np.concatenate((res, sqrt_cal * np.maximum(cal_floor - raw.total_variance(cal_k), 0.0)))
    return res


def _fd_jac(theta, *args, eps=1e-6):
    """Central finite-difference Jacobian of ``_residual``."""
    base = _residual(theta, *args)
    j = np.empty((base.size, theta.size))
    for p in range(theta.size):
        d = np.zeros_like(theta)
        d[p] = eps
        j[:, p] = (_residual(theta + d, *args) - _residual(theta - d, *args)) / (2 * eps)
    return j


def _theta(raw: RawSVI) -> np.ndarray:
    return np.array([raw.a, np.log(np.expm1(raw.b)), np.arctanh(raw.rho), raw.m, np.log(raw.sigma)])


K = np.linspace(-0.4, 0.4, 21)
ADMISSIBLE = RawSVI(a=0.02, b=0.10, rho=-0.30, m=0.0, sigma=0.20)  # penalties inactive


def _check(theta, band, cal_k, cal_floor, sqrt_cal):
    w_q = ADMISSIBLE.total_variance(K)
    sqrt_w = np.ones_like(K)
    args = (K, w_q, sqrt_w, band, cal_k, cal_floor, sqrt_cal)
    an = svi_residual_jacobian(theta, K, T, sqrt_w, band, MAW, PW, LEE, cal_k, cal_floor, sqrt_cal)
    fd = _fd_jac(theta, *args)
    assert an.shape == fd.shape
    np.testing.assert_allclose(an, fd, rtol=2e-4, atol=2e-6)


def test_mid_fit_admissible():
    _check(_theta(ADMISSIBLE), None, None, None, 0.0)


def test_band_fit_admissible():
    mid = np.sqrt(ADMISSIBLE.total_variance(K) / T)
    band = BandTarget(iv_lo=mid - 0.01, iv_mid=mid, iv_hi=mid + 0.01)
    _check(_theta(ADMISSIBLE), band, None, None, 0.0)


def test_calendar_floor_active():
    # A floor above the model variance on part of the range -> active calendar rows.
    cal_k = np.linspace(-0.2, 0.2, 9)
    cal_floor = ADMISSIBLE.total_variance(cal_k) + 0.01  # strictly above -> all active
    _check(_theta(ADMISSIBLE), None, cal_k, cal_floor, np.sqrt(1e6))


def test_lee_penalty_active():
    # b large -> wing = b(1+|rho|) > 2 -> the Lee subgradient row is active.
    violating = RawSVI(a=0.02, b=1.6, rho=-0.30, m=0.0, sigma=0.20)
    assert violating.b * (1 + abs(violating.rho)) > LEE
    _check(_theta(violating), None, None, None, 0.0)


def test_min_variance_penalty_active():
    # a negative -> min_var = a + b sigma sqrt(1-rho^2) < 0 -> active row.
    violating = RawSVI(a=-0.05, b=0.05, rho=-0.30, m=0.0, sigma=0.20)
    assert violating.a + violating.b * violating.sigma * np.sqrt(1 - violating.rho**2) < 0
    _check(_theta(violating), None, None, None, 0.0)

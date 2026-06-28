"""Analytic Multi-Core SIV Jacobian agrees with finite differences (FINDINGS R5 guard).

The closed-form Jacobian (``siv_residual_jacobian``) must match a central finite
difference of the SAME residual blocks the calibrator builds — the base (R=0) fit,
a multi-core (R=2) fit, the band objective, and the calendar floor — including the
hat partials (alpha / c / h / kappa) and the base partials (v0 / s0 / k0 / z0 /
kappa_p / kappa_c). Tested away from the band/calendar hinge kinks.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.band import BandTarget, band_residuals
from volfit.models.sigmoid.calibrate import _V_FLOOR, _eval_v
from volfit.models.sigmoid.jacobian import siv_residual_jacobian

T = 0.5
RIDGE = 1e-2
MAW = 0.05
Z = np.linspace(-3.0, 3.0, 25)

# A well-behaved base (v0,s0,k0,z0,kappa_p,kappa_c) + two hats (alpha,c,h,kappa).
BASE = np.array([0.04, 0.01, 0.30, 0.10, 4.0, 3.0])
HATS = np.array([0.20, -1.0, 0.40, 5.0, -0.15, 1.2, 0.50, 6.0])


def _residual(theta, n_cores, vol_q, sqrt_w, band, cal_z, cal_floor, sqrt_cal):
    """The gated residual (fit + ridge + calendar), same order as calibrate._fit."""
    mv = np.sqrt(np.maximum(_eval_v(theta, Z, n_cores), _V_FLOOR))
    if band is None:
        res = sqrt_w * (mv - vol_q)
    else:
        res = band_residuals(mv, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_w, MAW)
    if n_cores:
        res = np.concatenate([res, np.sqrt(RIDGE) * theta[6::4][:n_cores]])
    if cal_z is not None:
        w = np.maximum(_eval_v(theta, cal_z, n_cores), _V_FLOOR) * T
        res = np.concatenate([res, sqrt_cal * np.maximum(cal_floor - w, 0.0)])
    return res


def _fd(theta, *args, eps=1e-6):
    base = _residual(theta, *args)
    j = np.empty((base.size, theta.size))
    for p in range(theta.size):
        d = np.zeros_like(theta)
        d[p] = eps
        j[:, p] = (_residual(theta + d, *args) - _residual(theta - d, *args)) / (2 * eps)
    return j


def _check(theta, n_cores, band, cal_z, cal_floor, sqrt_cal):
    vol_q = np.sqrt(np.maximum(_eval_v(theta, Z, n_cores), _V_FLOOR)) + 0.001  # off the model
    sqrt_w = np.ones_like(Z)
    args = (n_cores, vol_q, sqrt_w, band, cal_z, cal_floor, sqrt_cal)
    an = siv_residual_jacobian(theta, Z, n_cores, T, sqrt_w, band, MAW, RIDGE, cal_z, cal_floor, sqrt_cal)
    fd = _fd(theta, *args)
    assert an.shape == fd.shape
    np.testing.assert_allclose(an, fd, rtol=2e-4, atol=2e-6)


def test_base_only_mid():
    _check(BASE, 0, None, None, None, 0.0)


def test_two_cores_mid():
    _check(np.concatenate([BASE, HATS]), 2, None, None, None, 0.0)


def test_two_cores_band():
    # A band entirely above the model -> violation rows active (sign -1), smooth anchor.
    theta = np.concatenate([BASE, HATS])
    mv = np.sqrt(np.maximum(_eval_v(theta, Z, 2), _V_FLOOR))
    band = BandTarget(iv_lo=mv + 0.01, iv_mid=mv + 0.015, iv_hi=mv + 0.02)
    _check(theta, 2, band, None, None, 0.0)


def test_calendar_active():
    theta = np.concatenate([BASE, HATS])
    cal_z = np.linspace(-1.5, 1.5, 9)
    cal_floor = np.maximum(_eval_v(theta, cal_z, 2), _V_FLOOR) * T + 0.01  # above -> all active
    _check(theta, 2, None, cal_z, cal_floor, np.sqrt(1e6))

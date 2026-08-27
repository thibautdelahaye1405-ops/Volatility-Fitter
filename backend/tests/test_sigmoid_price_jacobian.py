"""MCS price-space analytic Jacobian (ROADMAP rider "MCS analytic price-space
Jacobian", 2026-08-27): with overlayPriceResiduals on, the Multi-Core SIV fit
keeps its ANALYTIC Jacobian — the data rows chained row-wise through dC/dw
(models.sigmoid.price_rows) — instead of riding scipy's "2-point" FD.

Locks: (1) the analytic closure ``calibrate._fit`` hands scipy agrees with a
central finite difference of the REAL residual closure (raw and structural
charts, mid and band objectives — both captured through a stub solver, not a
mirror); (2) ``calibrate_sigmoid(price_residuals=True)`` lands on the same
smile as a fit forced through the FD path; (3) the vol-space rows are
byte-identical to their pre-rider formula (price_residuals off is untouched).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from volfit.calib.band import BandTarget, price_targets
from volfit.models.sigmoid import calibrate as calibrate_mod
from volfit.models.sigmoid.calibrate import _V_FLOOR, _eval_v, calibrate_sigmoid
from volfit.models.sigmoid.jacobian import _model_v_grad, siv_residual_jacobian
from volfit.models.sigmoid.structural import pack_structural_mcs

T = 0.5
SIGMA_REF = 0.2
SCALE = float(np.sqrt(T)) / SIGMA_REF  # k-space slope per z-space slope
CAP = 1.95
RIDGE, MAW = 1e-2, 0.05
Z = np.linspace(-3.0, 3.0, 25)
K = Z * SIGMA_REF * np.sqrt(T)
ONES = np.ones_like(Z)

# The test_sigmoid_jacobian point: a well-behaved base + two hats.
BASE = np.array([0.04, 0.01, 0.30, 0.10, 4.0, 3.0])
HATS = np.array([0.20, -1.0, 0.40, 5.0, -0.15, 1.2, 0.50, 6.0])
THETA_RAW = np.concatenate([BASE, HATS])
MODEL_VOL = np.sqrt(np.maximum(_eval_v(THETA_RAW, Z, 2), _V_FLOOR))


def _targets(with_band):
    """Quotes off the model (band entirely above it, so every hinge row is
    active and away from its kink) and the calibrator's frozen price rows."""
    if with_band:
        band = BandTarget(
            iv_lo=MODEL_VOL + 0.01, iv_mid=MODEL_VOL + 0.015, iv_hi=MODEL_VOL + 0.02
        )
        vol_q = band.iv_mid
    else:
        band, vol_q = None, MODEL_VOL + 0.001
    return band, vol_q, (K, *price_targets(K, vol_q**2 * T, T, band))


def _capture_closures(monkeypatch, theta, band, vol_q, price_rows, chart_cap):
    """Run ``_fit`` against a stub solver and hand back the residual and
    Jacobian closures it was given — the real row builders, not a mirror."""
    got = {}

    def stub(fun, x0, **kw):
        got["fun"], got["jac"] = fun, kw["jac"]
        return SimpleNamespace(x=x0)

    monkeypatch.setattr(calibrate_mod, "least_squares", stub)
    n = theta.size
    calibrate_mod._fit(
        theta, np.full(n, -np.inf), np.full(n, np.inf), Z, vol_q, ONES, 2,
        band=band, ridge=RIDGE, mid_anchor_weight=MAW, t=T,
        chart_cap=chart_cap, slope_scale=SCALE, price_rows=price_rows,
    )
    return got["fun"], got["jac"]


def _fd(fn, theta, eps=1e-6):
    base = fn(theta)
    j = np.empty((base.size, theta.size))
    for p in range(theta.size):
        d = np.zeros_like(theta)
        d[p] = eps
        j[:, p] = (fn(theta + d) - fn(theta - d)) / (2.0 * eps)
    return j


@pytest.mark.parametrize("with_band", [False, True])
@pytest.mark.parametrize("chart", ["raw", "structural"])
def test_mcs_price_jacobian_matches_fd(monkeypatch, chart, with_band):
    band, vol_q, pt = _targets(with_band)
    if chart == "raw":
        theta, cap = THETA_RAW, None
    else:
        theta = np.concatenate([pack_structural_mcs(BASE, CAP, SCALE), HATS])
        cap = CAP
    fun, jac = _capture_closures(monkeypatch, theta, band, vol_q, pt, cap)
    assert callable(jac)  # the gate no longer falls back to "2-point" in price mode
    an = jac(theta)
    fd = _fd(fun, theta)
    n_fit = 2 * Z.size if with_band else Z.size
    assert an.shape == fd.shape == (n_fit + 2, theta.size)  # data rows + 2 ridge rows
    np.testing.assert_allclose(an, fd, rtol=2e-4, atol=2e-6)


def _slice():
    """A smooth synthetic smile — skewed and convex, MCS-fittable but not
    exactly, so the fit has genuine residual structure."""
    t = 0.25
    k = np.linspace(-0.3, 0.3, 17)
    vol = 0.22 - 0.06 * k + 0.12 * k**2
    return k, vol**2 * t, t


@pytest.mark.parametrize("with_band", [False, True])
@pytest.mark.parametrize("chart", ["raw", "structural"])
def test_mcs_price_mode_analytic_matches_fd_fit(monkeypatch, chart, with_band):
    """The public price-mode fit (analytic gate) agrees with the same fit
    forced through scipy's finite differences to 1e-6 in vol."""
    k, w, t = _slice()
    band = None
    if with_band:
        mid = np.sqrt(w / t)
        band = BandTarget(iv_lo=mid - 0.004, iv_mid=mid, iv_hi=mid + 0.004)
    kw = dict(n_cores=0, band=band, chart=chart, price_residuals=True)
    analytic = calibrate_sigmoid(k, w, t, **kw)

    real_ls = calibrate_mod.least_squares

    def fd_ls(fun, x0, **kw_ls):
        kw_ls["jac"] = "2-point"  # every stage rides scipy's finite differences
        return real_ls(fun, x0, **kw_ls)

    monkeypatch.setattr(calibrate_mod, "least_squares", fd_ls)
    forced = calibrate_sigmoid(k, w, t, **kw)

    grid = np.linspace(-0.3, 0.3, 61)
    va = np.sqrt(analytic.implied_w(grid) / t)
    vf = np.sqrt(forced.implied_w(grid) / t)
    np.testing.assert_allclose(va, vf, rtol=0.0, atol=1e-6)


@pytest.mark.parametrize("with_band", [False, True])
def test_vol_mode_rows_untouched(with_band):
    """price_rows None (the toggle off): the vol-space data rows are
    BYTE-identical to the pre-rider formula sqrt_w · dv / (2 model_vol),
    floor-clamped — exact equality, not a tolerance."""
    band, _vol_q, _pt = _targets(with_band)
    v, dv = _model_v_grad(THETA_RAW, Z, 2)
    mv = np.sqrt(np.maximum(v, _V_FLOOR))
    dmv = dv / (2.0 * mv)[:, None]
    dmv[v <= _V_FLOOR] = 0.0
    j = siv_residual_jacobian(THETA_RAW, Z, 2, T, ONES, band, MAW, RIDGE, None, None, 0.0)
    if with_band:  # band above the model: violation sign -1, then the anchor rows
        expect = np.vstack([-dmv, np.sqrt(MAW) * dmv])
    else:
        expect = dmv
    assert j.shape[0] == expect.shape[0] + 2  # + the two ridge rows
    np.testing.assert_array_equal(j[: expect.shape[0]], expect)

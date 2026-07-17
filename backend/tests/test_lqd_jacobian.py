"""Analytic LQD-calibration Jacobian (ROADMAP perf #2).

The analytic Jacobian must agree with the finite-difference Jacobian scipy would
otherwise build (so trf converges to the same optimum, just faster). Checked
column-wise against a 3-point FD for the mid, calendar, and band configurations,
plus the infeasible-tail branch shape.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative

from volfit.calib.band import BandTarget
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.lqd.calibrate import _residuals, logistic_init
from volfit.models.lqd.jacobian import residual_jacobian

T = 0.5
K = np.linspace(-0.30, 0.30, 11)
W = 0.20**2 * T * (1.0 + 0.6 * K**2 - 0.12 * K)
TARGET = black_call(K, W)
SIGMA = np.sqrt(W / T)
INV_VEGA = 1.0 / (black_vega_sigma(K, SIGMA, T) + 1e-4)
SW = np.ones_like(K)
N_ORDER = 6
_N = np.arange(2, N_ORDER + 1, dtype=float)
REG = np.sqrt(1e-6) * np.where(_N >= 4, _N**1.0, 0.0)


def _theta():
    th = logistic_init(float(np.interp(0.0, K, W)), N_ORDER).to_vector()
    return th + 0.02 * np.arange(th.size)


def _args(cal_z=None, cal_floor=None, cal_k=None, cal_pfloor=None, cal_taper=None,
          plo=None, phi=None):
    # trailing None×4 = var_swap, prior_anchor, prior_var_swap, operator_prior
    return (K, TARGET, INV_VEGA, SW, REG, cal_z, cal_floor, 1e6,
            cal_k, cal_pfloor, cal_taper, plo, phi,
            0.90, 50.0, 0.05, None, None, None, None, 2001)


def _max_rel(theta, args):
    jan = residual_jacobian(theta, *args)
    jfd = approx_derivative(lambda th: _residuals(th, *args), theta, method="3-point")
    assert jan.shape == jfd.shape
    return float(np.abs(jan - jfd).max() / (np.abs(jfd).max() + 1e-12))


def test_jacobian_matches_fd_mid():
    assert _max_rel(_theta(), _args()) < 1e-3


def test_jacobian_matches_fd_calendar():
    cal_z = np.array([-3.0, -1.0, 0.0, 1.0, 3.0])
    cal_floor = np.array([0.95, 0.7, 0.45, 0.2, 0.02])
    assert _max_rel(_theta(), _args(cal_z=cal_z, cal_floor=cal_floor)) < 1e-3


def test_jacobian_matches_fd_confined_price_floor():
    """The support-confined price-space block (symmetric-surface Phase 0):
    tapered relu(price_floor - C(k)) rows, active by construction (floor set
    just above the model's own call curve at the constraint strikes)."""
    from volfit.models.lqd.basis import LQDParams
    from volfit.models.lqd.quadrature import build_slice

    theta = _theta()
    cal_k = np.linspace(-0.2, 0.2, 7)
    slice_ = build_slice(LQDParams.from_vector(theta))
    cal_pfloor = np.asarray(slice_.call_price(cal_k)) + 5e-4  # active rows
    cal_taper = np.linspace(0.3, 1.0, cal_k.size)
    args = _args(cal_k=cal_k, cal_pfloor=cal_pfloor, cal_taper=cal_taper)
    assert _max_rel(theta, args) < 1e-3


def test_jacobian_matches_fd_band():
    band = BandTarget(iv_lo=SIGMA - 0.01, iv_mid=SIGMA, iv_hi=SIGMA + 0.01)
    plo = black_call(K, band.iv_lo**2 * T)
    phi = black_call(K, band.iv_hi**2 * T)
    assert _max_rel(_theta(), _args(plo=plo, phi=phi)) < 1e-3


def test_infeasible_tail_branch_shape_and_finite():
    # R large -> A_R = e^{R + ...} >> 1 -> the infeasible (except) residual branch.
    theta = _theta()
    theta[1] = 1.5  # R
    jac = residual_jacobian(theta, *_args())
    assert jac.shape == (K.size + REG.size + 1, theta.size)  # fit + reg + barrier
    assert np.all(np.isfinite(jac))


def test_barrier_residual_finite_for_wild_tail_scale():
    """The A_R softplus barrier must stay finite for a wild trial theta:
    log1p(exp(x)) overflowed to inf past x ~ 709 (R = 20 gives A_R ~ e^20,
    x ~ 2.4e10), poisoning trf's cost; logaddexp(0, x) is stable (~x)."""
    theta = _theta()
    theta[1] = 20.0  # R -> A_R ~ e^20: infeasible branch + huge barrier arg
    res = _residuals(theta, *_args())
    assert np.all(np.isfinite(res))


def test_analytic_and_fd_fits_agree():
    """calibrate_slice (analytic, default) reaches the same params as a forced-FD
    fit — same optimum, the Jacobian only changes the path."""
    from scipy.optimize import least_squares

    init = logistic_init(float(np.interp(0.0, K, W)), N_ORDER).to_vector()
    args = _args()
    kw = dict(args=args, method="trf", xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=4000)
    an = least_squares(_residuals, init, jac=residual_jacobian, **kw)
    fd = least_squares(_residuals, init, jac="2-point", **kw)
    assert an.x == pytest.approx(fd.x, abs=1e-5)

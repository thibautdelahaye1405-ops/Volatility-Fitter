"""Generalized tails — Phase 2 (calibration & policy layer) locks.

Docs/generalized_tails_calendar_roadmap.md Phase 2:

1. The analytic Jacobian matches finite differences at alpha != 0 — the
   tail-correction derivative branches (power-continuation T and dT/dlam),
   the saddle-guard infeasible mirror, and fits beyond the old lambda_+ < 1
   wall.
2. Charts: a "logistic" request degrades to the endpoint chart at
   alpha_+ > 0 (eq. rightchart) and the optimum is chart-independent.
3. calibrate_slice at (0, 0) is BYTE-identical to a call without the alpha
   kwargs; under a nonzero scenario it fits the reference strip, and the
   fitted params carry the exponents.
4. Full-stack scenario: a common-alpha two-expiry ladder passes the Phase 0
   certificate through its generalized power-tail candidates; the barrier
   is re-pointed at the saddle guard.
5. Policy plumbing: FitSettings bounds, service packaging into the fit task,
   the committed record carrying the exponents.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative

from volfit.calib.band import BandTarget
from volfit.calib.calendar import calendar_floor_targets
from volfit.calib.calendar_certificate import ledger_certificate
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.lqd.basis import lee_slopes
from volfit.models.lqd.calibrate import (
    _alpha_barrier,
    _residuals,
    calibrate_slice,
    logistic_init,
    prepare_residual_args,
)
from volfit.models.lqd.charts import build_chart
from volfit.models.lqd.jacobian import residual_jacobian
from volfit.models.lqd.quadrature import Z_MAX
from volfit.models.lqd.tails import EPS_TAIL

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
ALPHAS = (0.25, 0.40)  # an asymmetric nonzero scenario


def _theta():
    th = logistic_init(float(np.interp(0.0, K, W)), N_ORDER).to_vector()
    return th + 0.02 * np.arange(th.size)


def _args(alphas=ALPHAS, cal_z=None, cal_floor=None, cal_k=None,
          cal_pfloor=None, cal_taper=None, plo=None, phi=None, vs=None):
    return (K, TARGET, INV_VEGA, SW, REG, cal_z, cal_floor, 1e6,
            cal_k, cal_pfloor, cal_taper, plo, phi,
            0.90, 50.0, 0.05, vs, None, None, None, alphas, 2001)


def _max_rel(theta, args):
    jan = residual_jacobian(theta, *args)
    jfd = approx_derivative(lambda th: _residuals(th, *args), theta, method="3-point")
    assert jan.shape == jfd.shape
    return float(np.abs(jan - jfd).max() / (np.abs(jfd).max() + 1e-12))


# ------------------------------------------------- analytic Jacobian at alpha
def test_jacobian_matches_fd_alpha_mid():
    assert _max_rel(_theta(), _args()) < 1e-3


def test_jacobian_matches_fd_alpha_band_and_calendar():
    band = BandTarget(iv_lo=SIGMA - 0.01, iv_mid=SIGMA, iv_hi=SIGMA + 0.01)
    plo = black_call(K, band.iv_lo**2 * T)
    phi = black_call(K, band.iv_hi**2 * T)
    assert _max_rel(_theta(), _args(plo=plo, phi=phi)) < 1e-3
    cal_z = np.array([-3.0, -1.0, 0.0, 1.0, 3.0])
    cal_floor = np.array([0.95, 0.7, 0.45, 0.2, 0.02])
    assert _max_rel(_theta(), _args(cal_z=cal_z, cal_floor=cal_floor)) < 1e-3


def test_jacobian_matches_fd_beyond_the_old_wall():
    """lambda_+ > 1 is a legitimate iterate at alpha_+ > 0: the tail-mass
    derivative branches must stay FD-consistent where the exponential
    subclass would already have refused."""
    theta = _theta()
    theta[1] = 0.3  # R -> lambda_+ ~ e^{0.3+...} > 1
    assert _max_rel(theta, _args(alphas=(0.0, 0.5))) < 1e-3


def test_saddle_guard_mirrors_infeasible_branch():
    theta = _theta()
    # lambda_+ (Z+1)^{-a} > 1 - eps  <=>  the analytic path must reject
    # exactly where build_slice refuses (no crash, penalty-branch shapes).
    theta[1] = float(np.log(1.1 * (Z_MAX + 1.0) ** 0.25))
    args = _args(alphas=(0.0, 0.25))
    jac = residual_jacobian(theta, *args)
    assert jac.shape == (K.size + REG.size + 1, theta.size)
    assert np.all(np.isfinite(jac))
    assert np.all(np.isfinite(_residuals(theta, *args)))


def test_barrier_repointed_at_saddle_guard():
    c0, s0 = _alpha_barrier(0.90, 50.0, 0.0)
    assert (c0, s0) == (0.90, 50.0)  # alpha = 0: untouched (byte-identity)
    f = (1.0 - EPS_TAIL) * (Z_MAX + 1.0) ** 0.5
    c1, s1 = _alpha_barrier(0.90, 50.0, 0.5)
    assert c1 == pytest.approx(0.90 * f) and s1 == pytest.approx(50.0 / f)
    # prepare_residual_args applies the map before freezing the tuple.
    args, _ = prepare_residual_args(K, W, T, n_order=N_ORDER, alpha_right=0.5)
    assert args[13] == pytest.approx(c1) and args[14] == pytest.approx(s1)
    assert args[-2] == (0.0, 0.5) and args[-1] == 2001


# ------------------------------------------------------------ chart + fits
def test_logistic_chart_degrades_to_endpoint_at_positive_alpha():
    assert build_chart(N_ORDER, "logistic").name == "logistic"
    assert build_chart(N_ORDER, "logistic", alpha_right=0.25).name == "endpoint"
    assert build_chart(N_ORDER, "endpoint", alpha_right=0.25).name == "endpoint"
    assert build_chart(N_ORDER, "lr", alpha_right=0.25) is None


def test_alpha_zero_kwargs_are_byte_identical():
    plain = calibrate_slice(K, W, t=T, n_order=N_ORDER)
    tagged = calibrate_slice(K, W, t=T, n_order=N_ORDER,
                             alpha_left=0.0, alpha_right=0.0)
    assert plain.params.to_vector().tobytes() == tagged.params.to_vector().tobytes()
    assert plain.cost == tagged.cost and plain.n_evaluations == tagged.n_evaluations


def test_fit_under_alpha_scenario_and_chart_independence():
    fits = {
        coords: calibrate_slice(
            K, W, t=T, n_order=N_ORDER, coords=coords,
            alpha_left=0.25, alpha_right=0.25,
        )
        for coords in ("lr", "logistic")
    }
    for fit in fits.values():
        assert fit.success and fit.max_iv_error < 5e-3
        assert fit.params.alpha_left == 0.25 and fit.params.alpha_right == 0.25
        assert lee_slopes(fit.params) == (0.0, 0.0)
        assert fit.slice.martingale_check() == pytest.approx(1.0, abs=1e-9)
    assert fits["lr"].params.to_vector() == pytest.approx(
        fits["logistic"].params.to_vector(), abs=1e-5
    )


def test_gaussian_rate_scenario_fits():
    fit = calibrate_slice(K, W, t=T, n_order=N_ORDER, coords="logistic",
                          alpha_left=0.5, alpha_right=0.5)
    assert fit.success and fit.max_iv_error < 5e-3
    assert np.all(np.isfinite(fit.slice.call_price(np.linspace(-3.0, 3.0, 61))))


# --------------------------------------------------- stack + certificate
def test_common_alpha_stack_certifies_through_power_tails():
    """Two expiries under the common-alpha policy: the far fit under the
    near ledger floor, then the Phase 0 certificate — whose tail candidates
    now run the POWER continuation branch — certifies the pair."""
    a = dict(alpha_left=0.25, alpha_right=0.25)
    near = calibrate_slice(K, W, t=T, n_order=N_ORDER, coords="logistic", **a)
    w_far = W * 1.9  # comfortably dominating far expiry
    cal_z, cal_floor = calendar_floor_targets(near.slice)
    far = calibrate_slice(
        K, w_far, t=2 * T, n_order=N_ORDER, coords="logistic",
        calendar_z=cal_z, calendar_floor=cal_floor, **a,
    )
    cert = ledger_certificate(near.slice, far.slice)
    assert cert.certified(tol=1e-6)
    assert cert.tail_order_ok
    # Reversed pair: violation on the whole line, orders flipped.
    rev = ledger_certificate(far.slice, near.slice)
    assert rev.min_gap < 0.0
    assert not rev.tail_order_ok


def test_certificate_power_tail_candidate_beyond_grid():
    """Grid-identical equal-alpha slices whose lambda_+ disagree: the gap
    turns negative only beyond the boundary; the power-branch candidate must
    catch it (the alpha > 0 mirror of the Phase 0 exponential tail lock)."""
    import dataclasses

    from volfit.models.lqd.basis import LQDParams
    from volfit.models.lqd.quadrature import build_slice

    near = build_slice(LQDParams(L=np.log(0.12), R=np.log(0.10),
                                 a=np.zeros(0), alpha_left=0.25, alpha_right=0.25))
    far2 = dataclasses.replace(near, q_z=near.q_z + 0.5, a_right=near.a_right * 0.7)
    cert = ledger_certificate(near, far2)
    assert not cert.tail_order_right
    assert cert.min_gap < 0.0
    assert cert.z_star > float(near.z[-1])  # the argmin is the tail candidate
    # Unequal exponents across a pair (outside the policy): the order clause
    # is decided by the exponents alone — lighter far tail loses.
    lighter = dataclasses.replace(
        near, params=dataclasses.replace(near.params, alpha_right=0.4))
    cert2 = ledger_certificate(near, lighter)
    assert not cert2.tail_order_right
    cert3 = ledger_certificate(lighter, near)  # heavier far tail: fine
    assert cert3.tail_order_right


# ------------------------------------------------------------ policy plumbing
def test_fit_settings_bounds_and_service_packaging():
    from datetime import date

    from volfit.api import service
    from volfit.api.schemas import FitSettings
    from volfit.api.state import AppState

    with pytest.raises(ValueError):
        FitSettings(tailAlphaRight=0.6)
    with pytest.raises(ValueError):
        FitSettings(tailAlphaLeft=-0.1)

    state = AppState(date(2026, 6, 10))
    fs = state.fit_settings()
    assert fs.tailAlphaLeft == 0.0 and fs.tailAlphaRight == 0.0
    state.set_fit_settings(
        fs.model_copy(update={"tailAlphaLeft": 0.25, "tailAlphaRight": 0.25})
    )
    iso = sorted(state.forwards("ALPHA"))[0].isoformat()
    record = service.calibrate_node(state, "ALPHA", iso, "mid")
    params = record.result.params
    assert params.alpha_left == 0.25 and params.alpha_right == 0.25
    assert lee_slopes(params) == (0.0, 0.0)
    assert record.result.slice.martingale_check() == pytest.approx(1.0, abs=1e-9)

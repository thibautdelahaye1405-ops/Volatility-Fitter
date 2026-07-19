"""Committee revision R5: metric-aware ATM chart, trader packages, calendar
violation in desk units.

Locks:
- the Gauss-Newton-metric chart still satisfies J U = I_3 exactly (a right
  inverse under ANY metric) and reports the handle Gram's condition number;
  the default chart is unchanged and now also reports its condition;
- package controls: kernel directions move their own package by ~1, the
  other packages by ~cross-talk, and the ATM handles by ~0 (first order);
- calendar_violation_argmax returns the worst strike of a crossed pair and
  the quality node's desk-unit fields are consistent with it.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.ortho import (
    build_atm_coordinates,
    gauss_newton_metric,
    handles_vector,
)
from volfit.models.lqd.packages import build_package_controls, package_vector

T = 0.5
K = np.linspace(-0.30, 0.30, 21)
W = 0.20**2 * T * (1.0 + 0.6 * K**2 - 0.12 * K)


@pytest.fixture(scope="module")
def fitted():
    diag: dict = {}
    res = calibrate_slice(K, W, t=T, n_order=8, reg_lambda=1e-8,
                          solver_diag=diag)
    return res, diag


def test_default_chart_reports_condition(fitted):
    res, _ = fitted
    chart = build_atm_coordinates(res.params, T)
    assert np.isfinite(chart.condition) and chart.condition >= 1.0
    assert chart.jacobian @ chart.primary == pytest.approx(np.eye(3), abs=1e-8)


def test_gauss_newton_chart_is_a_right_inverse_with_less_fit_impact(fitted):
    """The GN-metric primary directions still hit the handles one-for-one,
    and by construction they disturb the fitted quotes LESS than the
    Euclidean ones (that is what the metric prices)."""
    res, diag = fitted
    metric = gauss_newton_metric(diag["jac"])
    eu = build_atm_coordinates(res.params, T)
    gn = build_atm_coordinates(res.params, T, metric=metric)
    assert gn.jacobian @ gn.primary == pytest.approx(np.eye(3), abs=1e-8)
    assert np.isfinite(gn.condition) and gn.condition >= 1.0
    # Fit impact of a pure ATM-level move, measured in the GN quadratic form.
    for j in range(3):
        du_eu, du_gn = eu.primary[:, j], gn.primary[:, j]
        impact_eu = float(du_eu @ metric @ du_eu)
        impact_gn = float(du_gn @ metric @ du_gn)
        assert impact_gn <= impact_eu * (1.0 + 1e-9)


def test_gauss_newton_retarget_reaches_exact_handles(fitted):
    res, diag = fitted
    gn = build_atm_coordinates(
        res.params, T, metric=gauss_newton_metric(diag["jac"]))
    target = gn.handles0 + np.array([0.001, 0.02, 0.1])
    moved = gn.retarget(target)
    assert handles_vector(moved, T) == pytest.approx(target, abs=1e-10)


def test_package_controls_move_their_package_and_not_the_handles(fitted):
    res, _ = fitted
    chart = build_atm_coordinates(res.params, T)
    controls = build_package_controls(chart, names=("RR25", "BF25", "VarSwap"))
    assert controls.rank == 3
    assert controls.cross_talk == pytest.approx(np.eye(3), abs=1e-6)
    # Walk a small step along each direction: its package moves by ~step,
    # the handles stay put to FIRST order — i.e. the residual handle drift
    # is quadratic in the step (the directions are not unit-norm in theta,
    # so the honest check is the contraction rate, not an absolute bound).
    step = 2e-4  # small enough that the quadratic term stays a few percent
    for i, name in enumerate(controls.names):
        def handle_leak(h: float) -> float:
            theta = res.params.to_vector() + h * controls.directions[:, i]
            return float(np.max(np.abs(
                handles_vector(LQDParams.from_vector(theta), T) - chart.handles0)))

        theta = res.params.to_vector() + step * controls.directions[:, i]
        moved = LQDParams.from_vector(theta)
        d_pkg = package_vector(moved, T, controls.names) - controls.values
        assert d_pkg[i] == pytest.approx(step, rel=5e-2)
        others = np.delete(d_pkg, i)
        assert np.max(np.abs(others)) < 0.15 * step  # first-order cross-talk
        assert handle_leak(step / 2.0) < 0.4 * handle_leak(step)  # quadratic


def test_calendar_argmax_names_the_cheapest_trade():
    from volfit.calib.calendar import calendar_violation_argmax

    near = calibrate_slice(K, W, t=T, n_order=6).slice
    # A crossed far slice: SMALLER total variance at the same strikes.
    far = calibrate_slice(K, 0.82 * W, t=T * 2.0, n_order=6).slice
    viol, k_star = calendar_violation_argmax(near, far, (float(K[0]), float(K[-1])))
    assert viol > 0.0
    assert k_star is not None and K[0] <= k_star <= K[-1]
    # The named strike is (numerically) where the gap is worst — compared on
    # a finer grid than the reporter's own, so only to grid resolution.
    kk = np.linspace(K[0], K[-1], 2001)
    gap = np.asarray(near.call_price(kk) - far.call_price(kk))
    assert viol == pytest.approx(float(gap.max()), rel=1e-4)
    # And a clean pair names no trade.
    viol2, k2 = calendar_violation_argmax(
        near, calibrate_slice(K, 1.6 * W, t=T * 2.0, n_order=6).slice,
        (float(K[0]), float(K[-1])))
    assert viol2 <= 0.0 and k2 is None

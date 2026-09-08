"""LV operator arc O1 — the BDF2 time scheme of the affine Dupire march.

Gates:
  * the plan coefficients: constant-step BDF2 is (2/3, 4/3, 1/3), α − β = 1 on
    every step, the first step and every > ratio restart are implicit Euler;
  * "implicit" / "rannacher" plans leave the legacy marches byte-identical;
  * BDF2 is second order in time and far more accurate than implicit Euler at
    the same dt; its payoff-kink (ATM) error on a short front is a fraction of
    implicit Euler's at 8 steps (the front-operator finding);
  * the analytic BDF2 sensitivities match finite differences, with and without
    the free left-wing slope column;
  * the value-only reprice reproduces the solver's BDF2 value path bit-for-bit
    (the converged-operator metric stays attributable to the operator).
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.core.black import implied_total_variance
from volfit.models.localvol import AffineVarianceSurface, solve_affine_dupire
from volfit.models.localvol.dupire_twin import FlatSurface
from volfit.models.localvol.reprice import reprice_affine_dupire
from volfit.models.localvol.time_schemes import (
    BDF2_MAX_RATIO,
    bdf2_coefficients,
    build_plan,
)

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
EXPS = [0.25, 0.5, 1.0]


def _true_variance(t, x):
    return (0.032 + 0.006 * t + 0.030 * (1.0 - x) ** 2 + 0.012 * (1.0 - x)
            + 0.004 * np.sin(np.pi * t) * np.exp(-(((x - 1.0) / 0.35) ** 2)))


SURF = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=_true_variance(TAU[:, None], XI[None, :]))


def _tgrid(dt_max, exps=EXPS):
    pts, prev = [0.0], 0.0
    for e in exps:
        s = max(1, int(np.ceil((e - prev) / dt_max)))
        pts.extend(np.linspace(prev, e, s + 1)[1:].tolist())
        prev = e
    return np.array(pts)


# ------------------------------------------------------------------- plans
def test_constant_step_bdf2_coefficients():
    g, a, b = bdf2_coefficients(0.1, 0.1)
    assert (g, a, b) == pytest.approx((2.0 / 3.0, 4.0 / 3.0, 1.0 / 3.0))


def test_plan_first_step_and_restarts_are_implicit_and_conserve_constants():
    t = np.array([0.0, 0.01, 0.02, 0.03, 0.1, 0.17, 0.24])  # step 3 grows 7x
    plan = build_plan(t, "bdf2")
    assert plan.gamma[0] == 1.0 and plan.alpha[0] == 1.0 and plan.beta[0] == 0.0
    assert plan.beta[1] > 0.0 and plan.beta[2] > 0.0  # BDF2 once two levels exist
    assert plan.gamma[3] == 1.0 and plan.beta[3] == 0.0  # the restart
    assert plan.beta[4] > 0.0  # BDF2 resumes on the next uniform step
    assert np.allclose(plan.alpha - plan.beta, 1.0)
    assert np.all(plan.eps == 0.0)
    assert not plan.is_implicit and plan.uses_two_levels and not plan.uses_old_operator
    # a shrinking step never restarts (beta > 0), a growth just under the bound neither
    t2 = np.array([0.0, 0.1, 0.2, 0.21, 0.21 + 0.01 * (BDF2_MAX_RATIO - 0.01)])
    p2 = build_plan(t2, "bdf2")
    assert p2.beta[2] > 0.0 and p2.beta[3] > 0.0


def test_implicit_and_rannacher_plans_match_their_legacy_meaning():
    t = _tgrid(0.05)
    imp = build_plan(t, "implicit")
    assert imp.is_implicit
    ran = build_plan(t, "rannacher", rannacher_steps=2)
    assert ran.gamma[0] == 1.0 and ran.gamma[1] == 1.0 and ran.eps[1] == 0.0
    assert np.all(ran.gamma[2:] == 0.5) and np.all(ran.eps[2:] == 0.5)
    assert ran.uses_old_operator and not ran.uses_two_levels
    with pytest.raises(ValueError):
        build_plan(t, "leapfrog")


# ---------------------------------------------------------------- accuracy
def test_bdf2_is_second_order_and_beats_implicit_at_the_same_dt():
    ref = solve_affine_dupire(SURF, X_GRID, _tgrid(0.00125), EXPS, time_scheme="bdf2")
    pts = [(0, 0.8), (0, 1.0), (1, 0.9), (2, 1.1), (2, 1.0)]

    def err(sol):
        return max(abs(sol.price_at(i, x) - ref.price_at(i, x)) for i, x in pts)

    imp = err(solve_affine_dupire(SURF, X_GRID, _tgrid(0.02), EXPS))
    b_coarse = err(solve_affine_dupire(SURF, X_GRID, _tgrid(0.02), EXPS, time_scheme="bdf2"))
    b_fine = err(solve_affine_dupire(SURF, X_GRID, _tgrid(0.01), EXPS, time_scheme="bdf2"))
    assert b_coarse < 0.25 * imp  # at least 4x more accurate than implicit at dt = 0.02
    assert b_fine < 0.35 * b_coarse  # halving dt cuts the error ~4x (2nd order), margin


def test_bdf2_kink_error_on_a_short_front_is_a_fraction_of_implicit():
    """The front-operator finding: a flat 12 % surface marched to a 1-week
    expiry with 8 steps — implicit Euler's ATM error is ~0.15 σ / N (first
    order; several times that over the quoted strikes), BDF2's a tenth of it."""
    t1 = 7.0 / 365.0
    var = 0.12 ** 2
    x = np.linspace(0.0, 2.5, 1001)
    tg = np.linspace(0.0, t1, 9)
    k = np.array([0.0])

    def atm_err(scheme):
        sol = reprice_affine_dupire(FlatSurface(var), x, tg, [t1], time_scheme=scheme)
        w = implied_total_variance(k, sol.price_at(0, np.exp(k)))
        return abs(float(np.sqrt(w[0] / t1)) - 0.12) * 1e4

    e_imp, e_bdf = atm_err("implicit"), atm_err("bdf2")
    assert e_imp > 15.0  # the pathology, in vol bp (~0.15 x 1200 / 8)
    assert e_bdf < 0.3 * e_imp


# ------------------------------------------------------------ sensitivities
@pytest.mark.parametrize("fit_left_a", [False, True])
def test_bdf2_sensitivities_match_finite_differences(fit_left_a):
    t = _tgrid(0.02)
    surf = SURF.with_left_extrap_a(1.2) if fit_left_a else SURF
    sol = solve_affine_dupire(
        surf, X_GRID, t, EXPS, sensitivities=True, time_scheme="bdf2", fit_left_a=fit_left_a
    )
    flat = surf.theta.ravel()
    rng = np.random.default_rng(3)
    for _ in range(5):
        node = int(rng.integers(0, flat.size))
        i_exp = int(rng.integers(0, 3))
        x = float(rng.uniform(0.75, 1.2))
        eps = 1e-6
        bumped = []
        for sgn in (+1.0, -1.0):
            th = flat.copy()
            th[node] += sgn * eps
            s_b = solve_affine_dupire(
                surf.with_theta(th), X_GRID, t, EXPS, time_scheme="bdf2", fit_left_a=fit_left_a
            )
            bumped.append(float(s_b.price_at(i_exp, x)))
        fd = (bumped[0] - bumped[1]) / (2.0 * eps)
        an = float(sol.sens_at(i_exp, np.array([x]))[0, node])
        assert an == pytest.approx(fd, abs=2e-7, rel=2e-5)
    if fit_left_a:
        # the trailing dU/da column
        x = 0.6  # below x_nodes[1] = 0.7: the linear wing region is active there
        i_exp = 2
        eps = 1e-5
        bumped = []
        for sgn in (+1.0, -1.0):
            s_b = solve_affine_dupire(
                surf.with_left_extrap_a(1.2 + sgn * eps), X_GRID, t, EXPS,
                time_scheme="bdf2", fit_left_a=True,
            )
            bumped.append(float(s_b.price_at(i_exp, x)))
        fd = (bumped[0] - bumped[1]) / (2.0 * eps)
        an = float(sol.sens_at(i_exp, np.array([x]))[0, -1])
        assert an == pytest.approx(fd, abs=2e-7, rel=2e-4)


# ---------------------------------------------------------------- parity
def test_reprice_matches_solver_bdf2_value_path_bitwise():
    t = _tgrid(0.02)
    a = solve_affine_dupire(SURF, X_GRID, t, EXPS, time_scheme="bdf2")
    b = reprice_affine_dupire(SURF, X_GRID, t, EXPS, time_scheme="bdf2")
    assert np.array_equal(a.prices, b.prices)


def test_value_only_and_sensitivity_bdf2_marches_agree():
    t = _tgrid(0.02)
    a = solve_affine_dupire(SURF, X_GRID, t, EXPS, time_scheme="bdf2")
    b = solve_affine_dupire(SURF, X_GRID, t, EXPS, time_scheme="bdf2", sensitivities=True)
    assert np.allclose(a.prices, b.prices, rtol=0.0, atol=1e-13)

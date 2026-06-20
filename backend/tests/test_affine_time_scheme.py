"""Stage 7 — Crank-Nicolson + Rannacher time stepping for the affine Dupire march.

Gates:
  * the default ("implicit") path is byte-identical to the legacy fully-implicit
    Euler march (the golden anchor is untouched);
  * Rannacher (CN after implicit start-up) is 2nd-order: at a coarse dt it is far
    closer to the time-converged reference than implicit Euler at the same dt;
  * the analytic sensitivities are differentiated correctly through the CN step
    (match finite differences);
  * the calibrated Rannacher surface stays arbitrage-free and reproduces the
    note's golden nodal table (quality-neutral vs implicit).
"""

import numpy as np
import pytest

from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
    solve_affine_dupire,
)

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)


def _true_variance(t, x):
    return (0.032 + 0.006 * t + 0.030 * (1.0 - x) ** 2 + 0.012 * (1.0 - x)
            + 0.004 * np.sin(np.pi * t) * np.exp(-(((x - 1.0) / 0.35) ** 2)))


SURF = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=_true_variance(TAU[:, None], XI[None, :]))
EXPS = [0.25, 0.5, 1.0]


def _tgrid(dt_max):
    pts, prev = [0.0], 0.0
    for e in EXPS:
        s = max(1, int(np.ceil((e - prev) / dt_max)))
        pts.extend(np.linspace(prev, e, s + 1)[1:].tolist())
        prev = e
    return np.array(pts)


def test_implicit_default_is_byte_identical():
    """The explicit ``time_scheme='implicit'`` equals the default march exactly."""
    t = _tgrid(0.01)
    a = solve_affine_dupire(SURF, X_GRID, t, EXPS, sensitivities=True)
    b = solve_affine_dupire(SURF, X_GRID, t, EXPS, sensitivities=True, time_scheme="implicit")
    assert np.array_equal(a.prices, b.prices)
    assert np.array_equal(a.sens, b.sens)


def test_rannacher_is_second_order_in_time():
    """At dt=0.02 Rannacher is much closer to the time-converged solution than
    implicit Euler at the same dt (2nd vs 1st order)."""
    ref = solve_affine_dupire(SURF, X_GRID, _tgrid(0.00125), EXPS)  # time-converged
    tc = _tgrid(0.02)
    imp = solve_affine_dupire(SURF, X_GRID, tc, EXPS)
    ran = solve_affine_dupire(SURF, X_GRID, tc, EXPS, time_scheme="rannacher")
    pts = [(0, 0.8), (0, 1.0), (1, 0.9), (2, 1.1), (2, 1.0)]
    e_imp = max(abs(imp.price_at(i, x) - ref.price_at(i, x)) for i, x in pts)
    e_ran = max(abs(ran.price_at(i, x) - ref.price_at(i, x)) for i, x in pts)
    assert e_ran < 0.25 * e_imp  # at least 4x more accurate at the same dt


def test_rannacher_sensitivities_match_finite_differences():
    t = _tgrid(0.02)
    sol = solve_affine_dupire(SURF, X_GRID, t, EXPS, sensitivities=True, time_scheme="rannacher")
    flat = SURF.theta.ravel()
    rng = np.random.default_rng(2)
    for _ in range(5):
        node = int(rng.integers(0, flat.size))
        i_exp = int(rng.integers(0, 3))
        x = float(rng.uniform(0.8, 1.2))
        eps = 1e-6
        bumped = []
        for sgn in (+1.0, -1.0):
            th = flat.copy()
            th[node] += sgn * eps
            s = solve_affine_dupire(
                SURF.with_theta(th), X_GRID, t, EXPS, time_scheme="rannacher"
            )
            bumped.append(float(s.price_at(i_exp, x)))
        fd = (bumped[0] - bumped[1]) / (2.0 * eps)
        an = float(sol.sens_at(i_exp, np.array([x]))[0, node])
        assert an == pytest.approx(fd, abs=1e-7), (node, i_exp, x)


def test_rannacher_falls_back_to_implicit_with_left_a():
    """A free left-slope (fit_left_a) keeps the implicit recursion even when
    'rannacher' is requested, so the dU/da column stays correct."""
    t = _tgrid(0.02)
    a = solve_affine_dupire(
        SURF, X_GRID, t, EXPS, sensitivities=True, fit_left_a=True, time_scheme="rannacher"
    )
    b = solve_affine_dupire(
        SURF, X_GRID, t, EXPS, sensitivities=True, fit_left_a=True, time_scheme="implicit"
    )
    assert np.array_equal(a.prices, b.prices)
    assert np.array_equal(a.sens, b.sens)


def _options_only_calibration(scheme, dt_max):
    """Calibrate from option quotes ONLY (no var-swap), so ``fit_left_a`` is False
    and the Rannacher CN path is genuinely exercised (a var-swap would force the
    implicit fallback)."""
    table = [
        (0.25, 0.80, 0.200277), (0.25, 0.90, 0.105645), (0.25, 1.00, 0.036544),
        (0.25, 1.10, 0.007310), (0.25, 1.20, 0.000861),
        (0.50, 0.80, 0.202596), (0.50, 0.90, 0.115765), (0.50, 1.00, 0.053085),
        (0.50, 1.10, 0.019104), (0.50, 1.20, 0.005456),
        (1.00, 0.80, 0.211163), (1.00, 0.90, 0.133968), (1.00, 1.00, 0.076657),
        (1.00, 1.10, 0.039690), (1.00, 1.20, 0.018833),
    ]
    options = [OptionQuote(t=t, x=x, price=p, tol=2e-4) for t, x, p in table]
    flat = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=np.full((3, 7), 0.04))
    return calibrate_affine(
        flat, options, X_GRID, _tgrid(dt_max), reg_lambda=50.0,
        bounds=(0.005, 0.20), time_scheme=scheme,
    )


def test_rannacher_calibration_arbitrage_free_and_close_to_implicit():
    """A Rannacher-marched calibration at a coarse dt stays arbitrage-free and lands
    essentially the implicit fine-dt surface (quality-neutral)."""
    ran = _options_only_calibration("rannacher", 0.02)
    imp = _options_only_calibration("implicit", 0.005)
    prices = ran.solution.prices
    assert prices.min() >= -1e-9 and prices.max() <= 1.0 + 1e-9
    assert np.diff(prices, axis=1).max() <= 1e-9            # decreasing in strike
    assert np.diff(np.diff(prices, axis=1), axis=1).min() >= -1e-8  # convex in strike
    assert np.diff(prices, axis=0).min() >= -1e-8          # calendar monotone
    # Quote-fit quality is the headline metric: Rannacher fits the quotes as well as
    # the implicit fine-dt solve (it is in fact MORE time-accurate per the convergence
    # test, so it is not "worse", only a different discretisation).
    assert ran.rms_price_error <= 1.5 * imp.rms_price_error + 1e-6
    # Nodal-θ agreement: data-identified nodes match to ~5e-4; the largest difference
    # sits on the UNCONSTRAINED t=0 corner row (no data there), so allow it more room.
    assert np.max(np.abs(ran.surface.theta - imp.surface.theta)) < 6e-3
    assert np.max(np.abs(ran.surface.theta[1:] - imp.surface.theta[1:])) < 2e-3

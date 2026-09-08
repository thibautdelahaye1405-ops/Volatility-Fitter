"""LV operator arc O3/O4 — the graded time grid and the graded strike lattice.

Gates:
  * the time grid hits every expiry and every mark exactly, starts at 0, grows
    by at most 1 + growth per step (BDF2 never restarts after step 0), never
    exceeds the ceiling, and gives every slab at least ``slab_steps`` steps;
  * the strike lattice has x = 1 as an exact node, closes on 0 and x_max,
    respects every region's step, coarsens to the wing step outside, and its
    cell ratio never exceeds ``ratio``; it is far smaller than the uniform
    lattice a 2-day rung forces;
  * ``refine_cells`` / ``second_difference`` are bit-identical to the
    historical linspace / uniform stencil on a uniform lattice and correct on
    a graded one;
  * ``pde_lattice`` returns the legacy grids for implicit + uniform (the
    byte-identity anchor of every golden) and the graded ones otherwise;
  * a BDF2 fit on the graded lattice of a synthetic surface prices its quotes
    within a few bp of a converged reference, arb-free.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.models.localvol.pde_grids import (
    STRIKE_RATIO,
    TIME_DT_MAX,
    TIME_GROWTH,
    TIME_SLAB_STEPS,
    WING_DX,
    graded_strike_grid,
    graded_time_grid,
    is_uniform,
    refine_cells,
    second_difference,
    third_difference_weights,
)
from volfit.models.localvol.time_schemes import build_plan

EXPS = np.array([2.0, 7.0, 16.0, 107.0, 653.0]) / 365.0
ROWS = np.array([0.0, 0.5 / 365.0, 2.0 / 365.0, 7.0 / 365.0, 16.0 / 365.0, 50.0 / 365.0,
                 107.0 / 365.0, 300.0 / 365.0, 653.0 / 365.0])


# ---------------------------------------------------------------- time grid
def test_time_grid_hits_marks_exactly_and_grows_gently():
    t = graded_time_grid(EXPS, marks=ROWS)
    assert t[0] == 0.0
    assert np.all(np.diff(t) > 0.0)
    for e in np.concatenate([EXPS, ROWS[ROWS > 0]]):
        assert np.any(t == e)  # exact float identity (the solver's searchsorted check)
    dt = np.diff(t)
    ratios = dt[1:] / dt[:-1]
    assert ratios.max() <= 1.0 + TIME_GROWTH + 1e-9
    assert dt.max() <= TIME_DT_MAX + 1e-12
    assert dt[0] == pytest.approx(0.01 * ROWS[1])  # 1 % of the first mark
    # every slab between consecutive marks has >= slab_steps steps
    marks = np.unique(np.concatenate([[0.0], EXPS, ROWS]))
    for a, b in zip(marks[:-1], marks[1:]):
        assert np.count_nonzero((t > a) & (t <= b)) >= TIME_SLAB_STEPS
    # BDF2 restarts only at step 0
    plan = build_plan(t, "bdf2")
    assert plan.beta[0] == 0.0 and np.all(plan.beta[1:] > 0.0)


def test_time_grid_is_far_shorter_than_the_uniform_rule_on_a_dailies_ladder():
    from volfit.api.affine_fit import _pde_grids

    _, legacy = _pde_grids(EXPS, 0.3)
    graded = graded_time_grid(EXPS, marks=ROWS)
    assert graded.size < 0.6 * legacy.size  # 271 -> ~115 on the SPY dailies ladder


# -------------------------------------------------------------- strike grid
def _regions():
    # a 2-day SPY-like rung, a weekly, a monthly, a one-year: (lo, hi, step)
    return [
        (0.955, 1.03, 1.0 / 657.0),
        (0.93, 1.05, 0.0021),
        (0.85, 1.15, 0.006),
        (0.45, 2.3, 0.01),
    ]


def test_strike_grid_anchors_x1_closes_ends_and_respects_steps():
    x = graded_strike_grid(_regions(), 2.5)
    assert x[0] == 0.0 and x[-1] == 2.5
    i1 = int(np.searchsorted(x, 1.0))
    assert x[i1] == 1.0  # exact node (varswap_weights / atm_index requirement)
    assert np.all(np.diff(x) > 0.0)
    h = np.diff(x)
    ratios = np.maximum(h[1:] / h[:-1], h[:-1] / h[1:])
    assert ratios[1:-1].max() <= STRIKE_RATIO + 1e-9  # the closing cells may differ
    mid = 0.5 * (x[1:] + x[:-1])
    for lo, hi, step in _regions():
        inside = (mid >= lo) & (mid <= hi)
        assert h[inside].max() <= step * (1.0 + 1e-9)
    deep_wing = mid < 0.2
    assert h[deep_wing].max() <= WING_DX + 1e-12
    assert h[deep_wing].max() > 0.015  # the wing really coarsens
    # a fraction of the uniform lattice the 2-day rung forces (1/657 to 2.5 ≈ 1643 nodes)
    assert x.size < 500


def test_strike_grid_rejects_bad_x_max():
    with pytest.raises(ValueError):
        graded_strike_grid(_regions(), 0.9)


# -------------------------------------------------------------- helpers
def test_refine_cells_and_second_difference_are_bit_identical_on_uniform():
    x = 0.01 * np.arange(251)
    assert is_uniform(x)
    assert np.array_equal(refine_cells(x, 2), np.linspace(x[0], x[-1], 2 * (x.size - 1) + 1))
    c = np.maximum(1.0 - x, 0.0) ** 2 + 0.1 * np.sin(x)
    dx = 0.01
    legacy = (c[2:] - 2.0 * c[1:-1] + c[:-2]) / (dx * dx)
    assert np.array_equal(second_difference(x, c), legacy)
    c2 = np.vstack([c, 2.0 * c])
    assert np.array_equal(second_difference(x, c2), np.vstack([legacy, 2.0 * legacy]))


def test_refine_cells_and_second_difference_on_a_graded_lattice():
    x = graded_strike_grid(_regions(), 2.5)
    assert not is_uniform(x)
    x2 = refine_cells(x, 4)
    assert x2.size == 4 * (x.size - 1) + 1
    assert np.all(np.isin(x, x2))  # every node kept (x = 1 included)
    assert np.all(np.diff(x2) > 0.0)
    # exact for a quadratic on ANY lattice
    c = 3.0 * x * x - 2.0 * x + 1.0
    assert np.allclose(second_difference(x, c), 6.0, rtol=0.0, atol=1e-8)


# ----------------------------------------------------------- pde_lattice
def _rows():
    """Synthetic gathered rows (iso, tau, k, w, prepared, band) for a dailies ladder."""
    rows = []
    for i, t in enumerate(EXPS):
        vol = 0.14 + 0.02 * i
        s = vol * np.sqrt(t)
        k = np.linspace(-3.5 * s, 3.0 * s, 25)
        w = (vol**2) * t * (1.0 + 0.4 * (k / s) ** 2 / 10.0)
        rows.append((f"e{i}", float(t), k, w, None, None))
    return rows


def test_pde_lattice_legacy_modes_are_the_old_grids_and_graded_modes_differ():
    from volfit.api.affine_fit import _DT_MAX, _pde_dx, _pde_grids
    from volfit.api.affine_lattice import pde_lattice

    rows = _rows()
    k_hi = max(float(k.max()) for _, _, k, _, _, _ in rows)
    x_old, t_old = _pde_grids(EXPS, k_hi, _DT_MAX, _pde_dx(rows), x_max_min=2.5)
    x, t = pde_lattice(rows, EXPS, ROWS, k_hi, "implicit", "uniform", 2.5)
    assert np.array_equal(x, x_old) and np.array_equal(t, t_old)
    xg, tg = pde_lattice(rows, EXPS, ROWS, k_hi, "bdf2", "graded", 2.5)
    assert xg.size < 0.4 * x.size and tg.size < 0.6 * t.size
    assert xg[-1] == x[-1]  # the same right edge
    assert np.any(xg == 1.0)
    xu, tb = pde_lattice(rows, EXPS, ROWS, k_hi, "bdf2", "uniform", 2.5)
    assert np.array_equal(xu, x_old) and np.array_equal(tb, tg)


def test_bdf2_fit_on_the_graded_lattice_prices_its_quotes_arb_free():
    """A synthetic surface, its quotes on the graded operator: the fit reprices
    them within a few bp on a converged reference march and stays arb-free."""
    from volfit.core.black import implied_total_variance
    from volfit.models.localvol import AffineVarianceSurface, OptionQuote, calibrate_affine
    from volfit.models.localvol.affine import solve_affine_dupire
    from volfit.models.localvol.reprice import refined_grids, reprice_affine_dupire

    t_nodes = np.array([0.0, 0.05, 0.1, 0.25, 0.5, 1.0])
    x_nodes = np.array([0.5, 0.8, 0.9, 1.0, 1.1, 1.25, 1.6])
    tt, xx = np.meshgrid(t_nodes, x_nodes, indexing="ij")
    theta = 0.03 + 0.02 * (1.0 - xx) ** 2 + 0.004 * tt
    truth = AffineVarianceSurface(t_nodes=t_nodes, x_nodes=x_nodes, theta=theta)
    exps = [0.1, 0.25, 1.0]
    regions = [(np.exp(-6 * 0.18 * np.sqrt(e)), np.exp(6 * 0.18 * np.sqrt(e)),
                min(0.15 * 0.18 * np.sqrt(e), 0.01)) for e in exps]
    x = graded_strike_grid(regions, 2.5)
    t = graded_time_grid(exps, marks=t_nodes)
    # quotes from a converged reference of the TRUE surface
    x_f, t_f = refined_grids(x, t, 2, 4)
    ref = reprice_affine_dupire(truth, x_f, t_f, exps, time_scheme="bdf2")
    quotes = []
    for i, e in enumerate(exps):
        for xq in (0.85, 0.92, 1.0, 1.08, 1.15):
            quotes.append(OptionQuote(t=e, x=xq, price=float(ref.price_at(i, xq)), tol=1e-4))
    seed = truth.with_theta(np.full(truth.n_params, 0.035))
    cal = calibrate_affine(seed, quotes, x, t, time_scheme="bdf2", engine="numba", max_nfev=100)
    conv = reprice_affine_dupire(cal.surface, x_f, t_f, exps, time_scheme="bdf2")
    for i, e in enumerate(exps):
        for xq in (0.85, 0.92, 1.0, 1.08, 1.15):
            # every quote within a few tolerances in PRICE on the converged operator
            assert abs(conv.price_at(i, xq) - ref.price_at(i, xq)) < 5e-4
        for xq in (0.92, 1.0, 1.08):  # inside 2 sd: a few vol bp (wings have no vega)
            k = np.log(xq)
            w_fit = implied_total_variance(np.array([k]), conv.price_at(i, xq))[0]
            w_ref = implied_total_variance(np.array([k]), ref.price_at(i, xq))[0]
            assert abs(np.sqrt(w_fit / e) - np.sqrt(w_ref / e)) * 1e4 < 8.0
    sol = solve_affine_dupire(cal.surface, x, t, exps, time_scheme="bdf2")
    dens = second_difference(x, sol.prices)
    assert dens.min() > -1e-6


def test_third_difference_weights_are_the_raw_stencil_on_uniform_and_exact_on_graded():
    xu = 0.01 * np.arange(251)
    j = np.arange(3, 240, 7)
    w = third_difference_weights(xu, j)
    assert np.allclose(w, np.array([-1.0, 3.0, -3.0, 1.0])[None, :])
    xg = graded_strike_grid(_regions(), 2.5)
    j = np.arange(1, xg.size - 4, 3)
    w = third_difference_weights(xg, j)
    cubic = 0.7 * xg**3 - 1.1 * xg**2 + 0.3 * xg - 2.0
    row = w[:, 0] * cubic[j] + w[:, 1] * cubic[j + 1] + w[:, 2] * cubic[j + 2] + w[:, 3] * cubic[j + 3]
    h3 = (xg[j + 1] - xg[j]) ** 3
    assert np.allclose(row, 6.0 * 0.7 * h3, rtol=1e-9, atol=1e-14)  # 6 h^3 (third derivative / 6) = 4.2 h^3
    # a density-smoothness spec on the graded lattice carries the weights
    from volfit.models.localvol.affine_calib import OptionQuote, density_smoothness_rows

    quotes = [OptionQuote(t=0.1, x=x, price=0.05, tol=1e-3) for x in (0.9, 0.95, 1.0, 1.05, 1.1)]
    spec = density_smoothness_rows(xg, quotes, {0.1: 0.05}, 1.0)
    assert spec and spec[0][3] is not None and spec[0][3].shape == (spec[0][1].size, 4)
    spec_u = density_smoothness_rows(xu, quotes, {0.1: 0.05}, 1.0)
    assert spec_u and spec_u[0][3] is None and np.isscalar(spec_u[0][2])

"""Grid-design tests for the local-vol-affine fit (Stages 1-2 + convex wing).

Covers the refinements to how the P1 local-variance vertex grid is sized and
placed (volfit.api.affine_fit) and the spacing-aware roughness / convex-wing
constraint (volfit.models.localvol.affine_calib):

1. the spacing-aware roughness operator reduces to the legacy index-space one on
   a uniform grid (so the note's golden example is untouched);
2. the convex-wing stencils carry the correct columns + curvature coefficients;
3. the convex-wing penalty is byte-identical when off and genuinely convexifies a
   deliberately-concave left vol wing when on;
4. the delta-spaced strike axis is dense near ATM and reaches the wings.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.api.affine_fit import (
    _axis_scale,
    _delta_strike_nodes,
    _lv_bounds,
    _resolve_grid,
    _time_nodes,
)
from volfit.api.schemas import OptionsSettings
from scipy.special import ndtri
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    VarSwapQuote,
    calibrate_affine,
    solve_affine_dupire,
)
from volfit.models.localvol.affine import precompute_dupire_steps
from volfit.models.localvol.affine_calib import (
    second_difference_rows,
    second_difference_rows_spacing,
    wing_convexity_stencils,
)


# ------------------------------------------------------ Stage 2: roughness
def test_spacing_roughness_matches_index_on_uniform_grid():
    """On a uniform vertex grid the spacing-aware operator equals (1, -2, 1)."""
    t = np.array([0.0, 0.5, 1.0])
    x = np.array([0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2])
    legacy = second_difference_rows(t.size, x.size, rho=1.3)
    spaced = second_difference_rows_spacing(t, x, rho=1.3)
    assert spaced.shape == legacy.shape
    assert np.allclose(spaced, legacy, atol=1e-12)


def test_spacing_roughness_is_exact_curvature_on_nonuniform_grid():
    """The spacing-aware stencil recovers the TRUE second derivative of a quadratic
    on a non-uniform grid (the legacy index form is contaminated by position)."""
    t = np.array([0.0, 1.0])
    x = np.array([0.5, 0.9, 0.95, 1.0, 1.05, 1.1, 1.6])
    f = x**2  # exact f'' = 2 everywhere
    flat = np.concatenate([f, f])  # two identical t-major rows
    spaced = second_difference_rows_spacing(t, x, rho=1.0)
    legacy = second_difference_rows(t.size, x.size, rho=1.0)
    n_strike_per_row = x.size - 2  # interior nodes j = 1 .. n_x-2
    for r, j in zip(spaced[:n_strike_per_row], range(1, x.size - 1)):
        hbar2 = (0.5 * (x[j + 1] - x[j - 1])) ** 2  # un-normalize -> f''
        assert (r @ flat) / hbar2 == pytest.approx(2.0, abs=1e-9)
    # The index-space operator gives a position-dependent (wrong) curvature here.
    contaminated = legacy[:n_strike_per_row] @ flat
    assert not np.allclose(contaminated, contaminated[0])


# ----------------------------------------------- convex-wing stencil math
def test_wing_convexity_stencils_uniform_coeffs():
    t = np.array([0.0, 1.0])
    x = np.array([0.8, 0.9, 1.0, 1.1, 1.2])
    cols = np.array([0, 1, 2])  # the left region (at/below ~5Δ)
    col_m, col_0, col_p, cm, c0, cp = wing_convexity_stencils(t, x, cols)
    # eligible interior nodes among {0,1,2}: j in [1, n_x-2] = [1, 3] -> {1, 2};
    # one constraint per time row (2 rows) -> 4 constraints.
    assert col_0.size == 4
    assert np.allclose(cm, 1.0) and np.allclose(c0, -2.0) and np.allclose(cp, 1.0)
    # columns are t-major flat indices into theta (n_x = 5).
    assert set(col_0.tolist()) == {1, 2, 6, 7}


def test_wing_convexity_stencils_empty_when_no_interior_wing():
    t = np.array([0.0, 1.0])
    x = np.array([0.8, 0.9, 1.0, 1.1, 1.2])
    # only the boundary column 0 is flagged -> not interior -> no constraint.
    out = wing_convexity_stencils(t, x, np.array([0]))
    assert all(arr.size == 0 for arr in out)


# ------------------------------------- convex-wing penalty: off vs on effect
_X_GRID = 0.01 * np.arange(131)  # 0 .. 1.30, x = 1 at node 100
_T_GRID = 0.005 * np.arange(201)  # 0 .. 1.0, expiries 0.5 / 1.0 are nodes
_T_NODES = np.array([0.0, 0.5, 1.0])
_X_NODES = np.array([0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.20])
_EXPIRIES = [0.5, 1.0]


# --------------------------------- left-wing linear extrapolation (x < x_min)
def test_left_extrap_flat_linear_steeper():
    """Below x_min the variance is flat (a=0), continues with the first-cell slope
    (a=1), or steeper (a=1.5) — toward x=0, uncapped."""
    t = np.array([0.0, 1.0])
    x = np.array([0.70, 0.85, 1.00, 1.15, 1.30])
    row = np.array([0.09, 0.06, 0.04, 0.05, 0.07])  # put wing higher variance
    th = np.tile(row, (2, 1))
    xq = np.array([0.50])  # below x_min = 0.70
    flat = AffineVarianceSurface(t, x, th, left_extrap_a=0.0).variance(xq, 0.5)[0]
    lin = AffineVarianceSurface(t, x, th, left_extrap_a=1.0).variance(xq, 0.5)[0]
    steep = AffineVarianceSurface(t, x, th, left_extrap_a=1.5).variance(xq, 0.5)[0]
    assert flat == pytest.approx(0.09)  # clamped to the x_min vertex
    # slope = (0.06 - 0.09)/0.15 = -0.2; nu(0.5) = 0.09 + (0.5-0.7)*a*(-0.2)
    assert lin == pytest.approx(0.09 + (0.5 - 0.7) * 1.0 * -0.2)  # 0.13
    assert steep == pytest.approx(0.09 + (0.5 - 0.7) * 1.5 * -0.2)  # 0.15
    assert steep > lin > flat  # rises toward x=0; steeper with a


def test_da_sensitivity_matches_finite_difference():
    """The analytic dPrice/da (free-a column) matches a central finite difference."""
    t = np.array([0.0, 0.5, 1.0])
    x = np.array([0.60, 0.75, 0.90, 1.00, 1.10, 1.25, 1.40])
    row = 0.04 + 0.06 * np.maximum(1.0 - x, 0.0)  # left-skewed variance
    surf = AffineVarianceSurface(t, x, np.tile(row, (3, 1)), left_extrap_a=1.0)
    steps = precompute_dupire_steps(surf, _X_GRID, _T_GRID, with_left_lin=True)
    m = surf.n_params
    a0 = 1.0
    xq = np.array([0.45, 0.5])  # below x_min = 0.60, where da is nonzero
    sol = solve_affine_dupire(
        surf, _X_GRID, _T_GRID, _EXPIRIES, sensitivities=True, steps=steps,
        left_a=a0, fit_left_a=True,
    )
    da = sol.sens_at(0, xq)[:, m]  # the appended a-column

    def price(a):
        s = solve_affine_dupire(surf, _X_GRID, _T_GRID, _EXPIRIES, steps=steps, left_a=a)
        return s.price_at(0, xq)

    eps = 1e-6
    fd = (price(a0 + eps) - price(a0 - eps)) / (2.0 * eps)
    assert np.allclose(da, fd, atol=1e-7)


def test_free_a_reduces_varswap_error():
    """With a var-swap target richer than the options imply, a free left-wing slope
    enriches the deep-put tail and matches the var-swap better than a flat wing."""
    quotes = _time_varying_quotes()
    flat = AffineVarianceSurface(
        t_nodes=_T_NODES, x_nodes=_X_NODES, theta=np.full((3, 7), 0.06)
    )
    vs = [VarSwapQuote(t=t, total_var=(0.55**2) * t, tol=2e-3) for t in _EXPIRIES]
    fixed = calibrate_affine(
        flat.with_left_extrap_a(0.0), quotes, _X_GRID, _T_GRID, varswaps=vs, reg_lambda=1e-2
    )
    free = calibrate_affine(
        flat.with_left_extrap_a(1.0), quotes, _X_GRID, _T_GRID, varswaps=vs,
        reg_lambda=1e-2, fit_left_a=True,
    )
    assert free.left_extrap_a > 0.0  # the tail slope was used
    assert np.abs(free.varswap_errors).sum() < np.abs(fixed.varswap_errors).sum()


# ----------------------------------------- adaptive local-vol cap (bounds)
def _rows_with_iv(sigma: float, t: float = 0.5):
    """Minimal _gather-shaped rows carrying a flat implied vol of ``sigma``."""
    k = np.array([-0.1, 0.0, 0.1])
    w = (sigma * sigma * t) * np.ones(3)  # total variance = sigma^2 * t
    return [("e", t, k, w, None, None)]


def test_lv_bounds_cap_scales_with_observed_iv():
    opts = OptionsSettings()  # lvVolCapMult = 3.0
    lo, hi = _lv_bounds(_rows_with_iv(0.80), opts, 0.0025, 0.36)
    assert lo == pytest.approx(0.0025)  # floor unchanged
    assert np.sqrt(hi) == pytest.approx(3.0 * 0.80)  # 240% cap, not 60%


def test_lv_bounds_low_vol_keeps_request_cap():
    opts = OptionsSettings()
    _, hi = _lv_bounds(_rows_with_iv(0.15), opts, 0.0025, 0.36)
    assert np.sqrt(hi) == pytest.approx(0.60)  # 3*0.15 < 60% -> request cap wins


def test_lv_bounds_ceiling_caps_extreme_iv():
    opts = OptionsSettings()
    _, hi = _lv_bounds(_rows_with_iv(2.5), opts, 0.0025, 0.36)
    assert np.sqrt(hi) == pytest.approx(4.0)  # _LV_VAR_CEILING = 16 -> 400% vol


# --------------------------------------------------- Stage 3: time axis
def test_time_nodes_base_set_pre_node_and_expiries():
    """The base set (floor 0) is 0 + a pre-first-expiry node (T1/4) + every expiry."""
    exps = np.array([0.25, 0.5, 1.0, 2.0])
    t = _time_nodes(exps, 0)
    assert t[0] == 0.0
    assert t[1] == pytest.approx(0.0625)  # T1 / 4
    for e in exps:
        assert np.any(np.isclose(t, e))  # every expiry is a knee
    assert int((t > 0).sum()) == exps.size + 1  # pre-node + the expiries


def test_time_nodes_sqrt_t_floor_densifies_and_keeps_expiries():
    """A floor above the base count splits the widest sqrt(T) gaps up to it,
    without ever dropping a listed expiry."""
    exps = np.array([0.25, 2.0])
    base = _time_nodes(exps, 0)
    dense = _time_nodes(exps, 12)
    assert dense.size > base.size
    assert int((dense > 0).sum()) >= 12
    for e in exps:
        assert np.any(np.isclose(dense, e))


# ------------------------------------- delta strike axis: incremental densify
def test_delta_axis_lands_on_floor_not_overshoot():
    """The widest-gap refinement lands the strike count exactly on the floor
    (was: the doubling refine overshot to base*2^k). x = 1 is always present and is
    not double-counted, so the count is the floor."""
    # A wide observed range so all 13 delta nodes survive clipping (base = 13).
    floor = 25
    x = _delta_strike_nodes(0.20, 1.0, k_lo_obs=-1.2, k_hi_obs=1.2, n_floor=floor)
    assert x.size == floor  # exactly the floor — no doubling overshoot
    assert np.all(np.diff(x) > 0)  # sorted, strictly increasing
    assert np.any(np.isclose(x, 1.0))  # ATM vertex forced in


def test_delta_axis_two_names_reach_the_same_floor():
    """Two names whose base delta-node counts differ (one wing clipped harder) both
    land on the SAME floor — the fix for SPY-vs-NVDA divergent resolutions."""
    floor = 20
    # 'SPY-like': low scale, all nodes within range -> larger base.
    spy = _delta_strike_nodes(0.16, 1.0, k_lo_obs=-0.65, k_hi_obs=0.37, n_floor=floor)
    # 'NVDA-like': high scale, call wing clipped -> smaller base.
    nvda = _delta_strike_nodes(0.43, 0.5, k_lo_obs=-0.71, k_hi_obs=0.38, n_floor=floor)
    assert spy.size == floor and nvda.size == floor


def test_delta_axis_no_densify_when_base_exceeds_floor():
    """A floor below the natural (clipped) base count leaves the base set untouched
    (the floor is a minimum, never a cap)."""
    natural = _delta_strike_nodes(0.20, 1.0, k_lo_obs=-1.2, k_hi_obs=1.2, n_floor=2)
    assert natural.size > 5  # the full delta set survived
    same = _delta_strike_nodes(0.20, 1.0, k_lo_obs=-1.2, k_hi_obs=1.2, n_floor=natural.size - 3)
    assert same.size == natural.size  # floor below base -> no extra vertices


def _concave_wing_quotes() -> list[OptionQuote]:
    """Quotes from a surface whose local VOL is CONCAVE in x on the left wing
    (vol = 0.2 + 0.18*sqrt((1-x)+) ), so an unconstrained fit recovers concavity."""
    vol = 0.20 + 0.18 * np.sqrt(np.maximum(1.0 - _X_NODES, 0.0))
    theta = np.tile((vol * vol)[None, :], (_T_NODES.size, 1))
    truth = AffineVarianceSurface(t_nodes=_T_NODES, x_nodes=_X_NODES, theta=theta)
    sol = solve_affine_dupire(truth, _X_GRID, _T_GRID, _EXPIRIES)
    idx = {float(e): i for i, e in enumerate(sol.expiries)}
    xs = np.array([0.65, 0.75, 0.85, 0.95, 1.00, 1.05, 1.15])
    quotes = []
    for t in _EXPIRIES:
        prices = sol.price_at(idx[t], xs)
        for x, p in zip(xs, prices):
            quotes.append(OptionQuote(t=t, x=float(x), price=float(p), tol=2e-4))
    return quotes


def _time_varying_quotes() -> list[OptionQuote]:
    """Quotes from a surface whose local vol RISES with t, so an unconstrained fit
    leaves the t = 0 row away from the first calibrated row (front-tie target)."""
    vol = (
        0.20
        + 0.06 * _T_NODES[:, None]
        + 0.10 * np.sqrt(np.maximum(1.0 - _X_NODES[None, :], 0.0))
    )
    truth = AffineVarianceSurface(t_nodes=_T_NODES, x_nodes=_X_NODES, theta=vol * vol)
    sol = solve_affine_dupire(truth, _X_GRID, _T_GRID, _EXPIRIES)
    idx = {float(e): i for i, e in enumerate(sol.expiries)}
    xs = np.array([0.65, 0.75, 0.85, 0.95, 1.00, 1.05, 1.15])
    quotes = []
    for t in _EXPIRIES:
        for x, p in zip(xs, sol.price_at(idx[t], xs)):
            quotes.append(OptionQuote(t=t, x=float(x), price=float(p), tol=2e-4))
    return quotes


def test_front_tie_byte_identical_when_off():
    quotes = _time_varying_quotes()
    flat = AffineVarianceSurface(
        t_nodes=_T_NODES, x_nodes=_X_NODES, theta=np.full((3, 7), 0.06)
    )
    base = calibrate_affine(flat, quotes, _X_GRID, _T_GRID, reg_lambda=1e-2)
    off = calibrate_affine(
        flat, quotes, _X_GRID, _T_GRID, reg_lambda=1e-2, front_tie_weight=0.0
    )
    assert np.array_equal(base.surface.theta, off.surface.theta)


def test_front_tie_pulls_t0_toward_first_row():
    quotes = _time_varying_quotes()
    flat = AffineVarianceSurface(
        t_nodes=_T_NODES, x_nodes=_X_NODES, theta=np.full((3, 7), 0.06)
    )
    free = calibrate_affine(flat, quotes, _X_GRID, _T_GRID, reg_lambda=1e-2)
    tied = calibrate_affine(
        flat, quotes, _X_GRID, _T_GRID, reg_lambda=1e-2, front_tie_weight=1e2
    )
    gap_free = float(np.linalg.norm(free.surface.theta[0] - free.surface.theta[1]))
    gap_tied = float(np.linalg.norm(tied.surface.theta[0] - tied.surface.theta[1]))
    assert gap_free > 0.0
    assert gap_tied < gap_free  # the tie pins the front to the first row


def _left_wing_vol_curvature(theta_row: np.ndarray) -> float:
    """Min second difference of the VOL row over the left-wing nodes (x < 0.85);
    negative => concave."""
    vol = np.sqrt(theta_row)
    d2 = vol[2:] - 2.0 * vol[1:-1] + vol[:-2]  # uniform x spacing here
    left = _X_NODES[1:-1] < 0.85
    return float(d2[left].min())


def test_convex_wing_byte_identical_when_off():
    quotes = _concave_wing_quotes()
    flat = AffineVarianceSurface(
        t_nodes=_T_NODES, x_nodes=_X_NODES, theta=np.full((3, 7), 0.06)
    )
    cols = np.array([0, 1, 2, 3])
    base = calibrate_affine(flat, quotes, _X_GRID, _T_GRID, reg_lambda=1.0)
    off = calibrate_affine(
        flat, quotes, _X_GRID, _T_GRID, reg_lambda=1.0,
        convex_cols=cols, convex_weight=0.0,  # off -> no extra residual rows
    )
    assert np.array_equal(base.surface.theta, off.surface.theta)


def test_convex_wing_penalty_convexifies_left_wing():
    quotes = _concave_wing_quotes()
    flat = AffineVarianceSurface(
        t_nodes=_T_NODES, x_nodes=_X_NODES, theta=np.full((3, 7), 0.06)
    )
    cols = np.array([0, 1, 2, 3])  # x <= 0.90, the left wing
    free = calibrate_affine(flat, quotes, _X_GRID, _T_GRID, reg_lambda=1.0)
    convex = calibrate_affine(
        flat, quotes, _X_GRID, _T_GRID, reg_lambda=1.0,
        convex_cols=cols, convex_weight=1e5,
    )
    # The unconstrained fit recovers a concave left vol wing; the penalty lifts
    # the worst curvature toward convex (>= 0) at every fitted maturity row.
    for i in range(1, _T_NODES.size):  # skip the t=0 row (no quotes)
        free_c = _left_wing_vol_curvature(free.surface.theta[i])
        convex_c = _left_wing_vol_curvature(convex.surface.theta[i])
        assert free_c < 0.0  # the data wants concave
        assert convex_c > free_c  # the penalty pushes it convex-ward
        assert convex_c > -5e-3  # and essentially achieves convexity


def _rows_with_wing(k_lo: float):
    """Minimal _gather-style rows (iso, tau, k, w, prepared, band) — a low-vol
    skew quoted from ``k_lo`` to +0.2 across three expiries."""
    rows = []
    for t in (0.1, 0.5, 1.0):
        k = np.linspace(k_lo, 0.20, 15)
        vol = 0.15 + 0.10 * np.maximum(-k, 0.0)  # equity-like put skew, ~15% ATM
        rows.append((f"2026-{t}", float(t), k, vol * vol * t, None, None))
    return rows


def test_convex_wing_confined_to_quoted_extrapolation():
    """The convex-wing constraint must NOT bite on vertices the quotes already
    constrain — only the unquoted extrapolation tail. With a dense wing (quotes
    reaching well past the 5Δ-put strike) the 5Δ region is full of quoted
    vertices, but the data-bounded rule selects none, so the constraint can't
    fight the quotes (the SPY 26bp-at-gridXNodes=20 regression)."""
    rows = _rows_with_wing(k_lo=-0.5)  # quotes reach k = -0.5, past 5Δ
    opts = OptionsSettings(convexWing=True, gridStrikeMode="delta", gridXNodes=20)
    _, x_nodes, _, convex_cols = _resolve_grid(rows, opts)

    sigma_star, t_star = _axis_scale(rows)
    k_wing = sigma_star * np.sqrt(t_star) * float(ndtri(0.05))
    naive = np.flatnonzero(x_nodes <= np.exp(k_wing) * (1.0 + 1e-9))
    assert naive.size > 0  # the 5Δ region DOES contain (quoted) vertices...
    assert convex_cols is None  # ...but the fix excludes them (all within data)

    # Off ⇒ never selected, regardless of grid.
    _, _, _, off = _resolve_grid(rows, opts.model_copy(update={"convexWing": False}))
    assert off is None

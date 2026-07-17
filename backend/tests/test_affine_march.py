"""Stage 6' — Numba vectorized-Thomas Dupire march.

The compiled no-pivot Thomas march (volfit.models.localvol.affine_march) replaces the
~74%-of-cost scipy/LAPACK multi-RHS sensitivity solve. Gates: it reproduces the
banded march to rounding (prices + sensitivities), an end-to-end calibration with the
numba engine lands the banded surface within tol, and the dispatcher falls back to the
banded path for the cases the kernel does not cover (value-only, Rannacher, left-slope).
"""

import numpy as np
import pytest

from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
    solve_affine_dupire,
)
from volfit.models.localvol.affine_march import numba_available

pytestmark = pytest.mark.skipif(not numba_available(), reason="numba not installed")

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.005 * np.arange(201)
EXPS = [0.25, 0.5, 1.0]


def _surface():
    th = (0.032 + 0.006 * TAU[:, None] + 0.030 * (1 - XI[None, :]) ** 2
          + 0.012 * (1 - XI[None, :]))
    return AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=th)


def test_numba_march_matches_banded_prices_and_sens():
    surf = _surface()
    banded = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, engine="banded")
    numba = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, engine="numba")
    assert np.max(np.abs(numba.prices - banded.prices)) < 1e-12
    assert np.max(np.abs(numba.sens - banded.sens)) < 1e-11


def test_numba_engine_value_only_falls_back_to_banded():
    """The kernel covers only the sensitivity march; a value-only solve uses banded
    and is byte-identical to the default."""
    surf = _surface()
    a = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, engine="numba")
    b = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, engine="banded")
    assert np.array_equal(a.prices, b.prices)


def test_numba_engine_rannacher_falls_back_to_banded():
    """Rannacher (CN) is not covered by the kernel -> banded, identical to banded CN."""
    surf = _surface()
    a = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True,
                            time_scheme="rannacher", engine="numba")
    b = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True,
                            time_scheme="rannacher", engine="banded")
    assert np.array_equal(a.prices, b.prices)
    assert np.array_equal(a.sens, b.sens)


def _heavy_case(n_t_vtx, n_x_vtx, expiries, strikes):
    t_nodes = np.linspace(0.0, float(max(expiries)), n_t_vtx)
    x_nodes = np.linspace(0.6, 1.6, n_x_vtx)
    tt, xx = np.meshgrid(t_nodes, x_nodes, indexing="ij")
    theta = np.clip(0.04 + 0.01 * tt + 0.03 * (1 - xx) ** 2 + 0.01 * (1 - xx), 0.006, 0.19)
    surf = AffineVarianceSurface(t_nodes=t_nodes, x_nodes=x_nodes, theta=theta)
    x_grid = 0.01 * np.arange(251)
    t_pts, prev = [0.0], 0.0
    for e in expiries:
        n = max(1, int(np.ceil((float(e) - prev) / 0.01)))
        t_pts.extend(np.linspace(prev, float(e), n + 1)[1:].tolist())
        prev = float(e)
    t_grid = np.array(t_pts)
    sol = solve_affine_dupire(surf, x_grid, t_grid, list(expiries))
    idx = {float(t): i for i, t in enumerate(sol.expiries)}
    options = [
        OptionQuote(t=float(e), x=float(x), price=float(sol.price_at(idx[float(e)], x)), tol=2e-4)
        for e in expiries for x in strikes
    ]
    flat = AffineVarianceSurface(
        t_nodes=t_nodes, x_nodes=x_nodes, theta=np.full((n_t_vtx, n_x_vtx), 0.04)
    )
    return flat, options, x_grid, t_grid


def test_numba_calibration_matches_banded_surface():
    """End-to-end: the numba-engine fit lands the banded fit's surface (the ~1e-15
    march difference does not move the converged optimum materially)."""
    flat, options, x_grid, t_grid = _heavy_case(
        13, 21, np.linspace(0.1, 2.5, 10), np.linspace(0.72, 1.28, 17)
    )
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20))
    banded = calibrate_affine(flat, options, x_grid, t_grid, engine="banded", **kw)
    numba = calibrate_affine(flat, options, x_grid, t_grid, engine="numba", **kw)
    assert numba.cost == pytest.approx(banded.cost, rel=1e-4)
    assert np.max(np.abs(numba.surface.theta - banded.surface.theta)) < 1e-3


def test_numba_matches_banded_under_left_wing_clamp():
    """The positivity clamp (negative left-wing extrapolation floored at 0 with
    dnu/dtheta = 0 on clamped rows) is implemented independently in the banded
    and numba kernels — they must still agree to rounding."""
    t_nodes = np.array([0.0, 0.01, 0.1, 0.5])
    x_nodes = np.array([0.68, 0.7114, 0.85, 1.00, 1.15, 1.40])
    theta = np.tile(np.array([0.33, 0.74, 0.09, 0.02, 0.02, 0.04]), (4, 1))
    surf = AffineVarianceSurface(
        t_nodes=t_nodes, x_nodes=x_nodes, theta=theta, left_extrap_a=1.5
    )
    x_grid = 0.005 * np.arange(501)
    t_grid = np.concatenate([[0.0], np.linspace(0.001, 0.5, 120)])
    exps = [float(t_grid[40]), 0.5]
    banded = solve_affine_dupire(surf, x_grid, t_grid, exps, sensitivities=True, engine="banded")
    numba = solve_affine_dupire(surf, x_grid, t_grid, exps, sensitivities=True, engine="numba")
    assert np.all(np.isfinite(banded.prices)) and banded.prices.max() <= 1.0 + 1e-9
    assert np.max(np.abs(numba.prices - banded.prices)) < 1e-11
    assert np.max(np.abs(numba.sens - banded.sens)) < 1e-9

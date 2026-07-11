"""Memory guard for the theta-independent Dupire step basis (the phi tensor).

A worst-case universe (short-front dx cap x sub-stepped ladder x dense vertex
grid) makes the dense (n_steps, n_int, m) store GiB-scale and the allocation
fails ("Unable to allocate 1.66 GiB", the SPY 9-expiry live bug). Above the
VOLFIT_LV_PHI_DENSE_MB budget precompute_dupire_steps now degrades to an EXACT
row-sparse store (common path) or lazy per-step re-evaluation (left-lin split /
var-swap backward march). Gates here:

- the default build stays dense (byte-identical hot path untouched);
- the sparse banded solve is bit-identical to the dense banded solve (the
  densified step matrices are the same floats);
- the sparse Numba kernel matches to rounding (same gate as dense-numba);
- the lazy left-lin and var-swap fallbacks are bit-identical (same basis calls);
- an end-to-end calibration under a forced tiny budget lands the dense fit.
"""

import numpy as np
import pytest

from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
    precompute_dupire_steps,
    solve_affine_dupire,
)
from volfit.models.localvol.affine_march import numba_available
from volfit.models.localvol.varswap_pde import (
    precompute_varswap_steps,
    solve_varswap_source,
)

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.60, 0.80, 0.95, 1.00, 1.05, 1.20, 1.60])  # x_min > 0: left wing live
X_GRID = 0.02 * np.arange(101)  # from 0 to 2.0; x = 1 is node 50
T_GRID = 0.01 * np.arange(101)
EXPS = [0.25, 0.5, 1.0]


def _surface(interp: str = "delaunay", left_a: float = 0.0) -> AffineVarianceSurface:
    th = (0.032 + 0.006 * TAU[:, None] + 0.030 * (1 - XI[None, :]) ** 2
          + 0.012 * (1 - XI[None, :]))
    return AffineVarianceSurface(
        t_nodes=TAU, x_nodes=XI, theta=th, interp=interp, left_extrap_a=left_a
    )


def _force_sparse(monkeypatch):
    monkeypatch.setenv("VOLFIT_LV_PHI_DENSE_MB", "0")


def test_default_precompute_stays_dense():
    steps = precompute_dupire_steps(_surface(), X_GRID, T_GRID)
    assert isinstance(steps.phi, np.ndarray)
    assert steps.phi_vals is None and steps.surface is None


@pytest.mark.parametrize("interp", ["delaunay", "tri_lower", "tri_upper", "bilinear"])
@pytest.mark.parametrize("left_a", [0.0, 0.8])
def test_sparse_banded_solve_is_bit_identical(monkeypatch, interp, left_a):
    """Sparse extraction + per-step densify rebuilds the exact dense matrices, so
    the banded march output is bitwise equal to the dense-steps march."""
    surf = _surface(interp, left_a)
    dense = precompute_dupire_steps(surf, X_GRID, T_GRID)
    _force_sparse(monkeypatch)
    sparse = precompute_dupire_steps(surf, X_GRID, T_GRID)
    assert sparse.phi is None and sparse.phi_vals is not None
    assert np.array_equal(sparse.active_k, dense.active_k)
    kw = dict(sensitivities=True, engine="banded")
    a = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, steps=dense, **kw)
    b = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, steps=sparse, **kw)
    assert np.array_equal(a.prices, b.prices)
    assert np.array_equal(a.sens, b.sens)


@pytest.mark.skipif(not numba_available(), reason="numba not installed")
def test_sparse_numba_matches_dense_to_rounding(monkeypatch):
    """The sparse kernel applies the sensitivity source as a scatter (different
    rounding order than the dense fused term) — same 1e-12/1e-11 gate as the
    dense numba-vs-banded lock."""
    surf = _surface(left_a=0.8)
    dense = precompute_dupire_steps(surf, X_GRID, T_GRID)
    _force_sparse(monkeypatch)
    sparse = precompute_dupire_steps(surf, X_GRID, T_GRID)
    kw = dict(sensitivities=True, engine="numba")
    a = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, steps=dense, **kw)
    b = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, steps=sparse, **kw)
    assert np.max(np.abs(a.prices - b.prices)) < 1e-12
    assert np.max(np.abs(a.sens - b.sens)) < 1e-11


def test_lazy_left_lin_solve_is_bit_identical(monkeypatch):
    """The over-budget left-lin split re-evaluates basis_components per step —
    the same calls the dense build made, so the solve is bitwise equal."""
    surf = _surface(left_a=0.5)
    dense = precompute_dupire_steps(surf, X_GRID, T_GRID, with_left_lin=True)
    _force_sparse(monkeypatch)
    lazy = precompute_dupire_steps(surf, X_GRID, T_GRID, with_left_lin=True)
    assert lazy.phi is None and lazy.lazy_left_lin and lazy.surface is surf
    assert np.array_equal(lazy.active_k, dense.active_k)
    kw = dict(sensitivities=True, fit_left_a=True, left_a=0.7)
    a = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, steps=dense, **kw)
    b = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, steps=lazy, **kw)
    assert np.array_equal(a.prices, b.prices)
    assert np.array_equal(a.sens, b.sens)


@pytest.mark.parametrize("with_lin", [False, True])
def test_varswap_lazy_is_bit_identical(monkeypatch, with_lin):
    surf = _surface(left_a=0.5 if with_lin else 0.0)
    t_grid = T_GRID[:51]  # backward march to T = 0.5
    dense = precompute_varswap_steps(surf, X_GRID, t_grid, with_left_lin=with_lin)
    _force_sparse(monkeypatch)
    lazy = precompute_varswap_steps(surf, X_GRID, t_grid, with_left_lin=with_lin)
    assert lazy.phi_full is None and lazy.surface is surf
    kw = dict(sensitivities=True, fit_left_a=with_lin)
    if with_lin:
        kw["left_a"] = 0.6
    ia, da = solve_varswap_source(surf, X_GRID, t_grid, steps=dense, **kw)
    ib, db = solve_varswap_source(surf, X_GRID, t_grid, steps=lazy, **kw)
    assert ia == ib
    assert np.array_equal(da, db)


def _fit_case():
    """Small synthetic fit (pattern of test_affine_march._heavy_case)."""
    surf = _surface()
    sol = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS)
    idx = {float(t): i for i, t in enumerate(sol.expiries)}
    strikes = np.linspace(0.72, 1.28, 13)
    options = [
        OptionQuote(t=float(e), x=float(x), price=float(sol.price_at(idx[float(e)], x)), tol=2e-4)
        for e in EXPS for x in strikes
    ]
    flat = AffineVarianceSurface(
        t_nodes=TAU, x_nodes=XI, theta=np.full((TAU.size, XI.size), 0.04)
    )
    return flat, options


def test_calibration_over_budget_lands_dense_fit(monkeypatch):
    """End-to-end (the live-bug shape): a fit whose phi store exceeds the budget
    completes on the sparse path and lands the dense fit's surface."""
    flat, options = _fit_case()
    engine = "numba" if numba_available() else "banded"
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20), engine=engine)
    dense = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)
    _force_sparse(monkeypatch)
    sparse = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)
    assert sparse.cost == pytest.approx(dense.cost, rel=1e-4)
    assert np.max(np.abs(sparse.surface.theta - dense.surface.theta)) < 1e-3

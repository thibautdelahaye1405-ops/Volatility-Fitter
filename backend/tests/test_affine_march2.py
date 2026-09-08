"""LV operator arc O2 — the plan-generic compiled Dupire march (affine_march2).

Gates: for every scheme (implicit, Rannacher, BDF2) and both basis layouts
(dense, over-budget sparse) the kernel matches the banded march to solver
rounding in prices and sensitivities; the implicit plan through the generic
kernel agrees with the dedicated implicit kernel; the left-wing positivity
clamp (dν/dθ = 0 on clamped rows) is honoured; ``solve_affine_dupire`` routes
non-implicit plans there under ``engine="numba"`` and the calibration under
BDF2 lands the same surface on either engine.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.models.localvol import AffineVarianceSurface, solve_affine_dupire
from volfit.models.localvol.affine import precompute_dupire_steps
from volfit.models.localvol.affine_march import numba_available
from volfit.models.localvol.affine_march2 import march_plan, march_plan_sparse, warmup
from volfit.models.localvol.time_schemes import build_plan

pytestmark = pytest.mark.skipif(not numba_available(), reason="numba not importable")

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
EXPS = [0.25, 0.5, 1.0]
SCHEMES = ("implicit", "rannacher", "bdf2")


def _true_variance(t, x):
    return (0.032 + 0.006 * t + 0.030 * (1.0 - x) ** 2 + 0.012 * (1.0 - x)
            + 0.004 * np.sin(np.pi * t) * np.exp(-(((x - 1.0) / 0.35) ** 2)))


def _surface(left_a: float = 0.0) -> AffineVarianceSurface:
    return AffineVarianceSurface(
        t_nodes=TAU, x_nodes=XI, theta=_true_variance(TAU[:, None], XI[None, :]), left_extrap_a=left_a
    )


def _tgrid(dt_max):
    pts, prev = [0.0], 0.0
    for e in EXPS:
        s = max(1, int(np.ceil((e - prev) / dt_max)))
        pts.extend(np.linspace(prev, e, s + 1)[1:].tolist())
        prev = e
    return np.array(pts)


T_GRID = _tgrid(0.02)


def _stencil(x):
    h = np.diff(x)
    hm, hp = h[:-1], h[1:]
    xi2 = x[1:-1] ** 2
    a_m = xi2 / ((hm + hp) * hm)
    a_p = xi2 / ((hm + hp) * hp)
    return a_m, a_p, -(a_m + a_p)


def _want_step(t, exps):
    pos = np.searchsorted(t, exps)
    ws = np.full(t.size - 1, -1, dtype=np.int64)
    for i, p in enumerate(pos):
        ws[p - 1] = i
    return ws


@pytest.mark.parametrize("scheme", SCHEMES)
def test_dense_kernel_matches_banded(scheme):
    surf = _surface()
    banded = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, time_scheme=scheme)
    steps = precompute_dupire_steps(surf, X_GRID, T_GRID)
    a_m, a_p, a_0 = _stencil(X_GRID)
    pr, se = march_plan(
        steps.phi, surf.theta.ravel(), a_m, a_p, a_0, np.diff(T_GRID), build_plan(T_GRID, scheme),
        steps.active_k, _want_step(T_GRID, np.array(EXPS)), np.maximum(1.0 - X_GRID, 0.0), len(EXPS),
    )
    assert np.allclose(pr, banded.prices, rtol=0.0, atol=1e-13)
    assert np.allclose(se, banded.sens, rtol=1e-9, atol=1e-12)


@pytest.mark.parametrize("scheme", SCHEMES)
def test_sparse_kernel_matches_banded(scheme, monkeypatch):
    monkeypatch.setenv("VOLFIT_LV_PHI_DENSE_MB", "0")  # force the sparse store
    surf = _surface()
    banded = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, time_scheme=scheme)
    steps = precompute_dupire_steps(surf, X_GRID, T_GRID)
    assert steps.phi_vals is not None
    a_m, a_p, a_0 = _stencil(X_GRID)
    pr, se = march_plan_sparse(
        steps.phi_vals, steps.phi_cols, surf.theta.ravel(), a_m, a_p, a_0, np.diff(T_GRID),
        build_plan(T_GRID, scheme), steps.active_k, _want_step(T_GRID, np.array(EXPS)),
        np.maximum(1.0 - X_GRID, 0.0), len(EXPS), surf.n_params,
    )
    assert np.allclose(pr, banded.prices, rtol=0.0, atol=1e-13)
    assert np.allclose(se, banded.sens, rtol=1e-9, atol=1e-12)


def test_solver_routes_non_implicit_plans_to_the_generic_kernel(monkeypatch):
    """Under engine="numba" a BDF2 sensitivity solve must call affine_march2."""
    import volfit.models.localvol.affine_march2 as m2

    calls = []
    real = m2.march_plan
    monkeypatch.setattr(m2, "march_plan", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    surf = _surface()
    a = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, time_scheme="bdf2", engine="numba")
    b = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, time_scheme="bdf2", engine="banded")
    assert calls == [1]
    assert np.allclose(a.prices, b.prices, rtol=0.0, atol=1e-13)
    assert np.allclose(a.sens, b.sens, rtol=1e-9, atol=1e-12)


def test_kernel_honours_the_left_wing_clamp():
    """A bottom cell whose variance rises with x extrapolates negative below
    x_nodes[0]; the clamp floors ν at 0 with dν/dθ = 0 — same on both paths."""
    theta = _true_variance(TAU[:, None], XI[None, :]).copy()
    theta[:, 0] = 0.004  # far below theta[:, 1] -> the linear wing dives negative
    surf = AffineVarianceSurface(t_nodes=TAU, x_nodes=np.array([0.5, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20]),
                                 theta=theta, left_extrap_a=6.0)
    for scheme in ("rannacher", "bdf2"):
        a = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, time_scheme=scheme, engine="numba")
        b = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, sensitivities=True, time_scheme=scheme, engine="banded")
        assert np.all(np.isfinite(a.prices)) and a.prices.max() <= 1.0 + 1e-9
        assert np.allclose(a.prices, b.prices, rtol=0.0, atol=1e-13)
        assert np.allclose(a.sens, b.sens, rtol=1e-9, atol=1e-12)


def test_calibration_under_bdf2_matches_banded_surface():
    from volfit.models.localvol import OptionQuote, calibrate_affine

    surf = _surface()
    truth = solve_affine_dupire(surf, X_GRID, T_GRID, EXPS, time_scheme="bdf2")
    quotes = []
    for i, t in enumerate(EXPS):
        for x in (0.8, 0.9, 1.0, 1.1, 1.2):
            quotes.append(OptionQuote(t=t, x=x, price=float(truth.price_at(i, x)), tol=1e-4))
    seed = surf.with_theta(np.full(surf.n_params, 0.04))
    fits = {}
    for engine in ("banded", "numba"):
        cal = calibrate_affine(seed, quotes, X_GRID, T_GRID, time_scheme="bdf2", engine=engine, max_nfev=40)
        fits[engine] = cal.surface.theta
    assert np.allclose(fits["banded"], fits["numba"], rtol=1e-6, atol=1e-8)


def test_warmup_is_idempotent():
    warmup()
    warmup()

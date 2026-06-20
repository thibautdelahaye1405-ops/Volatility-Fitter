"""Stage 5 — matrix-free Gauss-Newton solver for the affine LV calibration.

Three layers of gate:
  * operator identities (volfit.models.localvol.affine_gn.LinearizedJacobian):
    the tangent action Jv matches finite differences, ⟨Jv, w⟩ = ⟨v, Jᵀw⟩, and a
    gradient α-test (the directional derivative of ½‖r‖² equals (Jᵀr)·d);
  * end-to-end equivalence: ``calibrate_affine(gn=True)`` lands the SAME surface
    (objective + nodal θ within tol) as the dense TRF path on the golden 3×7 case
    and a heavy ~525-vertex case, in no more PDE evaluations;
  * robustness: a bound-binding case stays inside the box with a populated
    active mask, and a forced GN breakdown falls back to dense TRF cleanly.
"""

import numpy as np
import pytest

from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    VarSwapQuote,
    calibrate_affine,
    solve_affine_dupire,
)
from volfit.models.localvol.affine_gn import LinearizedJacobian

# --- golden note grids (same as test_localvol_affine) ---------------------
TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.005 * np.arange(201)
QUOTE_TABLE = [
    (0.25, 0.80, 0.200277), (0.25, 0.90, 0.105645), (0.25, 1.00, 0.036544),
    (0.25, 1.10, 0.007310), (0.25, 1.20, 0.000861),
    (0.50, 0.80, 0.202596), (0.50, 0.90, 0.115765), (0.50, 1.00, 0.053085),
    (0.50, 1.10, 0.019104), (0.50, 1.20, 0.005456),
    (1.00, 0.80, 0.211163), (1.00, 0.90, 0.133968), (1.00, 1.00, 0.076657),
    (1.00, 1.10, 0.039690), (1.00, 1.20, 0.018833),
]
VARSWAP_TABLE = [(0.25, 0.033931), (0.50, 0.035713), (1.00, 0.037479)]


def _golden_inputs():
    options = [OptionQuote(t=t, x=x, price=p, tol=2e-4) for t, x, p, in QUOTE_TABLE]
    varswaps = [VarSwapQuote(t=t, total_var=t * r, tol=2e-4) for t, r in VARSWAP_TABLE]
    flat = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=np.full((3, 7), 0.04))
    return flat, options, varswaps


# =========================================================================
# 1. Operator identities (apply_jacobian / apply_jacobian_transpose)
# =========================================================================
def _price_residual_setup():
    """A small price-residual map r(θ) = C(θ) − y with its analytic Jacobian.

    Builds the golden surface, prices a handful of option points with forward
    sensitivities, and sets the market target to a perturbed surface's prices so
    the residual is non-trivial. Returns (surf, th0, quote_pts, J, r_fn, y).
    """
    th0 = np.full((3, 7), 0.04)
    surf = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=th0)
    quote_pts = [(t, x) for t, x, _ in QUOTE_TABLE]
    sol = solve_affine_dupire(surf, X_GRID, T_GRID, [0.25, 0.5, 1.0], sensitivities=True)
    idx = {float(t): i for i, t in enumerate(sol.expiries)}

    def prices(theta_flat):
        s = surf.with_theta(theta_flat)
        sv = solve_affine_dupire(s, X_GRID, T_GRID, [0.25, 0.5, 1.0])
        ix = {float(t): i for i, t in enumerate(sv.expiries)}
        return np.array([float(sv.price_at(ix[t], x)) for t, x in quote_pts])

    rng = np.random.default_rng(3)
    y = prices(th0.ravel() + 0.003 * rng.standard_normal(th0.size))  # market target
    J = np.vstack([sol.sens_at(idx[t], np.array([x]))[0] for t, x in quote_pts])
    r0 = prices(th0.ravel()) - y
    return surf, th0.ravel(), quote_pts, J, prices, y, r0


def test_apply_jacobian_matches_finite_differences():
    _, th0, _, J, prices, y, _ = _price_residual_setup()
    lin = LinearizedJacobian(J)
    rng = np.random.default_rng(11)
    v = rng.standard_normal(th0.size)
    eps = 1e-6
    fd = (prices(th0 + eps * v) - prices(th0 - eps * v)) / (2.0 * eps)
    assert np.allclose(lin.apply_jacobian(v), fd, atol=1e-6)


def test_jacobian_transpose_inner_product_identity():
    _, th0, _, J, *_ = _price_residual_setup()
    lin = LinearizedJacobian(J)
    rng = np.random.default_rng(5)
    v = rng.standard_normal(J.shape[1])
    w = rng.standard_normal(J.shape[0])
    lhs = float(lin.apply_jacobian(v) @ w)
    rhs = float(v @ lin.apply_jacobian_transpose(w))
    assert lhs == pytest.approx(rhs, rel=1e-12, abs=1e-12)


def test_gradient_alpha_test():
    """Directional derivative of f(θ)=½‖r(θ)‖² equals (Jᵀr)·d to O(α)."""
    _, th0, _, J, prices, y, r0 = _price_residual_setup()
    lin = LinearizedJacobian(J)
    g = lin.apply_jacobian_transpose(r0)  # = Jᵀr, the gradient

    def f(theta):
        r = prices(theta) - y
        return 0.5 * float(r @ r)

    rng = np.random.default_rng(7)
    d = rng.standard_normal(th0.size)
    directional = float(g @ d)
    a = 1e-6
    fd = (f(th0 + a * d) - f(th0 - a * d)) / (2.0 * a)
    assert fd == pytest.approx(directional, rel=1e-4, abs=1e-7)


# =========================================================================
# 2. End-to-end equivalence with dense TRF
# =========================================================================
def test_gn_matches_trf_on_golden():
    flat, options, varswaps = _golden_inputs()
    kw = dict(varswaps=varswaps, reg_lambda=50.0, bounds=(0.005, 0.20))
    trf = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)
    gn = calibrate_affine(flat, options, X_GRID, T_GRID, gn=True, **kw)
    assert gn.message.startswith("matrix-free")  # GN, not the fallback
    assert gn.cost == pytest.approx(trf.cost, rel=1e-4)
    assert np.max(np.abs(gn.surface.theta - trf.surface.theta)) < 2.5e-3
    # the heavy-grid payoff is fewer expensive PDE evaluations, never more
    assert gn.n_evals <= trf.n_evals


def _heavy_case(n_t_vtx, n_x_vtx, expiries, strikes, var_hi=0.20):
    t_nodes = np.linspace(0.0, float(max(expiries)), n_t_vtx)
    x_nodes = np.linspace(0.6, 1.6, n_x_vtx)
    tt, xx = np.meshgrid(t_nodes, x_nodes, indexing="ij")
    theta = np.clip(0.04 + 0.01 * tt + 0.03 * (1.0 - xx) ** 2 + 0.01 * (1.0 - xx), 0.006, 0.19)
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


def test_gn_matches_trf_on_heavy_grid():
    """~325-vertex case: GN must land the TRF surface in no more PDE evals."""
    flat, options, x_grid, t_grid = _heavy_case(
        13, 25, np.linspace(0.1, 2.5, 12), np.linspace(0.72, 1.28, 21)
    )
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20))
    trf = calibrate_affine(flat, options, x_grid, t_grid, **kw)
    gn = calibrate_affine(flat, options, x_grid, t_grid, gn=True, **kw)
    assert gn.message.startswith("matrix-free")
    assert gn.cost == pytest.approx(trf.cost, rel=1e-3)
    assert np.max(np.abs(gn.surface.theta - trf.surface.theta)) < 3e-3
    assert gn.n_evals <= trf.n_evals


# =========================================================================
# 3. Robustness — bounds and TRF fallback
# =========================================================================
def test_gn_respects_box_bounds():
    """A tight upper bound the unconstrained optimum would exceed: GN must stay in
    the box and mark the binding nodes active, agreeing with bounded TRF."""
    flat, options, x_grid, t_grid = _heavy_case(
        7, 11, np.linspace(0.1, 2.0, 6), np.linspace(0.75, 1.25, 9)
    )
    bounds = (0.02, 0.05)  # the generating surface runs above 0.05 in the wings
    trf = calibrate_affine(flat, options, x_grid, t_grid, reg_lambda=50.0, bounds=bounds)
    gn = calibrate_affine(flat, options, x_grid, t_grid, reg_lambda=50.0, bounds=bounds, gn=True)
    assert gn.surface.theta.min() >= bounds[0] - 1e-9
    assert gn.surface.theta.max() <= bounds[1] + 1e-9
    assert gn.diagnostics.active_bound_count > 0  # some node rests on a bound
    assert np.max(np.abs(gn.surface.theta - trf.surface.theta)) < 3e-3


def test_gn_falls_back_to_trf_on_breakdown(monkeypatch):
    """If the GN solver raises, ``calibrate_affine(gn=True)`` recovers via dense
    TRF and returns exactly the TRF surface."""
    flat, options, varswaps = _golden_inputs()
    kw = dict(varswaps=varswaps, reg_lambda=50.0, bounds=(0.005, 0.20))
    trf = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)

    def _boom(*args, **kwargs):
        raise ValueError("forced GN breakdown")

    monkeypatch.setattr("volfit.models.localvol.affine_calib.gauss_newton", _boom)
    fell_back = calibrate_affine(flat, options, X_GRID, T_GRID, gn=True, **kw)
    assert np.allclose(fell_back.surface.theta, trf.surface.theta, atol=1e-9)


def test_gn_starved_budget_still_returns_valid_surface():
    """A 1-eval budget cannot converge GN, so it reports non-convergence and falls
    back to TRF; the call must still return a finite, in-bounds surface (no crash)."""
    flat, options, varswaps = _golden_inputs()
    res = calibrate_affine(
        flat, options, X_GRID, T_GRID, varswaps=varswaps, reg_lambda=50.0,
        bounds=(0.005, 0.20), gn=True, max_nfev=1,
    )
    assert np.all(np.isfinite(res.surface.theta))
    assert res.surface.theta.min() >= 0.005 - 1e-9


def test_gn_early_stop_cuts_evals_without_fallback():
    """The GN stall early-stop (Stage 8, GN flavour) terminates a long GN fit at the
    best ACCEPTED iterate — status 4, no TRF fallback — in fewer evals than letting it
    run, while landing essentially the same surface."""
    flat, options, x_grid, t_grid = _heavy_case(
        9, 15, np.linspace(0.1, 2.0, 8), np.linspace(0.75, 1.25, 13)
    )
    # Perturb the quotes so the LSQ has an irreducible residual (the real-data regime):
    # GN then takes a long tail of tiny steps instead of converging in a few evals.
    rng = np.random.default_rng(0)
    options = [
        OptionQuote(t=o.t, x=o.x, price=o.price * (1.0 + 2e-3 * rng.standard_normal()), tol=o.tol)
        for o in options
    ]
    # tight GN tolerances so it would otherwise grind on -> the stall is the terminator
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20), gn=True,
              gtol=1e-14, xtol=1e-14, ftol=1e-14, max_nfev=160)
    full = calibrate_affine(flat, options, x_grid, t_grid, **kw)
    early = calibrate_affine(
        flat, options, x_grid, t_grid, stall_window=10, stall_rtol=3e-3, **kw
    )
    assert early.diagnostics.status == 4  # GN stall path (not a TRF fallback)
    assert early.message.startswith("matrix-free")
    assert early.n_evals < full.n_evals
    # the early-stop fits the quotes about as well as the full GN run (the tail evals
    # it skipped barely move the data fit; the unconstrained wing nodes may drift more)
    assert early.rms_price_error <= 1.3 * full.rms_price_error + 1e-6

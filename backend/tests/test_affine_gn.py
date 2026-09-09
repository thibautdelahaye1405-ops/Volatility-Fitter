"""Stage 5 — matrix-free Gauss-Newton solver for the affine LV calibration.

Three layers of gate:
  * operator identities (volfit.models.localvol.affine_gn.LinearizedJacobian):
    the tangent action Jv matches finite differences, ⟨Jv, w⟩ = ⟨v, Jᵀw⟩, and a
    gradient α-test (the directional derivative of ½‖r‖² equals (Jᵀr)·d);
  * end-to-end equivalence: ``calibrate_affine(gn=True)`` lands the SAME surface
    (objective + nodal θ within tol) as the dense TRF path on the golden 3×7 case
    and a heavy ~525-vertex case, in no more PDE evaluations;
  * robustness: a bound-binding case stays inside the box with a populated
    active mask, and a forced GN breakdown falls back to dense TRF cleanly;
  * the active-set step (2026-09-09, affine_activeset): on a LINEAR residual
    with a binding box the step it returns is feasible and its predicted
    residual is the exact residual at the step (the clipped-step blindness
    that rejected half the old solver's steps is gone); the band step model
    reproduces the band objective's residual at the linearised prices and its
    re-linearisation flips exactly the crossing rows; the shared-block band
    operator (LinearizedJacobian.row_scales / extra) matches its dense
    materialisation on Jv, Jᵀw, the column scale and to_dense;
  * the band objective end-to-end: on the golden case with ±3 % price bands,
    GN converges (no TRF fallback), lands the TRF cost within tolerance, and
    every quote ends inside its band.
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
from volfit.calib.band import band_violation
from volfit.models.localvol.affine_activeset import (
    BandStepModel,
    LinearStepModel,
    active_set_step,
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
    # On this SMALL golden (single-digit-eval convergence) GN's fixed
    # per-iteration overhead can cost a few extra evals depending on the
    # scipy/numpy version (CI 1.18/2.4 measured trf=7, gn=10); the
    # fewer-evals payoff is the HEAVY grid's contract, asserted strictly on
    # the heavy case below. Here: same ballpark, never runaway.
    assert gn.n_evals <= max(trf.n_evals + 5, 2 * trf.n_evals)


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


def test_sparse_reg_operator_matches_dense():
    """A LinearizedJacobian with a (dense data, sparse reg) split gives the same
    matvec / rmatvec / column-scale / dense as the equivalent single dense block (#3)."""
    import scipy.sparse as sp

    rng = np.random.default_rng(4)
    data = rng.standard_normal((18, 30))
    reg = rng.standard_normal((40, 30))
    reg[np.abs(reg) < 1.0] = 0.0  # make it genuinely sparse
    lin_sp = LinearizedJacobian(data, sp.csr_matrix(reg))
    lin_de = LinearizedJacobian(np.vstack([data, reg]))
    v = rng.standard_normal(30)
    w = rng.standard_normal(58)
    assert np.allclose(lin_sp.apply_jacobian(v), lin_de.apply_jacobian(v))
    assert np.allclose(lin_sp.apply_jacobian_transpose(w), lin_de.apply_jacobian_transpose(w))
    assert np.allclose(lin_sp.column_scale(), lin_de.column_scale())
    assert np.allclose(lin_sp.to_dense(), lin_de.jac)
    assert lin_sp.shape == lin_de.shape


def test_gn_sparse_reg_equals_dense_reg():
    """The calibrated GN surface is identical whether the regularisation block is
    assembled sparse (#3, the default) or dense — the optimisation is unchanged."""
    import volfit.models.localvol.affine_calib as ac

    flat, options, x_grid, t_grid = _heavy_case(
        11, 17, np.linspace(0.1, 2.0, 8), np.linspace(0.75, 1.25, 13)
    )
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20), gn=True)
    try:
        ac._GN_SPARSE_REG = True
        sparse_fit = calibrate_affine(flat, options, x_grid, t_grid, **kw)
        ac._GN_SPARSE_REG = False
        dense_fit = calibrate_affine(flat, options, x_grid, t_grid, **kw)
    finally:
        ac._GN_SPARSE_REG = True
    assert np.allclose(sparse_fit.surface.theta, dense_fit.surface.theta, atol=1e-9)


def test_gn_trf_fallback_then_stall_returns_surface(monkeypatch):
    """Regression (backtest LV crash on NVDA/NDX): when a GN fit falls back to dense
    TRF (the stiff-name path) AND that TRF run early-stops on the stall, the synthetic
    ``_stall_result`` must form the gradient via the matrix-free operator — ``gn_op``
    keeps ``jb`` a LinearizedJacobian, which has no ``.T``. Before the fix this raised
    ``AttributeError: 'LinearizedJacobian' object has no attribute 'T'``."""
    flat, options, x_grid, t_grid = _heavy_case(
        9, 15, np.linspace(0.1, 2.0, 8), np.linspace(0.75, 1.25, 13)
    )
    rng = np.random.default_rng(1)
    options = [  # irreducible residual so the TRF fallback grinds into the stall window
        OptionQuote(t=o.t, x=o.x, price=o.price * (1.0 + 2e-3 * rng.standard_normal()), tol=o.tol)
        for o in options
    ]

    def _boom(*args, **kwargs):  # force the GN->TRF fallback (the stiff-name behaviour)
        raise ValueError("forced GN breakdown")

    monkeypatch.setattr("volfit.models.localvol.affine_calib.gauss_newton", _boom)
    # Tight tolerances so the fallback TRF grinds tiny non-improving steps near the
    # optimum and trips the option-block stall (the NVDA/NDX behaviour) -> _stall_result.
    res = calibrate_affine(
        flat, options, x_grid, t_grid, reg_lambda=50.0, bounds=(0.005, 0.20),
        gn=True, stall_window=6, stall_rtol=3e-3, max_nfev=160,
        gtol=1e-14, xtol=1e-14, ftol=1e-14,
    )
    assert np.all(np.isfinite(res.surface.theta))  # no crash, valid surface
    assert res.surface.theta.min() >= 0.005 - 1e-9
    assert res.surface.theta.max() <= 0.20 + 1e-9


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


# =========================================================================
# 4. The active-set step (2026-09-09) and the band step model
# =========================================================================
def test_active_set_step_prediction_exact_on_linear_problem_with_binding_box():
    """r(p) = A p − b is linear, so the model residual the step reports must
    equal the true residual at p + Δ — INCLUDING when the box clips half the
    components (the old projected step scored the clipped step it never solved
    for and rejected it). The step is feasible and reduces the cost."""
    rng = np.random.default_rng(21)
    m, n = 40, 12
    A = rng.standard_normal((m, n))
    b = rng.standard_normal(m) * 3.0
    p0 = np.zeros(n)
    lo, hi = np.full(n, -0.15), np.full(n, 0.15)  # a tight box: the LS solution is far outside
    cur = (A @ p0 - b, A)
    lin = LinearizedJacobian(A)
    step, r_pred, info = active_set_step(cur, lin, p0, lo, hi, 1e-6, 1e-12, LinearStepModel())
    assert step is not None and info["passes"] >= 2  # the box bit, the free part was re-solved
    assert np.all(p0 + step >= lo - 1e-12) and np.all(p0 + step <= hi + 1e-12)
    assert np.count_nonzero(np.isclose(np.abs(step), 0.15)) >= 1  # something is pinned
    np.testing.assert_allclose(r_pred, A @ (p0 + step) - b, rtol=1e-10, atol=1e-10)
    assert 0.5 * float(r_pred @ r_pred) < 0.5 * float(cur[0] @ cur[0])  # a descent step


def _band_case():
    rng = np.random.default_rng(4)
    n, m = 9, 5
    jp = rng.standard_normal((n, m))
    p = 1.0 + 0.1 * rng.standard_normal(n)
    mid = p + 0.05 * rng.standard_normal(n)
    lo, hi = mid - 0.03, mid + 0.03
    lo[2] = hi[2] = mid[2]  # a collapsed band (haircut wider than the half-spread)
    eta = np.full(n, 0.02)
    sqrt_anchor = np.sqrt(0.05)
    res = np.concatenate([band_violation(p, lo, hi) / eta, sqrt_anchor * (p - mid) / eta])
    scales = (np.where(p > hi, 1.0, 0.0) - np.where(p < lo, 1.0, 0.0)) / eta, np.full(n, sqrt_anchor) / eta
    lin = LinearizedJacobian(jp, None, row_scales=scales)
    cur = (res, lin, None, p, None, jp)
    return BandStepModel(eta=eta, p_lo=lo, p_hi=hi), cur, lin, jp, p, mid, lo, hi, eta, sqrt_anchor


def test_band_step_model_predicts_the_band_residual_at_linearised_prices():
    model, cur, lin, jp, p, mid, lo, hi, eta, sa = _band_case()
    rng = np.random.default_rng(8)
    step = 0.02 * rng.standard_normal(jp.shape[1])
    p_lin = p + jp @ step
    expect = np.concatenate([band_violation(p_lin, lo, hi) / eta, sa * (p_lin - mid) / eta])
    np.testing.assert_allclose(model.predict(cur, lin, step), expect, rtol=1e-12, atol=1e-12)
    # A zero step is the current residual, and its status is the current one.
    np.testing.assert_allclose(model.predict(cur, lin, np.zeros(jp.shape[1])), cur[0], atol=1e-14)
    assert np.array_equal(model.status(cur, None), model.status(cur, np.zeros(jp.shape[1])))


def test_band_step_model_relinearises_on_the_predicted_side():
    """A status that moves a quote to the far side of its band gets that
    quote's SIGNED distance to that edge as residual (negative while it is
    still inside) and ± its price row as Jacobian; the anchor rows never
    change; the collapsed row keeps its fixed label."""
    model, cur, lin, jp, p, mid, lo, hi, eta, sa = _band_case()
    status = model.status(cur, None)
    assert status[2] == 1.0  # the collapsed band's fixed label
    inside = np.flatnonzero(status == 0.0)
    assert inside.size > 0
    i = int(inside[0])
    flipped = status.copy()
    flipped[i] = 1.0  # predicted to leave through the top edge
    r_eff, lin_eff = model.linearize(cur, lin, flipped)
    n = model.n
    assert r_eff[i] == (p[i] - hi[i]) / eta[i] and r_eff[i] < 0.0
    np.testing.assert_allclose(r_eff[n:], cur[0][n:])  # anchor rows untouched
    dense = lin_eff.to_dense()
    np.testing.assert_allclose(dense[i], jp[i] / eta[i])
    np.testing.assert_allclose(dense[n:], lin.to_dense()[n:])  # anchor block identical
    # The unchanged status hands back the current linearisation itself.
    r_same, lin_same = model.linearize(cur, lin, status)
    assert r_same is cur[0] and lin_same is lin


def test_shared_block_operator_matches_its_dense_materialisation():
    rng = np.random.default_rng(12)
    n, m, k = 7, 5, 3
    jp = rng.standard_normal((n, m))
    extra = rng.standard_normal((k, m))
    from scipy import sparse
    reg = sparse.csr_matrix(rng.standard_normal((4, m)) * (rng.random((4, m)) > 0.5))
    s1, s2 = rng.standard_normal(n), rng.standard_normal(n)
    shared = LinearizedJacobian(jp, reg, row_scales=(s1, s2), extra=extra)
    dense = np.vstack([s1[:, None] * jp, s2[:, None] * jp, extra, reg.toarray()])
    plain = LinearizedJacobian(dense)
    assert shared.shape == dense.shape and shared.n_data == 2 * n + k
    np.testing.assert_allclose(shared.to_dense(), dense)
    v = rng.standard_normal(m)
    w = rng.standard_normal(dense.shape[0])
    np.testing.assert_allclose(shared.apply_jacobian(v), dense @ v, rtol=1e-12)
    np.testing.assert_allclose(shared.apply_jacobian_transpose(w), dense.T @ w, rtol=1e-12)
    np.testing.assert_allclose(shared.column_scale(), plain.column_scale(), rtol=1e-12)


def test_gn_band_objective_matches_trf_on_golden():
    """The bid-ask / haircut objective on the GN path (2026-09-09): GN
    converges on its own, lands the TRF cost, and every quote sits inside
    its ±3 % price band — the band target is met, not merely approached."""
    flat, options, _ = _golden_inputs()
    banded = [
        OptionQuote(t=o.t, x=o.x, price=o.price, tol=o.tol, price_lo=0.97 * o.price, price_hi=1.03 * o.price)
        for o in options
    ]
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20))
    trf = calibrate_affine(flat, banded, X_GRID, T_GRID, **kw)
    gn = calibrate_affine(flat, banded, X_GRID, T_GRID, gn=True, **kw)
    assert gn.message.startswith("matrix-free")  # GN, not the fallback
    assert gn.cost <= trf.cost * 1.02 + 1e-9
    lo = np.array([o.price_lo for o in banded])
    hi = np.array([o.price_hi for o in banded])
    assert np.all(gn.option_prices >= lo * (1 - 1e-9)) and np.all(gn.option_prices <= hi * (1 + 1e-9))


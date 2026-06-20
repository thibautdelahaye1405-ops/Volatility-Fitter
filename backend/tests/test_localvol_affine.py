"""Golden tests: piecewise-affine local-variance calibration vs the note.

Reference: Docs/piecewise_affine_local_variance_calibration.tex, section
"Detailed numerical example".  The note's synthetic surface samples
eq. (example_true_surface) at the 3 x 7 vertex set and interpolates
piecewise-affinely; empirically (see git history) the published quote table
is reproduced to every printed decimal by a scipy/qhull *Delaunay*
triangulation of the vertices ("delaunay" mode), while fixed-diagonal splits
land ~2e-5 away -- so delaunay is the surface's default and the golden mode.

Golden numbers asserted here:
1. tab:quote_set     -- 15 normalized call prices (1e-6 printed precision)
                        and implied vols (1e-3 percent printed precision);
2. tab:var_quotes    -- 3 variance-swap rates via the log-contract
                        replication of eq. (variance_swap_static_replication)
                        integrated on x in [0.01, 2.20];
3. tab:fit_options / tab:fit_var / tab:calibrated_variances -- calibrating
                        from flat theta = 0.04 with bounds [0.005, 0.20],
                        price/variance tolerance 2e-4 and second-difference
                        roughness lambda = 50 reproduces the note's fit
                        quality (rms 7.56e-6, max 2.25e-5, rms IV 1.26 bp,
                        var-swap errors ~0.1-0.3 variance bp) and the
                        calibrated nodal table to < 2.5e-3 in variance.

Plus structural invariants: hat-function basis rows are a partition of unity
with barycentric positivity (note app. B), analytic forward sensitivities
(eq. (discrete_sensitivity)) match finite differences, and the calibrated
surface prices a dense grid free of butterfly/calendar violations.
"""

import numpy as np
import pytest

from volfit.core.black import implied_total_variance
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    VarSwapQuote,
    calibrate_affine,
    solve_affine_dupire,
    varswap_const,
    varswap_weights,
)

# --------------------------------------------------------------- note data
TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])


def true_variance(t, x):
    """eq. (example_true_surface) of the note."""
    return (
        0.032
        + 0.006 * t
        + 0.030 * (1.0 - x) ** 2
        + 0.012 * (1.0 - x)
        + 0.004 * np.sin(np.pi * t) * np.exp(-(((x - 1.0) / 0.35) ** 2))
    )


# tab:quote_set: (T, x, normalized call price, implied vol %)
QUOTE_TABLE = [
    (0.25, 0.80, 0.200277, 19.071),
    (0.25, 0.90, 0.105645, 18.579),
    (0.25, 1.00, 0.036544, 18.327),
    (0.25, 1.10, 0.007310, 18.245),
    (0.25, 1.20, 0.000861, 18.280),
    (0.50, 0.80, 0.202596, 19.285),
    (0.50, 0.90, 0.115765, 19.017),
    (0.50, 1.00, 0.053085, 18.832),
    (0.50, 1.10, 0.019104, 18.701),
    (0.50, 1.20, 0.005456, 18.616),
    (1.00, 0.80, 0.211163, 19.630),
    (1.00, 0.90, 0.133968, 19.411),
    (1.00, 1.00, 0.076657, 19.245),
    (1.00, 1.10, 0.039690, 19.126),
    (1.00, 1.20, 0.018833, 19.061),
]
# tab:var_quotes: (T, annualized fair variance rate)
VARSWAP_TABLE = [(0.25, 0.033931), (0.50, 0.035713), (1.00, 0.037479)]
# tab:calibrated_variances: nodal theta after the note's calibration
THETA_CALIBRATED = np.array(
    [
        [0.04607, 0.03973, 0.03348, 0.03198, 0.03109, 0.03429, 0.04105],
        [0.05064, 0.04220, 0.04006, 0.03905, 0.03769, 0.03613, 0.04515],
        [0.05513, 0.04675, 0.03963, 0.03813, 0.03699, 0.03755, 0.04621],
    ]
)

# The note's PDE grids: x_i = 0.01 i (0..220), t_n = 0.005 n (0..200).
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.005 * np.arange(201)
EXPIRIES = [0.25, 0.5, 1.0]


@pytest.fixture(scope="module")
def true_surface() -> AffineVarianceSurface:
    return AffineVarianceSurface(
        t_nodes=TAU, x_nodes=XI, theta=true_variance(TAU[:, None], XI[None, :])
    )


@pytest.fixture(scope="module")
def true_solution(true_surface):
    return solve_affine_dupire(true_surface, X_GRID, T_GRID, EXPIRIES, sensitivities=True)


def _expiry_index(solution):
    return {float(t): i for i, t in enumerate(solution.expiries)}


# -------------------------------------------------- 1. golden quote table
def test_quote_table_prices(true_solution):
    idx = _expiry_index(true_solution)
    for t, x, price, _ in QUOTE_TABLE:
        model = float(true_solution.price_at(idx[t], x))
        assert model == pytest.approx(price, abs=6e-7), (t, x)


def test_quote_table_implied_vols(true_solution):
    idx = _expiry_index(true_solution)
    for t, x, _, vol_pct in QUOTE_TABLE:
        price = float(true_solution.price_at(idx[t], x))
        w = float(implied_total_variance(np.log(x), price))
        assert 100.0 * np.sqrt(w / t) == pytest.approx(vol_pct, abs=6e-4), (t, x)


# ---------------------------------------------- 2. golden var-swap table
def test_varswap_table(true_solution):
    idx = _expiry_index(true_solution)
    q = varswap_weights(X_GRID, k_lo=0.01)
    const = varswap_const(X_GRID, k_lo=0.01)
    for t, rate in VARSWAP_TABLE:
        model_rate = (q @ true_solution.prices[idx[t]] + const) / t
        assert model_rate == pytest.approx(rate, abs=6e-7), t


# ----------------------------------------------- 3. structural invariants
def test_basis_partition_of_unity_and_nodal_interpolation(true_surface):
    x_probe = np.linspace(0.0, 2.2, 113)
    for t_probe in (0.0, 0.13, 0.5, 0.77, 1.0):
        phi = true_surface.basis(x_probe, t_probe)
        assert np.allclose(phi.sum(axis=1), 1.0, atol=1e-12)  # partition of unity
        assert phi.min() >= -1e-12  # barycentric positivity (note app. B)
        assert (np.abs(phi) > 1e-12).sum(axis=1).max() <= 3  # P1: <= 3 vertices
    # phi_l(z_j) = delta_lj at the vertices themselves
    for i, t in enumerate(TAU):
        phi = true_surface.basis(XI, float(t))
        expect = np.zeros((XI.size, true_surface.n_params))
        expect[np.arange(XI.size), i * XI.size + np.arange(XI.size)] = 1.0
        assert np.allclose(phi, expect, atol=1e-12)


def test_nodal_bounds_imply_surface_bounds(true_surface):
    x_probe = np.linspace(0.0, 2.2, 401)
    lo, hi = true_surface.theta.min(), true_surface.theta.max()
    for t_probe in np.linspace(0.0, 1.0, 11):
        v = true_surface.variance(x_probe, float(t_probe))
        assert v.min() >= lo - 1e-12 and v.max() <= hi + 1e-12


def test_forward_sensitivities_match_finite_differences(true_surface, true_solution):
    idx = _expiry_index(true_solution)
    flat = true_surface.theta.ravel()
    rng = np.random.default_rng(7)
    for _ in range(3):
        node = int(rng.integers(0, flat.size))
        t, x, _, _ = QUOTE_TABLE[int(rng.integers(0, len(QUOTE_TABLE)))]
        eps = 1e-6
        bumped = []
        for sign in (+1.0, -1.0):
            th = flat.copy()
            th[node] += sign * eps
            sol = solve_affine_dupire(true_surface.with_theta(th), X_GRID, T_GRID, [t])
            bumped.append(float(sol.price_at(0, x)))
        fd = (bumped[0] - bumped[1]) / (2.0 * eps)
        analytic = float(true_solution.sens_at(idx[t], np.array([x]))[0, node])
        assert analytic == pytest.approx(fd, abs=1e-7), (node, t, x)


# ------------------------------------------------ 4. golden calibration
@pytest.fixture(scope="module")
def calibration():
    options = [OptionQuote(t=t, x=x, price=p, tol=2e-4) for t, x, p, _ in QUOTE_TABLE]
    varswaps = [VarSwapQuote(t=t, total_var=t * r, tol=2e-4) for t, r in VARSWAP_TABLE]
    flat = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=np.full((3, 7), 0.04))
    return calibrate_affine(
        flat,
        options,
        X_GRID,
        T_GRID,
        varswaps=varswaps,
        reg_lambda=50.0,
        bounds=(0.005, 0.20),
    )


def test_calibration_fit_quality(calibration):
    # Note: rms 7.56e-6, max 2.25e-5 normalized price units.
    assert calibration.rms_price_error < 1.0e-5
    assert calibration.max_price_error < 3.0e-5
    iv_err_bp = []
    for (t, x, _, vol_pct), p in zip(QUOTE_TABLE, calibration.option_prices):
        w = float(implied_total_variance(np.log(x), p))
        iv_err_bp.append(100.0 * np.sqrt(w / t) - vol_pct)
    rms_iv_bp = 100.0 * float(np.sqrt(np.mean(np.square(iv_err_bp))))
    assert rms_iv_bp < 1.6  # note: 1.26 vol bp


def test_calibration_varswap_fit(calibration):
    # Note tab:fit_var rate errors: +0.116, -0.029, -0.258 variance bp.
    for err, (t, _) in zip(calibration.varswap_errors, VARSWAP_TABLE):
        assert abs(err / t) * 1e4 < 0.5, t


def test_calibration_recovers_note_nodal_table(calibration):
    # Published to 5 decimals; lambda = 50 lands within 1.5e-3 here -- assert
    # 2.5e-3 to leave room for optimizer/library drift without losing teeth.
    assert np.max(np.abs(calibration.surface.theta - THETA_CALIBRATED)) < 2.5e-3


def test_calibration_diagnostics_counters(calibration):
    """Stage-0 side metadata: counts/optimizer/wall-time are populated and
    self-consistent. Pure observation — it must not perturb any fitted value
    (the golden tests above already pin those), only describe the run."""
    d = calibration.diagnostics
    assert d is not None
    # problem-size counts match the note's 3 x 7 grid, 15 options, 3 var-swaps
    assert d.vertex_count == 21
    assert d.quote_count == 15
    assert d.varswap_count == 3
    assert d.pde_x_count == X_GRID.size and d.pde_t_count == T_GRID.size
    assert not d.fit_left_a
    # roughness rows: strike 3*(7-2)=15 + time 7*(3-2)=7 = 22; total residual
    # block = 15 options + 3 var-swaps + 22 roughness (mid mode, no convex/front)
    assert d.regularisation_row_count == 22
    assert d.residual_count == 15 + 3 + 22
    # optimizer counters surfaced from scipy least_squares
    assert d.nfev > 0 and d.njev > 0
    assert d.active_bound_count >= 0
    # wall-time breakdown is non-negative and the sensitivity march is timed
    assert d.wall_ms_total > 0.0
    assert d.wall_ms_pde_sensitivity > 0.0
    assert d.wall_ms_optimizer_outer >= 0.0


def test_solver_scaling_cuts_evals_without_moving_surface(calibration):
    """Stage 1: ``x_scale='jac'`` + 1e-8 tolerances (the new defaults, used by the
    ``calibration`` fixture) must converge in no more evals than the legacy
    isotropic-1e-12 solver AND land the same surface. The optimum here is
    well-identified, so a different solver *path* must not move theta — that is
    the gate that the speed-up is free of accuracy cost."""
    options = [OptionQuote(t=t, x=x, price=p, tol=2e-4) for t, x, p, _ in QUOTE_TABLE]
    varswaps = [VarSwapQuote(t=t, total_var=t * r, tol=2e-4) for t, r in VARSWAP_TABLE]
    flat = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=np.full((3, 7), 0.04))
    legacy = calibrate_affine(
        flat, options, X_GRID, T_GRID, varswaps=varswaps, reg_lambda=50.0,
        bounds=(0.005, 0.20), x_scale=1.0, xtol=1e-12, ftol=1e-12, gtol=1e-12,
    )
    assert calibration.diagnostics.nfev <= legacy.diagnostics.nfev
    # same converged optimum to ~machine precision (path-independent here)
    assert np.max(np.abs(calibration.surface.theta - legacy.surface.theta)) < 1e-6


def test_calibrated_surface_is_arbitrage_free(calibration):
    # Dense-grid checks per the note's "Validate" step: calls in [0, 1],
    # decreasing & convex in strike, nondecreasing in maturity.
    prices = calibration.solution.prices
    assert prices.min() >= -1e-12 and prices.max() <= 1.0 + 1e-12
    dx = np.diff(prices, axis=1)
    assert dx.max() <= 1e-10  # decreasing in strike
    assert np.diff(dx, axis=1).min() >= -1e-9  # convex in strike
    assert np.diff(prices, axis=0).min() >= -1e-9  # calendar monotone

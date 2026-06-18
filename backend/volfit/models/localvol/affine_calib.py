"""Direct calibration of the P1 local-variance surface to option/var-swap quotes.

Implements the objective of Docs/piecewise_affine_local_variance_calibration.tex,
eq. (calibration_objective): bound-constrained weighted least squares on

- option residuals   (P_j(theta) - y_j) / eta_j   (normalized forward calls),
- var-swap residuals (Z_q(theta) - z_q) / zeta_q  (TOTAL variance, z = T * rate),
- roughness          sqrt(lambda) * L (theta - theta_ref), with L the plain
  second-difference operator in strike and (scaled by rho) in time of the
  note's "Regularization choices" section.

Model var swaps use the static log-contract replication of
eq. (variance_swap_static_replication),

    I(T) = 2 int_0^1 P(T,k)/k^2 dk + 2 int_1^inf C(T,k)/k^2 dk,

evaluated by trapezoid on the PDE strike grid restricted to [k_lo, x_max]
(the note's example integrates on [0.01, 2.20]); P = C + k - 1 by parity.
Sensitivities reuse dC/dtheta from the forward-sensitivity PDE sweep
(eq. (discrete_sensitivity)), so the optimizer gets an analytic Jacobian:
one sensitivity-carrying PDE solve per trial theta serves every residual.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import MID_ANCHOR_WEIGHT, band_violation, band_violation_sign
from volfit.models.localvol.affine import (
    AffinePDESolution,
    AffineVarianceSurface,
    precompute_dupire_steps,
    solve_affine_dupire,
)


@dataclass(frozen=True)
class OptionQuote:
    """One normalized forward call quote (T, x = K/F, price y, tolerance eta).

    ``price_lo``/``price_hi`` are the call prices at the bid/ask (haircut-
    adjusted) band vols; when both are set the calibration uses the bid-ask /
    haircut band objective (volfit.calib.band) for this quote instead of the
    plain mid residual (``price`` is then the soft anchor).
    """

    t: float
    x: float
    price: float
    tol: float = 2e-4
    price_lo: float | None = None
    price_hi: float | None = None


@dataclass(frozen=True)
class VarSwapQuote:
    """One variance-swap quote: TOTAL variance z = T * fair rate, tolerance zeta."""

    t: float
    total_var: float
    tol: float = 2e-4


def varswap_weights(x_grid: np.ndarray, k_lo: float = 0.0) -> np.ndarray:
    """Trapezoid weights q with I(T) = q @ C(T, .) + const(parity).

    Splits eq. (variance_swap_static_replication) at the anchor k = 1 (which
    must be a grid point): below it the integrand is P/k^2 = (C + k - 1)/k^2,
    above it C/k^2 -- the affine parity part contributes a theta-independent
    constant, returned separately by ``varswap_const``.  Grid points with
    x <= k_lo (and x = 0, where 1/k^2 blows up) get zero weight.
    """
    x = np.asarray(x_grid, dtype=float)
    i1 = int(np.searchsorted(x, 1.0))
    if x[i1] != 1.0:
        raise ValueError("the var-swap anchor x = 1 must be a grid point")
    mask = x >= max(k_lo, 1e-12)
    q = np.zeros_like(x)
    # trapezoid over the put leg [k_lo, 1] and the call leg [1, x_max]
    put_idx = np.nonzero(mask & (x <= 1.0))[0]
    call_idx = np.nonzero(x >= 1.0)[0]
    for idx in (put_idx, call_idx):
        xs = x[idx]
        w = np.zeros(xs.size)
        dx = np.diff(xs)
        w[:-1] += 0.5 * dx
        w[1:] += 0.5 * dx
        q[idx] += 2.0 * w / (xs * xs)
    return q


def varswap_const(x_grid: np.ndarray, k_lo: float = 0.0) -> float:
    """Theta-independent parity part of the replication: 2 int (k-1)/k^2 over the put leg."""
    x = np.asarray(x_grid, dtype=float)
    idx = np.nonzero((x >= max(k_lo, 1e-12)) & (x <= 1.0))[0]
    xs = x[idx]
    f = (xs - 1.0) / (xs * xs)
    return float(2.0 * np.trapezoid(f, xs))


def second_difference_rows(n_t: int, n_x: int, rho: float = 1.0) -> np.ndarray:
    """Roughness operator L: second differences along strike and (x rho) time.

    Acts on the t-major flat theta vector of AffineVarianceSurface; matches
    the note's "second-difference penalties in time and moneyness".

    This index-space form (the plain (1, -2, 1) stencil) is correct only on a
    UNIFORM vertex grid; on a non-uniform grid (e.g. the delta-spaced strike
    axis) it mis-scales — penalizing tightly-spaced ATM nodes the same as the
    far, widely-spaced wing nodes, which over-smooths the wings. Use
    ``second_difference_rows_spacing`` when the vertex coordinates are known
    (the affine_fit path passes them); this index form is kept byte-identical
    for the note's golden example (uniform xi/tau).
    """
    rows = []
    m = n_t * n_x
    for i in range(n_t):  # along strike within each time row
        for j in range(1, n_x - 1):
            r = np.zeros(m)
            base = i * n_x + j
            r[base - 1], r[base], r[base + 1] = 1.0, -2.0, 1.0
            rows.append(r)
    if n_t >= 3:
        for j in range(n_x):  # along time within each strike column
            for i in range(1, n_t - 1):
                r = np.zeros(m)
                base = i * n_x + j
                r[base - n_x], r[base], r[base + n_x] = rho, -2.0 * rho, rho
                rows.append(r)
    return np.asarray(rows)


def _d2_coeffs(x_lo: float, x_mid: float, x_hi: float) -> tuple[float, float, float]:
    """Spacing-aware second-derivative stencil, normalized to the cell width.

    The non-uniform central second difference (eq. (nonuniform_second_derivative))
    is ~ 1/h², which would blow up the roughness penalty on a fine grid and
    collapse it on a coarse one. Scaling by the local mean spacing squared
    (h̄ = (h_m + h_p)/2) makes the stencil dimensionless: on a UNIFORM grid it
    reduces EXACTLY to the index-space (1, -2, 1), so the ``gridRegLambda`` /
    ``convexWingWeight`` knobs keep their scale, while on a non-uniform grid the
    curvature reflects the true vertex positions instead of assuming uniformity.
    """
    h_m = x_mid - x_lo
    h_p = x_hi - x_mid
    hbar2 = (0.5 * (h_m + h_p)) ** 2
    cm = hbar2 * 2.0 / ((h_m + h_p) * h_m)
    cp = hbar2 * 2.0 / ((h_m + h_p) * h_p)
    return cm, -(cm + cp), cp


def second_difference_rows_spacing(
    t_nodes: np.ndarray, x_nodes: np.ndarray, rho: float = 1.0
) -> np.ndarray:
    """Spacing-aware roughness operator L on the ACTUAL vertex coordinates.

    Same structure as ``second_difference_rows`` (second differences in strike
    within each time row, and in time within each strike column scaled by
    ``rho``), but each stencil uses the cell-width-normalized coefficients of
    ``_d2_coeffs`` at the real node positions. Reduces to the index-space form on
    a uniform grid; on the delta-spaced axis it stops over-penalizing the wings.
    """
    t = np.asarray(t_nodes, dtype=float)
    x = np.asarray(x_nodes, dtype=float)
    n_t, n_x = t.size, x.size
    m = n_t * n_x
    rows = []
    for i in range(n_t):  # along strike within each time row
        for j in range(1, n_x - 1):
            cm, c0, cp = _d2_coeffs(x[j - 1], x[j], x[j + 1])
            r = np.zeros(m)
            base = i * n_x + j
            r[base - 1], r[base], r[base + 1] = cm, c0, cp
            rows.append(r)
    if n_t >= 3:
        for j in range(n_x):  # along time within each strike column
            for i in range(1, n_t - 1):
                dm, d0, dp = _d2_coeffs(t[i - 1], t[i], t[i + 1])
                r = np.zeros(m)
                base = i * n_x + j
                r[base - n_x], r[base], r[base + n_x] = rho * dm, rho * d0, rho * dp
                rows.append(r)
    return np.asarray(rows) if rows else np.zeros((0, m))


def wing_convexity_stencils(
    t_nodes: np.ndarray, x_nodes: np.ndarray, wing_cols: np.ndarray
) -> tuple[np.ndarray, ...]:
    """Flat-index stencils for the 'convex vol below 5Δ' constraint.

    For every time row and every interior strike node ``j`` (1 ≤ j ≤ n_x-2) that
    is flagged a wing column (``wing_cols``, the nodes at/left of the 5Δ-put
    strike), return the three flat theta columns and the cell-width-normalized
    second-derivative coefficients of the VOL row in x. The caller forms the
    soft constraint sqrt(W)·relu(-(D²σ)) so concavity (D²σ < 0) is penalized and
    a convex left wing is unpenalized. Returns six empty arrays when fewer than
    one eligible node exists (e.g. the deep-delta nodes were clipped away).
    """
    x = np.asarray(x_nodes, dtype=float)
    n_t, n_x = int(np.asarray(t_nodes).size), x.size
    wing = set(int(c) for c in np.asarray(wing_cols).ravel())
    eligible = [j for j in range(1, n_x - 1) if j in wing]
    col_m, col_0, col_p = [], [], []
    coef_m, coef_0, coef_p = [], [], []
    for i in range(n_t):
        for j in eligible:
            cm, c0, cp = _d2_coeffs(x[j - 1], x[j], x[j + 1])
            base = i * n_x + j
            col_m.append(base - 1)
            col_0.append(base)
            col_p.append(base + 1)
            coef_m.append(cm)
            coef_0.append(c0)
            coef_p.append(cp)
    return (
        np.array(col_m, dtype=int),
        np.array(col_0, dtype=int),
        np.array(col_p, dtype=int),
        np.array(coef_m, dtype=float),
        np.array(coef_0, dtype=float),
        np.array(coef_p, dtype=float),
    )


@dataclass
class AffineCalibration:
    """Result of ``calibrate_affine``: surface, residual report, optimizer info."""

    surface: AffineVarianceSurface
    solution: AffinePDESolution  # at the option/var-swap quote maturities
    option_prices: np.ndarray  # model prices per option quote
    option_errors: np.ndarray  # model - market, normalized price units
    varswap_totals: np.ndarray  # model total variances per var-swap quote
    varswap_errors: np.ndarray  # model - market total variance
    cost: float
    n_evals: int
    message: str = ""
    left_extrap_a: float = 0.0  # fitted (or fixed) left-wing slope multiple
    _extras: dict = field(default_factory=dict)

    @property
    def rms_price_error(self) -> float:
        return float(np.sqrt(np.mean(self.option_errors**2)))

    @property
    def max_price_error(self) -> float:
        return float(np.max(np.abs(self.option_errors)))


def _model_values(
    solution: AffinePDESolution,
    options: list[OptionQuote],
    varswaps: list[VarSwapQuote],
    q_weights: np.ndarray,
    q_const: float,
    with_jac: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Option prices, var-swap totals (and Jacobian blocks) from a PDE solve."""
    exp_index = {float(t): i for i, t in enumerate(solution.expiries)}
    p = np.array([solution.price_at(exp_index[o.t], o.x) for o in options])
    z = np.array(
        [q_weights @ solution.prices[exp_index[v.t]] + q_const for v in varswaps]
    )
    if not with_jac:
        return p, z, None, None
    jp = np.vstack(
        [solution.sens_at(exp_index[o.t], np.array([o.x]))[0] for o in options]
    )
    jz = (
        np.vstack([q_weights @ solution.sens[exp_index[v.t]] for v in varswaps])
        if varswaps
        else np.zeros((0, solution.sens.shape[2]))
    )
    return p, z, jp, jz


def calibrate_affine(
    surface0: AffineVarianceSurface,
    options: list[OptionQuote],
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    *,
    varswaps: list[VarSwapQuote] | None = None,
    varswap_k_lo: float = 0.01,
    bounds: tuple[float, float] = (0.005, 0.20),
    reg_lambda: float = 1e-4,
    reg_rho: float = 1.0,
    reg_nodes: tuple[np.ndarray, np.ndarray] | None = None,
    convex_cols: np.ndarray | None = None,
    convex_weight: float = 0.0,
    front_tie_weight: float = 0.0,
    fit_left_a: bool = False,
    left_a_bounds: tuple[float, float] = (0.0, 20.0),
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
    theta_ref: np.ndarray | None = None,
    xtol: float = 1e-12,
    ftol: float = 1e-12,
    gtol: float = 1e-12,
    max_nfev: int = 200,
) -> AffineCalibration:
    """Bound-constrained LSQ fit of nodal local variances (note's Algorithm).

    ``surface0`` provides the vertex set, interpolation mode and the initial
    guess; ``theta_ref`` defaults to the initial theta (the note: "a flat
    variance or the previous day's calibrated surface").  One PDE solve with
    forward sensitivities per trial theta yields both residuals and the
    analytic Jacobian; results are memoized so scipy's separate fun/jac
    callbacks cost a single solve.

    ``reg_nodes`` = (t_nodes, x_nodes): when given, the roughness operator is the
    spacing-aware ``second_difference_rows_spacing`` on the real vertex positions
    (correct on the delta-spaced grid); when None it falls back to the index-space
    ``second_difference_rows`` (byte-identical to the note's golden example).
    ``convex_cols`` (with ``convex_weight`` > 0) adds the soft 'convex vol below
    5Δ' constraint at those strike columns: a hinge sqrt(W)·relu(-(D²σ)) per time
    row penalizing concavity of the VOL row in x. ``front_tie_weight`` > 0 adds the
    soft front tie sqrt(W)·(θ[0,:] − θ[1,:]) per strike column — a one-sided
    difference pinning the unconstrained t = 0 row to the first (data-identified)
    row so it stops leaking into the shortest, most-curved smile. Off (None / 0)
    for any of these ⇒ no extra rows, so the fit is byte-identical.

    ``fit_left_a`` makes the surface's LEFT-wing extrapolation slope multiple
    ``a`` (volfit.models.localvol.affine, ``left_extrap_a``) a free calibration
    variable (init = ``surface0.left_extrap_a``, bounds ``left_a_bounds``), with
    an analytic dPrice/da sensitivity — so a var-swap quote can set the deep-put
    tail steepness directly instead of distorting the data-fitted interior. When
    False, ``a`` stays fixed at ``surface0.left_extrap_a`` (0 ⇒ flat wing).
    """
    varswaps = varswaps or []
    expiries = sorted({o.t for o in options} | {v.t for v in varswaps})
    q_w = varswap_weights(x_grid, varswap_k_lo) if varswaps else np.zeros_like(x_grid)
    q_c = varswap_const(x_grid, varswap_k_lo) if varswaps else 0.0
    if reg_nodes is not None:
        l_rows = second_difference_rows_spacing(reg_nodes[0], reg_nodes[1], reg_rho)
    else:
        l_rows = second_difference_rows(surface0.t_nodes.size, surface0.x_nodes.size, reg_rho)
    # Soft 'convex vol below 5Δ' constraint: precompute the theta-independent
    # stencils once (cols + cell-width-normalized D²-in-x coefficients).
    convex_on = (
        convex_cols is not None
        and convex_weight > 0.0
        and np.asarray(convex_cols).size > 0
    )
    if convex_on:
        cvx = wing_convexity_stencils(surface0.t_nodes, surface0.x_nodes, convex_cols)
        cvx_on = cvx[0].size > 0
        sqrt_cvx = np.sqrt(convex_weight)
    else:
        cvx_on = False
    # Front tie: one-sided time difference θ[0,:] − θ[1,:] per strike column
    # (theta-independent, so the linear operator is built once).
    front_on = front_tie_weight > 0.0 and surface0.t_nodes.size >= 2
    if front_on:
        n_x0 = surface0.x_nodes.size
        front_rows = np.zeros((n_x0, surface0.theta.size))
        cols = np.arange(n_x0)
        front_rows[cols, cols] = 1.0  # θ[0, j]
        front_rows[cols, n_x0 + cols] = -1.0  # θ[1, j]
        sqrt_front = np.sqrt(front_tie_weight)
    ref = surface0.theta.ravel().copy() if theta_ref is None else np.asarray(theta_ref)
    sqrt_lam = np.sqrt(reg_lambda)
    eta = np.array([o.tol for o in options])
    zeta = np.array([v.tol for v in varswaps])
    z_mkt = np.array([v.total_var for v in varswaps])
    y_mkt = np.array([o.price for o in options])
    # Band fit: present iff the quotes carry call-price band edges.
    band_mode = bool(options) and options[0].price_lo is not None
    p_lo = np.array([o.price_lo for o in options]) if band_mode else None
    p_hi = np.array([o.price_hi for o in options]) if band_mode else None
    sqrt_anchor = np.sqrt(mid_anchor_weight)
    n_evals = 0
    cache: dict[bytes, tuple] = {}
    m = surface0.n_params
    # The hat basis and active-column schedule depend only on the vertex set and
    # grids (not theta), so build them once and reuse for every trial theta. With
    # a free left-wing slope the base / linear-delta bases are stored separately.
    steps = precompute_dupire_steps(surface0, x_grid, t_grid, with_left_lin=fit_left_a)

    def _pad_a(j: np.ndarray) -> np.ndarray:
        """Append a zero da-column to a theta-only Jacobian block (when fitting a)."""
        if not fit_left_a:
            return j
        return np.hstack([j, np.zeros((j.shape[0], 1))])

    def _option_block(p: np.ndarray, jp: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Option residuals + Jacobian: mid LSQ, or the band objective.

        The band block stacks the vega-normalized band violation and the soft
        mid anchor (volfit.calib.band); its subgradient is 0 inside the band.
        """
        if not band_mode:
            return (p - y_mkt) / eta, jp / eta[:, None]
        viol = band_violation(p, p_lo, p_hi) / eta
        anchor = sqrt_anchor * (p - y_mkt) / eta
        sign = band_violation_sign(p, p_lo, p_hi)
        j_viol = (sign / eta)[:, None] * jp
        j_anchor = sqrt_anchor * jp / eta[:, None]
        return np.concatenate([viol, anchor]), np.vstack([j_viol, j_anchor])

    def evaluate(params: np.ndarray) -> tuple:
        nonlocal n_evals
        key = params.tobytes()
        hit = cache.get(key)
        if hit is not None:
            return hit
        n_evals += 1
        theta = params[:m] if fit_left_a else params
        a = float(params[m]) if fit_left_a else surface0.left_extrap_a
        surf = surface0.with_theta(theta).with_left_extrap_a(a)
        sol = solve_affine_dupire(
            surf, x_grid, t_grid, expiries, sensitivities=True, steps=steps,
            left_a=a, fit_left_a=fit_left_a,
        )
        # jp/jz carry an extra da-column at the end when fit_left_a (matching the
        # solver's appended sensitivity column), so the theta-only blocks below are
        # padded with a zero da-column via _pad_a.
        p, z, jp, jz = _model_values(sol, options, varswaps, q_w, q_c, True)
        res_opt, jac_opt = _option_block(p, jp)
        res = np.concatenate(
            [res_opt, (z - z_mkt) / zeta, sqrt_lam * (l_rows @ (theta - ref))]
        )
        jac = np.vstack([jac_opt, jz / zeta[:, None], _pad_a(sqrt_lam * l_rows)])
        if cvx_on:
            # Soft convexity of the VOL row sigma = sqrt(theta) in x at the wing
            # columns: curv = D²sigma (cell-width-normalized); penalize curv < 0.
            col_m, col_0, col_p, c_m, c_0, c_p = cvx
            sig = np.sqrt(np.maximum(theta, 1e-12))
            curv = c_m * sig[col_m] + c_0 * sig[col_0] + c_p * sig[col_p]
            viol = sqrt_cvx * np.maximum(-curv, 0.0)
            dsig = 0.5 / sig  # dsigma/dtheta
            fac = np.where(curv < 0.0, -sqrt_cvx, 0.0)  # subgradient gate
            jac_cvx = np.zeros((curv.size, theta.size))
            ar = np.arange(curv.size)
            jac_cvx[ar, col_m] = fac * c_m * dsig[col_m]
            jac_cvx[ar, col_0] = fac * c_0 * dsig[col_0]
            jac_cvx[ar, col_p] = fac * c_p * dsig[col_p]
            res = np.concatenate([res, viol])
            jac = np.vstack([jac, _pad_a(jac_cvx)])
        if front_on:
            res = np.concatenate([res, sqrt_front * (front_rows @ theta)])
            jac = np.vstack([jac, _pad_a(sqrt_front * front_rows)])
        cache.clear()  # keep only the latest params (fun + jac pairing)
        out = (res, jac, sol, p, z)
        cache[key] = out
        return out

    if fit_left_a:  # parameter vector is [theta (m), a (1)] with its own bounds
        p0 = np.concatenate([surface0.theta.ravel(), [surface0.left_extrap_a]])
        lb = np.concatenate([np.full(m, bounds[0]), [left_a_bounds[0]]])
        ub = np.concatenate([np.full(m, bounds[1]), [left_a_bounds[1]]])
        opt_bounds: tuple = (lb, ub)
    else:
        p0 = surface0.theta.ravel()
        opt_bounds = bounds
    result = least_squares(
        lambda p: evaluate(p)[0],
        p0,
        jac=lambda p: evaluate(p)[1],
        bounds=opt_bounds,
        method="trf",
        xtol=xtol,
        ftol=ftol,
        gtol=gtol,
        max_nfev=max_nfev,
    )
    _, _, sol, p, z = evaluate(result.x)
    theta_hat = result.x[:m] if fit_left_a else result.x
    a_hat = float(result.x[m]) if fit_left_a else surface0.left_extrap_a
    return AffineCalibration(
        surface=surface0.with_theta(theta_hat).with_left_extrap_a(a_hat),
        solution=sol,
        option_prices=p,
        option_errors=p - y_mkt,
        varswap_totals=z,
        varswap_errors=z - z_mkt,
        cost=float(result.cost),
        n_evals=n_evals,
        message=str(result.message),
        left_extrap_a=a_hat,
    )

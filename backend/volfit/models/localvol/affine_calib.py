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
    """
    varswaps = varswaps or []
    expiries = sorted({o.t for o in options} | {v.t for v in varswaps})
    q_w = varswap_weights(x_grid, varswap_k_lo) if varswaps else np.zeros_like(x_grid)
    q_c = varswap_const(x_grid, varswap_k_lo) if varswaps else 0.0
    l_rows = second_difference_rows(surface0.t_nodes.size, surface0.x_nodes.size, reg_rho)
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
    # The hat basis and active-column schedule depend only on the vertex set and
    # grids (not theta), so build them once and reuse for every trial theta.
    steps = precompute_dupire_steps(surface0, x_grid, t_grid)

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

    def evaluate(theta: np.ndarray) -> tuple:
        nonlocal n_evals
        key = theta.tobytes()
        hit = cache.get(key)
        if hit is not None:
            return hit
        n_evals += 1
        surf = surface0.with_theta(theta)
        sol = solve_affine_dupire(
            surf, x_grid, t_grid, expiries, sensitivities=True, steps=steps
        )
        p, z, jp, jz = _model_values(sol, options, varswaps, q_w, q_c, True)
        res_opt, jac_opt = _option_block(p, jp)
        res = np.concatenate(
            [res_opt, (z - z_mkt) / zeta, sqrt_lam * (l_rows @ (theta - ref))]
        )
        jac = np.vstack([jac_opt, jz / zeta[:, None], sqrt_lam * l_rows])
        cache.clear()  # keep only the latest theta (fun + jac pairing)
        out = (res, jac, sol, p, z)
        cache[key] = out
        return out

    result = least_squares(
        lambda th: evaluate(th)[0],
        surface0.theta.ravel(),
        jac=lambda th: evaluate(th)[1],
        bounds=bounds,
        method="trf",
        xtol=xtol,
        ftol=ftol,
        gtol=gtol,
        max_nfev=max_nfev,
    )
    _, _, sol, p, z = evaluate(result.x)
    return AffineCalibration(
        surface=surface0.with_theta(result.x),
        solution=sol,
        option_prices=p,
        option_errors=p - y_mkt,
        varswap_totals=z,
        varswap_errors=z - z_mkt,
        cost=float(result.cost),
        n_evals=n_evals,
        message=str(result.message),
    )

"""Calibration of the Multi-Core SIV slice (Docs/Multi_Core_SIV_Technical_Note.tex).

Implements the robust workflow of section "Calibration methodology":

  1. fit the one-core SIV base (R = 0) to the quotes;
  2. seed R signed hats greedily at the largest variance residuals;
  3. refine the full (6 + 4R)-parameter set jointly with bound constraints and a
     mild ridge penalty on the hat amplitudes (eqs calibration-objective,
     kernel-bounds, linear-amplitude-fit).

Residuals are in implied-vol units (the natural quoting scale). All positive
parameters (K0, the wing steepnesses, the hat half-widths and steepnesses) are
bound-constrained directly through scipy's trust-region reflective solver.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import MID_ANCHOR_WEIGHT, BandTarget, band_residuals
from volfit.calib.operators import OperatorPriorTarget, operator_residuals
from volfit.calib.prior import PriorAnchorTarget, prior_anchor_residuals
from volfit.calib.varswap import VarSwapTarget, varswap_residual
from volfit.core.black import black_call
from volfit.models.sigmoid.jacobian import siv_residual_jacobian
from volfit.models.sigmoid.kernels import gatheral_g_from_z, hat, hat_p, hat_pp, siv_base
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv

#: Per-hat starting half-width / steepness (note's WW example, eq ww-fit-model).
_H_INIT = 0.40
_KAPPA_INIT = 5.0
#: Practical kernel bounds (eq kernel-bounds): half-width and steepness ranges.
_H_BOUNDS = (0.15, 1.5)
_KAPPA_BOUNDS = (1.0, 12.0)
#: Centre padding beyond the quoted z-range for hat placement.
_C_PAD = 0.5
#: Mild ridge on hat amplitudes (eq calibration-objective l2 term) — keeps
#: overlapping cores from exploding without biasing well-determined amplitudes.
_RIDGE = 1e-2
#: Variance floor mirroring MultiCoreSiv (keeps vol = sqrt(v) real).
_V_FLOOR = 1e-8

#: Put-wing no-butterfly regularizer (FINDINGS_calibration_arb R6). The zero-wing
#: hats can break convexity (Durrleman g < 0) in the UNQUOTED tail; a soft penalty
#: sqrt(lambda_j) * max(-g(z_j), 0) on a grid extending past the traded range pushes
#: g >= 0 where no quote disciplines it. Zero on an arb-free slice ⇒ byte-identical.
#: ``WING_PENALTY_BASE`` is the base strength (variance² units, like the SVI penalty),
#: scaled by ``OptionsSettings.sivWingPenaltyPct`` at the service; the put side is
#: weighted ``_WING_PUT_FACTOR`` heavier (F4: ~64% of violations are put-side).
WING_PENALTY_BASE = 1e3
_WING_PAD = 2.0  # how far past the quoted z-range the penalty grid extends (z units)
_WING_GRID = 49  # grid points over the extended range
_WING_PUT_FACTOR = 2.0


def _eval_g(theta: np.ndarray, z: np.ndarray, n_cores: int, t: float, sigma_ref: float) -> np.ndarray:
    """Durrleman/Gatheral g(z) of the model slice (>= 0 ⇔ no butterfly arb)."""
    v0, s0, k0, z0, kp, kc = theta[:6]
    v, vz, vzz = siv_base(z, v0, s0, k0, z0, kp, kc)
    for r in range(n_cores):
        alpha, c, h, kappa = theta[6 + 4 * r : 10 + 4 * r]
        v = v + alpha * hat(z, c, h, kappa)
        vz = vz + alpha * hat_p(z, c, h, kappa)
        vzz = vzz + alpha * hat_pp(z, c, h, kappa)
    return gatheral_g_from_z(z, np.maximum(v, _V_FLOOR), vz, vzz, t, sigma_ref)


def _reference_vol(vol_quotes: np.ndarray, k: np.ndarray) -> float:
    """Reference vol fixing the z-scale: the quoted vol nearest the money."""
    atm = float(vol_quotes[np.argmin(np.abs(k))])
    return atm if atm > 1e-3 else float(np.median(vol_quotes))


def _eval_v(theta: np.ndarray, z: np.ndarray, n_cores: int) -> np.ndarray:
    """Model variance v_R(z) for a flat parameter vector (base + n_cores hats)."""
    v0, s0, k0, z0, kp, kc = theta[:6]
    v, _, _ = siv_base(z, v0, s0, k0, z0, kp, kc)
    for r in range(n_cores):
        alpha, c, h, kappa = theta[6 + 4 * r : 10 + 4 * r]
        v = v + alpha * hat(z, c, h, kappa)
    return v


def _base_init(z: np.ndarray, v_quotes: np.ndarray) -> np.ndarray:
    """Data-driven start for the 6 base parameters from the variance quotes."""
    order = np.argsort(z)
    zs, vs = z[order], v_quotes[order]
    d = max(0.3 * (zs[-1] - zs[0]) / 2.0, 0.1)
    v_lo, v_mid, v_hi = np.interp([-d, 0.0, d], zs, vs)
    s0 = (v_hi - v_lo) / (2.0 * d)
    k0 = max((v_hi - 2.0 * v_mid + v_lo) / (d * d), 1e-2)
    return np.array([max(v_mid, 1e-4), s0, k0, 0.0, 3.0, 3.0])


def _base_bounds(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lo = np.array([1e-6, -10.0, 0.0, z.min() - 2.0, 0.2, 0.2])
    hi = np.array([25.0, 10.0, 10.0, z.max() + 2.0, 25.0, 25.0])
    return lo, hi


def _seed_cores(z: np.ndarray, residual: np.ndarray, n_cores: int) -> list[np.ndarray]:
    """Greedily place hats at the largest |residual|, enforcing centre spacing."""
    sep = max((z.max() - z.min()) / (2.0 * n_cores), 0.2)
    seeds: list[np.ndarray] = []
    remaining = residual.copy()
    for _ in range(n_cores):
        i = int(np.argmax(np.abs(remaining)))
        c = float(z[i])
        alpha = float(np.clip(residual[i], -1.0, 1.0))
        seeds.append(np.array([alpha, c, _H_INIT, _KAPPA_INIT]))
        remaining[np.abs(z - c) < sep] = 0.0  # mask the neighbourhood, then repeat
    return seeds


def _core_bounds(z: np.ndarray) -> tuple[list[float], list[float]]:
    lo = [-1.0, z.min() - _C_PAD, _H_BOUNDS[0], _KAPPA_BOUNDS[0]]
    hi = [1.0, z.max() + _C_PAD, _H_BOUNDS[1], _KAPPA_BOUNDS[1]]
    return lo, hi


def _fit(
    theta0: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    z: np.ndarray,
    vol_quotes: np.ndarray,
    sqrt_w: np.ndarray,
    n_cores: int,
    band: BandTarget | None = None,
    ridge: float = _RIDGE,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
    var_swap: VarSwapTarget | None = None,
    sigma_ref: float = 1.0,
    t: float = 1.0,
    calendar_k: np.ndarray | None = None,
    calendar_floor: np.ndarray | None = None,
    calendar_weight: float = 1e6,
    prior_anchor: PriorAnchorTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
    prior_var_swap: VarSwapTarget | None = None,
    wing_z: np.ndarray | None = None,
    wing_sqrt_lambda: np.ndarray | None = None,
    solver_diag: dict | None = None,
) -> np.ndarray:
    """Bounded least-squares of the data term plus the amplitude ridge.

    The data term is the plain mid residual (``band is None``) or the bid-ask /
    haircut band objective in vol space (volfit.calib.band). ``ridge`` is the hat
    amplitude penalty strength and ``mid_anchor_weight`` the band's mid anchor. A
    ``var_swap`` target adds one var-swap penalty (volfit.calib.varswap); it maps
    the model back to log-moneyness via z = k / (sigma_ref sqrt(t)) so the
    replication integrates over k. ``sigma_ref``/``t`` are only used then.

    ``calendar_k``/``calendar_floor`` add the model-agnostic calendar hinge
    against the previous, shorter expiry's total variance (see
    volfit.calib.calendar.variance_floor_targets); both None leaves the fit
    byte-identical. The grid k is mapped to z via the same sigma_ref/t scaling.
    """
    cal_on = calendar_k is not None and calendar_floor is not None
    cal_z = np.asarray(calendar_k, float) / (sigma_ref * np.sqrt(t)) if cal_on else None
    cal_floor = np.asarray(calendar_floor, float) if cal_on else None
    sqrt_cal = np.sqrt(calendar_weight)

    def residuals(theta: np.ndarray) -> np.ndarray:
        model_vol = np.sqrt(np.maximum(_eval_v(theta, z, n_cores), _V_FLOOR))
        if band is None:
            res = sqrt_w * (model_vol - vol_quotes)
        else:
            res = band_residuals(
                model_vol, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_w, mid_anchor_weight
            )
        if n_cores:
            alphas = theta[6::4][:n_cores]
            res = np.concatenate([res, np.sqrt(ridge) * alphas])
        if var_swap is not None:
            def implied_w(kk: np.ndarray) -> np.ndarray:
                zz = kk / (sigma_ref * np.sqrt(t))
                return np.maximum(_eval_v(theta, zz, n_cores), _V_FLOOR) * t
            res = np.concatenate([res, [varswap_residual(implied_w, var_swap)]])
        if cal_on:
            # No calendar arb: total variance w = v(z)*t must not drop below floor.
            w_model = np.maximum(_eval_v(theta, cal_z, n_cores), _V_FLOOR) * t
            res = np.concatenate([res, sqrt_cal * np.maximum(cal_floor - w_model, 0.0)])
        if prior_anchor is not None or operator_prior is not None or prior_var_swap is not None:
            def implied_w(kk: np.ndarray) -> np.ndarray:
                zz = np.asarray(kk, float) / (sigma_ref * np.sqrt(t))
                return np.maximum(_eval_v(theta, zz, n_cores), _V_FLOOR) * t
            if prior_anchor is not None:
                cp = black_call(prior_anchor.k, implied_w(prior_anchor.k))
                res = np.concatenate([res, prior_anchor_residuals(cp, prior_anchor)])
            if operator_prior is not None:
                res = np.concatenate([res, operator_residuals(implied_w, operator_prior)])
            if prior_var_swap is not None:  # prior's var-swap level (operator companion)
                res = np.concatenate([res, [varswap_residual(implied_w, prior_var_swap)]])
        if wing_sqrt_lambda is not None:
            # Put-wing no-butterfly regularizer (R6): zero on an arb-free slice.
            g = _eval_g(theta, wing_z, n_cores, t, sigma_ref)
            res = np.concatenate([res, wing_sqrt_lambda * np.maximum(-g, 0.0)])
        return res

    def _wing_fd_jac(theta: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """Central finite-difference of the wing-penalty rows only — cheap (a small
        g grid), so the dominant fit/ridge/calendar blocks stay analytic (hybrid)."""
        def wres(th: np.ndarray) -> np.ndarray:
            g = _eval_g(th, wing_z, n_cores, t, sigma_ref)
            return wing_sqrt_lambda * np.maximum(-g, 0.0)

        base = wres(theta)
        jw = np.empty((base.size, theta.size))
        for p in range(theta.size):
            d = np.zeros_like(theta)
            d[p] = eps
            jw[:, p] = (wres(theta + d) - wres(theta - d)) / (2.0 * eps)
        return jw

    theta0 = np.clip(theta0, lo, hi)
    # Analytic Jacobian (R5) for the var-swap/prior-free configuration (mid OR band
    # fit + the amplitude ridge + calendar) — ~2 evals/step instead of scipy's
    # (6+4R+1) finite differences, the dominant cost of multi-core fits. The
    # var-swap / strike-gap / operator-prior blocks keep the finite-difference path
    # (correct, not accelerated), exactly as LQD and SVI gate their analytic Jacobian.
    # trf is kept (the parameters are bound-constrained, unlike the LM-fit SVI).
    use_analytic = (
        var_swap is None
        and prior_anchor is None
        and operator_prior is None
        and prior_var_swap is None
    )
    jac = "2-point"
    if use_analytic:
        def jac(theta: np.ndarray) -> np.ndarray:  # noqa: F811 — gated analytic Jacobian
            j = siv_residual_jacobian(
                theta, z, n_cores, t, sqrt_w, band, mid_anchor_weight, ridge,
                cal_z, cal_floor, sqrt_cal,
            )
            if wing_sqrt_lambda is not None:  # hybrid: FD only the cheap g-penalty rows
                j = np.vstack([j, _wing_fd_jac(theta)])
            return j

    result = least_squares(
        residuals, theta0, bounds=(lo, hi), jac=jac, method="trf", xtol=1e-12, ftol=1e-12
    )
    if solver_diag is not None:
        # Note 15 Phase 2 side-channel: the solution-point Jacobian / residual
        # for the observation filter's information matrix J^T W J.
        solver_diag.update(
            jac=np.asarray(result.jac, dtype=float),
            residual=np.asarray(result.fun, dtype=float),
            theta=np.asarray(result.x, dtype=float).copy(),
            n_fit_rows=int(z.size if band is None else 2 * z.size),
            n_quotes=int(z.size),
        )
    return result.x


def calibrate_sigmoid(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    weights: np.ndarray | None = None,
    n_cores: int = 0,
    band: BandTarget | None = None,
    ridge: float = _RIDGE,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
    var_swap: VarSwapTarget | None = None,
    calendar_k: np.ndarray | None = None,
    calendar_floor: np.ndarray | None = None,
    calendar_weight: float = 1e6,
    prior_anchor: PriorAnchorTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
    prior_var_swap: VarSwapTarget | None = None,
    wing_penalty: float = 0.0,
    solver_diag: dict | None = None,
) -> MultiCoreSiv:
    """Fit the Multi-Core SIV slice to total-variance quotes (eq mcsiv-slice).

    ``n_cores`` is the number R of zero-wing hats added on top of the base SIV
    (the "cores" slider). It is capped so the model never has more free
    parameters than quotes (6 + 4R <= N), guarding sparse short-dated chains
    against fitting spurious narrow kernels (note section identifiability).
    ``band`` switches the final fit to the bid-ask / haircut band objective
    (volfit.calib.band); the base-seeding stage always fits mid so the hats are
    placed on meaningful residuals.

    ``calendar_k``/``calendar_floor`` (volfit.calib.calendar.variance_floor_targets)
    add the model-agnostic calendar hinge against the previous, shorter expiry —
    applied only in the final refine stage (the base-seeding stage stays mid), so
    both None leaves the fit byte-identical.

    ``prior_anchor`` (strike-gap mode) and ``operator_prior`` (operator / hybrid
    modes) add the prior-persistence residual blocks in the final refine stage
    only (the base-seeding stays mid), matching the LQD/SVI paths — the Multi-Core
    SIV overlay is no longer a prior exception (roadmap Phase 3). Both None (the
    default) leave the fit byte-identical.

    ``solver_diag`` (Note 15 Phase 2): filled from the FINAL refine stage's
    solver (the fit that produces the returned parameters), for the observation
    filter's information matrix. None (the default) is byte-identical.
    """
    k = np.asarray(k, dtype=float)
    vol_quotes = np.sqrt(np.asarray(w_quotes, dtype=float) / t)
    v_quotes = np.asarray(w_quotes, dtype=float) / t
    sqrt_w = np.ones_like(k) if weights is None else np.sqrt(np.asarray(weights, float))

    n_cores = max(0, min(int(n_cores), (k.size - 6) // 4))
    sigma_ref = _reference_vol(vol_quotes, k)
    z = k / (sigma_ref * np.sqrt(t))

    # Put-wing no-butterfly regularizer grid (R6): extends past the traded z-range
    # into the unquoted tails, weighted heavier on the put side. None ⇒ off ⇒
    # byte-identical (applied only in the refine stage, never the base seeding).
    wing_z = wing_sqrt_lambda = None
    if wing_penalty > 0.0 and z.size:
        wing_z = np.linspace(z.min() - _WING_PAD, z.max() + _WING_PAD, _WING_GRID)
        put_factor = np.where(wing_z < 0.0, _WING_PUT_FACTOR, 1.0)
        wing_sqrt_lambda = np.sqrt(wing_penalty * put_factor)

    # Stage 1: base SIV (R = 0), always on mid — gives a stable centre and the
    # residuals used to place the hats.
    base_lo, base_hi = _base_bounds(z)
    base = _fit(_base_init(z, v_quotes), base_lo, base_hi, z, vol_quotes, sqrt_w, 0)

    # Stage 2: seed hats on the base residual, then refine everything jointly
    # under the requested objective (band or mid).
    if n_cores > 0:
        residual = v_quotes - _eval_v(base, z, 0)
        seeds = _seed_cores(z, residual, n_cores)
        theta0 = np.concatenate([base, *seeds])
        clo, chi = _core_bounds(z)
        lo = np.concatenate([base_lo, *([clo] * n_cores)])
        hi = np.concatenate([base_hi, *([chi] * n_cores)])
        theta = _fit(
            theta0, lo, hi, z, vol_quotes, sqrt_w, n_cores,
            band=band, ridge=ridge, mid_anchor_weight=mid_anchor_weight,
            var_swap=var_swap, sigma_ref=sigma_ref, t=t,
            calendar_k=calendar_k, calendar_floor=calendar_floor,
            calendar_weight=calendar_weight,
            prior_anchor=prior_anchor, operator_prior=operator_prior,
            prior_var_swap=prior_var_swap,
            wing_z=wing_z, wing_sqrt_lambda=wing_sqrt_lambda,
            solver_diag=solver_diag,
        )
    else:
        theta = _fit(
            base, base_lo, base_hi, z, vol_quotes, sqrt_w, 0,
            band=band, ridge=ridge, mid_anchor_weight=mid_anchor_weight,
            var_swap=var_swap, sigma_ref=sigma_ref, t=t,
            calendar_k=calendar_k, calendar_floor=calendar_floor,
            calendar_weight=calendar_weight,
            prior_anchor=prior_anchor, operator_prior=operator_prior,
            prior_var_swap=prior_var_swap,
            wing_z=wing_z, wing_sqrt_lambda=wing_sqrt_lambda,
            solver_diag=solver_diag,
        )

    cores = tuple(
        HatCore(
            alpha=float(theta[6 + 4 * r]),
            c=float(theta[7 + 4 * r]),
            h=float(theta[8 + 4 * r]),
            kappa=float(theta[9 + 4 * r]),
        )
        for r in range(n_cores)
    )
    return MultiCoreSiv(
        v0=float(theta[0]),
        s0=float(theta[1]),
        k0=float(theta[2]),
        z0=float(theta[3]),
        kappa_p=float(theta[4]),
        kappa_c=float(theta[5]),
        sigma_ref=sigma_ref,
        t=t,
        cores=cores,
    )

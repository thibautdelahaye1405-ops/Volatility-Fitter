"""Calibration of the Multi-Core SIV slice (Docs/Multi_Core_SIV_Technical_Note.tex).

Implements the robust workflow of section "Calibration methodology":

  1. fit the one-core SIV base (R = 0) to the quotes;
  2. seed R signed hats greedily at the largest variance residuals;
  3. refine the full (6 + 4R)-parameter set jointly with bound constraints and a
     mild ridge penalty on the hat amplitudes (eqs calibration-objective,
     kernel-bounds, linear-amplitude-fit);
  4. kernel governance (V3.1 leg 5, the book's "governed dial"): prune hats
     whose |alpha| sits below the quote-noise resolution floor and refit once
     without them — byte-identical when nothing prunes.

Residuals are in implied-vol units (the natural quoting scale). All positive
parameters (K0, the wing steepnesses, the hat half-widths and steepnesses) are
bound-constrained directly through scipy's trust-region reflective solver.

V3.1 file split (400-line policy): the seeding/bounds/evaluation helpers live
in ``seeding.py``, the wing/belly penalty blocks in ``penalties.py``, and the
structural base chart in ``structural.py``; the historical names are
re-exported here so the public import surface is unchanged.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import (
    MID_ANCHOR_WEIGHT,
    BandTarget,
    band_residuals,
    effective_mid_anchor,
    price_targets,
    quote_residual_magnitude,
    robust_multipliers,
)
from volfit.calib.extrap import ExtrapTarget, extrap_residuals
from volfit.calib.operators import OperatorPriorTarget, operator_residuals
from volfit.calib.prior import PriorAnchorTarget, prior_anchor_residuals
from volfit.calib.tails import TailMatchTarget
from volfit.calib.varswap import VarSwapTarget, varswap_residual
from volfit.core.black import black_call
from volfit.models.sigmoid.jacobian import siv_residual_jacobian
from volfit.models.sigmoid.penalties import (  # noqa: F401 — re-export shims
    BELLY_MARGIN, WING_PENALTY_BASE, _eval_g, belly_rows, fd_rows, wing_penalty_grid,
)
from volfit.models.sigmoid.seeding import (  # noqa: F401 — re-export shims
    _RIDGE, _V_FLOOR, _base_bounds, _base_init, _core_bounds, _eval_v,
    _reference_vol, _seed_cores, alpha_resolution_floor,
)
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv, analytic_lee_slopes
from volfit.models.sigmoid.structural import (
    pack_structural_mcs, siv_residual_jacobian_structural,
    structural_bounds_mcs, unpack_structural_mcs,
)
from volfit.models.sigmoid.tail_rows import mcs_tail_jacobian, mcs_tail_rows

#: Default Lee wing-slope cap for the structural chart — mirrors the buffered
#: FitSettings.leeSlopeMax production default (committee R1: beta = 2 itself
#: admits negative tail density, so the cap is strictly under Lee's bound).
#: Only read when ``chart="structural"``; the raw chart has no cap (its wings
#: are diagnosed, not fenced — the historical behaviour, byte-identical).
_LEE_SLOPE_MAX = 1.95
#: Stiffness ramp of a tail-matched refine (fractions of the target's stiff
#: weight solved in turn, warm-started, before the full-weight solve).
_TAIL_CONTINUATION = (1e-4, 1e-3, 1e-2, 1e-1)
#: The tail-matched refine's anchor ridge: sqrt(lambda) (theta - theta_plain)
#: / max(|theta_plain|, floor) per solver coordinate. 1e-6 makes a FULL
#: relative move cost what a 10 bp error on one quote costs — invisible to
#: the belly fit, decisive along the far-wing valley (curvature ~1e-9 there).
_ANCHOR_LAMBDA = 1e-6
_ANCHOR_FLOOR = 0.1


def _scaled_tail_match(target: TailMatchTarget, frac: float) -> TailMatchTarget:
    """The same tail target at ``frac`` of its stiff weight (var-swap row too)."""
    vs = target.var_swap
    return replace(
        target,
        weight=target.weight * frac,
        var_swap=None if vs is None else replace(vs, weight=vs.weight * frac),
    )


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
    calendar_k_ceil: np.ndarray | None = None,
    calendar_ceiling: np.ndarray | None = None,
    prior_anchor: PriorAnchorTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
    prior_var_swap: VarSwapTarget | None = None,
    wing_z: np.ndarray | None = None,
    wing_sqrt_lambda: np.ndarray | None = None,
    belly_z: np.ndarray | None = None,
    extrap: "ExtrapTarget | None" = None,
    chart_cap: float | None = None,
    slope_scale: float = 1.0,
    solver_diag: dict | None = None,
    price_rows: tuple | None = None,
    scheme_mean_w: float | None = None,
    tail_match: TailMatchTarget | None = None,
    anchor: tuple[np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    """Bounded least-squares of the data term plus the amplitude ridge.

    ``tail_match`` (volfit.calib.tails — the Compare view's tail-matching
    toggles) appends the stiff var-swap / Lee-slope / edge rows (analytic
    Jacobian, sigmoid/tail_rows); ``anchor`` = (theta_ref, scale) adds the
    tiny scaled ridge sqrt(_ANCHOR_LAMBDA) (theta - theta_ref) / scale on the
    SOLVER vector (the LAST block) that makes a tail-matched refine the
    smallest deformation of the plain fit — without it the far-wing
    parameters the quotes never see trade off along a flat valley the
    trust-region solver inches through for its whole budget. Both None
    (every production fit) are byte-identical.

    The data term is the plain mid residual (``band is None``) or the bid-ask /
    haircut band objective in vol space (volfit.calib.band); ``ridge`` is the
    hat-amplitude penalty and ``mid_anchor_weight`` the band's mid anchor. The
    optional blocks (var-swap, calendar floor/ceiling hinges, priors, the R6
    wing regularizer) mirror the historical signature; each None default is
    byte-identical, and grids in k map to z via the sigma_ref/t scaling.

    ``belly_z`` (V3.1 leg 2) adds the belly-repair hinge rows
    (penalties.belly_rows) on a z-grid over the TRADED range; None (every fit
    except a repair refit) is byte-identical. ``chart_cap`` (V3.1 leg 3)
    switches the optimizer to the structural base chart of ``structural.py``
    with that Lee cap: ``theta0``/``lo``/``hi`` and the returned vector are
    then CHART-space in the first 6 coordinates (hats stay raw); None (the
    default) is the historical raw vector, byte-identical.

    ``price_rows`` (overlayPriceResiduals) is the frozen ``(k, target_price,
    inv_vega, price_lo, price_hi)`` tuple switching the data rows to the LQD
    convention — vega-normalized price residuals / a price-space band hinge —
    on the SAME analytic gate (price_rows.py chains dC/dw row-wise, both
    charts, FD-locked); None (the default) keeps the vol-space rows byte-identical.
    ``scheme_mean_w`` freezes the extrap block's mean quote weight at the
    SCHEME weights so the IRLS reweighting (calibrate_sigmoid) touches the
    data rows only; None computes it from ``sqrt_w`` (the historical value).
    """
    cal_on = calendar_k is not None and calendar_floor is not None
    cal_z = np.asarray(calendar_k, float) / (sigma_ref * np.sqrt(t)) if cal_on else None
    cal_floor = np.asarray(calendar_floor, float) if cal_on else None
    ceil_on = calendar_k_ceil is not None and calendar_ceiling is not None
    ceil_z = np.asarray(calendar_k_ceil, float) / (sigma_ref * np.sqrt(t)) if ceil_on else None
    ceil_w = np.asarray(calendar_ceiling, float) if ceil_on else None
    sqrt_cal = np.sqrt(calendar_weight)
    _anchor_sqrt = float(np.sqrt(_ANCHOR_LAMBDA))

    def to_raw(theta: np.ndarray) -> np.ndarray:
        """Chart -> raw parameter vector (identity on the raw chart)."""
        if chart_cap is None:
            return theta
        return np.concatenate(
            [unpack_structural_mcs(theta[:6], chart_cap, slope_scale), theta[6:]]
        )

    def residuals(theta: np.ndarray) -> np.ndarray:
        theta_r = to_raw(theta)
        model_vol = np.sqrt(np.maximum(_eval_v(theta_r, z, n_cores), _V_FLOOR))
        if price_rows is not None:
            # Price-residual mode (the LQD convention): vega-normalized call
            # prices, band hinge on the frozen price edges.
            pk, target_price, inv_vega, price_lo, price_hi = price_rows
            model_price = black_call(pk, model_vol**2 * t)
            if band is None:
                res = sqrt_w * inv_vega * (model_price - target_price)
            else:
                res = band_residuals(
                    model_price, price_lo, price_hi, target_price,
                    sqrt_w * inv_vega, mid_anchor_weight,
                )
        elif band is None:
            res = sqrt_w * (model_vol - vol_quotes)
        else:
            res = band_residuals(
                model_vol, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_w, mid_anchor_weight
            )
        if n_cores:
            alphas = theta_r[6::4][:n_cores]
            res = np.concatenate([res, np.sqrt(ridge) * alphas])
        if var_swap is not None:
            def implied_w(kk: np.ndarray) -> np.ndarray:
                zz = kk / (sigma_ref * np.sqrt(t))
                return np.maximum(_eval_v(theta_r, zz, n_cores), _V_FLOOR) * t
            res = np.concatenate([res, [varswap_residual(implied_w, var_swap)]])
        if cal_on:
            # No calendar arb: total variance w = v(z)*t must not drop below floor.
            w_model = np.maximum(_eval_v(theta_r, cal_z, n_cores), _V_FLOOR) * t
            res = np.concatenate([res, sqrt_cal * np.maximum(cal_floor - w_model, 0.0)])
        if ceil_on:
            # Symmetric counterpart: must not rise above the LONGER expiry.
            w_model = np.maximum(_eval_v(theta_r, ceil_z, n_cores), _V_FLOOR) * t
            res = np.concatenate([res, sqrt_cal * np.maximum(w_model - ceil_w, 0.0)])
        if prior_anchor is not None or operator_prior is not None or prior_var_swap is not None:
            def implied_w(kk: np.ndarray) -> np.ndarray:
                zz = np.asarray(kk, float) / (sigma_ref * np.sqrt(t))
                return np.maximum(_eval_v(theta_r, zz, n_cores), _V_FLOOR) * t
            if prior_anchor is not None:
                cp = black_call(prior_anchor.k, implied_w(prior_anchor.k))
                res = np.concatenate([res, prior_anchor_residuals(cp, prior_anchor)])
            if operator_prior is not None:
                res = np.concatenate([res, operator_residuals(implied_w, operator_prior)])
            if prior_var_swap is not None:
                # Prior's var-swap companion; varswap_residual honors the
                # carrier mode (absolute / atm_spread). FD Jacobian path.
                res = np.concatenate([res, [varswap_residual(implied_w, prior_var_swap)]])
        if wing_sqrt_lambda is not None:
            # Put-wing no-butterfly regularizer (R6): zero on an arb-free slice.
            g = _eval_g(theta_r, wing_z, n_cores, t, sigma_ref)
            res = np.concatenate([res, wing_sqrt_lambda * np.maximum(-g, 0.0)])
        if belly_z is not None:
            # Belly-repair hinge (V3.1 leg 2): zero on a certified slice.
            res = np.concatenate([res, belly_rows(theta_r, belly_z, n_cores, t, sigma_ref)])
        if extrap is not None:
            res = np.concatenate([res, _extrap_rows(theta)])
        if tail_match is not None:
            res = np.concatenate([res, _tail_rows(theta)])
        if anchor is not None:
            res = np.concatenate([res, _anchor_sqrt * (theta - anchor[0]) / anchor[1]])
        return res

    def _w_and_lee(theta: np.ndarray):
        """The iterate's total-variance curve w(k) and its closed-form
        asymptotic k-space slopes (V3.1 leg 1, eq mcsbetak: the kernels are
        zero-wing, so the base decides both tails)."""
        theta_r = to_raw(theta)

        def w_of_k(kk: np.ndarray) -> np.ndarray:
            zz = np.asarray(kk, float) / (sigma_ref * np.sqrt(t))
            return np.maximum(_eval_v(theta_r, zz, n_cores), _V_FLOOR) * t

        v0, s0, k0, z0, kp, kc = theta_r[:6]
        lee_fn = lambda: analytic_lee_slopes(  # noqa: E731
            s0 - 2.0 * k0 / kp, s0 + 2.0 * k0 / kc, sigma_ref, t
        )
        return w_of_k, lee_fn

    def _extrap_rows(theta: np.ndarray) -> np.ndarray:
        """Tapered extrapolated-region rows (Notes 09/10 Phase 2)."""
        w_of_k, lee_fn = _w_and_lee(theta)
        return extrap_residuals(
            w_of_k, extrap, t,
            # Frozen at the scheme weights under IRLS (same float otherwise).
            mean_weight=(
                scheme_mean_w if scheme_mean_w is not None else float(np.mean(sqrt_w**2))
            ),
            lee_fn=lee_fn,
        )

    def _tail_rows(theta: np.ndarray) -> np.ndarray:
        """Tail-matching rows (Compare toggles, volfit.calib.tails) — LAST block."""
        return mcs_tail_rows(to_raw(theta), n_cores, sigma_ref, t, tail_match)

    def _tail_jac(theta: np.ndarray) -> np.ndarray:
        """Analytic Jacobian of the tail rows (sigmoid/tail_rows); on the
        structural chart the 6 base columns chain through the chart map
        (a 6x6 central difference of the closed-form unpack — cheap)."""
        j = mcs_tail_jacobian(to_raw(theta), n_cores, sigma_ref, t, tail_match)
        if chart_cap is not None:
            eps = 1e-6
            chain = np.empty((6, 6))
            for p in range(6):
                d = np.zeros(6)
                d[p] = eps
                chain[:, p] = (
                    unpack_structural_mcs(theta[:6] + d, chart_cap, slope_scale)
                    - unpack_structural_mcs(theta[:6] - d, chart_cap, slope_scale)
                ) / (2.0 * eps)
            j[:, :6] = j[:, :6] @ chain
        return j

    def _wing_res(theta: np.ndarray) -> np.ndarray:
        g = _eval_g(to_raw(theta), wing_z, n_cores, t, sigma_ref)
        return wing_sqrt_lambda * np.maximum(-g, 0.0)

    def _belly_res(theta: np.ndarray) -> np.ndarray:
        return belly_rows(to_raw(theta), belly_z, n_cores, t, sigma_ref)

    theta0 = np.clip(theta0, lo, hi)
    # Analytic Jacobian (R5) for the var-swap/prior-free configuration — ~2
    # evals/step vs scipy's (6+4R+1) FDs; the var-swap / prior blocks keep the
    # FD path, exactly as LQD and SVI gate theirs. trf is kept (bound
    # constraints). The structural chart runs the SAME gate through the
    # closed-form 6x6 chain; wing/belly/extrap blocks are hybrid central-FD.
    use_analytic = (
        var_swap is None
        and prior_anchor is None
        and operator_prior is None
        and prior_var_swap is None
    )
    jac = "2-point"
    if use_analytic:
        def jac(theta: np.ndarray) -> np.ndarray:  # noqa: F811 — gated analytic Jacobian
            if chart_cap is None:
                j = siv_residual_jacobian(
                    theta, z, n_cores, t, sqrt_w, band, mid_anchor_weight, ridge,
                    cal_z, cal_floor, sqrt_cal, ceil_z, ceil_w, price_rows=price_rows,
                )
            else:
                j = siv_residual_jacobian_structural(
                    theta, z, n_cores, t, sqrt_w, band, mid_anchor_weight, ridge,
                    cal_z, cal_floor, sqrt_cal, ceil_z, ceil_w,
                    chart_cap, slope_scale, price_rows=price_rows,
                )
            if wing_sqrt_lambda is not None:  # hybrid: FD only the cheap g-penalty rows
                j = np.vstack([j, fd_rows(_wing_res, theta)])
            if belly_z is not None:  # hybrid: FD only the repair hinge rows
                j = np.vstack([j, fd_rows(_belly_res, theta)])
            if extrap is not None:  # hybrid: FD only the small extrap block
                j = np.vstack([j, fd_rows(_extrap_rows, theta)])
            if tail_match is not None:  # analytic (sigmoid/tail_rows): one replication, not 2P
                j = np.vstack([j, _tail_jac(theta)])
            if anchor is not None:  # the scaled ridge is diagonal in the solver vector
                j = np.vstack([j, np.diag(_anchor_sqrt / anchor[1])])
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
    calendar_k_ceil: np.ndarray | None = None,
    calendar_ceiling: np.ndarray | None = None,
    prior_anchor: PriorAnchorTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
    prior_var_swap: VarSwapTarget | None = None,
    wing_penalty: float = 0.0,
    belly_grid: np.ndarray | None = None,
    extrap: ExtrapTarget | None = None,
    chart: str = "raw",
    lee_slope_max: float = _LEE_SLOPE_MAX,
    solver_diag: dict | None = None,
    mid_anchor_tau_ref: float | None = None,
    robust_loss: str = "off",
    robust_f_scale: float = 0.005,
    price_residuals: bool = False,
    tail_match: TailMatchTarget | None = None,
) -> MultiCoreSiv:
    """Fit the Multi-Core SIV slice to total-variance quotes (eq mcsiv-slice).

    ``tail_match`` (volfit.calib.tails — the Compare view's tail-matching
    toggles) adds the stiff var-swap / Lee-slope / edge rows to the refine
    stage (the base seeding stays mid); None (the default) is byte-identical.

    ``n_cores`` is the number R of zero-wing hats added on top of the base SIV
    (the "cores" slider). It is capped so the model never has more free
    parameters than quotes (6 + 4R <= N), guarding sparse short-dated chains
    against fitting spurious narrow kernels (note section identifiability).
    ``band`` switches the final fit to the bid-ask / haircut band objective
    (volfit.calib.band); the base-seeding stage always fits mid so the hats are
    placed on meaningful residuals.

    ``calendar_k``/``calendar_floor`` (volfit.calib.calendar.variance_floor_targets)
    add the model-agnostic calendar hinge against the previous, shorter expiry;
    ``prior_anchor`` (strike-gap mode) and ``operator_prior`` (operator / hybrid
    modes) the prior-persistence residual blocks, matching the LQD/SVI paths
    (roadmap Phase 3). All are applied only in the final refine stage (the
    base-seeding stage stays mid); None (each default) is byte-identical.

    ``belly_grid`` (V3.1 leg 2, the SVI R2 repair-rider mirror): a k-grid over
    the traded range adding the belly hinge rows (penalties.belly_rows,
    WING_PENALTY_BASE * max(-g + BELLY_MARGIN, 0)) in the refine stage; the
    display path passes it only on a REPAIR refit after a failed certificate,
    so a clean first fit stays byte-identical.

    ``chart`` (V3.1 leg 3): "raw" = the historical bounded vector (default,
    byte-identical); "structural" = the (β_L, β_R, z*, v*, κ_P, κ_C) base
    chart of ``structural.py`` — the base's k-space Lee wing slopes
    (eq mcsbetak) lifted logistically against the buffered ``lee_slope_max``
    cap, strictly Lee-clean at every finite iterate. Seeding always runs raw;
    the refine solves in the chart. Both charts run the analytic Jacobian.

    ``solver_diag`` (Note 15 Phase 2): filled from the FINAL solve that
    produces the returned parameters. None (the default) is byte-identical.

    Kernel governance (V3.1 leg 5): hats whose |alpha| sits below the
    quote-noise resolution floor (seeding.alpha_resolution_floor) are pruned
    and the slice refit ONCE without them; ``cores`` reports the EFFECTIVE
    count. Nothing pruned ⇒ byte-identical.

    Short-dated objective knobs (all defaults byte-identical):
    ``mid_anchor_tau_ref`` attenuates the band's mid anchor by
    min(1, sqrt(t / tau_ref)) (calib.band.effective_mid_anchor).
    ``robust_loss``/``robust_f_scale`` run two IRLS passes over the QUOTE
    rows of the refine stage only, AFTER seeding/governance — scipy's global
    ``loss=`` would also soften the ridge / calendar / prior / wing rows,
    which must stay quadratic; the multipliers are solver-internal (the
    user-facing weights stay the scheme weights) and the extrap block's mean
    weight is frozen at the scheme value. ``price_residuals``
    (overlayPriceResiduals) switches the refine-stage data rows to the LQD
    convention — vega-normalized price residuals, band edges as call prices
    (calib.band.price_targets) — on the analytic Jacobian, both charts (see
    ``_fit`` / price_rows.py); the base-seeding stage always stays a
    scheme-weighted vol-space mid fit (its role is placing the hats).
    """
    k = np.asarray(k, dtype=float)
    w_arr = np.asarray(w_quotes, dtype=float)
    vol_quotes = np.sqrt(w_arr / t)
    v_quotes = w_arr / t
    sqrt_w = np.ones_like(k) if weights is None else np.sqrt(np.asarray(weights, float))
    # Short-dated knobs: tau-attenuated mid anchor (identity when the ref is
    # None) and the frozen price-space targets (None keeps vol-space rows).
    maw_eff = effective_mid_anchor(mid_anchor_weight, t, mid_anchor_tau_ref)
    pt = (k, *price_targets(k, w_arr, t, band)) if price_residuals else None

    n_cores = max(0, min(int(n_cores), (k.size - 6) // 4))
    sigma_ref = _reference_vol(vol_quotes, k)
    sq_t = np.sqrt(t)
    z = k / (sigma_ref * sq_t)

    # Put-wing no-butterfly regularizer grid (R6) and the belly-repair grid
    # (V3.1 leg 2), both in z; None ⇒ off ⇒ byte-identical (refine stage only).
    wing_z, wing_sqrt_lambda = wing_penalty_grid(z, wing_penalty)
    belly_z = None
    if belly_grid is not None and np.asarray(belly_grid).size:
        belly_z = np.asarray(belly_grid, dtype=float) / (sigma_ref * sq_t)

    structural = chart == "structural"
    slope_scale = sq_t / sigma_ref  # k-space slope per z-space slope (eq mcsbetak)

    # Stage 1: base SIV (R = 0), always on mid AND always in the raw chart —
    # it exists to give a stable centre and the residuals that place the hats.
    base_lo, base_hi = _base_bounds(z)
    base = _fit(_base_init(z, v_quotes), base_lo, base_hi, z, vol_quotes, sqrt_w, 0)

    refine_kwargs = dict(
        band=band, ridge=ridge, mid_anchor_weight=maw_eff,
        price_rows=pt, scheme_mean_w=float(np.mean(sqrt_w**2)),
        var_swap=var_swap, sigma_ref=sigma_ref, t=t,
        calendar_k=calendar_k, calendar_floor=calendar_floor,
        calendar_weight=calendar_weight,
        calendar_k_ceil=calendar_k_ceil, calendar_ceiling=calendar_ceiling,
        prior_anchor=prior_anchor, operator_prior=operator_prior,
        prior_var_swap=prior_var_swap,
        wing_z=wing_z, wing_sqrt_lambda=wing_sqrt_lambda,
        belly_z=belly_z,
        extrap=extrap,
        chart_cap=lee_slope_max if structural else None,
        slope_scale=slope_scale,
        solver_diag=solver_diag,
        tail_match=tail_match,
    )
    base_theta0 = pack_structural_mcs(base, lee_slope_max, slope_scale) if structural else base
    ref_lo, ref_hi = structural_bounds_mcs(z) if structural else (base_lo, base_hi)

    # Stage 2: seed hats on the base residual, then refine everything jointly
    # under the requested objective (band or mid). A tail-matched refine is
    # WARM-STARTED from the plain refine's solution: the stiff rows are then
    # met in a few iterations as the smallest deformation of the plain fit,
    # instead of a long walk from the seeds along the far-wing valley the
    # quotes never see (the plain path is byte-identical: one solve).
    if n_cores > 0:
        residual = v_quotes - _eval_v(base, z, 0)
        seeds = _seed_cores(z, residual, n_cores)
        theta0 = np.concatenate([base_theta0, *seeds])
        clo, chi = _core_bounds(z)
        lo = np.concatenate([ref_lo, *([clo] * n_cores)])
        hi = np.concatenate([ref_hi, *([chi] * n_cores)])
    else:
        theta0, lo, hi = base_theta0, ref_lo, ref_hi
    if tail_match is not None:
        theta0 = _fit(theta0, lo, hi, z, vol_quotes, sqrt_w, n_cores, **{**refine_kwargs, "tail_match": None})
        # The tail-matched refine is the SMALLEST deformation of that plain
        # solution meeting the stiff rows: an anchor ridge (see _fit) on the
        # solver vector turns the far-wing valley — parameters the quotes never
        # see trading off with no cost — into a bowl the solver can descend.
        # A stiffness ramp (continuation) then lets each solve converge instead
        # of the trust region collapsing against the full-weight rows at once.
        refine_kwargs["anchor"] = (theta0.copy(), np.maximum(np.abs(theta0), _ANCHOR_FLOOR))
        for frac in _TAIL_CONTINUATION:
            soft = _scaled_tail_match(tail_match, frac)
            theta0 = _fit(theta0, lo, hi, z, vol_quotes, sqrt_w, n_cores, **{**refine_kwargs, "tail_match": soft})
    theta = _fit(theta0, lo, hi, z, vol_quotes, sqrt_w, n_cores, **refine_kwargs)

    def to_raw(th: np.ndarray) -> np.ndarray:
        if not structural:
            return th
        return np.concatenate(
            [unpack_structural_mcs(th[:6], lee_slope_max, slope_scale), th[6:]]
        )

    # Kernel governance (V3.1 leg 5): prune sub-resolution hats, refit once.
    theta_raw = to_raw(theta)
    if n_cores > 0:
        alphas = theta_raw[6::4][:n_cores]
        floor = alpha_resolution_floor(theta_raw, z, vol_quotes, n_cores, sigma_ref)
        keep = np.abs(alphas) >= floor
        if not keep.all():
            n_keep = int(keep.sum())
            kept_blocks = [theta[6 + 4 * r : 10 + 4 * r] for r in range(n_cores) if keep[r]]
            theta0 = np.concatenate([theta[:6], *kept_blocks]) if n_keep else theta[:6]
            clo, chi = _core_bounds(z)
            lo = np.concatenate([ref_lo, *([clo] * n_keep)])
            hi = np.concatenate([ref_hi, *([chi] * n_keep)])
            n_cores = n_keep
            theta = _fit(theta0, lo, hi, z, vol_quotes, sqrt_w, n_cores, **refine_kwargs)
            theta_raw = to_raw(theta)

    # IRLS robust passes over the quote rows only (calibrate_sigmoid docstring):
    # multipliers from the ACTIVE-space data residuals at the current solution,
    # warm-started refits at the same bounds. "off" never enters this block.
    if robust_loss != "off" and z.size:
        for _ in range(2):
            model_vol = np.sqrt(np.maximum(_eval_v(theta_raw, z, n_cores), _V_FLOOR))
            if pt is not None:
                _pk, target_price, inv_vega, price_lo, price_hi = pt
                r = quote_residual_magnitude(
                    black_call(k, model_vol**2 * t), target_price,
                    price_lo, price_hi, maw_eff, inv_vega,
                )
            elif band is None:
                r = quote_residual_magnitude(model_vol, vol_quotes, None, None, maw_eff)
            else:
                r = quote_residual_magnitude(
                    model_vol, band.iv_mid, band.iv_lo, band.iv_hi, maw_eff
                )
            sq_w_r = sqrt_w * np.sqrt(robust_multipliers(r, robust_loss, robust_f_scale))
            theta = _fit(theta, lo, hi, z, vol_quotes, sq_w_r, n_cores, **refine_kwargs)
            theta_raw = to_raw(theta)

    cores = tuple(
        HatCore(*(float(x) for x in theta_raw[6 + 4 * r : 10 + 4 * r]))
        for r in range(n_cores)
    )
    v0, s0, k0, z0, kp, kc = (float(x) for x in theta_raw[:6])
    return MultiCoreSiv(
        v0=v0, s0=s0, k0=k0, z0=z0, kappa_p=kp, kappa_c=kc,
        sigma_ref=sigma_ref, t=t, cores=cores,
    )

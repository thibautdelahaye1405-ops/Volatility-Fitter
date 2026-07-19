"""One-expiry LQD calibration (note section 7 and Appendix C).

Objective: vega-normalized price residuals (eq. vega_resid) so the loss is
approximately a volatility error while every feasible iterate remains a
genuine arbitrage-free density,

    min_theta  sum_i w_i ((C_lqd(k_i) - B(k_i, w_i)) / (vega_i + eta))^2
             + lam * sum_{n>=4} n^{2r} a_n^2          (eq. calib_objective)

subject to the structural right-tail bound A_R < 1 (eq. right_admissible),
handled with a smooth soft barrier plus a hard rejection.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import MID_ANCHOR_WEIGHT, BandTarget, band_residuals
from volfit.calib.operators import OperatorPriorTarget, operator_residuals
from volfit.calib.prior import PriorAnchorTarget, prior_anchor_residuals
from volfit.calib.varswap import VarSwapTarget, varswap_residual_w
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.lqd.basis import LQDParams, endpoint_scales
from volfit.models.lqd.charts import build_chart, endpoint_transform  # noqa: F401 — endpoint_transform re-exported for back-compat
from volfit.models.lqd.jacobian import residual_jacobian
from volfit.models.lqd.quadrature import LQDSlice, build_slice

# Soft-barrier location/steepness for A_R: starts pushing back well before
# the hard integrability bound A_R < 1 so finite-difference Jacobians stay smooth.
_BARRIER_CENTER = 0.90
_BARRIER_SCALE = 50.0
_VEGA_FLOOR = 1e-4

# Grid size for the *optimization* slices (the ~900 finite-difference Jacobian
# evaluations). The Simpson quadrature error of the 2001-node grid is already
# orders of magnitude below the 5 vol-bp fit budget, so the converged parameters
# agree with the full 8001-node fit to ~1e-6 while each iterate builds ~3x
# faster. The accepted slice is always rebuilt at the full N_POINTS for the
# reported result, density, var-swap and calendar diagnostics.
OPT_N_POINTS = 2001


@dataclass(frozen=True)
class CalibrationResult:
    """Fitted parameters plus convergence/fit diagnostics."""

    params: LQDParams
    slice: LQDSlice
    cost: float
    n_evaluations: int
    success: bool
    max_iv_error: float  # max |model - quote| implied vol over the quotes


def logistic_init(w0_guess: float, n_order: int = 6) -> LQDParams:
    """Logistic base initializer (note 7.2): a_n = 0, L = R = log s with the
    variance match Var(X) ~ pi^2 s^2 / 3 = w0."""
    s = np.sqrt(3.0 * w0_guess) / np.pi
    return LQDParams(L=float(np.log(s)), R=float(np.log(s)), a=np.zeros(n_order - 1))


def _residuals(
    theta: np.ndarray,
    k: np.ndarray,
    target_price: np.ndarray,
    inv_vega: np.ndarray,
    sqrt_weights: np.ndarray,
    reg: np.ndarray,
    cal_z: np.ndarray | None,
    cal_floor: np.ndarray | None,
    cal_weight: float,
    cal_k: np.ndarray | None,
    cal_pfloor: np.ndarray | None,
    cal_taper: np.ndarray | None,
    price_lo: np.ndarray | None,
    price_hi: np.ndarray | None,
    barrier_center: float,
    barrier_scale: float,
    mid_anchor_weight: float,
    var_swap: VarSwapTarget | None,
    prior_anchor: PriorAnchorTarget | None,
    prior_var_swap: VarSwapTarget | None,
    operator_prior: OperatorPriorTarget | None,
    n_points: int,
) -> np.ndarray:
    """Stacked fit + regularization + calendar + barrier residuals.

    The data block is the mid price residual (``price_lo``/``price_hi`` None) or
    the bid-ask / haircut band objective (volfit.calib.band) in vega-normalized
    price space — the band edges are the call prices at the band vols, so the
    monotone vega scaling keeps it ~ a vol-space band fit. A ``var_swap`` target
    adds one vol-space penalty pulling the slice's fair var-swap to the quote
    (volfit.calib.varswap).
    """
    params = LQDParams.from_vector(theta)
    _, a_right = endpoint_scales(params)
    # A wild trial theta can overflow the endpoint exp to inf (or carry a NaN
    # through); clamp so the rejection penalty and barrier stay finite — a
    # non-finite residual poisons trf's step control instead of repelling it.
    if not np.isfinite(a_right) or a_right > 1e6:
        a_right = 1e6
    n_cal = 0 if cal_z is None else cal_z.size
    n_calk = 0 if cal_k is None else cal_k.size
    n_prior = 0 if prior_anchor is None else prior_anchor.k.size
    n_op = 0 if operator_prior is None else len(operator_prior.names)
    band_mode = price_lo is not None
    n_fit = (2 * k.size) if band_mode else k.size
    vs = np.empty(0) if var_swap is None else np.zeros(1)
    pa = np.empty(0) if prior_anchor is None else np.zeros(n_prior)
    pvs = np.empty(0) if prior_var_swap is None else np.zeros(1)
    op = np.empty(0) if operator_prior is None else np.zeros(n_op)
    try:
        slice_ = build_slice(params, n_points=n_points)
        model_price = slice_.call_price(k)
        if band_mode:
            fit = band_residuals(
                model_price, price_lo, price_hi, target_price,
                sqrt_weights * inv_vega, mid_anchor_weight,
            )
        else:
            fit = sqrt_weights * (model_price - target_price) * inv_vega
        # Soft calendar slack (note eq. slack_calendar): penalize the later
        # expiry's integrated upper-quantile curve dropping below the floor.
        # Evaluated at the constraint z-values so it is exact on whatever grid
        # this slice is built on (the optimization grid may be coarser).
        if n_cal:
            cal = np.sqrt(cal_weight) * np.maximum(
                cal_floor - slice_.asset_share_at(cal_z), 0.0
            )
        else:
            cal = np.empty(0)
        # Support-confined price-space floor (volfit.calib.calendar.
        # confined_calendar_floor): the normalized call must stay at or above
        # the near expiry's on the common quote support, with the taper fading
        # the rows beyond it. This is the constraint form that CANNOT be
        # windowed in G(alpha) space (tail contamination — see that module).
        if n_calk:
            taper = 1.0 if cal_taper is None else cal_taper
            calk = np.sqrt(cal_weight) * taper * np.maximum(
                cal_pfloor - slice_.call_price(cal_k), 0.0
            )
        else:
            calk = np.empty(0)
        if var_swap is not None:
            # LQD's exact closed-form var-swap (note: var_swap_strike = -2 E[X])
            # is cheap; the generic replication would re-solve implied_w on a
            # grid every Jacobian column and make the fit minutes-slow.
            vs = np.array([varswap_residual_w(slice_.var_swap_strike(), var_swap)])
        if prior_anchor is not None:
            # Soft data-gap anchor toward the (transported) prior at delta-locations
            # (one extra call_price evaluation; vega-normalized like the data block).
            pa = prior_anchor_residuals(slice_.call_price(prior_anchor.k), prior_anchor)
        if prior_var_swap is not None:
            # Prior's var-swap level as a model-free total-variance moment (cheap
            # closed form), scaled by how unobserved the smile is.
            pvs = np.array([varswap_residual_w(slice_.var_swap_strike(), prior_var_swap)])
        if operator_prior is not None:
            # Quote-operator prior (ATM/RR/BF): pull the model's operators toward
            # the prior's where the live quotes don't identify them (design note §5).
            op = operator_residuals(slice_.implied_w, operator_prior)
    except ValueError:
        # Infeasible trial (A_R >= 1, or an interior-excursion overflow —
        # quadrature.EXP_BUDGET): large finite penalty keeps trf moving back.
        fit = np.full(n_fit, 10.0 + a_right)
        cal = np.zeros(n_cal)
        calk = np.zeros(n_calk)
        pa = np.zeros(n_prior)
        pvs = np.zeros(0 if prior_var_swap is None else 1)
        op = np.zeros(n_op)
    # Softplus via logaddexp: log1p(exp(x)) overflows to inf past x ~ 709 (a
    # wild trial theta easily reaches A_R ~ e^20), which poisons trf's cost;
    # logaddexp(0, x) is the same function evaluated stably (~x for large x).
    barrier = np.logaddexp(0.0, barrier_scale * (a_right - barrier_center))
    return np.concatenate((fit, reg * theta[2:], cal, calk, [barrier], vs, pa, pvs, op))


def prepare_residual_args(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    n_order: int = 6,
    weights: np.ndarray | None = None,
    reg_lambda: float = 0.0,
    reg_power: float = 1.0,
    calendar_z: np.ndarray | None = None,
    calendar_floor: np.ndarray | None = None,
    calendar_weight: float = 1e6,
    calendar_k: np.ndarray | None = None,
    calendar_price_floor: np.ndarray | None = None,
    calendar_taper: np.ndarray | None = None,
    band: BandTarget | None = None,
    barrier_center: float = _BARRIER_CENTER,
    barrier_scale: float = _BARRIER_SCALE,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
    var_swap: VarSwapTarget | None = None,
    prior_anchor: PriorAnchorTarget | None = None,
    prior_var_swap: VarSwapTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
    opt_n_points: int = OPT_N_POINTS,
) -> tuple[tuple, bool]:
    """Build the frozen ``_residuals``/``residual_jacobian`` argument tuple for
    one slice, plus the analytic-Jacobian eligibility flag.

    This is calibrate_slice's preprocessing (quote prices, vega normalizers,
    band edges, regularization vector) split out so the joint symmetric
    solver (volfit.calib.symmetric) can stack per-slice residual blocks from
    the exact same objective a standalone fit uses.
    """
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    weights = np.ones_like(k) if weights is None else np.asarray(weights, dtype=float)

    # Quote prices and vega normalizers are fixed during optimization.
    target_price = black_call(k, w_quotes)
    sigma = np.sqrt(w_quotes / t)
    inv_vega = 1.0 / (black_vega_sigma(k, sigma, t) + _VEGA_FLOOR)
    sqrt_weights = np.sqrt(weights)

    # Band fit: precompute the call-price band edges from the vol band edges.
    price_lo = price_hi = None
    if band is not None:
        price_lo = black_call(k, band.iv_lo**2 * t)
        price_hi = black_call(k, band.iv_hi**2 * t)

    # Regularization vector aligned with theta[2:] = (a_2, ..., a_N).
    n_idx = np.arange(2, n_order + 1, dtype=float)
    reg = np.sqrt(reg_lambda) * np.where(n_idx >= 4, n_idx**reg_power, 0.0)

    # The var-swap and prior-anchor terms are not differentiated analytically
    # yet, so their presence gates the fit back to the FD Jacobian.
    use_analytic = (
        var_swap is None
        and prior_anchor is None
        and prior_var_swap is None
        and operator_prior is None
    )
    args = (
        k,
        target_price,
        inv_vega,
        sqrt_weights,
        reg,
        calendar_z,
        calendar_floor,
        calendar_weight,
        calendar_k,
        calendar_price_floor,
        calendar_taper,
        price_lo,
        price_hi,
        barrier_center,
        barrier_scale,
        mid_anchor_weight,
        var_swap,
        prior_anchor,
        prior_var_swap,
        operator_prior,
        opt_n_points,
    )
    return args, use_analytic


def calibrate_slice(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    n_order: int = 6,
    weights: np.ndarray | None = None,
    reg_lambda: float = 0.0,
    reg_power: float = 1.0,
    init: LQDParams | None = None,
    calendar_z: np.ndarray | None = None,
    calendar_floor: np.ndarray | None = None,
    calendar_weight: float = 1e6,
    calendar_k: np.ndarray | None = None,
    calendar_price_floor: np.ndarray | None = None,
    calendar_taper: np.ndarray | None = None,
    band: BandTarget | None = None,
    barrier_center: float = _BARRIER_CENTER,
    barrier_scale: float = _BARRIER_SCALE,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
    var_swap: VarSwapTarget | None = None,
    prior_anchor: PriorAnchorTarget | None = None,
    prior_var_swap: VarSwapTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
    opt_n_points: int = OPT_N_POINTS,
    solver_diag: dict | None = None,
    coords: str = "lr",
) -> CalibrationResult:
    """Fit one LQD slice to total-variance quotes (k_i, w_i) at expiry ``t``.

    ``reg_lambda``/``reg_power`` implement the high-order damping
    lam * n^{2r} a_n^2; the first Legendre mode a_2..a_3 is left free.

    ``calendar_z``/``calendar_floor`` (volfit.calib.calendar.
    calendar_floor_targets) make this slice respect the full-grid convex
    order G(alpha) >= floor against the previous expiry; the quadratic slack
    weight ``calendar_weight`` follows eq. (slack_calendar). The floor is
    enforced at the constraint z-values, so it is exact regardless of the
    optimization grid resolution.

    ``calendar_k``/``calendar_price_floor``/``calendar_taper``
    (volfit.calib.calendar.confined_calendar_floor) are the SUPPORT-CONFINED
    alternative: normalized-call ordering C(k) >= floor on the common quote
    support of the two expiries, with the taper fading the rows beyond it —
    the production surface path, immune to the phantom-calendar tail drag.
    Both blocks share ``calendar_weight``; either may be None independently.

    ``opt_n_points`` is the quadrature grid used during optimization (default
    OPT_N_POINTS = 2001); the accepted slice is rebuilt at the full N_POINTS for
    the returned result and all diagnostics.

    ``band`` switches the data term to the bid-ask / haircut band objective
    (volfit.calib.band); the band's vol edges become call-price edges so the
    vega-normalized residual stays comparable to the mid fit. None keeps the mid.

    ``barrier_center``/``barrier_scale`` shape the A_R soft barrier (eq.
    right_admissible) and ``mid_anchor_weight`` the band's mid anchor — all
    FitSettings coefficients, defaulting to the historical constants.

    ``var_swap`` (volfit.calib.varswap) adds a single soft penalty pulling the
    slice's fair var-swap toward a quoted level; None (the default) leaves the
    objective byte-identical.

    ``prior_anchor`` (volfit.calib.prior) adds vega-normalized residuals pulling
    the fit toward a (transported) prior at delta-locations, weighted by the
    data-gap precision (the strike-gap prior mode); ``prior_var_swap`` adds the
    prior's var-swap level as a companion total-variance moment. ``operator_prior``
    (volfit.calib.operators) adds the quote-operator prior block (ATM/RR/BF) for
    the operator / hybrid prior modes. All None (the default) leave the objective
    byte-identical.

    ``solver_diag`` (Note 15 Phase 2): a caller-owned dict filled with the
    solver's solution-point Jacobian / residual / theta and the fit-block row
    count, so the observation filter can form the information matrix J^T W J
    without a second fit (weights/vega scaling are already folded into the
    rows). Pure side-channel; None (the default) is byte-identical. Always
    recorded in the (L, R, a) coordinates regardless of ``coords``.

    ``coords`` selects the optimization chart (volfit.models.lqd.charts):
    "lr" (historical, the raw (L, R, a) vector — the library-level
    byte-identical default), "endpoint" (Phase 5: (log A_L, log A_R, a),
    body modes endpoint-neutral so acute central convexity no longer
    mechanically drags the asymptotic wings during the solve) or "logistic"
    (the endpoint chart with A_R = expit(rho): the admissibility wall
    A_R < 1 is unreachable, every chart point is admissible — the
    production API default). Same family and same objective in all three,
    so the optimum is chart-independent to solver tolerance.
    """
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    sigma = np.sqrt(w_quotes / t)

    # Analytic Jacobian (ROADMAP perf #2) for the var-swap/prior-free residual
    # configuration (mid or band fit + reg + calendar + barrier) — one quadrature
    # pass instead of trf's (P+1) finite-difference rebuilds; the frozen
    # argument tuple is shared with the joint symmetric solver.
    args, use_analytic = prepare_residual_args(
        k, w_quotes, t, n_order=n_order, weights=weights,
        reg_lambda=reg_lambda, reg_power=reg_power,
        calendar_z=calendar_z, calendar_floor=calendar_floor,
        calendar_weight=calendar_weight, calendar_k=calendar_k,
        calendar_price_floor=calendar_price_floor, calendar_taper=calendar_taper,
        band=band, barrier_center=barrier_center, barrier_scale=barrier_scale,
        mid_anchor_weight=mid_anchor_weight, var_swap=var_swap,
        prior_anchor=prior_anchor, prior_var_swap=prior_var_swap,
        operator_prior=operator_prior, opt_n_points=opt_n_points,
    )

    if init is None:
        w0_guess = float(np.interp(0.0, k, w_quotes))
        init = logistic_init(w0_guess, n_order=n_order)

    chart = build_chart(n_order, coords)
    fun, jac_fn, x0 = _residuals, residual_jacobian, init.to_vector()
    if chart is not None:

        def fun(x, *a, _c=chart):  # noqa: E306 — chart wrapper, theta = c(x)
            return _residuals(_c.to_theta(x), *a)

        def jac_fn(x, *a, _c=chart):  # chain rule: J_x = J_theta dtheta/dx
            return residual_jacobian(_c.to_theta(x), *a) @ _c.dtheta_dx(x)

        x0 = chart.from_theta(init.to_vector())

    result = least_squares(
        fun,
        x0,
        jac=jac_fn if use_analytic else "2-point",
        args=args,
        method="trf",
        # 1e-10 is still ~6 orders below the ~5 vol-bp fit budget (the note's own
        # fit reaches ~1.2 bp), so the optimum is unchanged to display precision —
        # but it stops trf from grinding extra (P+1)-eval Jacobian iterations
        # chasing a 1e-15 reduction that is invisible in the priced surface.
        xtol=1e-10,
        ftol=1e-10,
        gtol=1e-10,
        max_nfev=4000,
    )

    # Chart solve: map the solution (and its Jacobian) back to the canonical
    # (L, R, a) coordinates every consumer speaks.
    x_star = np.asarray(result.x, dtype=float)
    jac_star = np.asarray(result.jac, dtype=float)
    theta_star = x_star
    if chart is not None:
        theta_star = chart.to_theta(x_star)
        jac_star = chart.pull_jacobian(jac_star, x_star)

    if solver_diag is not None:
        solver_diag.update(
            jac=jac_star,
            residual=np.asarray(result.fun, dtype=float),
            theta=theta_star.copy(),
            n_fit_rows=int(k.size if band is None else 2 * k.size),
            n_quotes=int(k.size),
        )

    params = LQDParams.from_vector(theta_star)
    slice_ = build_slice(params)
    iv_model = np.sqrt(slice_.implied_w(k) / t)
    max_iv_error = float(np.nanmax(np.abs(iv_model - sigma)))

    return CalibrationResult(
        params=params,
        slice=slice_,
        cost=float(result.cost),
        n_evaluations=int(result.nfev),
        success=bool(result.success),
        max_iv_error=max_iv_error,
    )

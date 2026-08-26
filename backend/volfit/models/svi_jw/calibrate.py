"""One-expiry raw-SVI calibration (Gatheral parametrization).

Fits the raw SVI total-variance slice

    w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + sigma^2))

to total-variance quotes by Levenberg-Marquardt least squares. Residuals are
in implied-volatility units (the natural quoting scale), optionally
vega-weighted. The five parameters are reparametrized so the unconstrained
solver always proposes an admissible slice:

    b = softplus(theta_b) >= 0,   rho = tanh(theta_rho) in (-1, 1),
    sigma = exp(theta_sigma) > 0, a and m free.

Two soft no-arbitrage penalties keep the optimizer inside the feasible cone
without ever distorting a clean fit (both are exactly zero on an admissible
slice, e.g. the SPX benchmark of Docs/lqd_model_note.tex section 8):

  * non-negative minimum variance  a + b sigma sqrt(1 - rho^2) >= 0;
  * Lee wing bound  b (1 + |rho|) <= 2 - eps  (the asymptotic total-variance
    slope must stay STRICTLY under Lee's moment bound of 2 — the boundary
    itself admits negative tail density; see _LEE_SLOPE_MAX).

The data-driven initializer reads the smile bottom (argmin of w) for m and a,
and the two wing slopes for b and rho, so a single LM pass converges on
liquid smiles. See models/svi_jw/svi.py for RawSVI and the JW conversion.
"""

from __future__ import annotations

from dataclasses import dataclass

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
from volfit.calib.rms import max_quote_error
from volfit.calib.extrap import ExtrapTarget, extrap_residuals
from volfit.calib.operators import OperatorPriorTarget, operator_residuals
from volfit.calib.prior import PriorAnchorTarget, prior_anchor_residuals
from volfit.calib.varswap import VarSwapTarget, varswap_residual
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.svi_jw.jacobian import (
    svi_residual_jacobian,
    svi_residual_jacobian_structural,
)
from volfit.models.svi_jw.structural import pack_structural, unpack_structural
from volfit.models.svi_jw.svi import RawSVI, durrleman_g_raw

#: Soft-penalty weight for the two no-arbitrage constraints. Large enough to
#: dominate a violated constraint, small in vol^2 units so an admissible fit
#: (penalty == 0) is untouched.
_PENALTY = 1e3
#: Lee's bound is beta <= 2, but the boundary itself is NOT safe (committee
#: revision R1, 2026-07-24): at beta = 2 the tail limit of Durrleman's g is
#: (4 - beta^2)/16 = 0 and the sign is decided at the next order,
#: g ~ (alpha - 2)/(4k) with alpha = a - 2m — e.g. (a,b,rho,m,s) =
#: (0.04, 2, 0, 0, 0.2) passes BOTH screens with zero penalty yet has
#: g(10) = -0.0485 (negative tail density). The default cap is therefore
#: strictly buffered. The buffer costs nothing economically: at 1.95 the
#: excluded laws have moment budget p* = (2-beta)^2/(8 beta) < 2e-4 beyond
#: the first moment, and beta < cap restores "g eventually positive".
LEE_SLOPE_BUFFER = 0.05
_LEE_SLOPE_MAX = 2.0 - LEE_SLOPE_BUFFER
#: Belly-repair hinge (committee R2/R3 rider): rows penalty_weight *
#: max(-g + margin, 0) on a grid over the traded range — zero on a certified
#: slice, and the margin pushes a repaired dip slightly PAST zero so the
#: certificate's own numerical tolerance passes cleanly.
_BELLY_MARGIN = 2e-4


@dataclass(frozen=True)
class SVICalibration:
    """Fitted raw-SVI slice plus convergence/fit diagnostics."""

    raw: RawSVI
    cost: float
    n_evaluations: int
    success: bool
    max_iv_error: float  # max |model - quote| implied vol over the quotes


def _softplus(x: float) -> float:
    """Numerically stable softplus, log(1 + e^x)."""
    return float(np.logaddexp(0.0, x))


def _unpack(theta: np.ndarray) -> RawSVI:
    """Map the unconstrained vector to an admissible RawSVI."""
    return RawSVI(
        a=float(theta[0]),
        b=_softplus(float(theta[1])),
        rho=float(np.tanh(theta[2])),
        m=float(theta[3]),
        sigma=float(np.exp(theta[4])),
    )


def _init_theta(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Data-driven start: smile bottom for (a, m), wing slopes for (b, rho)."""
    order = np.argsort(k)
    k_s, w_s = k[order], w[order]
    i_min = int(np.argmin(w_s))
    m0 = float(k_s[i_min])
    w_min = float(w_s[i_min])

    # Asymptotic wing slopes: right -> b(1 + rho), |left| -> b(1 - rho).
    mid = len(k_s) // 2
    right = (w_s[-1] - w_s[mid]) / max(k_s[-1] - k_s[mid], 1e-3)
    left = (w_s[mid] - w_s[0]) / max(k_s[mid] - k_s[0], 1e-3)
    slope_r = max(right, 1e-3)
    slope_l = max(-left, 1e-3)  # left wing of w descends as k rises toward mid
    b0 = max(0.5 * (slope_r + slope_l), 1e-3)
    rho0 = float(np.clip((slope_r - slope_l) / (slope_r + slope_l), -0.99, 0.99))
    sigma0 = max(0.1 * (k_s[-1] - k_s[0]), 1e-2)
    a0 = max(w_min - b0 * sigma0 * np.sqrt(1.0 - rho0 * rho0), 1e-6)

    # Invert the reparametrization for b (softplus) and sigma (exp); atanh(rho).
    theta_b = float(np.log(np.expm1(b0))) if b0 > 1e-6 else -6.0
    return np.array([a0, theta_b, float(np.arctanh(rho0)), m0, float(np.log(sigma0))])


def _penalties(raw: RawSVI, penalty_weight: float, lee_slope_max: float) -> np.ndarray:
    """Soft no-arbitrage residuals (zero on an admissible slice)."""
    min_var = raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho * raw.rho)
    wing = raw.b * (1.0 + abs(raw.rho))
    return penalty_weight * np.array(
        [
            max(-min_var, 0.0),  # minimum total variance must be >= 0
            max(wing - lee_slope_max, 0.0),  # Lee wing-slope bound
        ]
    )


def calibrate_svi(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    weights: np.ndarray | None = None,
    band: BandTarget | None = None,
    penalty_weight: float = _PENALTY,
    lee_slope_max: float = _LEE_SLOPE_MAX,
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
    extrap: "ExtrapTarget | None" = None,
    solver_diag: dict | None = None,
    chart: str = "raw",
    belly_grid: np.ndarray | None = None,
    mid_anchor_tau_ref: float | None = None,
    robust_loss: str = "off",
    robust_f_scale: float = 0.005,
    price_residuals: bool = False,
) -> SVICalibration:
    """Least-squares fit of a raw-SVI slice to total-variance quotes.

    ``k``/``w_quotes`` are log-moneyness and total implied variance; ``t`` the
    expiry year fraction (only the vol/vega scaling depends on it). ``weights``
    are per-quote LSQ weights (defaults to unit); they multiply the squared
    vol residual, so pass vega^2 or liquidity weights to emphasise quotes.
    ``band`` switches the data term to the bid-ask / haircut band objective
    (volfit.calib.band) evaluated in vol space; None keeps the mid LSQ.

    ``penalty_weight`` / ``lee_slope_max`` are the soft no-arbitrage coefficients
    (FitSettings); ``mid_anchor_weight`` the band's mid anchor. All default to
    the historical constants, so a default fit is byte-identical. ``var_swap``
    (volfit.calib.varswap) adds one vol-space penalty pulling the slice's fair
    var-swap toward a quote; None keeps the objective unchanged.

    ``calendar_k``/``calendar_floor`` (from volfit.calib.calendar.variance_floor_targets)
    add the model-agnostic calendar constraint against the previous, shorter
    expiry: a soft hinge ``sqrt(calendar_weight)*max(floor - w(k), 0)`` keeping
    this slice's total variance at or above the nearer one (no calendar arb).
    Both None (the default) leave the objective byte-identical.

    ``calendar_k_ceil``/``calendar_ceiling`` are the SYMMETRIC counterpart
    (the symmetric-surface overlay repair): a ceiling from the NEXT, longer
    expiry's displayed slice, ``sqrt(calendar_weight)*max(w(k) - ceiling, 0)``,
    so a violating pair splits the correction instead of pushing it all into
    the far fit. Both None (the default) leave the objective byte-identical.

    ``prior_anchor`` (volfit.calib.prior, the strike-gap mode) and
    ``operator_prior`` (volfit.calib.operators, the operator / hybrid modes) add
    the prior-persistence residual blocks — the same semantics LQD receives, so
    the SVI display overlay is no longer an exception (roadmap Phase 3). Both None
    (the default) leave the objective byte-identical.

    ``extrap`` (volfit.calib.extrap, Notes 09/10 Phase 2) adds the tapered
    extrapolated-region blocks: a Durrleman-g butterfly hinge on the slice's
    own envelope, the tapered calendar hinge against the previous displayed
    slice, and the scalar wing-slope-order hinge (analytic slopes b(1∓ρ)).
    All rows are zero on an admissible fit; None (the default) is
    byte-identical. The extrap rows are FD-differentiated (a small hybrid
    block, like the MCS wing penalty), so the analytic Jacobian is kept.

    ``solver_diag`` (Note 15 Phase 2): a caller-owned dict filled with the
    solver's solution-point Jacobian / residual / theta and the fit-block row
    count, for the observation filter's information matrix J^T W J. Pure
    side-channel; None (the default) is byte-identical.

    ``chart`` (committee R3): "raw" = the historical (a, softplus b, tanh rho,
    m, log s) vector (default, byte-identical); "structural" = the
    (β_L, β_R, k*, w*, κ*) chart of models/svi_jw/structural.py — every finite
    iterate is strictly positive-floor and strictly Lee-clean, so the two
    penalty rows are structurally zero and the trial-w clip never fires. Both
    charts run the ANALYTIC Jacobian under the same gate (the structural
    chain matrix is closed-form since the adoption follow-up, 2026-07-26).

    ``belly_grid`` (committee R2 repair rider): a k-grid over the traded range
    adding the belly butterfly hinge ``penalty_weight * max(-g + margin, 0)``
    per point (closed-form g). Zero rows on a certified slice; the display
    path passes it only on a REPAIR refit after a failed certificate, so a
    clean first fit stays byte-identical.

    Short-dated objective knobs (all defaults byte-identical):
    ``mid_anchor_tau_ref`` attenuates the band's mid anchor by
    min(1, sqrt(t / tau_ref)) (calib.band.effective_mid_anchor; None = the
    constant anchor). ``robust_loss``/``robust_f_scale`` run two IRLS passes
    over the QUOTE rows only — scipy's global ``loss=`` would also soften
    the no-arb penalty / calendar / prior rows, which must stay quadratic —
    re-solving warm-started with sqrt of the huber/cauchy multipliers folded
    into the data weights (calib.band.robust_multipliers; the multipliers
    are solver-internal — user-facing weights stay the scheme weights).
    ``price_residuals`` (FitSettings.overlayPriceResiduals) switches the
    data rows to the LQD convention: vega-normalized PRICE residuals with
    1/vega frozen at the mid vol and the band edges converted to call
    prices (calib.band.price_targets); the analytic Jacobian follows via
    the row-wise chain factor dC/dw (black_vega_w). The IRLS residual
    definition follows the active space, and the anchor attenuation applies
    in either space.
    """
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    vol_quotes = np.sqrt(w_quotes / t)
    sqrt_weights = np.ones_like(k) if weights is None else np.sqrt(np.asarray(weights, float))
    # Effective (tau-attenuated) mid anchor; sq_w is the MUTABLE data-row
    # weight the IRLS passes rescale (sqrt_weights itself stays the frozen
    # scheme weight — the extrap block's mean-weight reads it).
    maw_eff = effective_mid_anchor(mid_anchor_weight, t, mid_anchor_tau_ref)
    sq_w = sqrt_weights
    # Price-residual mode (the LQD convention): quote prices / vega
    # normalizers / price band edges frozen at the mid vols.
    pt = price_targets(k, w_quotes, t, band) if price_residuals else None
    target_price = inv_vega = price_lo = price_hi = None
    if pt is not None:
        target_price, inv_vega, price_lo, price_hi = pt
    # Chart selection (R3): the structural chart honors the SAME configured
    # cap — its wings live strictly inside (0, lee_slope_max) by the lift.
    unpack = (
        _unpack if chart == "raw"
        else (lambda th: unpack_structural(th, lee_slope_max))
    )
    belly_k = (
        np.asarray(belly_grid, dtype=float)
        if belly_grid is not None and np.asarray(belly_grid).size
        else None
    )
    cal_on = calendar_k is not None and calendar_floor is not None
    cal_k = np.asarray(calendar_k, float) if cal_on else None
    cal_floor = np.asarray(calendar_floor, float) if cal_on else None
    ceil_on = calendar_k_ceil is not None and calendar_ceiling is not None
    ceil_k = np.asarray(calendar_k_ceil, float) if ceil_on else None
    ceil_w = np.asarray(calendar_ceiling, float) if ceil_on else None
    sqrt_cal = np.sqrt(calendar_weight)

    def residuals(theta: np.ndarray) -> np.ndarray:
        raw = unpack(theta)
        if pt is not None:
            # Price-residual mode: sqrt_w * inv_vega * (C(k, w_model) - C_mid),
            # band hinge on the call-price band edges (same monotone space).
            model_price = black_call(k, np.maximum(raw.total_variance(k), 1e-12))
            if band is None:
                fit = sq_w * inv_vega * (model_price - target_price)
            else:
                fit = band_residuals(
                    model_price, price_lo, price_hi, target_price,
                    sq_w * inv_vega, maw_eff,
                )
        else:
            model_vol = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / t)
            if band is None:
                fit = sq_w * (model_vol - vol_quotes)
            else:
                fit = band_residuals(
                    model_vol, band.iv_lo, band.iv_hi, band.iv_mid, sq_w, maw_eff
                )
        res = np.concatenate((fit, _penalties(raw, penalty_weight, lee_slope_max)))
        if belly_k is not None:
            # Belly-repair hinge (R2 rider): zero on a certified slice.
            g = durrleman_g_raw(raw, belly_k)
            res = np.concatenate(
                (res, penalty_weight * np.maximum(-g + _BELLY_MARGIN, 0.0))
            )
        if var_swap is not None:
            res = np.concatenate((res, [varswap_residual(raw.total_variance, var_swap)]))
        if prior_var_swap is not None:
            # Prior's var-swap companion (operator/strike-gap). varswap_residual
            # honors the target's carrier mode (absolute level or ATM spread);
            # this block rides the FD Jacobian path (use_analytic gates it off).
            res = np.concatenate((res, [varswap_residual(raw.total_variance, prior_var_swap)]))
        if cal_on:
            # No calendar arb: total variance must not drop below the nearer expiry.
            cal = sqrt_cal * np.maximum(cal_floor - raw.total_variance(cal_k), 0.0)
            res = np.concatenate((res, cal))
        if ceil_on:
            # Symmetric counterpart: must not rise above the LONGER expiry.
            ceil = sqrt_cal * np.maximum(raw.total_variance(ceil_k) - ceil_w, 0.0)
            res = np.concatenate((res, ceil))
        if prior_anchor is not None:
            # Strike-gap prior: vega-normalized pull toward the prior's call prices.
            cp = black_call(prior_anchor.k, np.maximum(raw.total_variance(prior_anchor.k), 1e-12))
            res = np.concatenate((res, prior_anchor_residuals(cp, prior_anchor)))
        if operator_prior is not None:
            # Quote-operator prior (ATM/RR/BF) toward the prior's operators.
            res = np.concatenate((res, operator_residuals(raw.total_variance, operator_prior)))
        if extrap is not None:
            res = np.concatenate((res, _extrap_rows(raw)))
        return res

    def _extrap_rows(raw: RawSVI) -> np.ndarray:
        """Tapered extrapolated-region rows (LAST in the residual vector)."""
        return extrap_residuals(
            raw.total_variance, extrap, t,
            mean_weight=float(np.mean(sqrt_weights**2)),
            # SVI's asymptotic total-variance slopes are exact: b(1 -/+ rho).
            lee_fn=lambda: (raw.b * (1.0 - raw.rho), raw.b * (1.0 + raw.rho)),
        )

    def _extrap_fd_jac(theta: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """Central FD of the extrap rows only — the hybrid-Jacobian pattern of
        the MCS wing penalty: the dominant blocks stay analytic."""
        base = _extrap_rows(unpack(theta))
        jw = np.empty((base.size, theta.size))
        for p in range(theta.size):
            d = np.zeros_like(theta)
            d[p] = eps
            jw[:, p] = (
                _extrap_rows(unpack(theta + d)) - _extrap_rows(unpack(theta - d))
            ) / (2.0 * eps)
        return jw

    theta0 = _init_theta(k, w_quotes)
    if chart != "raw":  # same data-driven start, expressed in the new chart
        theta0 = pack_structural(_unpack(theta0), lee_slope_max)
    # Committee R5 (adversarial battery): LM needs at least as many residual
    # rows as parameters — a 1-2 quote board would crash inside scipy with an
    # opaque message. Refuse DETERMINISTICALLY with a reason instead (the
    # caller's fallback policy: keep the last good surface / another family).
    if residuals(theta0).size < 5:
        raise ValueError(
            f"SVI needs at least 3 usable quotes (got {k.size}): "
            "5 parameters against fewer residual rows is unsolvable"
        )
    # Analytic Jacobian (R4; structural chain added as the R3 adoption follow-up)
    # for the var-swap/prior-free configuration (mid OR band fit + penalties +
    # calendar) — ~2 evals/step vs scipy's 1+P finite differences. The var-swap /
    # strike-gap / operator-prior blocks are not yet differentiated, so those fits
    # keep the finite-difference LM path (correct, just not accelerated), exactly
    # as LQD gates its analytic Jacobian. The belly-repair hinge (R2 rider, repair
    # refits only) also takes the FD path for now.
    use_analytic = (
        var_swap is None
        and prior_anchor is None
        and prior_var_swap is None
        and operator_prior is None
        and chart in ("raw", "structural")
        and belly_k is None
    )
    if use_analytic:
        jac_fn = (
            svi_residual_jacobian if chart == "raw" else svi_residual_jacobian_structural
        )

        def jac(theta: np.ndarray) -> np.ndarray:
            j = jac_fn(
                theta, k, t, sq_w, band, maw_eff,
                penalty_weight, lee_slope_max, cal_k, cal_floor, sqrt_cal,
                ceil_k, ceil_w, price_targets=pt,
            )
            if extrap is not None:  # hybrid: FD only the small extrap block
                j = np.vstack([j, _extrap_fd_jac(theta)])
            return j

    def _run(theta_start: np.ndarray):
        # Keep the SAME LM optimizer + tolerance — only swap the Jacobian from scipy's
        # 1+P finite differences to the closed form. LM (not trf) is deliberate: on
        # noisy real chains LM converges in far fewer iterations than trf through the
        # penalty kinks, so a same-convergence drop-in is ~2.6x with results unchanged
        # to fit precision (trf at 1e-10 was measured SLOWER on real nodes).
        if use_analytic:
            return least_squares(
                residuals, theta_start, jac=jac, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15
            )
        return least_squares(residuals, theta_start, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15)

    result = _run(theta0)

    # IRLS robust passes over the quote rows only (see the docstring): the
    # multipliers follow the ACTIVE residual space; "off" never enters here.
    if robust_loss != "off" and k.size:
        for _ in range(2):
            raw_i = unpack(result.x)
            if pt is not None:
                model = black_call(k, np.maximum(raw_i.total_variance(k), 1e-12))
                r = quote_residual_magnitude(
                    model, target_price, price_lo, price_hi, maw_eff, inv_vega
                )
            else:
                model = np.sqrt(np.maximum(raw_i.total_variance(k), 1e-12) / t)
                if band is None:
                    r = quote_residual_magnitude(model, vol_quotes, None, None, maw_eff)
                else:
                    r = quote_residual_magnitude(
                        model, band.iv_mid, band.iv_lo, band.iv_hi, maw_eff
                    )
            sq_w = sqrt_weights * np.sqrt(
                robust_multipliers(r, robust_loss, robust_f_scale)
            )
            result = _run(result.x)
    if solver_diag is not None:
        solver_diag.update(
            jac=np.asarray(result.jac, dtype=float),
            residual=np.asarray(result.fun, dtype=float),
            theta=np.asarray(result.x, dtype=float).copy(),
            n_fit_rows=int(k.size if band is None else 2 * k.size),
            n_quotes=int(k.size),
        )
    raw = unpack(result.x)

    model_vol = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / t)
    max_iv_error = max_quote_error(model_vol, vol_quotes, band)  # vs the fit target
    return SVICalibration(
        raw=raw,
        cost=float(result.cost),
        n_evaluations=int(result.nfev),
        success=bool(result.success),
        max_iv_error=max_iv_error,
    )


def _vega_weights(k: np.ndarray, w_quotes: np.ndarray, t: float) -> np.ndarray:
    """Black vega^2 weights at the quote vols (vega-normalized fit option)."""
    vol = np.sqrt(np.asarray(w_quotes, float) / t)
    vega = black_vega_sigma(np.asarray(k, float), vol, t)
    return vega * vega

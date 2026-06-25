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
  * Lee wing bound  b (1 + |rho|) <= 2  (the asymptotic total-variance slope
    cannot exceed Lee's moment bound of 2).

The data-driven initializer reads the smile bottom (argmin of w) for m and a,
and the two wing slopes for b and rho, so a single LM pass converges on
liquid smiles. See models/svi_jw/svi.py for RawSVI and the JW conversion.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import MID_ANCHOR_WEIGHT, BandTarget, band_residuals
from volfit.calib.operators import OperatorPriorTarget, operator_residuals
from volfit.calib.prior import PriorAnchorTarget, prior_anchor_residuals
from volfit.calib.varswap import VarSwapTarget, varswap_residual
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.svi_jw.svi import RawSVI

#: Soft-penalty weight for the two no-arbitrage constraints. Large enough to
#: dominate a violated constraint, small in vol^2 units so an admissible fit
#: (penalty == 0) is untouched.
_PENALTY = 1e3
#: Lee's asymptotic total-variance wing-slope bound: w(k)/|k| -> beta <= 2.
_LEE_SLOPE_MAX = 2.0


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
    prior_anchor: PriorAnchorTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
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

    ``prior_anchor`` (volfit.calib.prior, the strike-gap mode) and
    ``operator_prior`` (volfit.calib.operators, the operator / hybrid modes) add
    the prior-persistence residual blocks — the same semantics LQD receives, so
    the SVI display overlay is no longer an exception (roadmap Phase 3). Both None
    (the default) leave the objective byte-identical.
    """
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    vol_quotes = np.sqrt(w_quotes / t)
    sqrt_weights = np.ones_like(k) if weights is None else np.sqrt(np.asarray(weights, float))
    cal_on = calendar_k is not None and calendar_floor is not None
    cal_k = np.asarray(calendar_k, float) if cal_on else None
    cal_floor = np.asarray(calendar_floor, float) if cal_on else None
    sqrt_cal = np.sqrt(calendar_weight)

    def residuals(theta: np.ndarray) -> np.ndarray:
        raw = _unpack(theta)
        model_vol = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / t)
        if band is None:
            fit = sqrt_weights * (model_vol - vol_quotes)
        else:
            fit = band_residuals(
                model_vol, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_weights, mid_anchor_weight
            )
        res = np.concatenate((fit, _penalties(raw, penalty_weight, lee_slope_max)))
        if var_swap is not None:
            res = np.concatenate((res, [varswap_residual(raw.total_variance, var_swap)]))
        if cal_on:
            # No calendar arb: total variance must not drop below the nearer expiry.
            cal = sqrt_cal * np.maximum(cal_floor - raw.total_variance(cal_k), 0.0)
            res = np.concatenate((res, cal))
        if prior_anchor is not None:
            # Strike-gap prior: vega-normalized pull toward the prior's call prices.
            cp = black_call(prior_anchor.k, np.maximum(raw.total_variance(prior_anchor.k), 1e-12))
            res = np.concatenate((res, prior_anchor_residuals(cp, prior_anchor)))
        if operator_prior is not None:
            # Quote-operator prior (ATM/RR/BF) toward the prior's operators.
            res = np.concatenate((res, operator_residuals(raw.total_variance, operator_prior)))
        return res

    theta0 = _init_theta(k, w_quotes)
    result = least_squares(residuals, theta0, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15)
    raw = _unpack(result.x)

    model_vol = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / t)
    max_iv_error = float(np.max(np.abs(model_vol - vol_quotes))) if k.size else 0.0
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

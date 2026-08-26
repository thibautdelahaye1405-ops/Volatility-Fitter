"""Bid-ask band fitting objective (fit-to-bid-ask and fit-to-haircut modes).

The default "mid" mode penalizes |mid - model| only. The band modes instead
penalize the model leaving the quoted band and only *gently* anchor it to mid:

    loss_i = max(model_i - hi_i, 0)^2 + max(lo_i - model_i, 0)^2
             + MID_ANCHOR_WEIGHT * (model_i - mid_i)^2,

so the fit is free to sit anywhere inside [lo, hi] (no penalty), is pulled back
hard once it leaves the band, and is softly centred on mid. "bidask" uses the
raw band (lo, hi) = (bid, ask); "haircut" tightens each side toward mid by
``haircut`` volatility points, clamped never to cross mid (eq below):

    modified_bid = min(bid + haircut, mid),
    modified_ask = max(mid, ask - haircut).

The hinge is monotone in the quote value, so the same construction works in any
monotone space: implied vol (SVI, Sigmoid) or vega-normalized option price
(LQD, LV) where price ~ vol error after vega scaling. The band itself is always
specified in vol space (vols, vol-point haircut) and converted to the model's
native space by the caller; ``band_residuals`` is space-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.core.black import black_call, black_vega_sigma

#: Weight of the soft |mid - model| anchor relative to the band penalty (= 1).
#: Small, so the band dominates but the curve still centres on mid in-band.
MID_ANCHOR_WEIGHT = 0.05

#: Default haircut in absolute vol (0.5 volatility points), tunable per fit.
DEFAULT_HAIRCUT = 0.005

#: Vega floor for the tick-floor IV conversion (mirror of the LQD price
#: objective's ``models.lqd.calibrate._VEGA_FLOOR``): below it a deep-wing
#: quote's IV-per-tick diverges, so the conversion saturates instead.
TICK_VEGA_FLOOR = 1e-4


@dataclass(frozen=True)
class BandTarget:
    """Resolved per-quote vol band for the band fit modes (aligned to k).

    ``iv_lo``/``iv_hi`` are the (haircut-adjusted) band edges; ``iv_mid`` is the
    anchor. Empty / None is used by callers to signal the plain "mid" mode.
    """

    iv_lo: np.ndarray
    iv_mid: np.ndarray
    iv_hi: np.ndarray


def resolve_band(
    iv_bid: np.ndarray,
    iv_mid: np.ndarray,
    iv_ask: np.ndarray,
    fit_mode: str,
    haircut: float = DEFAULT_HAIRCUT,
) -> BandTarget | None:
    """Build the band target for a fit mode, or None for plain "mid".

    For "haircut" each side is moved ``haircut`` vol points toward mid but never
    past it, so a quote tighter than 2*haircut collapses to (mid, mid) and the
    band fit degenerates gracefully to a mid fit on that strike.
    """
    if fit_mode == "mid":
        return None
    iv_bid = np.asarray(iv_bid, dtype=float)
    iv_mid = np.asarray(iv_mid, dtype=float)
    iv_ask = np.asarray(iv_ask, dtype=float)
    if fit_mode == "haircut":
        lo = np.minimum(iv_bid + haircut, iv_mid)
        hi = np.maximum(iv_mid, iv_ask - haircut)
    else:  # "bidask"
        lo, hi = iv_bid, iv_ask
    return BandTarget(iv_lo=lo, iv_mid=iv_mid, iv_hi=hi)


def apply_tick_floor(
    band: BandTarget | None,
    k: np.ndarray,
    tau: float,
    tick_norm: float | None,
    ticks: float,
) -> BandTarget | None:
    """Floor each quote's band half-width about its MID at ``ticks`` price
    ticks of IV (FitSettings.bandTickFloorTicks) — only ever WIDENING.

    A short-dated wing quote whose bid-ask prints below the price tick grid
    claims sub-tick IV certainty the market never quoted: one tick in
    normalized price is ``tick_norm`` = tick_size / (discount * forward), and
    its IV width at the quote's own (vega-floored) Black vega is
    ``tick_norm / max(vega, TICK_VEGA_FLOOR)``. Each side is pushed to at
    least half the ``ticks``-tick width from mid, AFTER the haircut so the
    floor wins; a side already wider than the floor is untouched (the
    original bid/ask asymmetry survives). ``ticks`` <= 0 or a tickless chain
    (``tick_norm`` None — synthetic/IV-exact feeds) returns ``band``
    unchanged, byte-identical.
    """
    if band is None or ticks <= 0.0 or not tick_norm or tick_norm <= 0.0 or tau <= 0.0:
        return band
    vega = np.maximum(black_vega_sigma(np.asarray(k, dtype=float), band.iv_mid, tau), TICK_VEGA_FLOOR)
    h = ticks * (tick_norm / vega)  # the floored full band width, in vol
    return BandTarget(
        iv_lo=np.minimum(band.iv_lo, band.iv_mid - 0.5 * h),
        iv_mid=band.iv_mid,
        iv_hi=np.maximum(band.iv_hi, band.iv_mid + 0.5 * h),
    )


def effective_mid_anchor(weight: float, tau: float, tau_ref: float | None) -> float:
    """Tau-aware mid-anchor attenuation (FitSettings.midAnchorTauRef).

    The data rows of a slice objective blow up ~1/sqrt(tau) at short
    maturities while the shape regularization is tau-free, so a 1-week
    smile's tick-quantized mid staircase outguns the ridge many-fold. With a
    reference maturity ``tau_ref`` (years) set, the anchor weight becomes
    ``weight * min(1, sqrt(tau / tau_ref))`` — full strength at and beyond
    the reference, fading like sqrt(tau) below it, restoring a
    maturity-uniform anchor-vs-shape contest. ``tau_ref`` None returns
    ``weight`` UNTOUCHED (the historical constant path: no float arithmetic
    at all, byte-identity).
    """
    if tau_ref is None:
        return weight
    return float(weight) * min(1.0, float(np.sqrt(tau / tau_ref)))


def robust_multipliers(r: np.ndarray, loss: str, f_scale: float) -> np.ndarray:
    """IRLS weight multipliers m_i for the DATA rows (FitSettings.robustLoss).

    ``r`` are the per-quote data-residual magnitudes in the residual's own
    (~vol) units — see ``quote_residual_magnitude``; ``f_scale`` the robust
    scale below which a residual keeps full weight. huber: min(1,
    f/|r|) — the classical linear taper; cauchy: 1/(1 + (r/f)^2) — a harder
    redescending cut. Any other ``loss`` (i.e. "off") returns unit
    multipliers. Folding sqrt(m_i) into the data rows' sqrt-weights turns
    one weighted-LSQ re-solve into one IRLS step of the robust M-estimate.
    """
    r = np.abs(np.asarray(r, dtype=float))
    if loss == "huber":
        return np.minimum(1.0, f_scale / np.maximum(r, 1e-16))
    if loss == "cauchy":
        return 1.0 / (1.0 + (r / f_scale) ** 2)
    return np.ones_like(r)


def quote_residual_magnitude(
    model: np.ndarray,
    mid: np.ndarray,
    lo: np.ndarray | None,
    hi: np.ndarray | None,
    mid_anchor_weight: float,
    scale: np.ndarray | float = 1.0,
) -> np.ndarray:
    """Per-quote UNWEIGHTED data-residual magnitude, for the IRLS reweighting.

    Mid mode (``lo``/``hi`` None): ``scale * |model - mid|``. Band mode: the
    combined hinge+anchor magnitude ``scale * sqrt(violation^2 +
    mid_anchor_weight * (model - mid)^2)`` — the square root of the quote's
    per-point band loss, so an in-band quote contributes only its (small)
    anchor pull. All quantities live in the calibrator's ACTIVE residual
    space (vol, or vega-normalized price with ``scale`` = 1/vega). The
    SCHEME weights are deliberately excluded: FitSettings.robustFScale is
    specified in the residual's own units, not in weighted units.
    """
    model = np.asarray(model, dtype=float)
    mid = np.asarray(mid, dtype=float)
    if lo is None:
        return np.asarray(scale, dtype=float) * np.abs(model - mid)
    viol = band_violation(model, lo, hi)
    return np.asarray(scale, dtype=float) * np.sqrt(
        viol**2 + mid_anchor_weight * (model - mid) ** 2
    )


def price_targets(
    k: np.ndarray, w_quotes: np.ndarray, t: float, band: BandTarget | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Vega-normalized price-space fit targets — the LQD convention — for the
    SVI / MCS price-residual mode (FitSettings.overlayPriceResiduals).

    Mirrors ``models.lqd.calibrate.prepare_residual_args``: the quote's call
    price at its mid total variance, the 1/(vega + TICK_VEGA_FLOOR)
    normalizer FROZEN at the mid vol, and (band modes) the call-price band
    edges at the band-edge total variances. Returns ``(target_price,
    inv_vega, price_lo, price_hi)`` with the last two None in mid mode.
    """
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    target_price = black_call(k, w_quotes)
    sigma = np.sqrt(w_quotes / t)
    inv_vega = 1.0 / (black_vega_sigma(k, sigma, t) + TICK_VEGA_FLOOR)
    price_lo = price_hi = None
    if band is not None:
        price_lo = black_call(k, band.iv_lo**2 * t)
        price_hi = black_call(k, band.iv_hi**2 * t)
    return target_price, inv_vega, price_lo, price_hi


def band_violation(model: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Nonnegative distance of ``model`` outside the band [lo, hi].

    ``relu(model - hi) + relu(lo - model)``: at most one term is nonzero since
    lo <= hi, so its square equals the two-sided squared-hinge penalty. The
    subgradient w.r.t. model is ``sign(model - hi)_+ - sign(lo - model)_+`` =
    ``band_violation_sign`` (used for the LV analytic Jacobian).
    """
    return np.maximum(model - hi, 0.0) + np.maximum(lo - model, 0.0)


def band_violation_sign(model: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """d(band_violation)/d(model): +1 above the band, -1 below, 0 inside."""
    return np.where(model > hi, 1.0, 0.0) - np.where(model < lo, 1.0, 0.0)


def band_residuals(
    model: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    mid: np.ndarray,
    scale: np.ndarray | float = 1.0,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
) -> np.ndarray:
    """Stacked least-squares residuals for the band objective.

    Returns ``[scale * violation, sqrt(mid_anchor_weight) * scale * (model - mid)]``
    (length 2N for N quotes). ``scale`` is a per-quote multiplier in the model's
    residual space (unit vol weights, or 1/vega price normalization).
    ``mid_anchor_weight`` is the anchor strength relative to the band penalty
    (the FitSettings coefficient; defaults to the historical MID_ANCHOR_WEIGHT).
    Squaring and summing reproduces ``loss_i`` of the module docstring.
    """
    scale = np.asarray(scale, dtype=float)
    viol = scale * band_violation(model, lo, hi)
    anchor = np.sqrt(mid_anchor_weight) * scale * (model - mid)
    return np.concatenate([viol, anchor])

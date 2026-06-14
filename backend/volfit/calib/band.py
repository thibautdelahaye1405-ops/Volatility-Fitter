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

#: Weight of the soft |mid - model| anchor relative to the band penalty (= 1).
#: Small, so the band dominates but the curve still centres on mid in-band.
MID_ANCHOR_WEIGHT = 0.05

#: Default haircut in absolute vol (0.5 volatility points), tunable per fit.
DEFAULT_HAIRCUT = 0.005


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

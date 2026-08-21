"""Calibration-consistent goodness-of-fit: the weighted RMS implied-vol error.

The RMS error the viewers report mirrors what the calibrator actually minimizes
(ROADMAP RMS refinement), so the number means "how well does the displayed fit
meet its own objective":

  * **distance to the chosen fit target** — in "mid" mode the per-quote error is
    ``model - mid``; in the band modes it is the band VIOLATION
    ``max(model - hi, 0) + max(lo - model, 0)`` (zero inside [lo, hi]), with the
    haircut-tightened band for "haircut". This matches ``calib.band``;
  * **the active weighting scheme** (equal or time-value density) — the same
    per-quote weights the fit uses (``calib.weights``);
  * **the var-swap quote**, when one is active for the node: one extra term
    (model vs quoted var-swap vol) carrying the var-swap penalty weight.

Everything is in decimal vol. A node contributes ``(sum_weighted_sq, sum_weight)``
so the whole-surface number is just the pooled aggregate across its expiries.

``quote_errors`` is the ONE per-quote error vector behind every reported
goodness-of-fit number — the parametric ``max_iv_error`` (LQD / SVI / joint
stack / overlays), the Local-Vol surface ``rms / max / conv`` bp and the
model-compare columns all read it, so none of them silently scores the mid
when the user fits a band.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.band import BandTarget


def quote_errors(
    model_iv: np.ndarray, iv_mid: np.ndarray, band: BandTarget | None = None
) -> np.ndarray:
    """Per-quote vol error of a model against the FIT TARGET: the signed
    ``model - mid`` when ``band`` is None ("mid" mode), else the nonnegative
    band violation ``relu(model - hi) + relu(lo - model)`` (bid-ask / haircut
    band — zero inside). Arrays aligned to the fit inputs (k)."""
    model_iv = np.asarray(model_iv, dtype=float)
    if band is None:
        return model_iv - np.asarray(iv_mid, dtype=float)
    from volfit.calib.band import band_violation

    return band_violation(model_iv, band.iv_lo, band.iv_hi)


def max_quote_error(
    model_iv: np.ndarray, iv_mid: np.ndarray, band: BandTarget | None = None
) -> float:
    """``max |quote_errors|`` over the finite entries; 0 for no quotes."""
    err = np.abs(quote_errors(model_iv, iv_mid, band))
    err = err[np.isfinite(err)]
    return float(err.max()) if err.size else 0.0


def node_error_terms(
    model_iv: np.ndarray,
    iv_mid: np.ndarray,
    weights: np.ndarray | None = None,
    band: BandTarget | None = None,
    var_swap: tuple[float, float, float] | None = None,
) -> tuple[float, float]:
    """``(sum_i u_i e_i^2, sum_i u_i)`` for one node's fit-target vol error.

    ``e_i`` is ``model - mid`` (band None ⇒ "mid" mode) or the band violation
    (``band`` given ⇒ bid-ask / haircut). ``weights`` are the per-quote scheme
    weights (None ⇒ equal). ``var_swap = (model_vol, quote_vol, weight)`` adds the
    var-swap term at its penalty weight; None / weight 0 omits it. Returning the
    numerator + denominator lets the caller pool nodes into a surface RMS.
    """
    model_iv = np.asarray(model_iv, dtype=float)
    if model_iv.size:
        err = quote_errors(model_iv, iv_mid, band)
        u = np.ones_like(model_iv) if weights is None else np.asarray(weights, dtype=float)
        num = float(np.sum(u * err * err))
        den = float(np.sum(u))
    else:
        num = den = 0.0
    if var_swap is not None:
        model_vol, quote_vol, weight = var_swap
        if weight > 0.0:
            num += weight * (model_vol - quote_vol) ** 2
            den += weight
    return num, den


def rms(num: float, den: float) -> float:
    """``sqrt(num / den)`` (decimal vol), 0 when there is nothing to score."""
    return float(np.sqrt(num / den)) if den > 0.0 else 0.0

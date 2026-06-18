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
"""

from __future__ import annotations

import numpy as np

from volfit.calib.band import BandTarget


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
        if band is None:
            err = model_iv - np.asarray(iv_mid, dtype=float)
        else:
            from volfit.calib.band import band_violation

            err = band_violation(model_iv, band.iv_lo, band.iv_hi)
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

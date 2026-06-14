"""Model choice for the displayed slice fit (ROADMAP "Next up" #1).

The LQD engine is the API's analytic backbone: density, the graph universe,
local-vol extraction, term structure and prior densities all read the
exact LQD slice/parameters, so volfit.api.service.fit_or_get ALWAYS fits LQD.
When the hyperparameter panel selects another family (SVI-JW or sigmoid),
this module fits that family to the same prepared quotes and attaches the
result as a ``DisplayFit`` overlay on the FitRecord. The Smile Viewer's chart,
diagnostics, quote table, 3D surface and SSR scenario then read the overlay
(volfit.api.service.displayed_* helpers); every other endpoint keeps reading
the LQD fit unchanged, so model choice never destabilises the analytics.

Diagnostics for the overlay come from volfit.models.diagnostics (numeric ATM
handles, log-contract var-swap, Lee wing slopes) since only LQD has the
closed forms. SVI calibration is volfit.models.svi_jw.calibrate_svi; sigmoid
is volfit.models.sigmoid.calibrate_sigmoid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.calib.band import BandTarget
from volfit.calib.varswap import VarSwapTarget
from volfit.models.base import SmileModel
from volfit.models.diagnostics import (
    SliceHandles,
    numeric_handles,
    numeric_lee_slopes,
    numeric_var_swap_w,
)
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import calibrate_svi

#: Models fitted as a display overlay here (LQD is the dedicated default path).
OVERLAY_MODELS = ("svi", "sigmoid")


@dataclass(frozen=True)
class DisplayFit:
    """A non-LQD slice fit shown by the Smile Viewer, with numeric diagnostics.

    ``slice`` is any SmileModel (RawSVI or SigmoidSmile); the handles and
    var-swap are computed model-agnostically. ``lee_left``/``lee_right`` are
    the total-variance wing slopes; there is no A_L/A_R endpoint-scale concept
    outside LQD, so the smile payload reports those as 0 for an overlay.
    """

    model: str
    slice: SmileModel
    handles: SliceHandles
    var_swap_w: float
    lee_left: float
    lee_right: float
    max_iv_error: float


def _max_iv_error(slice_: SmileModel, k: np.ndarray, w: np.ndarray, t: float) -> float:
    """Worst per-quote implied-vol error of a fitted slice."""
    if k.size == 0:
        return 0.0
    model_vol = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / t)
    quote_vol = np.sqrt(np.asarray(w, float) / t)
    return float(np.max(np.abs(model_vol - quote_vol)))


def build_display_fit(
    model: str,
    k: np.ndarray,
    w: np.ndarray,
    t: float,
    weights: np.ndarray | None,
    settings,
    band: BandTarget | None = None,
    var_swap: VarSwapTarget | None = None,
) -> DisplayFit | None:
    """Fit the chosen overlay family; None for "lqd" (the dedicated path).

    ``settings`` is the FitSettings whose per-model coefficients (nCores, the SVI
    penalty weight / Lee-slope bound, the sigmoid ridge, the band mid anchor)
    drive the overlay calibration. ``band`` switches both overlay families to the
    bid-ask / haircut band objective (volfit.calib.band); None keeps the mid fit.
    ``var_swap`` (volfit.calib.varswap) adds the var-swap quote penalty to the
    overlay fit, matching the LQD path; None leaves the overlay unchanged.
    """
    if model not in OVERLAY_MODELS:
        return None
    if model == "svi":
        cal = calibrate_svi(
            k, w, t, weights=weights, band=band,
            penalty_weight=settings.sviPenaltyWeight,
            lee_slope_max=settings.leeSlopeMax,
            mid_anchor_weight=settings.midAnchorWeight,
            var_swap=var_swap,
        )
        slice_: SmileModel = cal.raw
        max_err = cal.max_iv_error
    else:  # sigmoid (Multi-Core SIV)
        slice_ = calibrate_sigmoid(
            k, w, t, weights=weights, n_cores=settings.nCores, band=band,
            ridge=settings.sigmoidRidge,
            mid_anchor_weight=settings.midAnchorWeight,
            var_swap=var_swap,
        )
        max_err = _max_iv_error(slice_, k, w, t)
    lee_left, lee_right = numeric_lee_slopes(slice_)
    return DisplayFit(
        model=model,
        slice=slice_,
        handles=numeric_handles(slice_, t),
        var_swap_w=numeric_var_swap_w(slice_),
        lee_left=lee_left,
        lee_right=lee_right,
        max_iv_error=max_err,
    )

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

This module lives under volfit.models (not volfit.api) so the fit-pool worker
processes (volfit.calib.fit_task) can import it without executing the FastAPI
app package; volfit.api.fit_models re-exports it for the historical path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.calib.band import BandTarget
from volfit.calib.rms import max_quote_error
from volfit.calib.operators import OperatorPriorTarget
from volfit.calib.prior import PriorAnchorTarget
from volfit.calib.varswap import VarSwapTarget
from volfit.models.base import SmileModel
from volfit.models.diagnostics import (
    SliceHandles,
    belly_certificate,
    numeric_handles,
    numeric_lee_slopes,
    numeric_var_swap_w,
)
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import calibrate_svi

#: Models fitted as a display overlay here (LQD is the dedicated default path).
OVERLAY_MODELS = ("svi", "sigmoid")

#: Belly-repair refit grid density over the traded range (committee R2 rider;
#: the 801-point certificate re-checks the result — the hinge only needs
#: enough resolution to see the dip it is repairing).
_REPAIR_POINTS = 101


@dataclass(frozen=True)
class DisplayFit:
    """A non-LQD slice fit shown by the Smile Viewer, with numeric diagnostics.

    ``slice`` is any SmileModel (RawSVI or SigmoidSmile); the handles and
    var-swap are computed model-agnostically. ``lee_left``/``lee_right`` are
    the total-variance wing slopes; there is no A_L/A_R endpoint-scale concept
    outside LQD, so the smile payload reports those as 0 for an overlay.
    ``belly_repaired`` (committee R2 rider): the first SVI fit failed the
    belly certificate and THIS slice is the certified repair refit.
    """

    model: str
    slice: SmileModel
    handles: SliceHandles
    var_swap_w: float
    lee_left: float
    lee_right: float
    max_iv_error: float
    belly_repaired: bool = False


def _max_iv_error(
    slice_: SmileModel, k: np.ndarray, w: np.ndarray, t: float, band: BandTarget | None = None
) -> float:
    """Worst per-quote implied-vol error of a fitted slice against the FIT
    TARGET: |model - mid| (``band`` None) or the band violation (bid-ask /
    haircut band, zero inside) — volfit.calib.rms.quote_errors."""
    if k.size == 0:
        return 0.0
    model_vol = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / t)
    quote_vol = np.sqrt(np.asarray(w, float) / t)
    return max_quote_error(model_vol, quote_vol, band)


def build_display_fit(
    model: str,
    k: np.ndarray,
    w: np.ndarray,
    t: float,
    weights: np.ndarray | None,
    settings,
    band: BandTarget | None = None,
    var_swap: VarSwapTarget | None = None,
    calendar_floor: tuple[np.ndarray, np.ndarray] | None = None,
    calendar_ceiling: tuple[np.ndarray, np.ndarray] | None = None,
    calendar_weight: float = 1e6,
    prior_anchor: PriorAnchorTarget | None = None,
    operator_prior: OperatorPriorTarget | None = None,
    prior_var_swap: VarSwapTarget | None = None,
    wing_penalty: float = 0.0,
    extrap=None,
) -> DisplayFit | None:
    """Fit the chosen overlay family; None for "lqd" (the dedicated path).

    ``settings`` is any object carrying the per-model overlay coefficients
    (nCores, the SVI penalty weight / Lee-slope bound, the sigmoid ridge, the
    band mid anchor) — the FitSettings schema or the picklable
    volfit.calib.fit_task.OverlaySettings stand-in. ``band`` switches both
    overlay families to the bid-ask / haircut band objective (volfit.calib.band);
    None keeps the mid fit. ``var_swap`` (volfit.calib.varswap) adds the
    var-swap quote penalty to the overlay fit, matching the LQD path; None
    leaves the overlay unchanged.

    ``calendar_floor`` is the ``(k_grid, w_floor)`` pair from
    volfit.calib.calendar.variance_floor_targets (the previous, shorter expiry's
    total variance); when present both overlay families gain the model-agnostic
    calendar hinge with strength ``calendar_weight``. ``calendar_ceiling`` is
    the symmetric ``(k_grid, w_ceiling)`` counterpart from the NEXT, longer
    expiry's displayed slice (the symmetric overlay repair's two-sided target,
    so a violating pair splits the correction). None leaves the fit
    byte-identical (the LQD-only path passes None).

    ``prior_anchor`` (strike-gap mode) and ``operator_prior`` (operator / hybrid
    modes) carry the prior-persistence penalty into the overlay calibration, so
    the SVI / Multi-Core Sigmoid (MCS) overlays receive the SAME prior semantics
    as the LQD backbone (roadmap Phase 3 — the asymmetry fix). Both None leave
    the overlay byte-identical.

    ``extrap`` (volfit.calib.extrap.ExtrapTarget, Notes 09/10 Phase 2) adds the
    tapered extrapolated-region enforcement blocks to either overlay family;
    None (the default, and whenever ``OptionsSettings.extrapEnforce`` is off)
    leaves the overlay byte-identical.
    """
    if model not in OVERLAY_MODELS:
        return None
    cal_k = cal_floor = None
    if calendar_floor is not None:
        cal_k, cal_floor = calendar_floor
    ceil_k = ceil_w = None
    if calendar_ceiling is not None:
        ceil_k, ceil_w = calendar_ceiling
    belly_repaired = False
    if model == "svi":
        svi_kwargs = dict(
            weights=weights, band=band,
            penalty_weight=settings.sviPenaltyWeight,
            lee_slope_max=settings.leeSlopeMax,
            mid_anchor_weight=settings.midAnchorWeight,
            var_swap=var_swap,
            calendar_k=cal_k, calendar_floor=cal_floor, calendar_weight=calendar_weight,
            calendar_k_ceil=ceil_k, calendar_ceiling=ceil_w,
            prior_anchor=prior_anchor, operator_prior=operator_prior,
            prior_var_swap=prior_var_swap,
            extrap=extrap,
            chart=getattr(settings, "sviChart", "raw"),
        )
        cal = calibrate_svi(k, w, t, **svi_kwargs)
        slice_: SmileModel = cal.raw
        max_err = cal.max_iv_error
        # Committee R2 repair rider: certified-or-repaired AT the fit, so the
        # publish gate rejects only what a coherent repair cannot fix. A clean
        # first fit never sees a second solve (byte-identical path); a failed
        # repair keeps the FIRST fit — quality reports it uncertified and the
        # publish gate blocks it.
        if getattr(settings, "bellyRepair", True) and k.size >= 2:
            cert = belly_certificate(cal.raw, float(np.min(k)), float(np.max(k)))
            if cert is not None and not cert.certified:
                grid = np.linspace(float(np.min(k)), float(np.max(k)), _REPAIR_POINTS)
                repaired = calibrate_svi(k, w, t, belly_grid=grid, **svi_kwargs)
                re_cert = belly_certificate(
                    repaired.raw, float(np.min(k)), float(np.max(k))
                )
                if re_cert is not None and re_cert.certified:
                    slice_ = repaired.raw
                    max_err = repaired.max_iv_error
                    belly_repaired = True
    else:  # sigmoid (Multi-Core SIV)
        sig_kwargs = dict(
            weights=weights, n_cores=settings.nCores, band=band,
            ridge=settings.sigmoidRidge,
            mid_anchor_weight=settings.midAnchorWeight,
            var_swap=var_swap,
            calendar_k=cal_k, calendar_floor=cal_floor, calendar_weight=calendar_weight,
            calendar_k_ceil=ceil_k, calendar_ceiling=ceil_w,
            prior_anchor=prior_anchor, operator_prior=operator_prior,
            prior_var_swap=prior_var_swap,
            wing_penalty=wing_penalty,
            extrap=extrap,
            # V3.1 leg 3: MCS optimization chart (default "raw", byte-identical)
            # against the same buffered Lee cap the SVI chart honours.
            chart=getattr(settings, "mcsChart", "raw"),
            lee_slope_max=settings.leeSlopeMax,
        )
        slice_ = calibrate_sigmoid(k, w, t, **sig_kwargs)
        max_err = _max_iv_error(slice_, k, w, t, band)
        # V3.1 leg 2 — the sigmoid mirror of the SVI R2 repair rider above:
        # certified-or-repaired AT the fit. A clean first fit never sees a
        # second solve (byte-identical path); a failed repair keeps the FIRST
        # fit — quality reports it uncertified and the publish gate blocks it.
        if getattr(settings, "bellyRepair", True) and k.size >= 2:
            cert = belly_certificate(slice_, float(np.min(k)), float(np.max(k)))
            if cert is not None and not cert.certified:
                grid = np.linspace(float(np.min(k)), float(np.max(k)), _REPAIR_POINTS)
                repaired = calibrate_sigmoid(k, w, t, belly_grid=grid, **sig_kwargs)
                re_cert = belly_certificate(
                    repaired, float(np.min(k)), float(np.max(k))
                )
                if re_cert is not None and re_cert.certified:
                    slice_ = repaired
                    max_err = _max_iv_error(slice_, k, w, t, band)
                    belly_repaired = True
    if model == "sigmoid":
        # V3.1 leg 1: closed-form asymptotic slopes (eq mcsbetak; the kernels
        # are zero-wing) replace the far-grid FD for the sigmoid family.
        lee_left, lee_right = slice_.lee_slopes()
    else:
        lee_left, lee_right = numeric_lee_slopes(slice_)
    return DisplayFit(
        model=model,
        slice=slice_,
        handles=numeric_handles(slice_, t),
        var_swap_w=numeric_var_swap_w(slice_),
        lee_left=lee_left,
        lee_right=lee_right,
        max_iv_error=max_err,
        belly_repaired=belly_repaired,
    )

"""Per-fit documents and evidence metrics of a series lane (SERIES ARC S3).

One stored fit (``LaneFitDoc``) carries what the replay needs without a
refit — the LQD backbone + the displayed overlay in the snapshot-file
calibration shape (``snapshot_files``), the fit diagnostics in the
fit-history shape (``history.persist_fit``) — and the evidence row the
Lanes stage draws: rms / max error in vol bp on the fit's own weights (the
Quality lens definitions, ``service._node_rms_terms`` + ``quality.
_node_handles``), the Lee wing slopes, the belly repair flag, the PULL of
the lane against its free reference (ATM distance in bp, skew distance —
``compare_anchoring.attach_pull``'s vocabulary), and the filter's last
step (ζ, gain, provenance) when the lane runs one. Roughness — the
frame-to-frame handle path — is a strip-level quantity computed from these
rows at read time (S5), never stored twice.
"""

from __future__ import annotations

import numpy as np

from volfit.api import quality, service
from volfit.api.filter_history import step_doc
from volfit.api.schemas_series import LaneFitDoc
from volfit.api.snapshot_files import _display_doc
from volfit.models.lqd.atm import atm_handles


def _rms_of_terms(num: float, den: float) -> float:
    return float(np.sqrt(num / den)) if den > 0.0 else 0.0


def slice_fit_doc(state, lane_id: str, idx: int, ticker: str, iso: str, fit_mode: str,
                  record, fit_ms: float | None = None) -> LaneFitDoc:
    """The stored document of one committed parametric slice."""
    p = record.result.params
    prepared, result = record.prepared, record.result
    handles = atm_handles(result.slice, prepared.t)
    atm_vol, skew, lee_left, lee_right, max_iv = quality._node_handles(record)
    num, den = service._node_rms_terms(state, ticker, iso, record, fit_mode)
    diagnostics = {
        "t": float(prepared.t), "tau": float(prepared.tau), "fitMode": fit_mode,
        "forward": float(prepared.forward), "discount": float(prepared.discount),
        "atmVol": float(handles.sigma0), "skew": float(handles.skew),
        "curvature": float(handles.curvature),
        "varSwapVol": float(np.sqrt(max(result.slice.var_swap_strike(), 0.0) / prepared.t)),
        "cost": float(result.cost), "nEvaluations": int(result.n_evaluations),
        "success": bool(result.success), "maxIvError": float(result.max_iv_error),
        "kMin": float(prepared.k.min()) if prepared.k.size else None,
        "kMax": float(prepared.k.max()) if prepared.k.size else None,
    }
    metrics = {
        "rmsBp": round(_rms_of_terms(num, den) * 1e4, 3),
        "maxIvBp": round(float(max_iv) * 1e4, 3),
        "nQuotes": int(prepared.k.size),
        "atmVol": float(atm_vol), "skew": float(skew),
        "leeLeft": float(lee_left), "leeRight": float(lee_right),
        "bellyRepaired": bool(record.display.belly_repaired) if record.display is not None
        else False,
    }
    return LaneFitDoc(
        laneId=lane_id, idx=idx, expiry=iso,
        model=record.display.model if record.display is not None else "lqd",
        params={"L": float(p.L), "R": float(p.R), "a": np.asarray(p.a, dtype=float).tolist(),
                "alphaL": float(p.alpha_left), "alphaR": float(p.alpha_right)},
        display=_display_doc(record.display), diagnostics=diagnostics, metrics=metrics,
        fitMs=fit_ms,
    )


def surface_fit_doc(lane_id: str, idx: int, resp, fit_ms: float | None = None) -> LaneFitDoc:
    """The stored document of one affine LV surface (``expiry`` None): the
    vertices and nodal variances the prior snapshot keeps, the fit's own
    error summary as the metrics."""
    theta = [[float(v) * float(v) for v in row] for row in resp.localVol]
    return LaneFitDoc(
        laneId=lane_id, idx=idx, expiry=None, model="affine",
        params={"tNodes": list(resp.tNodes), "xNodes": list(resp.xNodes), "theta": theta},
        diagnostics={"rmsPriceError": float(resp.rmsPriceError),
                     "maxPriceError": float(resp.maxPriceError),
                     "surfaceRmsError": float(resp.surfaceRmsError),
                     "calendarViolations": int(resp.calendarViolations),
                     "nEvals": int(resp.nEvals), "message": str(resp.message)},
        metrics={"rmsBp": round(float(resp.rmsIvErrorBp), 3),
                 "maxIvBp": round(float(resp.maxIvErrorBp), 3),
                 "arbitrageFree": bool(resp.arbitrageFree),
                 "nVertices": len(resp.tNodes) * len(resp.xNodes)},
        fitMs=fit_ms,
    )


def attach_pull(fit: LaneFitDoc, reference: LaneFitDoc | None) -> LaneFitDoc:
    """The lane's distance from its free reference on the same (frame,
    expiry): ATM in vol bp, skew; the reference reads zero on both."""
    if reference is None or fit.expiry is None:
        return fit
    m = dict(fit.metrics)
    ref = reference.metrics
    if "atmVol" in m and "atmVol" in ref:
        m["pullAtmBp"] = round((m["atmVol"] - ref["atmVol"]) * 1e4, 2)
    if "skew" in m and "skew" in ref:
        m["pullSkew"] = round(m["skew"] - ref["skew"], 5)
    return fit.model_copy(update={"metrics": m})


def attach_filter(fit: LaneFitDoc, ring) -> LaneFitDoc:
    """The lane's filter evidence for the node at this frame: the last step
    of its ring (ζ per handle, gain, provenance, reset / contamination)."""
    if ring is None or len(ring) == 0:
        return fit
    step = step_doc(ring.steps()[-1])
    m = dict(fit.metrics)
    m["zeta"] = step.get("zeta")
    m["gain"] = step.get("gain")
    m["filterProvenance"] = step.get("provenance")
    m["filterReset"] = step.get("resetReason")
    m["contaminated"] = bool(step.get("contaminated", False))
    return fit.model_copy(update={"metrics": m})

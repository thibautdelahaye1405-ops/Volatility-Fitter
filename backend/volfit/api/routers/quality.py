"""GET /quality — the universe fit-quality dashboard (volfit.api.quality).

A pure cached-state read (never fits): safe to poll and to refetch on every
calibration epoch, like /calibration/status.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from volfit.api.quality import DEFAULT_RMS_BUDGET_BP, build_quality_report
from volfit.api.schemas_quality import QualityReport

router = APIRouter(tags=["quality"])


@router.get("/quality", response_model=QualityReport)
def quality_report(
    request: Request,
    fit_mode: str | None = None,
    rms_budget_bp: float = DEFAULT_RMS_BUDGET_BP,
) -> QualityReport:
    """Universe quality report for the given fit mode (default: the last mode
    viewed in the app, matching the bare-Calibrate resolution)."""
    state = request.app.state.volfit
    return build_quality_report(state, fit_mode, rms_budget_bp)

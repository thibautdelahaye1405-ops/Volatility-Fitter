"""GET /surface/{ticker} — sigma(k, T) mesh for the 3D vol-surface chart.

ROADMAP Phase 6 [REQ 2026-06-12]: every fitted expiry of the ticker sampled
on one shared log-moneyness grid (full rectangular mesh, rotatable chart).
The assembly (and the union-grid rationale) lives in volfit.api.surface.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from volfit.api.schemas import FitMode, SurfaceResponse
from volfit.api.state import UnknownNodeError
from volfit.api.surface import surface_payload

router = APIRouter()


@router.get("/surface/{ticker}", response_model=SurfaceResponse)
def get_surface(
    ticker: str, request: Request, fit_mode: FitMode = Query("mid")
) -> SurfaceResponse:
    try:
        return surface_payload(request.app.state.volfit, ticker, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

"""GET /localvol/{ticker} — extracted Dupire local-vol grid + diagnostics.

Exposes the local-volatility grid model over the fitted surface (ROADMAP
Phase 2 leftover): forward-variance buckets between listed expiries, Dupire
extraction with butterfly gating, and the discrete no-arbitrage residuals.
The heavy lifting (and the per-session cache) lives in volfit.api.localvol.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from volfit.api.localvol import localvol_payload
from volfit.api.schemas import FitMode, LocalVolGridResponse
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/localvol/{ticker}", response_model=LocalVolGridResponse)
def get_localvol(
    ticker: str, request: Request, fit_mode: FitMode = Query("mid")
) -> LocalVolGridResponse:
    try:
        return localvol_payload(request.app.state.volfit, ticker, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

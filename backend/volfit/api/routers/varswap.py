"""Variance-swap quote endpoints (shared by Parametric & Local Vol).

POST /smiles/{ticker}/{expiry}/varswap  body {action, level?} -> SmileData
POST /smiles/{ticker}/{expiry}/varswap/undo                   -> SmileData
POST /smiles/{ticker}/{expiry}/varswap/redo                   -> SmileData

All three return the refreshed (instantly refitted) SmileData. Semantic edit
errors (missing/non-positive level, no quote to exclude) surface as ValueError
and map to 422; unknown nodes map to 404. Undo/redo on an empty stack is a 200
no-op by contract. The added var-swap penalty only affects calibration while
OptionsSettings.varSwapEnabled is on; editing the quote is always allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import varswap
from volfit.api.schemas import FitMode, SmileData, VarSwapEditRequest
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.post("/smiles/{ticker}/{expiry}/varswap", response_model=SmileData)
def apply_varswap(
    ticker: str,
    expiry: str,
    body: VarSwapEditRequest,
    request: Request,
    fit_mode: FitMode = "mid",
) -> SmileData:
    try:
        return varswap.apply_varswap_edit(
            request.app.state.volfit, ticker, expiry, fit_mode, body
        )
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/smiles/{ticker}/{expiry}/varswap/undo", response_model=SmileData)
def undo_varswap(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> SmileData:
    try:
        return varswap.undo_varswap(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/smiles/{ticker}/{expiry}/varswap/redo", response_model=SmileData)
def redo_varswap(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> SmileData:
    try:
        return varswap.redo_varswap(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

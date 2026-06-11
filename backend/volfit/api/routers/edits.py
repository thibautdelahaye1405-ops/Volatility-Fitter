"""Quote-edit endpoints of the fit-session model (ROADMAP Phase 5).

POST /smiles/{ticker}/{expiry}/edits  body {action, index?, mid?} -> SmileData
POST /smiles/{ticker}/{expiry}/undo                              -> SmileData
POST /smiles/{ticker}/{expiry}/redo                              -> SmileData

All three return the refreshed (instantly refitted) SmileData. Semantic edit
errors (bad index, missing mid, too few quotes left) surface as ValueError
from the session machine and map to 422; unknown nodes map to 404 as
everywhere else. Undo/redo on an empty stack is a 200 no-op by contract.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import edits
from volfit.api.schemas import FitMode, QuoteEditRequest, SmileData
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.post("/smiles/{ticker}/{expiry}/edits", response_model=SmileData)
def apply_edit(
    ticker: str, expiry: str, body: QuoteEditRequest, request: Request, fit_mode: FitMode = "mid"
) -> SmileData:
    try:
        return edits.apply_quote_edit(request.app.state.volfit, ticker, expiry, fit_mode, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/smiles/{ticker}/{expiry}/undo", response_model=SmileData)
def undo(ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid") -> SmileData:
    try:
        return edits.undo_edit(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/smiles/{ticker}/{expiry}/redo", response_model=SmileData)
def redo(ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid") -> SmileData:
    try:
        return edits.redo_edit(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

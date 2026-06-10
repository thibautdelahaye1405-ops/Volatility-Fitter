"""Smile endpoints: fitted smile payloads and prior-curve saves.

GET /smiles/{ticker}/{expiry}?fit_mode=...  -> SmileData (frontend contract)
POST /smiles/{ticker}/{expiry}/prior        -> snapshot the current fit as
the node's prior, shown alongside later fits in the Smile Viewer.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import service
from volfit.api.schemas import FitMode, PriorSavedResponse, SmileData
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/smiles/{ticker}/{expiry}", response_model=SmileData)
def get_smile(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> SmileData:
    try:
        return service.smile_payload(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/smiles/{ticker}/{expiry}/prior", response_model=PriorSavedResponse)
def save_prior(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> PriorSavedResponse:
    state = request.app.state.volfit
    try:
        record = service.fit_or_get(state, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    state.save_prior((ticker, expiry), service.model_curve(record))
    return PriorSavedResponse(saved=True)

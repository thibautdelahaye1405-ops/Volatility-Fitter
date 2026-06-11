"""Smile endpoints: fitted payloads, prior saves and density/quantile data.

GET  /smiles/{ticker}/{expiry}?fit_mode=...  -> SmileData (frontend contract)
POST /smiles/{ticker}/{expiry}/prior         -> snapshot the current fit as
the node's prior: the display curve shown alongside later fits PLUS the
fitted LQD params, so the prior's density can be rebuilt (PriorRecord).
GET  /smiles/{ticker}/{expiry}/density       -> current fit's risk-neutral
density and quantile function, and the saved prior's when one exists.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import analytics, service
from volfit.api.schemas import DensityResponse, FitMode, PriorSavedResponse, SmileData
from volfit.api.state import PriorRecord, UnknownNodeError

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
    state.save_prior(
        (ticker, expiry),
        PriorRecord(
            curve=service.model_curve(record),
            params=record.result.params,
            t=record.prepared.t,
        ),
    )
    return PriorSavedResponse(saved=True)


@router.get("/smiles/{ticker}/{expiry}/density", response_model=DensityResponse)
def get_density(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> DensityResponse:
    try:
        return analytics.density_payload(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

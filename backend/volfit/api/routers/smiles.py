"""Smile endpoints: fitted payloads, priors, density and table export.

GET  /smiles/{ticker}/{expiry}?fit_mode=...  -> SmileData (frontend contract)
POST /smiles/{ticker}/{expiry}/prior         -> snapshot the current fit as
the node's prior: the display curve shown alongside later fits PLUS the
fitted LQD params, so the prior's density can be rebuilt (PriorRecord).
GET  /smiles/{ticker}/{expiry}/density       -> current fit's risk-neutral
density and quantile function, and the saved prior's when one exists.
GET  /smiles/{ticker}/{expiry}/table         -> quote/price/IV grid (JSON)
GET  /smiles/{ticker}/{expiry}/table.csv     -> same table as a CSV download
([REQ 2026-06-12] table export; assembly in volfit.api.table).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from volfit.api import analytics, service, table
from volfit.api.schemas import (
    DensityResponse,
    FitMode,
    PriorSavedResponse,
    SmileData,
    StackedDensityResponse,
    TableResponse,
)
from volfit.api.state import PriorRecord, UnknownNodeError

router = APIRouter()


# NOTE: declared before /smiles/{ticker}/{expiry} so "densities" is not captured
# as an expiry path parameter (FastAPI matches routes in declaration order).
@router.get("/smiles/{ticker}/densities", response_model=StackedDensityResponse)
def get_stacked_densities(
    ticker: str, request: Request, fit_mode: FitMode = "mid"
) -> StackedDensityResponse:
    state = request.app.state.volfit
    try:
        with state.activity.activity("density", f"Computing {ticker} densities"):
            return analytics.stacked_densities(state, ticker, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/smiles/{ticker}/{expiry}", response_model=SmileData)
def get_smile(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> SmileData:
    state = request.app.state.volfit
    state.note_fit_mode(fit_mode)  # so Calibrate re-points the mode on screen
    try:
        return service.smile_payload(state, ticker, expiry, fit_mode)
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
    if record is None:  # gated, never calibrated: nothing to snapshot as a prior
        raise HTTPException(status_code=409, detail="calibrate the node before saving a prior")
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


@router.get("/smiles/{ticker}/{expiry}/table", response_model=TableResponse)
def get_table(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> TableResponse:
    try:
        return table.table_payload(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/smiles/{ticker}/{expiry}/table.csv")
def get_table_csv(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> Response:
    try:
        payload = table.table_payload(request.app.state.volfit, ticker, expiry, fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    filename = f"{ticker}_{expiry}_quotes.csv"
    return Response(
        content=table.table_csv(payload),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

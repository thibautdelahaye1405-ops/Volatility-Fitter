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
GET  /smiles/{ticker}/{expiry}/weights       -> per-quote calibration weights
(V3.4 item 5; poll-safe, assembly in volfit.api.weights_view).
GET  /smiles/{ticker}/{expiry}/filter/history -> the node's committed filter
steps (V3.9 item 7; poll-safe, assembly in volfit.api.filter_history).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from volfit.api import analytics, filter_history, observation_filter, service, table, weights_view
from volfit.api.schemas import (
    DensityResponse,
    FilterDiagnostics,
    FilterHistoryResponse,
    FitMode,
    PriorDiagnostics,
    PriorSavedResponse,
    SmileData,
    StackedDensityResponse,
    TableResponse,
)
from volfit.api.schemas_weights import WeightsData
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


@router.get("/smiles/{ticker}/{expiry}/prior-diagnostics", response_model=PriorDiagnostics)
def get_prior_diagnostics(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> PriorDiagnostics:
    """Auditable prior-persistence state for the node (design note §9.4): the active
    operators/factors with their gap + weight. Advisory — never raises."""
    return service.prior_diagnostics(request.app.state.volfit, ticker, expiry, fit_mode)


@router.get("/smiles/{ticker}/{expiry}/filter", response_model=FilterDiagnostics)
def get_filter_diagnostics(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> FilterDiagnostics:
    """The node's observation-filter step (Note 15 invariant 5): prediction,
    observation, innovation, gain, posterior + covariance audits. Advisory —
    never raises; ``active=False`` when the filter is off or unseeded."""
    return observation_filter.filter_diagnostics(
        request.app.state.volfit, ticker, expiry, fit_mode
    )


@router.get(
    "/smiles/{ticker}/{expiry}/filter/history", response_model=FilterHistoryResponse
)
def get_filter_history(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> FilterHistoryResponse:
    """The node's last <= 64 committed observation-filter steps, oldest first
    (V3.9 item 7 — the FilterTimeline's feed). Read-only and POLL-SAFE: never
    fits; ``active=False`` with empty steps when the filter is off or the node
    has no committed history yet. In-memory only."""
    return filter_history.history_payload(
        request.app.state.volfit, ticker, expiry, fit_mode
    )


@router.get("/smiles/{ticker}/{expiry}/weights", response_model=WeightsData)
def get_weights(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode = "mid"
) -> WeightsData:
    """Per-quote calibration weights (V3.4 item 5). Read-only and POLL-SAFE:
    prepared quotes + session edits only — never triggers a fit. ``fit_mode``
    is accepted for URL symmetry with the sibling smile reads but is unused:
    the weight scheme applies identically in every fit mode."""
    _ = fit_mode  # mode-orthogonal (volfit.calib.weights module docstring)
    try:
        return weights_view.weights_payload(request.app.state.volfit, ticker, expiry)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


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

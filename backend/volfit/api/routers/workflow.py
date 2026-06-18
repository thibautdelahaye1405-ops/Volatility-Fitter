"""Calibration / data-fetch workflow endpoints (the trigger model).

GET  /calibration/status            -> background-job + lit/stale node state
POST /calibrate                     -> background-calibrate ALL lit nodes
POST /calibrate/cancel              -> cancel the running background job
POST /calibrate/{ticker}            -> (re)calibrate one ticker's lit expiries (sync)
POST /calibrate/{ticker}/{expiry}   -> (re)calibrate one node (sync)
POST /fetch/spots                   -> probe live spots -> transport (no refit)
POST /fetch/options                 -> refetch chains (+ auto-calibrate if enabled)
POST /priors/seed                   -> seed previous-close priors on demand
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from volfit.api import workflow
from volfit.api.schemas import (
    CalibrationStatus,
    FetchRequest,
    FetchResult,
    FitMode,
    LiveSpot,
    SchedulerStatus,
)
from volfit.api.state import AppState

router = APIRouter()


def _mode(state: AppState, fit_mode: FitMode | None) -> str:
    """Resolve the fit target for a calibration/status action: the explicit query
    param when the caller (the frontend) supplies one, else the mode the user is
    currently viewing (``AppState.last_fit_mode``). This keeps Calibrate, the
    stale accounting and the auto-fetch all targeting the SAME per-mode calibrated
    pointer the smile is displayed in — a bid-ask / haircut smile no longer stays
    frozen because the work always re-pointed the "mid" pointer."""
    return fit_mode if fit_mode is not None else state.last_fit_mode


@router.get("/calibration/status", response_model=CalibrationStatus)
def get_status(request: Request, fit_mode: FitMode | None = None) -> CalibrationStatus:
    state = request.app.state.volfit
    return workflow.status(state, _mode(state, fit_mode))


@router.get("/scheduler", response_model=SchedulerStatus)
def get_scheduler(request: Request) -> SchedulerStatus:
    return workflow.scheduler_status(request.app.state.volfit)


@router.post("/calibrate/cancel", response_model=CalibrationStatus)
def cancel(request: Request, fit_mode: FitMode | None = None) -> CalibrationStatus:
    state = request.app.state.volfit
    state.calibration_jobs.cancel()
    return workflow.status(state, _mode(state, fit_mode))


@router.post("/calibrate", response_model=CalibrationStatus)
def calibrate_all(request: Request, fit_mode: FitMode | None = None) -> CalibrationStatus:
    state = request.app.state.volfit
    mode = _mode(state, fit_mode)
    workflow.calibrate_all(state, mode)  # False (already running) -> status reflects it
    return workflow.status(state, mode)


@router.post("/calibrate/{ticker}/{expiry}", response_model=CalibrationStatus)
def calibrate_one(
    ticker: str, expiry: str, request: Request, fit_mode: FitMode | None = None
) -> CalibrationStatus:
    state = request.app.state.volfit
    mode = _mode(state, fit_mode)
    workflow.calibrate_one(state, ticker, expiry, mode)
    return workflow.status(state, mode)


@router.post("/calibrate/{ticker}", response_model=CalibrationStatus)
def calibrate_ticker(
    ticker: str, request: Request, fit_mode: FitMode | None = None
) -> CalibrationStatus:
    state = request.app.state.volfit
    mode = _mode(state, fit_mode)
    workflow.calibrate_ticker(state, ticker, mode)
    return workflow.status(state, mode)


@router.post("/fetch/spots", response_model=dict[str, LiveSpot])
def fetch_spots(body: FetchRequest, request: Request) -> dict[str, LiveSpot]:
    return workflow.fetch_spots(request.app.state.volfit, body.tickers)


@router.post("/fetch/options", response_model=FetchResult)
def fetch_options(
    body: FetchRequest, request: Request, fit_mode: FitMode | None = None
) -> FetchResult:
    state = request.app.state.volfit
    return workflow.fetch_options(state, body.tickers, _mode(state, fit_mode))


@router.post("/priors/seed", response_model=dict[str, int])
def seed_priors(body: FetchRequest, request: Request) -> dict[str, int]:
    return {"seeded": workflow.seed_priors(request.app.state.volfit, body.tickers)}

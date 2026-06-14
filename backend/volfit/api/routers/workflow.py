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
    LiveSpot,
    SchedulerStatus,
)

router = APIRouter()


@router.get("/calibration/status", response_model=CalibrationStatus)
def get_status(request: Request) -> CalibrationStatus:
    return workflow.status(request.app.state.volfit)


@router.get("/scheduler", response_model=SchedulerStatus)
def get_scheduler(request: Request) -> SchedulerStatus:
    return workflow.scheduler_status(request.app.state.volfit)


@router.post("/calibrate/cancel", response_model=CalibrationStatus)
def cancel(request: Request) -> CalibrationStatus:
    state = request.app.state.volfit
    state.calibration_jobs.cancel()
    return workflow.status(state)


@router.post("/calibrate", response_model=CalibrationStatus)
def calibrate_all(request: Request) -> CalibrationStatus:
    state = request.app.state.volfit
    workflow.calibrate_all(state)  # False (already running) -> status reflects it
    return workflow.status(state)


@router.post("/calibrate/{ticker}/{expiry}", response_model=CalibrationStatus)
def calibrate_one(ticker: str, expiry: str, request: Request) -> CalibrationStatus:
    state = request.app.state.volfit
    workflow.calibrate_one(state, ticker, expiry)
    return workflow.status(state)


@router.post("/calibrate/{ticker}", response_model=CalibrationStatus)
def calibrate_ticker(ticker: str, request: Request) -> CalibrationStatus:
    state = request.app.state.volfit
    workflow.calibrate_ticker(state, ticker)
    return workflow.status(state)


@router.post("/fetch/spots", response_model=dict[str, LiveSpot])
def fetch_spots(body: FetchRequest, request: Request) -> dict[str, LiveSpot]:
    return workflow.fetch_spots(request.app.state.volfit, body.tickers)


@router.post("/fetch/options", response_model=FetchResult)
def fetch_options(body: FetchRequest, request: Request) -> FetchResult:
    return workflow.fetch_options(request.app.state.volfit, body.tickers)


@router.post("/priors/seed", response_model=dict[str, int])
def seed_priors(body: FetchRequest, request: Request) -> dict[str, int]:
    return {"seeded": workflow.seed_priors(request.app.state.volfit, body.tickers)}

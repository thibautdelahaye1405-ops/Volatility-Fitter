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

import asyncio
from time import monotonic

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

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


#: SSE watch cadence (s): how often the server re-reads its own in-process status.
#: This is a cheap local attribute read (no I/O), and an event is pushed to the
#: client ONLY when the payload actually changes — so the client holds one
#: connection and refetches views only on real epoch/spot/activity changes instead
#: of polling every 500 ms. (ROADMAP perf #4.)
_SSE_TICK = 0.25
_SSE_HEARTBEAT = 15.0  # keep-alive comment when nothing changed, to hold the conn


@router.get("/calibration/stream")
async def stream_status(request: Request, fit_mode: FitMode | None = None) -> StreamingResponse:
    """Server-Sent Events stream of the calibration status (push, not poll).

    Emits the same `CalibrationStatus` payload as `/calibration/status`, but only
    when it changes (plus a periodic keep-alive). `text/event-stream` is excluded
    from GZip by Starlette, so events flush in real time. The frontend keeps the
    plain poll as a fallback, so an absent/again-down stream never freezes the UI.
    """
    state = request.app.state.volfit
    mode = _mode(state, fit_mode)

    async def gen():
        last: str | None = None
        last_beat = monotonic()
        while True:
            if await request.is_disconnected():
                break
            payload = workflow.status(state, mode).model_dump_json()
            now = monotonic()
            if payload != last:
                last = payload
                last_beat = now
                yield f"data: {payload}\n\n"
            elif now - last_beat >= _SSE_HEARTBEAT:
                last_beat = now
                yield ": keepalive\n\n"
            await asyncio.sleep(_SSE_TICK)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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

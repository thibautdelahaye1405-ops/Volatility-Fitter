"""Fast spot-move endpoints (no-recalibration transport).

GET  /spot/{ticker}            -> shift, anchor, prevailing market spot, follow
                                  mode, dynamics regime (the Spot panel's state)
PUT  /spot/{ticker}            -> the dial: a hypothetical spot shift (transports
                                  smile / term / LV grid; no refit; follow=scenario)
PUT  /spot/{ticker}/follow     -> follow the market spot or the scenario (dial)
POST /spot/{ticker}/calibrate  -> Recalibrate ONE ticker: the top-bar Calibrate
                                  verb (same scope, same snapshot rule) as the
                                  background job
GET  /spot/{ticker}/live       -> re-probe the provider spot (real-time polling)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from volfit.api import spot
from volfit.api.schemas import (
    FitMode,
    LiveSpot,
    RecalibrateResult,
    SpotFollowRequest,
    SpotShiftRequest,
    SpotState,
)
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/spot/{ticker}/live", response_model=LiveSpot)
def get_live_spot(ticker: str, request: Request) -> LiveSpot:
    try:
        return spot.live_spot(request.app.state.volfit, ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/spot/{ticker}/calibrate", response_model=RecalibrateResult)
def post_calibrate(
    ticker: str,
    request: Request,
    fit_mode: FitMode | None = None,
    scope: Literal["both", "parametric", "lv"] = "both",
) -> RecalibrateResult:
    """Recalibrate one ticker. ``fit_mode`` targets the mode the smile is viewed
    in (else the last viewed one) and ``scope`` mirrors the top-bar Calibrate
    split control (Parametric + LV / Parametric only / Local-Vol only)."""
    state = request.app.state.volfit
    mode = fit_mode if fit_mode is not None else state.last_fit_mode
    try:
        return spot.recalibrate(state, ticker, mode, scope)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put("/spot/{ticker}/follow", response_model=SpotState)
def put_follow(ticker: str, body: SpotFollowRequest, request: Request) -> SpotState:
    try:
        return spot.set_follow(request.app.state.volfit, ticker, body.follow)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/spot/{ticker}", response_model=SpotState)
def get_spot(ticker: str, request: Request) -> SpotState:
    try:
        return spot.spot_state(request.app.state.volfit, ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put("/spot/{ticker}", response_model=SpotState)
def put_spot(ticker: str, body: SpotShiftRequest, request: Request) -> SpotState:
    try:
        return spot.set_shift(request.app.state.volfit, ticker, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

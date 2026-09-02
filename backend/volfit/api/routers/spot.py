"""Fast spot-move endpoints (no-recalibration transport).

GET  /spot/{ticker}            -> current shift + anchor spot + dynamics regime
PUT  /spot/{ticker}            -> set a hypothetical/live spot shift (transports
                                  smile / term / LV grid; no refit)
POST /spot/{ticker}/calibrate  -> the explicit "Re-anchor": clear the shift,
                                  refetch the chain and calibrate the ticker's
                                  lit nodes in the background at the live spot
GET  /spot/{ticker}/live       -> re-probe the provider spot (real-time polling)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import spot
from volfit.api.schemas import FitMode, LiveSpot, ReanchorResult, SpotShiftRequest, SpotState
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/spot/{ticker}/live", response_model=LiveSpot)
def get_live_spot(ticker: str, request: Request) -> LiveSpot:
    try:
        return spot.live_spot(request.app.state.volfit, ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/spot/{ticker}/calibrate", response_model=ReanchorResult)
def post_calibrate(
    ticker: str, request: Request, fit_mode: FitMode | None = None
) -> ReanchorResult:
    """Re-anchor one ticker. ``fit_mode`` targets the mode the smile is viewed
    in (else the last viewed one), like the workflow router's Calibrate verbs."""
    state = request.app.state.volfit
    mode = fit_mode if fit_mode is not None else state.last_fit_mode
    try:
        return spot.recalibrate(state, ticker, mode)
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

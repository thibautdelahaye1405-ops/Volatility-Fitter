"""GET /asof, POST /asof — the as-of (day -> moment) selector under Data Source.

Thin wrapper over volfit.api.asof. GET reports the current selection and the
day-grouped capabilities (recent business days, and per day whether a close /
captures / intraday fetch are available). POST applies either a high-level
``moment`` pick (``{mode:"moment", on, moment, offsetMinutes}``) or a low-level
explicit selection (``{mode:"live"|"eod"|"captured"|...}``) and re-prices.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from volfit.api.asof import asof_payload, set_asof, set_moment
from volfit.api.state import UnknownNodeError

router = APIRouter()


class AsOfDay(BaseModel):
    date: str  # ISO date
    isToday: bool
    hasClose: bool  # an official close is available for this day
    hasCaptures: bool  # at least one captured intraday snapshot exists
    intraday: bool  # the provider can fetch an arbitrary instant this day


class AsOfResponse(BaseModel):
    mode: str  # "live" | "prev_close" | "eod" | "captured" | "intraday"
    on: str | None  # ISO date for "eod"
    ts: str | None  # ISO datetime for "captured" / "intraday"
    day: str | None  # the dropdown day the selection resolved from
    moment: str | None  # "close" | "latest" | "before_close"
    offset: int | None  # minutes-before-close for "before_close"
    supportedModes: list[str]
    intradayCapable: bool
    closeOffsets: list[int]  # preset "minutes before close" choices
    days: list[AsOfDay]  # recent business days with data, newest first


class AsOfRequest(BaseModel):
    mode: str  # "live" | "moment" | "eod" | "captured" | "prev_close" | "intraday"
    on: str | None = None  # ISO date ("eod" / "moment")
    ts: str | None = None  # ISO datetime ("captured")
    moment: str | None = None  # "close" | "latest" | "before_close" (mode="moment")
    offsetMinutes: int | None = None  # for moment="before_close"


@router.get("/asof", response_model=AsOfResponse)
def get_asof(request: Request) -> AsOfResponse:
    return AsOfResponse(**asof_payload(request.app.state.volfit))


@router.post("/asof", response_model=AsOfResponse)
def post_asof(body: AsOfRequest, request: Request) -> AsOfResponse:
    state = request.app.state.volfit
    try:
        if body.mode == "moment":
            if body.on is None or body.moment is None:
                raise ValueError("moment selection requires 'on' and 'moment'")
            payload = set_moment(state, body.on, body.moment, body.offsetMinutes)
        else:
            payload = set_asof(state, body.mode, body.on, body.ts)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return AsOfResponse(**payload)

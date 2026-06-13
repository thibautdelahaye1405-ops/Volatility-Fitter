"""GET /asof, POST /asof — the as-of (timestamp) selector under Data Source.

Thin wrapper over volfit.api.asof. GET reports the current selection and what
the active source/store can offer (supported modes, EOD trading days, captured
intraday timestamps); POST applies a selection and re-prices the stack.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from volfit.api.asof import asof_payload, set_asof
from volfit.api.state import UnknownNodeError

router = APIRouter()


class AsOfResponse(BaseModel):
    mode: str  # "live" | "prev_close" | "eod" | "captured"
    on: str | None  # ISO date for "eod"
    ts: str | None  # ISO datetime for "captured"
    supportedModes: list[str]
    prevCloseAvailable: bool
    historyDates: list[str]  # provider EOD trading days, newest first
    captured: list[str]  # captured intraday timestamps, newest first


class AsOfRequest(BaseModel):
    mode: str
    on: str | None = None
    ts: str | None = None


@router.get("/asof", response_model=AsOfResponse)
def get_asof(request: Request) -> AsOfResponse:
    return AsOfResponse(**asof_payload(request.app.state.volfit))


@router.post("/asof", response_model=AsOfResponse)
def post_asof(body: AsOfRequest, request: Request) -> AsOfResponse:
    try:
        payload = set_asof(request.app.state.volfit, body.mode, body.on, body.ts)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return AsOfResponse(**payload)

"""Forward-mode and market-settings endpoints ([REQ 2026-06-12]).

GET  /forwards/{ticker}          -> per-expiry forward diagnostics (parity
                                    regression vs theoretical vs manual)
PUT  /forwards/{ticker}/{expiry} -> set that expiry's forward policy; the
                                    forwards version busts fit caches, so
                                    the next GET /smiles refits on the new
                                    forward
GET  /settings/market/{ticker}   -> the ticker's rate/dividend settings
PUT  /settings/market/{ticker}   -> update them (theoretical forwards move;
                                    caches bust only on a real change)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import market
from volfit.api.carry import carry_curve
from volfit.api.schemas import (
    CarryCurveResponse,
    ForwardEntry,
    ForwardPolicy,
    ForwardsResponse,
    MarketSettings,
)
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/forwards/{ticker}", response_model=ForwardsResponse)
def get_forwards(ticker: str, request: Request) -> ForwardsResponse:
    try:
        return market.forwards_payload(request.app.state.volfit, ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/carry/{ticker}", response_model=CarryCurveResponse)
def get_carry(ticker: str, request: Request, joint: bool = False) -> CarryCurveResponse:
    """The versioned per-ticker CarryCurve (R1 item 7): forward / discount /
    option-implied borrow per expiry with source tags — 'unidentified' is a
    calm, common state, never a silent zero-borrow. ``joint=true`` adds the
    R2 item-11 borrow/de-Am fixed point per identifiable expiry: the
    EEP-consistent borrow with iteration/failure accounting."""
    try:
        return carry_curve(request.app.state.volfit, ticker, joint=joint)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put("/forwards/{ticker}/{expiry}", response_model=ForwardEntry)
def put_forward_policy(
    ticker: str, expiry: str, body: ForwardPolicy, request: Request
) -> ForwardEntry:
    try:
        return market.apply_forward_policy(request.app.state.volfit, ticker, expiry, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/settings/market/{ticker}", response_model=MarketSettings)
def get_market_settings(ticker: str, request: Request) -> MarketSettings:
    try:
        return market.get_market_settings(request.app.state.volfit, ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put("/settings/market/{ticker}", response_model=MarketSettings)
def put_market_settings(
    ticker: str, body: MarketSettings, request: Request
) -> MarketSettings:
    try:
        return market.set_market_settings(request.app.state.volfit, ticker, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

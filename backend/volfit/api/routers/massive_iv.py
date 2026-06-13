"""GET /massive/iv/{ticker} — Massive's precomputed IV/greeks (read-only overlay).

Surfaces the implied vols and greeks Massive computes per contract as a
*read-only* comparison overlay for the Smile Viewer, distinct from volfit's own
fitted smile. It needs no quote entitlement (greeks/IV are returned on the base
options tier), so it works even where bid/ask are gated. Only meaningful when
the active provider is the Massive provider; any other provider yields a 404 so
the frontend can hide the toggle.

Note the IVs are Massive's *American* implied vols under their own forward /
dividend assumptions — informational only; volfit's analytics stay on the
de-Americanized European fit.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from volfit.data.massive import MassiveProvider

router = APIRouter()


class MassiveIvPoint(BaseModel):
    """One contract's Massive IV/greeks (camelCase per the frontend contract)."""

    expiry: str
    strike: float | None
    callPut: str
    iv: float
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    openInterest: int | None = None
    dayClose: float | None = None


class MassiveIvResponse(BaseModel):
    ticker: str
    points: list[MassiveIvPoint]


@router.get("/massive/iv/{ticker}", response_model=MassiveIvResponse)
def get_massive_iv(
    ticker: str, request: Request, expiry: str | None = Query(None)
) -> MassiveIvResponse:
    """Massive IV/greeks for a ticker, optionally restricted to one expiry."""
    provider = request.app.state.volfit.provider
    if not isinstance(provider, MassiveProvider):
        raise HTTPException(
            status_code=404, detail="Massive IV overlay requires the Massive provider"
        )
    if ticker.upper() not in provider.list_tickers():
        raise HTTPException(status_code=404, detail=f"unknown ticker {ticker!r}")
    expiries: list[date] | None = None
    if expiry:
        try:
            expiries = [date.fromisoformat(expiry)]
        except ValueError:
            raise HTTPException(status_code=422, detail=f"bad expiry {expiry!r}") from None
    points = [MassiveIvPoint(**row) for row in provider.iv_surface(ticker, expiries)]
    return MassiveIvResponse(ticker=ticker.upper(), points=points)

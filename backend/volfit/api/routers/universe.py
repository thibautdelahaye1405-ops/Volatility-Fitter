"""GET /universe — available tickers and expiry ladders (ROADMAP Phase 5).

This backs the product's universe-selection screen: the user picks among all
asset tickers and expiries the provider can serve.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from volfit.api.schemas import ExpiryInfo, UniverseResponse

router = APIRouter()


@router.get("/universe", response_model=UniverseResponse)
def get_universe(request: Request) -> UniverseResponse:
    state = request.app.state.volfit
    tickers = state.provider.list_tickers()
    expiries = {
        ticker: [
            ExpiryInfo(expiry=expiry.isoformat(), t=state.year_fraction(expiry))
            for expiry in sorted(state.forwards(ticker))
        ]
        for ticker in tickers
    }
    return UniverseResponse(
        asOf=state.reference_date.isoformat(), tickers=tickers, expiries=expiries
    )

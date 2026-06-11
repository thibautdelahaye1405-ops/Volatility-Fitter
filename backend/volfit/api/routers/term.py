"""POST /term/{ticker} — ATM term structure with event-dilated calendar.

Body is a TermStructureRequest {fitMode?, events?, eventsEnabled?}; event
specs are validated by pydantic (time > 0, weight >= 0, so malformed events
are 422s before any fitting). Unknown tickers map to 404 as everywhere else.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import analytics
from volfit.api.schemas import TermStructureRequest, TermStructureResponse
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.post("/term/{ticker}", response_model=TermStructureResponse)
def term_structure(
    ticker: str, body: TermStructureRequest, request: Request
) -> TermStructureResponse:
    try:
        return analytics.term_structure(request.app.state.volfit, ticker, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

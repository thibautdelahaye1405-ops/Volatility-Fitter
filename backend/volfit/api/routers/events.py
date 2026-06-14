"""Per-ticker event-calendar endpoints (shared event-time dilation input).

GET /events/{ticker}  -> EventCalendar   (empty list when never set)
PUT /events/{ticker}  body EventCalendar -> EventCalendar

The event calendar drives the term-structure's event-time dilation
(volfit.calib.event_time). Storing it per ticker on AppState makes it one
shared source of truth that survives Parametric tab switches and ticker
changes, instead of living only in the Term sub-tab's view-local state. Event
specs are validated by pydantic (time > 0, weight >= 0), so malformed
calendars are 422s.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import event_autocalib
from volfit.api.schemas import EventAutocalibrateRequest, EventCalendar
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/events/{ticker}", response_model=EventCalendar)
def get_events(ticker: str, request: Request) -> EventCalendar:
    state = request.app.state.volfit
    return EventCalendar(events=state.events(ticker))


@router.put("/events/{ticker}", response_model=EventCalendar)
def put_events(ticker: str, body: EventCalendar, request: Request) -> EventCalendar:
    state = request.app.state.volfit
    return EventCalendar(events=state.set_events(ticker, body.events))


@router.post("/events/{ticker}/autocalibrate", response_model=EventCalendar)
def autocalibrate_events_route(
    ticker: str, body: EventAutocalibrateRequest, request: Request
) -> EventCalendar:
    try:
        return event_autocalib.autocalibrate(request.app.state.volfit, ticker, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

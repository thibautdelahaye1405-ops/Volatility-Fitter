"""Universe endpoints: enumerate, search, add/remove tickers, named universes.

Backs the product's universe-selection screen (frontend Universe tab): the
user searches the provider catalogue, adds/removes tickers from the active
universe, and saves/loads named universes. Each expiry rung carries its
expiry-type tag (volfit.data.expiries) for bulk selection by type. Logic and
the VolStore persistence live in volfit.api.universe_service.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from volfit.api import universe_service as svc
from volfit.api.schemas import UniverseResponse
from volfit.api.schemas_universe import (
    AddTickerRequest,
    ExpiryPickerResponse,
    SavedUniversesResponse,
    SetExpiriesRequest,
    SymbolSearchResponse,
)
from volfit.api.state import UnknownNodeError

router = APIRouter()


def _state(request: Request):
    return request.app.state.volfit


@router.get("/universe", response_model=UniverseResponse)
def get_universe(request: Request) -> UniverseResponse:
    return svc.universe_payload(_state(request))


@router.get("/universe/search", response_model=SymbolSearchResponse)
def search_symbols(
    request: Request, q: str = Query("", min_length=0), limit: int = Query(10, ge=1, le=25)
) -> SymbolSearchResponse:
    return svc.search(_state(request), q, limit)


@router.post("/universe/tickers", response_model=UniverseResponse)
def add_ticker(body: AddTickerRequest, request: Request) -> UniverseResponse:
    try:
        return svc.add_ticker(_state(request), body.symbol)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.delete("/universe/tickers/{symbol}", response_model=UniverseResponse)
def remove_ticker(symbol: str, request: Request) -> UniverseResponse:
    try:
        return svc.remove_ticker(_state(request), symbol)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:  # removing the last ticker
        raise HTTPException(status_code=422, detail=str(exc)) from None


# --------------------------------------------------------- expiry selection
@router.get("/universe/{ticker}/expiries", response_model=ExpiryPickerResponse)
def get_expiries(ticker: str, request: Request) -> ExpiryPickerResponse:
    try:
        return svc.expiry_picker(_state(request), ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put("/universe/{ticker}/expiries", response_model=ExpiryPickerResponse)
def put_expiries(
    ticker: str, body: SetExpiriesRequest, request: Request
) -> ExpiryPickerResponse:
    try:
        return svc.set_expiries(_state(request), ticker, body.expiries)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:  # empty selection / malformed date
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/universe/{ticker}/expiries/reset", response_model=ExpiryPickerResponse)
def reset_expiries(ticker: str, request: Request) -> ExpiryPickerResponse:
    try:
        return svc.reset_expiries(_state(request), ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


# --------------------------------------------------------- named universes
@router.get("/universes", response_model=SavedUniversesResponse)
def list_saved(request: Request) -> SavedUniversesResponse:
    return svc.saved(_state(request))


@router.post("/universes/{name}", response_model=SavedUniversesResponse)
def save_universe(name: str, request: Request) -> SavedUniversesResponse:
    try:
        return svc.save_current(_state(request), name)
    except ValueError as exc:  # no store configured / empty name
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.delete("/universes/{name}", response_model=SavedUniversesResponse)
def delete_universe(name: str, request: Request) -> SavedUniversesResponse:
    try:
        return svc.delete_saved(_state(request), name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/universe/load/{name}", response_model=UniverseResponse)
def load_universe(name: str, request: Request) -> UniverseResponse:
    try:
        return svc.load_saved(_state(request), name)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:  # no store / no usable tickers
        raise HTTPException(status_code=422, detail=str(exc)) from None

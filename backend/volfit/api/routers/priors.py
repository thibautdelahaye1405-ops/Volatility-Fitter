"""Prior-framework endpoints: save all current calibrations, report availability.

* ``POST /priors/save-all`` snapshots every active ticker's calibrated surface
  (per-expiry model + LQD backbone + market state + LV grid) and persists it.
* ``GET  /priors`` reports, per active ticker, what is saved (timestamps + ages,
  node count, whether an LV surface was captured) — backs the Fetch button.
* ``GET  /priors/history/{ticker}`` lists the ticker's saved-snapshot history
  metadata (V3.9 item 8 evidence) — read-only, newest save first.

Fetching / transporting / anchoring on these snapshots are Phase B/C.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import priors
from volfit.api.schemas import FitMode
from volfit.api.schemas_prior import (
    PriorFetchResult,
    PriorHistoryEntry,
    PriorHistoryResponse,
    PriorSaveResult,
    PriorStatus,
)

router = APIRouter()


@router.post("/priors/save-all", response_model=PriorSaveResult)
def save_all_priors(request: Request, fitMode: FitMode = "mid") -> PriorSaveResult:
    return priors.save_all(request.app.state.volfit, fitMode)


@router.post("/priors/fetch", response_model=PriorFetchResult)
def fetch_priors(request: Request, fitMode: FitMode = "mid") -> PriorFetchResult:
    """Resolve each ticker's prior via the freshness ladder (Saved -> 15-min-before
    -previous-close -> previous-close) and set it active (the dotted overlay/anchor)."""
    return priors.fetch_all(request.app.state.volfit, fitMode)


@router.get("/priors", response_model=PriorStatus)
def get_priors(request: Request) -> PriorStatus:
    return priors.prior_status(request.app.state.volfit)


@router.get("/priors/history/{ticker}", response_model=PriorHistoryResponse)
def get_prior_history(ticker: str, request: Request) -> PriorHistoryResponse:
    """The ticker's saved-snapshot history metadata, newest save first
    (V3.9 item 8 evidence). Read-only and poll-safe — nothing is fitted and
    the stored surface documents are never deserialized. 404 for a ticker
    outside the known universe; an empty list when nothing has been saved.
    entries[0] is always the same snapshot GET /priors reports as latest."""
    state = request.app.state.volfit
    symbol = ticker.upper()
    if not state.known_ticker(symbol):
        raise HTTPException(status_code=404, detail=f"unknown ticker {symbol}")
    return PriorHistoryResponse(
        ticker=symbol,
        entries=[PriorHistoryEntry(**e) for e in state.list_prior_snapshots(symbol)],
    )

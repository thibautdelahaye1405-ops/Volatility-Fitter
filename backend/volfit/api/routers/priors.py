"""Prior-framework endpoints: save all current calibrations, report availability.

* ``POST /priors/save-all`` snapshots every active ticker's calibrated surface
  (per-expiry model + LQD backbone + market state + LV grid) and persists it.
* ``GET  /priors`` reports, per active ticker, what is saved (timestamps, node
  count, whether an LV surface was captured) — backs the Fetch button's state.

Fetching / transporting / anchoring on these snapshots are Phase B/C.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from volfit.api import priors
from volfit.api.schemas import FitMode
from volfit.api.schemas_prior import PriorFetchResult, PriorSaveResult, PriorStatus

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

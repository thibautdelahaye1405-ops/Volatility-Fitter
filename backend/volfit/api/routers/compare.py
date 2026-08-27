"""Model-comparison endpoint (V3.2 item 12).

GET /smiles/{ticker}/{expiry}/compare?models=lqd,svi,sigmoid,essvi&fit_mode=...
-> CompareResponse: every requested family fitted to the node's prepared
quotes with uniform metrics + per-family analytic validity ("essvi" is the
compare-only Gatheral-Jacquier SSVI slice). READ-ONLY with respect to the
committed calibration (volfit.api.compare docstring): a compare never moves
the calibrated pointer, never creates a fit-cache entry and never bumps a
version — the extra fits live in the endpoint's own side cache. 422 for an
unknown/empty models CSV; 404 for an unknown node.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import compare
from volfit.api.schemas import FitMode
from volfit.api.schemas_compare import CompareResponse
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/smiles/{ticker}/{expiry}/compare", response_model=CompareResponse)
def get_compare(
    ticker: str,
    expiry: str,
    request: Request,
    models: str = "lqd,svi,sigmoid,essvi",
    fit_mode: FitMode = "mid",
) -> CompareResponse:
    """Side-by-side LQD / SVI-JW / MCS / eSSVI comparison on one node (lazy:
    the UI fetches only when the Compare view opens — up to 3 extra fits,
    cached)."""
    requested: list[str] = []
    for name in (m.strip().lower() for m in models.split(",")):
        if name and name not in requested:
            requested.append(name)
    unknown = [m for m in requested if m not in compare.COMPARE_MODELS]
    if not requested or unknown:
        raise HTTPException(
            status_code=422,
            detail=f"models must be a CSV subset of {list(compare.COMPARE_MODELS)}"
            + (f"; unknown: {unknown}" if unknown else "; got none"),
        )
    state = request.app.state.volfit
    try:
        with state.activity.activity("compare", f"Comparing models on {ticker} {expiry}"):
            return compare.compare_payload(state, ticker, expiry, tuple(requested), fit_mode)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

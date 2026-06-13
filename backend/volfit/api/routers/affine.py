"""POST /fit/affine/{ticker} — direct local-vol-affine surface calibration.

Calibrates the piecewise-affine local-variance surface straight to the
ticker's option quotes and returns the nodal surface, the per-expiry
reconstructed arbitrage-free smiles and the fit/no-arb diagnostics. The
heavy lifting and the per-request cache live in volfit.api.affine_fit.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api.affine_fit import affine_payload
from volfit.api.schemas_affine import AffineFitRequest, AffineFitResponse
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.post("/fit/affine/{ticker}", response_model=AffineFitResponse)
def fit_affine(
    ticker: str, request: Request, body: AffineFitRequest | None = None
) -> AffineFitResponse:
    try:
        return affine_payload(request.app.state.volfit, ticker, body or AffineFitRequest())
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:  # too few expiries / quotes to fit a surface
        raise HTTPException(status_code=422, detail=str(exc)) from None

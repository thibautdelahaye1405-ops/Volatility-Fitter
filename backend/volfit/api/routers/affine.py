"""POST /fit/affine/{ticker} (+ /density, /term, /table) — local-vol-affine fit.

Calibrates the piecewise-affine local-variance surface straight to the
ticker's option quotes and returns the nodal surface, the per-expiry
reconstructed arbitrage-free smiles and the fit/no-arb diagnostics. The
heavy lifting and the per-request cache live in volfit.api.affine_fit.

The /density, /term and /table sub-routes derive the Local Vol workspace's
Parametric-style views from the SAME cached fit (volfit.api.affine_views); they
take the AffineFitRequest body so they hit the same cache key as the surface fit.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api.affine_fit import affine_payload, grid_info, optimal_grid_size
from volfit.api.affine_views import affine_density, affine_table, affine_term
from volfit.api.schemas import DensityResponse, TableResponse, TermStructureResponse
from volfit.api.schemas_affine import (
    AffineFitRequest,
    AffineFitResponse,
    GridInfo,
    OptimalGridSize,
)
from volfit.api.state import UnknownNodeError

router = APIRouter()


def _body(body: AffineFitRequest | None) -> AffineFitRequest:
    return body or AffineFitRequest()


@router.get("/fit/affine/{ticker}/optimal-size", response_model=OptimalGridSize)
def affine_optimal_size(ticker: str, request: Request) -> OptimalGridSize:
    try:
        return optimal_grid_size(request.app.state.volfit, ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/fit/affine/{ticker}/grid-info", response_model=GridInfo)
def affine_grid_info(ticker: str, request: Request) -> GridInfo:
    """The actual vertex grid the current Options produce (for the Options panel)."""
    try:
        return grid_info(request.app.state.volfit, ticker)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/fit/affine/{ticker}", response_model=AffineFitResponse)
def fit_affine(
    ticker: str, request: Request, body: AffineFitRequest | None = None
) -> AffineFitResponse:
    try:
        return affine_payload(request.app.state.volfit, ticker, _body(body))
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:  # too few expiries / quotes to fit a surface
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/fit/affine/{ticker}/term", response_model=TermStructureResponse)
def fit_affine_term(
    ticker: str, request: Request, body: AffineFitRequest | None = None
) -> TermStructureResponse:
    try:
        return affine_term(request.app.state.volfit, ticker, _body(body))
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/fit/affine/{ticker}/density", response_model=DensityResponse)
def fit_affine_density(
    ticker: str, expiry: str, request: Request, body: AffineFitRequest | None = None
) -> DensityResponse:
    try:
        return affine_density(request.app.state.volfit, ticker, expiry, _body(body))
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:  # too few expiries, or unknown expiry
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/fit/affine/{ticker}/table", response_model=TableResponse)
def fit_affine_table(
    ticker: str, expiry: str, request: Request, body: AffineFitRequest | None = None
) -> TableResponse:
    try:
        return affine_table(request.app.state.volfit, ticker, expiry, _body(body))
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

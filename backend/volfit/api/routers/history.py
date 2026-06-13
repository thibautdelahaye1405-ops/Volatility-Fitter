"""Fit-history endpoint ([REQ 2026-06-12] fit time-series scaffold).

GET /history/{ticker}/{tenor_days}?fit_mode=... -> HistoryResponse: the
per-snapshot trajectory of fitted handles at the listed expiry nearest to
``tenor_days``, read from the persisted `fits` table (volfit.api.history).
Empty points (not 404) when persistence is unconfigured or the store has no
rows yet; unknown tickers are 404s per the API-wide pattern.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import history
from volfit.api.schemas import FitMode, HistoryResponse
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/history/{ticker}/{tenor_days}", response_model=HistoryResponse)
def get_history(
    ticker: str, tenor_days: int, request: Request, fit_mode: FitMode = "mid"
) -> HistoryResponse:
    try:
        return history.history_payload(
            request.app.state.volfit, ticker, tenor_days, fit_mode
        )
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

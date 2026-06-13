"""Fit time-series schemas ([REQ 2026-06-12] fit history scaffold).

Pydantic models for GET /history/{ticker}/{tenor_days}: the per-snapshot
trajectory of one constant-maturity tenor, assembled from the calibrations
persisted into the VolStore `fits` table (volfit.api.history). Split out of
volfit.api.schemas to respect the 400-line file policy; schemas.py
re-exports everything here, so callers keep a single import surface. Field
names are camelCase per the frontend contract (charting UI deferred).
"""

from __future__ import annotations

from pydantic import BaseModel


class HistoryPoint(BaseModel):
    """One snapshot's fitted handles at the requested tenor.

    ``expiry`` is the listed expiry whose days-to-expiry (from the snapshot
    date) was nearest to the requested tenor — constant-maturity by nearest
    rung, no interpolation at scaffold stage.
    """

    ts: str  # snapshot timestamp ISO (the time-series key)
    expiry: str  # ISO expiry actually used for this tenor point
    t: float  # year fraction of that expiry at fit time
    atmVol: float
    skew: float
    curvature: float
    varSwapVol: float
    maxIvErrorBp: float
    forward: float


class HistoryResponse(BaseModel):
    """Time series of fitted handles, sorted by snapshot timestamp."""

    ticker: str
    tenorDays: int
    fitMode: str
    points: list[HistoryPoint]

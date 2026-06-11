"""Pydantic schemas for the volfit HTTP API (ROADMAP Phase 5).

The smile payload field names are FROZEN against the frontend contract in
frontend/src/lib/mockData.ts: `SmilePoint`, `QuoteBand`, `SmileDiagnostics`
and `SmileData` must serialize to exactly the camelCase shapes the React
Smile Viewer already consumes, so swapping its mock module for live API
calls is a one-line change. Request/response models for the surface fit,
graph solver and SSR scenario endpoints follow the same convention.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from volfit.dynamics.ssr import Regime

#: Quote-weighting modes for slice calibration (product spec: fit to mid,
#: fit to bid-ask, or fit to a haircut bid-ask).
FitMode = Literal["mid", "bidask", "haircut"]


# ------------------------------------------------------------- smile payload
class SmilePoint(BaseModel):
    """One point of a continuous model curve in (log-moneyness, vol) space."""

    k: float
    vol: float


class QuoteBand(BaseModel):
    """One market quote as a bid/ask band of implied vols at log-moneyness k.

    ``index`` is the quote's position in the prepared array — stable for the
    session and the key used by quote edits. ``excluded`` quotes are dropped
    from calibration but still listed (the UI dims them); ``amended`` flags a
    user-overridden mid (bid/ask stay the original market band).
    """

    k: float
    bid: float
    ask: float
    mid: float
    index: int
    excluded: bool
    amended: bool


class SmileDiagnostics(BaseModel):
    """Headline diagnostics displayed next to the smile chart."""

    atmVol: float
    skew: float
    curvature: float
    aLeft: float  # endpoint scales A_L, A_R (eqs. AL, AR of the LQD note)
    aRight: float
    leeLeft: float  # Lee wing slopes beta_L, beta_R (eqs. betaL, betaR)
    leeRight: float
    varSwapVol: float


class SmileData(BaseModel):
    """Everything the Smile Viewer needs for one (underlying, expiry) node."""

    ticker: str
    expiry: str  # ISO date
    T: float  # year fraction to expiry
    forward: float
    model: list[SmilePoint]
    prior: list[SmilePoint]
    quotes: list[QuoteBand]
    kMin: float
    kMax: float
    diagnostics: SmileDiagnostics
    canUndo: bool  # quote-edit session undo/redo availability
    canRedo: bool  # (both False when the node has no edit session yet)


# ------------------------------------------------------------------ universe
class ExpiryInfo(BaseModel):
    """One listed expiry of a ticker with its year fraction."""

    expiry: str
    t: float


class UniverseResponse(BaseModel):
    """Available tickers and their expiry ladders."""

    asOf: str
    tickers: list[str]
    expiries: dict[str, list[ExpiryInfo]]


class PriorSavedResponse(BaseModel):
    """Acknowledgement of a prior-curve save."""

    saved: bool = True


# --------------------------------------------------------------- quote edits
class QuoteEditRequest(BaseModel):
    """One quote-set edit on a smile node (fit-session model).

    ``exclude``/``include`` require ``index``; ``amend`` requires ``index``
    and ``mid`` (the replacement mid *implied vol*, e.g. 0.21); ``reset``
    clears every edit. Semantic validation (range, missing fields, the
    minimum-quote guard) lives in volfit.api.session.EditSession.apply.
    """

    action: Literal["exclude", "include", "amend", "reset"]
    index: int | None = None
    mid: float | None = None


# --------------------------------------------------------------- surface fit
class SurfaceFitRequest(BaseModel):
    """Fit all expiries of one ticker, sequential and calendar-constrained."""

    ticker: str
    fitMode: FitMode = "mid"
    enforceCalendar: bool = True


class SurfaceFitResponse(BaseModel):
    """Per-expiry fits plus calendar diagnostics, nearest to farthest."""

    ticker: str
    expiries: list[str]
    calendarResiduals: list[float]  # max_alpha (G_near - G_far), 0 for first
    maxIvErrorBp: list[float]
    smiles: list[SmileData]


# --------------------------------------------------------------- graph solve
class GraphObservation(BaseModel):
    """One observed handle shift on a smile node, in absolute handle units."""

    ticker: str
    expiry: str
    dAtmVol: float
    dSkew: float = 0.0
    dCurv: float = 0.0


class GraphSolveRequest(BaseModel):
    """Propagate sparse handle observations through the smile universe."""

    observations: list[GraphObservation] = Field(min_length=1)
    etaScale: float = 1.0  # multiplies the directed-smoothness weight eta


class GraphNodeResult(BaseModel):
    """Posterior ATM-vol summary for one node of the universe."""

    ticker: str
    expiry: str
    t: float
    baseAtmVol: float
    postAtmVol: float
    shiftBp: float
    sd: float
    bandLo: float  # 95% credible band on the posterior ATM vol
    bandHi: float
    observed: bool


class GraphSolveResponse(BaseModel):
    """Posterior field over every node of the smile universe."""

    nodes: list[GraphNodeResult]


class GraphNodeInfo(BaseModel):
    """Baseline (pre-solve) fitted handles of one universe node."""

    ticker: str
    expiry: str
    t: float
    atmVol: float
    skew: float
    curvature: float


class GraphNodesResponse(BaseModel):
    """The full smile universe with baseline handles (Graph Viewer lattice)."""

    nodes: list[GraphNodeInfo]


# ------------------------------------------------------------------ scenario
class ScenarioRequest(BaseModel):
    """SSR scenario: shift one smile for a spot move under a dynamics regime.

    ``regime`` is a named regime ("sticky_moneyness" | "sticky_strike" |
    "sticky_local_vol") or a custom numeric SSR value.
    """

    ticker: str
    expiry: str
    spotReturn: float
    regime: Regime | float = Regime.STICKY_STRIKE
    fitMode: FitMode = "mid"


class ScenarioResponse(BaseModel):
    """Base and shifted smiles on a shared k grid, plus the resolved SSR."""

    k: list[float]
    baseVol: list[float]
    shiftedVol: list[float]
    ssr: float
    regime: str

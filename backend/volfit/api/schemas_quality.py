"""Response models for the universe fit-quality dashboard (GET /quality).

The dashboard aggregates CACHED calibrations only — per-node fit RMS, arb
flags (Lee wings, adjacent-expiry calendar), staleness, filter state and the
per-ticker LV surface health — into one publish-readiness screen. Reading it
never triggers a fit (volfit.api.quality guards on the calibrated pointers),
so it is as cheap as a status poll and safe to refresh on every calibration
epoch. Mirrors the schemas.py / schemas_affine.py split.
"""

from __future__ import annotations

from pydantic import BaseModel


class QualityNode(BaseModel):
    """One lit (ticker, expiry) node's quality row."""

    ticker: str
    expiry: str  # ISO date
    tau: float  # variance-time maturity (0 when no fit)
    hasFit: bool  # calibrated at least once (gated nodes start False)
    stale: bool  # inputs drifted since the last calibration
    model: str  # displayed model id ("lqd" | "svi" | "sigmoid")
    nQuotes: int
    rmsBp: float  # weighted RMS vol error vs the fit target, in vol bp
    maxIvBp: float  # worst per-quote IV error of the displayed fit, in vol bp
    atmVol: float
    skew: float
    leeLeft: float  # total-variance wing slopes (Lee bound: <= 2)
    leeRight: float
    leeOk: bool
    calendarViolation: float  # worst convex-order violation vs the previous fitted expiry
    calendarOk: bool
    varSwapQuoted: bool  # an active var-swap quote participates in this node's fit
    filterActive: bool  # observation filter holds a committed state for this node
    filterContaminated: bool  # measurement taken while a persistence prior was active
    ready: bool  # publish-ready under the report's rule (see QualityReport)
    issues: list[str]  # human-readable reasons ready is False (empty when ready)


class LvQuality(BaseModel):
    """One ticker's cached LV (affine) surface health."""

    hasFit: bool
    stale: bool
    rmsIvErrorBp: float
    maxIvErrorBp: float
    surfaceRmsBp: float  # pooled weighted RMS (same basis as the parametric rows)
    arbitrageFree: bool
    calendarViolations: int  # adjacent-maturity price decreases on the PDE grid
    worstMinDensity: float  # most negative per-expiry min density (butterfly proxy)


class QualityTicker(BaseModel):
    """Per-ticker rollup of its lit nodes + LV surface."""

    ticker: str
    nodes: int  # lit nodes
    fitted: int
    stale: int
    surfaceRmsBp: float  # quote-weight-pooled RMS across the fitted nodes
    worstNodeRmsBp: float
    arbFlags: int  # nodes failing Lee or calendar
    ready: int  # publish-ready node count
    lv: LvQuality | None = None  # None when LV disabled / never calibrated


class QualitySummary(BaseModel):
    """Universe headline tiles."""

    tickers: int
    litNodes: int
    darkNodes: int
    fitted: int
    stale: int
    noFit: int
    readyNodes: int
    arbFlags: int
    medianRmsBp: float  # over fitted nodes (0 when none)
    worstRmsBp: float
    filterMode: str  # observation-filter mode ("off" | "overlay" | "active")
    priorMode: str  # prior-persistence mode
    lvTickers: int  # tickers with a cached LV surface
    lvArbFree: int


class QualityReport(BaseModel):
    """GET /quality response.

    Publish-readiness rule (per node): hasFit AND NOT stale AND leeOk AND
    calendarOk AND rmsBp <= rmsBudgetBp. ``issues`` lists every failed check
    per node; ``filterContaminated`` is advisory and never blocks readiness.
    """

    fitMode: str
    rmsBudgetBp: float
    summary: QualitySummary
    tickers: list[QualityTicker]
    nodes: list[QualityNode]

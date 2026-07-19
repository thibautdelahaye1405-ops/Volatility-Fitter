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
    # --- R5 (committee point 8): the same violation in desk units, plus the
    # cheapest offending trade. None whenever there is no positive violation
    # (or the unit is unavailable — e.g. no tick size on synthetic chains).
    calendarWorstStrike: float | None = None  # K* of the sell-near/buy-far spread
    calendarViolationCurrency: float | None = None  # per share, discounted
    calendarViolationTicks: float | None = None  # currency / option tick size
    calendarViolationSpreadFrac: float | None = None  # vs local bid-ask price width
    # --- extrapolated-region arb (Notes 09/10 Phase 1): MEASURED, advisory only —
    # never gates ``ready``. Envelope = beyond the traded strikes, while the
    # model's own OTM value >= 1 bp of forward ("extrapolated but not worthless").
    extrapMinG: float | None = None  # worst Durrleman g over the envelope (>=0 clean)
    extrapOk: bool = True  # extrapMinG >= 0 (or no envelope)
    extrapCalBp: float | None = None  # worst calendar crossing vs prev expiry, vol bp
    extrapCalOk: bool = True  # extrapCalBp ~ 0 (or no previous slice)
    wingOrderOk: bool | None = None  # asymptotic Lee-slope order vs prev (far >= near)
    varSwapQuoted: bool  # an active var-swap quote participates in this node's fit
    filterActive: bool  # observation filter holds a committed state for this node
    filterContaminated: bool  # measurement taken while a persistence prior was active
    #: Age (minutes) of the ticker's loaded LIVE chain (volfit.api.data_age);
    #: None when not applicable (historical as-of, synthetic, nothing fetched).
    #: Red-stale data (past OptionsSettings.dataAgeRedMin) fails readiness.
    dataAgeMin: float | None = None
    #: Quarantined-quote counts by reason (quote prep, R1 item 6): tick_floor,
    #: below_intrinsic, missing_or_crossed, wing, ... ADVISORY — the screens
    #: predate this record; naming the drops never changes readiness.
    screened: dict[str, int] = {}
    #: Kept quotes whose Black vega sits below the diagnostic floor — their
    #: IV residuals are numerically meaningless (price space is authoritative).
    vegaFloored: int = 0
    ready: bool  # publish-ready under the report's rule (see QualityReport)
    issues: list[str]  # human-readable reasons ready is False (empty when ready)


class LvQuality(BaseModel):
    """One ticker's cached LV (affine) surface health."""

    hasFit: bool
    stale: bool
    rmsIvErrorBp: float
    maxIvErrorBp: float
    surfaceRmsBp: float  # pooled weighted RMS (same basis as the parametric rows)
    #: HONEST fit RMS (bp): the calibrated surface repriced on a CONVERGED
    #: operator (dt/4, dx/2 — models.localvol.reprice). In-operator rms is
    #: blind to time-discretization error (the optimizer compensates), so a
    #: large gap between this and rmsIvErrorBp flags an operator-compensated
    #: surface — judge the LV fit by THIS number.
    rmsConvergedBp: float = 0.0
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
    extrapFlags: int = 0  # nodes with extrapolated-region arb (advisory)
    dataAgeMin: float | None = None  # loaded live-chain age, minutes (see QualityNode)
    #: Carry identifiability (CarryCurve v0, ADVISORY): expiries with a
    #: defensible option-implied borrow read vs the calm "unidentified" rest.
    #: Gating on carry confidence arrives with the R2 joint borrow/de-Am work.
    carryIdentified: int = 0
    carryUnidentified: int = 0
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
    extrapFlags: int = 0  # nodes with extrapolated-region arb (advisory, not gating)
    medianRmsBp: float  # over fitted nodes (0 when none)
    worstRmsBp: float
    filterMode: str  # observation-filter mode ("off" | "overlay" | "active")
    priorMode: str  # prior-persistence mode
    lvTickers: int  # tickers with a cached LV surface
    lvArbFree: int
    #: Tickers whose loaded live chain is red-stale (age past dataAgeRedMin) —
    #: their nodes are not publish-ready however good the fits look.
    staleDataTickers: int = 0


class QualityReport(BaseModel):
    """GET /quality response.

    Publish-readiness rule (per node): hasFit AND NOT stale AND leeOk AND
    calendarOk AND rmsBp <= rmsBudgetBp AND the ticker's live data is not
    red-stale (dataAgeMin < OptionsSettings.dataAgeRedMin, when applicable).
    ``issues`` lists every failed check per node; ``filterContaminated`` and
    amber data age are advisory and never block readiness.
    """

    fitMode: str
    rmsBudgetBp: float
    summary: QualitySummary
    tickers: list[QualityTicker]
    nodes: list[QualityNode]

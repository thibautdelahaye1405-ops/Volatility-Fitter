"""Response models for GET /smiles/{ticker}/{expiry}/compare (V3.2 item 12).

Side-by-side model comparison LQD / SVI-JW / Multi-Core Sigmoid / eSSVI
(the compare-only Gatheral-Jacquier SSVI slice, volfit.models.essvi): one
``CompareModelFit`` per requested family, each carrying the fitted curve on
the smile display grid plus the uniform metric set the offline adjudication
instrument reports (backtest.dispatch.fit_node) — precision, ATM handles,
Lee wing slopes, var-swap and the per-family ANALYTIC butterfly validity
(volfit.models.diagnostics.analytic_butterfly: density positivity for LQD,
exact Durrleman g for SVI / MCS / eSSVI). Reading is STRICTLY fit-pointer-neutral
(the quality.py doctrine); results live in the endpoint's own side cache.
Mirrors the schemas_quality / schemas_weights small-module split
(file-size policy). All metric fields are optional-friendly: ``None`` means
not defined / not finite for that family, never a wire break.
"""

from __future__ import annotations

from pydantic import BaseModel

from volfit.api.schemas import SmilePoint


class CompareValidity(BaseModel):
    """Per-family analytic no-butterfly signal of one compared fit."""

    #: "density" (LQD: risk-neutral density minimum, >= 0 by construction) |
    #: "g" (SVI / MCS / eSSVI: exact Durrleman g minimum, < 0 => arb) | "recon"
    #: (no analytic form — no verdict).
    kind: str
    #: The minimum of the family's analytic quantity over the traded range.
    minValue: float | None = None
    #: minValue >= -tolerance for the kind; None when kind == "recon".
    certified: bool | None = None


class TailMatchInfo(BaseModel):
    """What the tail-matching toggles (volfit.calib.tails) did on this compare:
    the flags asked for, the ones that could apply, the reference numbers the
    straight-wing families were pulled onto, and why a flag was dropped."""

    requested: list[str] = []  # subset of ("varswap", "lee", "edge"), wire order
    applied: list[str] = []  # the constraints the SVI-JW / MCS rows carried
    target: str = "lqd"  # the reference family
    #: False when the reference's tails are generalized (LQD alpha > 0): its
    #: asymptotic Lee slope is 0, unreachable for a straight-wing family.
    leeAvailable: bool = True
    #: True when a reference Lee slope was pulled under the family cap.
    leeClamped: bool = False
    #: Human note when something was dropped (Lee unavailable, LQD fit failed).
    note: str | None = None
    referenceVarSwapVol: float | None = None
    referenceLeeLeft: float | None = None
    referenceLeeRight: float | None = None
    edgeKLeft: float | None = None  # the quoted edges the "edge" flag matches at
    edgeKRight: float | None = None


class CompareModelFit(BaseModel):
    """One model family's fit + uniform metrics on the compared node."""

    model: str  # family id: "lqd" | "svi" | "sigmoid" | "essvi"
    label: str  # display name ("LQD" | "SVI-JW" | "MCS" | "eSSVI")
    ok: bool = True
    error: str | None = None  # fit failure (recorded, never a 500)
    #: IV curve on the SAME display grid the smile payload uses.
    curve: list[SmilePoint] = []
    rmsBp: float | None = None  # fit-target RMS vol error (vol bp)
    maxIvBp: float | None = None  # worst per-quote |model - mid| (vol bp)
    atmVol: float | None = None
    skew: float | None = None
    leeLeft: float | None = None  # total-variance wing slopes
    leeRight: float | None = None
    #: Structural tail contract per side (volfit.models.wings): "exponential"
    #: (straight variance wing — SVI/MCS/eSSVI always; LQD at alpha = 0),
    #: "intermediate" (LQD 0 < alpha < 1/2) or "gaussian" (LQD alpha = 1/2).
    #: The wing coefficient of the exponential class is the Lee column above.
    tailLeft: str | None = None
    tailRight: str | None = None
    varSwapVol: float | None = None
    validity: CompareValidity | None = None
    nParams: int | None = None  # free parameters of the fitted slice
    fitMs: float | None = None  # ad-hoc fit wall time; None when reused
    #: True when this row reads the ACTIVE displayed family's committed
    #: record (fresh fit_key) instead of an ad-hoc fit — read-only reuse.
    reused: bool = False
    #: The tail-matching constraints this row's fit carried (empty for the
    #: reference LQD, the eSSVI yardstick and every unconstrained fit).
    tailMatched: list[str] = []


class CompareResponse(BaseModel):
    """All requested families fitted to one (ticker, expiry) node."""

    ticker: str
    expiry: str  # ISO date, as requested
    fitMode: str
    activeModel: str  # FitSettings.model at compare time
    models: list[CompareModelFit] = []
    #: Present whenever tail matching was requested (even if nothing applied).
    tailMatch: TailMatchInfo | None = None

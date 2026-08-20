"""Response models for GET /smiles/{ticker}/{expiry}/compare (V3.2 item 12).

Side-by-side model comparison LQD / SVI-JW / Multi-Core Sigmoid: one
``CompareModelFit`` per requested family, each carrying the fitted curve on
the smile display grid plus the uniform metric set the offline adjudication
instrument reports (backtest.dispatch.fit_node) — precision, ATM handles,
Lee wing slopes, var-swap and the per-family ANALYTIC butterfly validity
(volfit.models.diagnostics.analytic_butterfly: density positivity for LQD,
exact Durrleman g for SVI / MCS). Reading is STRICTLY fit-pointer-neutral
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
    #: "g" (SVI / MCS: exact Durrleman g minimum, < 0 => arb) | "recon"
    #: (no analytic form — no verdict).
    kind: str
    #: The minimum of the family's analytic quantity over the traded range.
    minValue: float | None = None
    #: minValue >= -tolerance for the kind; None when kind == "recon".
    certified: bool | None = None


class CompareModelFit(BaseModel):
    """One model family's fit + uniform metrics on the compared node."""

    model: str  # family id: "lqd" | "svi" | "sigmoid"
    label: str  # display name ("LQD" | "SVI-JW" | "MCS")
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
    varSwapVol: float | None = None
    validity: CompareValidity | None = None
    nParams: int | None = None  # free parameters of the fitted slice
    fitMs: float | None = None  # ad-hoc fit wall time; None when reused
    #: True when this row reads the ACTIVE displayed family's committed
    #: record (fresh fit_key) instead of an ad-hoc fit — read-only reuse.
    reused: bool = False


class CompareResponse(BaseModel):
    """All requested families fitted to one (ticker, expiry) node."""

    ticker: str
    expiry: str  # ISO date, as requested
    fitMode: str
    activeModel: str  # FitSettings.model at compare time
    models: list[CompareModelFit] = []

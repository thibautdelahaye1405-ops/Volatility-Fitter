"""Market-settings and forward-mode schemas ([REQ 2026-06-12]).

Pydantic models for GET/PUT /settings/market/{ticker} (rate + dividend model
per ticker) and GET/PUT /forwards (per-expiry forward policy with side-by-
side parity/theoretical/manual diagnostics). Split out of volfit.api.schemas
to respect the 400-line file policy; schemas.py re-exports everything here,
so callers keep a single import surface. Field names are camelCase per the
frontend contract.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DividendSpec(BaseModel):
    """One discrete dividend: cash amount (or fraction of spot, under the
    proportional convention) going ex on ``exDate``."""

    exDate: str  # ISO 'YYYY-MM-DD'
    amount: float = Field(ge=0.0)

    @field_validator("exDate")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        date.fromisoformat(value)  # 422 on malformed dates, not a 500 later
        return value


class MarketSettings(BaseModel):
    """Per-ticker rate and dividend model behind theoretical forwards.

    ``rate`` is a flat continuously compounded interest rate. The dividend
    fields mirror volfit.data.dividends.DividendModel: a flat continuous
    yield, discrete dividends (absolute cash or proportional), or "mixed"
    (discrete inside ``switchYears``, continuous yield beyond).
    """

    rate: float = 0.0
    dividendMode: Literal[
        "continuous", "discrete_absolute", "discrete_proportional", "mixed"
    ] = "continuous"
    dividendYield: float = 0.0
    dividends: list[DividendSpec] = Field(default_factory=list)
    switchYears: float = Field(1.0, gt=0.0)


class ForwardPolicy(BaseModel):
    """How one (ticker, expiry) forward is resolved for fitting.

    - "parity":      the put-call-parity regression (the default);
    - "theoretical": spot grown by the ticker's MarketSettings;
    - "manual":      the user-entered ``manualForward`` (required then,
                     ignored otherwise; the discount still comes from
                     parity, falling back to exp(-rate t)).
    """

    mode: Literal["parity", "theoretical", "manual"] = "parity"
    manualForward: float | None = Field(None, gt=0.0)

    @model_validator(mode="after")
    def _manual_needs_level(self) -> "ForwardPolicy":
        if self.mode == "manual" and self.manualForward is None:
            raise ValueError("manualForward is required when mode == 'manual'")
        return self


class ForwardEntry(BaseModel):
    """Side-by-side forward diagnostics of one expiry.

    The parity block is None-filled when no parity regression exists for the
    expiry; ``activeForward``/``activeDiscount`` are what fits actually use
    under the current policy, ``activeSource`` names the winning mode.
    """

    expiry: str  # ISO date
    t: float  # year fraction
    parityForward: float | None
    parityDiscount: float | None
    parityResidualRms: float | None
    parityNStrikes: int | None
    parityNOutliers: int | None
    theoForward: float
    theoDiscount: float
    mode: str  # the stored ForwardPolicy mode
    manualForward: float | None
    activeForward: float
    activeDiscount: float
    activeSource: str
    #: Option-implied borrow (continuous, bp/yr) read off the parity-vs-
    #: theoretical forward gap at this expiry — None when carry is
    #: UNIDENTIFIED here (zero-carry chain, thin/noisy parity, or a
    #: non-parity forward mode). The COMMON state for single names; the UI
    #: presents it calmly, never as a silent zero (CarryCurve v0).
    impliedBorrowBp: float | None = None


class CarryPoint(BaseModel):
    """One expiry's carry decomposition with per-component provenance
    (roadmap R1 item 7 — CarryCurve v0).

    Sources: ``parity_implied`` (read off the option market), ``desk``
    (user-entered), ``model`` (grown from rate + dividend model), ``prior``
    (carried assumption), ``unidentified`` (no defensible read — NEVER a
    silent zero-borrow fallback)."""

    expiry: str
    t: float
    forward: float
    forwardSource: str
    discount: float
    discountSource: str
    borrowBp: float | None  # continuous implied borrow, bp/yr; None = unidentified
    borrowSource: str  # "parity_implied" | "joint_deam" | "unidentified"
    identifiable: bool  # parity carries information at this expiry
    nStrikes: int = 0  # parity-pair count behind the read
    residualRms: float = 0.0  # parity regression residual (price units)
    nOutliers: int = 0  # parity pairs dropped by the stale screen
    #: R2 item 11 (joint borrow/de-Am fixed point, GET /carry?joint=true):
    #: the EEP-consistent borrow — de-Am at the trial carry with the SAME
    #: dividend schedule in both legs, iterated to the parity/theoretical
    #: fixed point. None when not requested / not identifiable / the model
    #: mix is unsupported (proportional dividends fall back to v0). The
    #: failure accounting is the exit gate's "explicit failure rates".
    jointBorrowBp: float | None = None
    jointIterations: int | None = None
    jointConverged: bool | None = None
    jointDeamFailures: int | None = None
    #: ATM IV moved (vol bp) by 100 bp of borrow at fixed strike/price
    #: (closed form, carry_solve.iv_borrow_sensitivity_bp) — the trader's
    #: materiality read: an UNIDENTIFIED borrow matters exactly when this
    #: times the plausible borrow range is large. Uses the cached fit's ATM
    #: vol when one exists, the (weakly different) sigma->0 limit otherwise.
    ivBorrowSensBpPer100: float | None = None


class CarryCurveResponse(BaseModel):
    """GET /carry/{ticker} — the versioned per-ticker carry object.

    Aggregates what forwards/dividends/rate supply piecemeal: a discount +
    dividend + borrow view per expiry, every component tagged with its
    source and the borrow leg carrying an explicit identifiability verdict.
    Versioned by the same counters the fit caches key on, so a published
    surface can cite exactly which carry it was built against."""

    ticker: str
    spot: float
    rate: float
    rateSource: str = "desk"  # MarketSettings.rate — flat, user-owned
    dividendMode: str
    dividendSource: str  # "desk" (editor/settings) | "none"
    zeroCarry: bool = False
    forwardsVersion: int = 0
    dataVersion: int = 0
    points: list[CarryPoint]
    identified: int = 0  # expiries with a defensible borrow read
    unidentified: int = 0  # the calm, common state — never silently zero


class ForwardsResponse(BaseModel):
    """Per-expiry forward diagnostics of one ticker (Forwards panel)."""

    ticker: str
    spot: float
    exerciseStyle: str  # "european" | "american" (drives de-Americanization)
    #: True when the chain is an IV-synthesized zero-carry fallback (delayed
    #: tier, NBBO gated): parity is pinned to F = spot, D = 1 by construction
    #: and the UI should say so rather than present it as a market read.
    zeroCarry: bool = False
    entries: list[ForwardEntry]

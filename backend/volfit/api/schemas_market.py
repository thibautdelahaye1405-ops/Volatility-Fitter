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

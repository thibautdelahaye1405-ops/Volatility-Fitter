"""Plain value objects exchanged across the data layer.

Design intent (ROADMAP Phase 3): providers, storage and calibration all speak
the same immutable containers, so a chain can be scraped, persisted, reloaded
and handed to the fitter without any translation step.  Quotes carry *raw*
market fields only; derived quantities (forwards, weights, implied vols) are
computed downstream — the single exception is the trivial `mid` convenience.

Conventions
-----------
- `call_put` is a one-character flag, 'C' or 'P'.
- Missing market fields are `None` (never 0.0, which is a valid price).
- Expiries are `datetime.date`; timestamps are timezone-naive `datetime`
  in the provider's clock (UTC recommended).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class OptionQuote:
    """One raw option quote as observed from a provider.

    `mid` is `None` when the market is one-sided (missing bid or ask) or
    crossed (bid > ask) — downstream weighting treats such quotes as
    unusable for mid-based calibration.
    """

    ticker: str
    expiry: date
    strike: float
    call_put: str  # 'C' or 'P'
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.call_put not in ("C", "P"):
            raise ValueError(f"call_put must be 'C' or 'P', got {self.call_put!r}")

    @property
    def mid(self) -> float | None:
        """Mid price, or None if bid/ask is missing or the market is crossed."""
        if self.bid is None or self.ask is None:
            return None
        if self.bid > self.ask:
            return None
        return 0.5 * (self.bid + self.ask)

    @property
    def spread(self) -> float | None:
        """Quoted bid-ask spread, or None if either side is missing."""
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid


@dataclass(frozen=True)
class ChainSnapshot:
    """A full option chain for one underlying at one instant.

    The snapshot is the unit of persistence (one row in `snapshots`, many in
    `quotes`) and the unit of work for forward implication and calibration.

    `exercise_style` records what the listed contracts are: "european" (cash
    indices) or "american" (US single stocks / ETFs). American quotes carry
    an early-exercise premium on top of their European value, so quote prep
    (volfit.api.quotes) de-Americanizes them before European fitting.
    """

    ticker: str
    spot: float
    timestamp: datetime
    quotes: list[OptionQuote] = field(default_factory=list)
    exercise_style: str = "european"  # "european" | "american"
    #: True for chains SYNTHESIZED from provider per-contract IVs at zero carry
    #: (every price is Black at F = spot, D = 1, zero spread — e.g. Massive's
    #: delayed-tier fallback when NBBO quotes are gated). Such chains carry no
    #: put-call-parity information: the provider's call/put IVs embed ITS carry
    #: model, so a parity regression reads the asymmetry as a spurious
    #: forward/discount. Consumers must pin F = spot, D = 1 instead.
    zero_carry: bool = False

    def __post_init__(self) -> None:
        if self.exercise_style not in ("european", "american"):
            raise ValueError(
                "exercise_style must be 'european' or 'american', "
                f"got {self.exercise_style!r}"
            )

    def is_zero_carry(self) -> bool:
        """The explicit flag only — deliberately NOT inferred from chain-wide
        zero spreads: EOD close marks also quote bid == ask yet their mids
        carry genuine parity information. The flag persists with the snapshot
        (store schema v5), so replayed synthesized chains keep it."""
        return self.zero_carry

    def expiries(self) -> list[date]:
        """Sorted unique expiries present in the chain."""
        return sorted({q.expiry for q in self.quotes})

    def quotes_for(self, expiry: date) -> list[OptionQuote]:
        """All quotes (calls and puts) for one expiry."""
        return [q for q in self.quotes if q.expiry == expiry]


@dataclass(frozen=True)
class Instrument:
    """Static reference data for one underlying."""

    ticker: str
    name: str
    currency: str

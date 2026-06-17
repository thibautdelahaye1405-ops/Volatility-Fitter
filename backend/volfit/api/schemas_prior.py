"""Prior-framework DTOs: a full calibration snapshot per ticker.

A *prior* is a complete, timestamped snapshot of a ticker's calibrated surface —
everything needed to reproduce the same modelled prices later and to transport
them to a new spot:

  * the market state it was calibrated in (ref spot, per-expiry forward/discount,
    the dividend/rate config, the event calendar driving the variance clock);
  * per expiry, the fitted model (its id + params) AND the LQD backbone params
    (the canonical analytic priced object the var-swap/density/anchor all use);
  * the ticker's local-vol (affine) surface vertices + nodal local vols, if one
    has been calibrated.

Snapshots are persisted (VolStore.prior_snapshots) with history; ``dataTs`` is the
market moment the calibration reflects (what the fetch freshness ladder compares
against the previous close), ``savedTs`` the wall-clock save time.
"""

from __future__ import annotations

from pydantic import BaseModel


class PriorNode(BaseModel):
    """One expiry's calibrated smile inside a prior snapshot."""

    expiry: str  # ISO date
    tCal: float  # calendar year fraction
    tau: float  # event-weighted variance years the smile is quoted in
    forward: float
    discount: float
    model: str  # displayed model id ("lqd" | "svi" | "sigmoid")
    lqd: list[float]  # LQD backbone parameter vector (LQDParams.to_vector)
    display: dict | None = None  # displayed-model params (None when model == "lqd")
    atmVol: float  # snapshot diagnostics (for the prior overlay / age display)
    skew: float


class LvSurfaceSnapshot(BaseModel):
    """The affine local-vol surface vertices + nodal local variances."""

    tNodes: list[float]  # vertex times (increasing)
    xNodes: list[float]  # vertex normalized strikes x = K/F
    theta: list[list[float]]  # nodal local VARIANCES, shape (len(tNodes), len(xNodes))


class PriorSurfaceSnapshot(BaseModel):
    """A full, timestamped calibration snapshot for one ticker (the prior)."""

    ticker: str
    dataTs: str  # market moment reflected (ISO datetime)
    savedTs: str  # wall-clock save time (ISO datetime)
    asOfLabel: str  # human label of the data moment (e.g. "live", "prev_close 2026-06-12")
    refSpot: float
    market: dict  # MarketSettings.model_dump() (rate / dividendMode / dividends / ...)
    events: list[dict] = []  # event calendar (EventSpec dumps) for tau reproduction
    nodes: list[PriorNode]
    lvSurface: LvSurfaceSnapshot | None = None


class PriorTickerStatus(BaseModel):
    """Saved- and active-prior availability summary for one ticker (GET /priors)."""

    ticker: str
    dataTs: str | None = None  # latest SAVED snapshot's market moment
    savedTs: str | None = None
    asOfLabel: str | None = None
    nodeCount: int = 0
    hasLvSurface: bool = False
    #: The ACTIVE (fetched) prior, if 'Fetch priors' has run: the freshness-ladder
    #: branch it came from and the market moment it reflects.
    activeSource: str | None = None  # "saved" | "15min" | "close" | None
    activeDataTs: str | None = None


class PriorStatus(BaseModel):
    """Saved-prior availability across the active universe (GET /priors)."""

    tickers: list[PriorTickerStatus]


class PriorSaveResult(BaseModel):
    """Outcome of POST /priors/save-all."""

    tickers: list[str]  # tickers whose surface was snapshotted
    nodes: int  # total nodes captured
    persisted: bool  # whether a store is configured (so it survives a restart)


class PriorFetchTicker(BaseModel):
    """Per-ticker outcome of the fetch freshness ladder."""

    ticker: str
    source: str  # "saved" | "15min" | "close" | "none"
    dataTs: str | None = None  # the active prior's market moment (None if none found)
    nodeCount: int = 0


class PriorFetchResult(BaseModel):
    """Outcome of POST /priors/fetch (the freshness ladder per ticker)."""

    tickers: list[PriorFetchTicker]

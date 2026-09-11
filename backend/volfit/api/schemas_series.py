"""Series schemas — the SERIES ARC S0 contract (Docs/series_replay_roadmap.md).

A *Series* = one ticker × an ordered set of instants × a set of *lanes*; a
*frame* = one instant's stored chain + every lane's fits; a *lane* = a
settings PATCH over the series' frozen base settings, evaluated THROUGH
TIME (its prior at frame i is its own frame i−1 fit; its filter state is
carried frame to frame; a free lane has no temporal state). The twelve
decisions D1–D12 were ratified 2026-09-10; the shapes here are the wire
and storage contract every later phase (S1 store, S2 harvest, S3 lanes, S4+
lens) builds on. Field names are camelCase per the frontend contract.

What is deliberately NOT here: any new ``OptionsSettings`` / ``FitSettings``
field (lanes carry patches over the existing models, so the help schema does
not move — the anchoring-axis ruling: never "variant calibrations" in
Options) and the ``volfit-series/1`` file envelope (S6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from volfit.api.schemas import FitMode, FitSettings, OptionsSettings

# ------------------------------------------------------------------ vocabulary

#: How the frames are obtained (D7): historical = harvested now from the
#: source's history; live = one frame per tick from now on; import = stored
#: snapshots (the app's captures, a backtest store, a fixture directory).
SeriesMode = Literal["historical", "live", "import"]

#: The clock step (§3.1). ``session_close`` = one frame per session at the
#: close instant; ``daily`` / ``weekly`` = one frame at ``timeOfDay`` (the
#: pack's "before close" default 15:45 ET).
SeriesStep = Literal["1m", "5m", "15m", "30m", "1h", "session_close", "daily", "weekly"]

#: Seconds per step for the sub-day grid (the calendar steps resolve through
#: the session calendar, not a fixed number of seconds).
STEP_SECONDS: dict[str, int] = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}

#: Live-mode floor = the auto-update snapshot floor (2026-09-02g); the
#: historical floor is the finest grid the NBBO history serves sensibly.
LIVE_FLOOR_SECONDS = 15
HISTORICAL_FLOOR_SECONDS = 60

#: Ladder policy (D6): ``pinned`` = the ticker's universe expiries at
#: creation, each frame dropping the ones expired at its instant; ``term`` /
#: ``0dte`` = the intraday capture ladders re-evaluated per frame.
LadderPolicy = Literal["pinned", "term", "0dte"]

#: Lane families: the three parametric families of ``FitSettings.model`` and
#: the affine local-vol surface.
LaneFamily = Literal["lqd", "svi", "sigmoid", "lv"]

#: How a lane with temporal state starts (D4).
LaneSeed = Literal["cold", "warmup", "live_prior"]

SeriesStatus = Literal[
    "draft", "queued", "harvesting", "calibrating", "paused", "done", "failed", "cancelled"
]
FrameStatus = Literal["pending", "harvesting", "ready", "failed", "skipped"]
FitStatus = Literal["pending", "done", "failed", "skipped"]

#: Upper design point: a full session at one minute is 390 frames; a
#: multi-day daily series stays far below this.
MAX_FRAMES = 2000
MAX_LANES = 8
#: Default (lane, frame) wall-clock cap, s — the LV view's client budget; the
#: S3 rails read 0.4–1.3 s per frame, the worst honest outlier 160 s.
DEFAULT_FRAME_BUDGET_S = 300

_FIT_FIELDS = frozenset(FitSettings.model_fields)
_OPTIONS_FIELDS = frozenset(OptionsSettings.model_fields)
_FAMILY_MODEL = {"lqd": "lqd", "svi": "svi", "sigmoid": "sigmoid"}


# ----------------------------------------------------------------------- spec


class SeriesClock(BaseModel):
    """The instants: ``start`` + ``step`` and either ``count`` or ``end``.
    ``start`` None = now (live mode) / the latest servable instant
    (historical). ``sessionOnly`` skips non-trading days and out-of-session
    instants. ``timeOfDay`` (HH:MM in ``tz``) anchors the daily / weekly
    steps; ``warmupFrames`` are harvested BEFORE ``start`` and used only to
    seed lanes that start ``warmup`` (they are frames too, flagged)."""

    start: datetime | None = None
    end: datetime | None = None
    step: SeriesStep = "15m"
    count: int | None = Field(default=None, ge=1, le=MAX_FRAMES)
    sessionOnly: bool = True
    timeOfDay: str = "15:45"
    tz: str = "America/New_York"
    warmupFrames: int = Field(default=0, ge=0, le=64)

    @model_validator(mode="after")
    def _count_or_end(self) -> "SeriesClock":
        if self.count is None and self.end is None:
            raise ValueError("a series clock needs a count or an end instant")
        if self.end is not None and self.start is not None and self.end <= self.start:
            raise ValueError("the end instant must follow the start instant")
        hh, _, mm = self.timeOfDay.partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise ValueError("timeOfDay must be HH:MM")
        return self

    @property
    def step_seconds(self) -> int | None:
        """Seconds per step for the sub-day steps; None for calendar steps."""
        return STEP_SECONDS.get(self.step)


class SeriesLadder(BaseModel):
    """Which expiries each frame carries (D6). ``expiries`` is the pinned
    list (ISO dates) resolved at creation for ``pinned``; empty otherwise."""

    policy: LadderPolicy = "pinned"
    expiries: list[str] = []
    maxExpiries: int | None = Field(default=None, ge=1, le=40)


class LaneSpec(BaseModel):
    """One model configuration through time (D3 / D4). ``patchFit`` and
    ``patchOptions`` are partial dicts over ``FitSettings`` /
    ``OptionsSettings`` applied with ``model_copy(update=)`` on the series'
    frozen base; keys are validated against the models' fields. ``family``
    decides the engine: the parametric families set ``patchFit.model``
    (must agree when given); ``lv`` turns ``localVolEnabled`` on."""

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=80)
    family: LaneFamily = "lqd"
    colour: str | None = None
    fitMode: FitMode | None = None  # None = the series fit mode
    patchFit: dict[str, Any] = {}
    patchOptions: dict[str, Any] = {}
    production: bool = False
    seed: LaneSeed = "cold"

    @model_validator(mode="after")
    def _validate_patches(self) -> "LaneSpec":
        bad_fit = sorted(set(self.patchFit) - _FIT_FIELDS)
        bad_opt = sorted(set(self.patchOptions) - _OPTIONS_FIELDS)
        if bad_fit or bad_opt:
            raise ValueError(
                f"lane {self.id!r}: unknown patch keys "
                f"fit={bad_fit} options={bad_opt}"
            )
        if self.family in _FAMILY_MODEL:
            want = _FAMILY_MODEL[self.family]
            got = self.patchFit.get("model")
            if got is not None and got != want:
                raise ValueError(
                    f"lane {self.id!r}: family {self.family} but patchFit.model={got!r}"
                )
            self.patchFit = {**self.patchFit, "model": want}
        else:  # lv: the affine surface rides the LV stage of the lane state
            if self.patchOptions.get("localVolEnabled") is False:
                raise ValueError(f"lane {self.id!r}: an lv lane cannot disable localVolEnabled")
            self.patchOptions = {**self.patchOptions, "localVolEnabled": True}
        return self

    @property
    def temporal(self) -> bool:
        """True when the lane carries state between frames (a prior mode
        other than off, or a filter on) — its frames must run in order."""
        prior = self.patchOptions.get("priorPersistenceMode")
        filt = self.patchOptions.get("observationFilterMode")
        return (prior is not None and prior != "off") or (filt is not None and filt != "off")


class SeriesSpec(BaseModel):
    """What the user asked for (the dialog, §3.1). ``tickers`` carries the
    D2 extension seam and must equal ``[ticker]`` in v1.

    ``frameBudgetSeconds`` caps ONE (lane, frame) calibration (2026-09-11: a
    filter lane spent 17 min on a frame and held a series at 8/10): past it
    the lane keeps its committed slice fits, its repair / LV rows fail with
    the reason, the run moves on. None = unlimited; the desk has no budget."""

    name: str = Field(min_length=1, max_length=120)
    ticker: str = Field(min_length=1)
    tickers: list[str] = []
    source: str | None = None
    mode: SeriesMode = "historical"
    clock: SeriesClock = SeriesClock(count=20)
    ladder: SeriesLadder = SeriesLadder()
    fitMode: FitMode = "mid"
    lanes: list[LaneSpec] = Field(min_length=1, max_length=MAX_LANES)
    frameBudgetSeconds: int | None = Field(default=DEFAULT_FRAME_BUDGET_S, ge=5, le=86_400)
    note: str = ""

    @model_validator(mode="after")
    def _lanes_and_tickers(self) -> "SeriesSpec":
        if not self.tickers:
            self.tickers = [self.ticker]
        if self.tickers != [self.ticker]:
            raise ValueError("v1 series carry exactly one ticker (D2)")
        ids = [lane.id for lane in self.lanes]
        if len(set(ids)) != len(ids):
            raise ValueError(f"lane ids must be unique: {ids}")
        stars = [lane for lane in self.lanes if lane.production]
        if len(stars) > 1:
            raise ValueError("at most one production lane")
        if not stars:  # default: the first lane is the production lane
            self.lanes = [lane.model_copy(update={"production": i == 0})
                          for i, lane in enumerate(self.lanes)]
        if self.mode == "live" and self.clock.step_seconds is not None:
            if self.clock.step_seconds < LIVE_FLOOR_SECONDS:
                raise ValueError(f"live step floor is {LIVE_FLOOR_SECONDS} s")
        if self.mode == "historical" and self.clock.step_seconds is not None:
            if self.clock.step_seconds < HISTORICAL_FLOOR_SECONDS:
                raise ValueError(f"historical step floor is {HISTORICAL_FLOOR_SECONDS} s")
        for lane in self.lanes:
            if lane.seed == "live_prior" and self.mode != "live":
                raise ValueError(f"lane {lane.id!r}: seed live_prior needs a live series")
            if lane.seed == "warmup" and self.clock.warmupFrames == 0:
                raise ValueError(f"lane {lane.id!r}: seed warmup needs clock.warmupFrames")
        return self

    @property
    def production_lane(self) -> LaneSpec:
        return next(lane for lane in self.lanes if lane.production)


# ------------------------------------------------------------- stored shapes


class SeriesProgress(BaseModel):
    """The runner's counters (S2 / S3): frames harvested and fits made, the
    item under work and the last error; ``updatedTs`` is the checkpoint."""

    status: SeriesStatus = "draft"
    framesTotal: int = 0
    framesReady: int = 0
    fitsTotal: int = 0
    fitsDone: int = 0
    current: str | None = None
    error: str | None = None
    startedTs: str | None = None
    updatedTs: str | None = None


class FrameDoc(BaseModel):
    """One frame of the index (§5 ``series_frames``): the instant, the stored
    chain it points at and what the harvest found there."""

    idx: int = Field(ge=0)
    ts: str
    snapshotId: int | None = None
    spot: float | None = None
    quoteKind: str | None = None  # "quotes" (NBBO) | "marks" — the chart's diamonds
    nQuotes: int = 0
    expiries: list[str] = []
    warmup: bool = False
    status: FrameStatus = "pending"
    error: str | None = None
    harvestedTs: str | None = None


class LaneFitDoc(BaseModel):
    """One stored fit (§5 ``series_fits``): a parametric slice when
    ``expiry`` is set, the LV surface when it is None. ``params`` /
    ``display`` follow the snapshot-file calibration shape
    (``snapshot_files._calibrations_doc``) so a frame re-renders without a
    refit; ``metrics`` is the evidence row (rms / max / arb / pull / ζ)."""

    laneId: str
    idx: int = Field(ge=0)
    expiry: str | None = None
    model: str
    params: dict[str, Any] = {}
    display: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    fitMs: float | None = None
    status: FitStatus = "done"
    error: str | None = None


class SeriesDoc(BaseModel):
    """The whole series as stored (§5 ``series``): the spec, the frozen base
    settings, the progress and the frame index. Fits are read per frame."""

    id: str
    createdTs: str
    updatedTs: str
    spec: SeriesSpec
    baseFit: FitSettings
    baseOptions: OptionsSettings
    progress: SeriesProgress = SeriesProgress()
    frames: list[FrameDoc] = []


class SeriesSummary(BaseModel):
    """One row of the series list (the picker in the lens header)."""

    id: str
    name: str
    ticker: str
    source: str | None = None
    mode: SeriesMode
    status: SeriesStatus
    createdTs: str
    nFrames: int = 0
    nFramesReady: int = 0
    nLanes: int = 0


class SeriesListResponse(BaseModel):
    series: list[SeriesSummary] = []


# ------------------------------------------------------------ wire payloads


class SeriesEstimate(BaseModel):
    """POST /series/estimate — the resolved instants, which of them the
    source can serve, and the wall-time budget shown before Start (§3.1)."""

    instants: list[str] = []
    servable: list[bool] = []
    nFrames: int = 0
    harvestSeconds: float = 0.0
    calibrateSeconds: float = 0.0
    perLaneSeconds: dict[str, float] = {}
    warnings: list[str] = []


class SeriesCreateResponse(BaseModel):
    id: str
    estimate: SeriesEstimate


class SliceCurveDoc(BaseModel):
    """One lane's smile at one expiry of one frame, ready to draw: log-
    moneyness abscissae, implied vols, the handles and the slice metrics."""

    expiry: str
    t: float
    forward: float
    k: list[float] = []
    iv: list[float] = []
    atmVol: float | None = None
    skew: float | None = None
    curvature: float | None = None
    metrics: dict[str, Any] = {}


class SurfaceGridDoc(BaseModel):
    """One lane's σ(k, τ) grid at one frame for the Surface stage."""

    k: list[float] = []
    tau: list[float] = []
    expiries: list[str] = []
    sigma: list[list[float]] = []  # rows = tau, cols = k


class LaneFrameDoc(BaseModel):
    """Everything one lane contributes to one frame payload."""

    laneId: str
    slices: list[SliceCurveDoc] = []
    surface: SurfaceGridDoc | None = None
    term: list[dict[str, Any]] = []  # per expiry: atmVol, varSwapVol, both clocks
    metrics: dict[str, Any] = {}
    status: FitStatus = "done"


class FramePayload(BaseModel):
    """GET /series/{id}/frame/{idx} — the frame's market plus every requested
    lane's curves, grid, term points and metrics in ONE response, so the
    scrubber prefetches whole frames. ``market`` is the per-expiry quote
    band document the Smile chart already consumes (S4 pins its shape)."""

    seriesId: str
    idx: int
    ts: str
    quoteKind: str | None = None
    spot: float | None = None
    expiries: list[str] = []
    forwards: dict[str, float] = {}
    market: dict[str, Any] = {}
    lanes: dict[str, LaneFrameDoc] = {}


class StripPayload(BaseModel):
    """GET /series/{id}/strip — the filmstrip: per frame scalars, and per
    lane a dict of metric name → per-frame values (None where no fit)."""

    seriesId: str
    idx: list[int] = []
    ts: list[str] = []
    spot: list[float | None] = []
    atmVol: dict[str, list[float | None]] = {}  # laneId -> per frame (shown expiry)
    lanes: dict[str, dict[str, list[float | None]]] = {}

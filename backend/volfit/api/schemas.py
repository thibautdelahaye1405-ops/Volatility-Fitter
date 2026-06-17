"""Pydantic schemas for the volfit HTTP API (ROADMAP Phase 5).

The smile payload field names are FROZEN against the frontend contract in
frontend/src/lib/mockData.ts: `SmilePoint`, `QuoteBand`, `SmileDiagnostics`
and `SmileData` must serialize to exactly the camelCase shapes the React
Smile Viewer already consumes, so swapping its mock module for live API
calls is a one-line change. Request/response models for the surface fit,
graph solver, SSR scenario, term-structure and density endpoints follow the
same convention.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Market-settings / forward-mode and fit-history schemas live in their own
# modules (file-size policy) and are re-exported here so the API keeps one
# schema import surface.
from volfit.api.schemas_history import (  # noqa: F401  (re-export)
    HistoryPoint,
    HistoryResponse,
)
from volfit.api.schemas_market import (  # noqa: F401  (re-export)
    DividendSpec,
    ForwardEntry,
    ForwardPolicy,
    ForwardsResponse,
    MarketSettings,
)
from volfit.dynamics.ssr import Regime

#: Quote-weighting modes for slice calibration (product spec: fit to mid,
#: fit to bid-ask, or fit to a haircut bid-ask).
FitMode = Literal["mid", "bidask", "haircut"]


# ------------------------------------------------------------- fit settings
class FitSettings(BaseModel):
    """Global slice-fit hyperparameters (the Smile Viewer's panel).

    PUT /settings/fit applies them to every subsequent fit: the settings
    version is folded into the fit-cache key, so all views (smile, term,
    density, local-vol) refit consistently — no per-endpoint threading.
    ``model`` chooses the smile family the Smile Viewer charts: "lqd" (the
    arbitrage-free quantile-density default, also the analytic backbone), or
    the "svi" / "sigmoid" overlays (volfit.api.fit_models) calibrated to the
    same quotes. ``nOrder``/``regLambda``/``regPower`` only affect LQD; the
    overlay families ignore them. ``nCores`` is the number R of zero-wing hat
    kernels of the Multi-Core SIV ("sigmoid") slice (the slider analogue of the
    LQD Legendre order, eq param-count of the MC-SIV note); it only affects the
    sigmoid family. LQD is always fitted under the hood, so the density,
    term-structure, local-vol and graph views stay LQD-based. ``haircut`` is the
    band tightening of the "haircut" fit mode in absolute vol (0.005 = 0.5 vol
    points); it only affects fit_mode="haircut" (volfit.calib.band).
    ``weightScheme`` chooses the per-quote calibration weights (volfit.calib.
    weights): "equal" (unit weights, the historical scheme) or "tv_density"
    (time-value density weights — economic time-value shape with the strike
    oversampling divided out); it applies in every fit mode and to every model.
    """

    model: Literal["lqd", "svi", "sigmoid"] = "lqd"
    nOrder: int = Field(6, ge=4, le=16)  # Legendre order N of the LQD slice
    regLambda: float = Field(1e-6, ge=0.0, le=1.0)  # lam * n^{2r} a_n^2 damping
    regPower: float = Field(1.0, ge=0.0, le=4.0)  # the r in n^{2r}
    nCores: int = Field(2, ge=0, le=6)  # Multi-Core SIV hat count R (sigmoid only)
    haircut: float = Field(0.005, ge=0.0, le=0.05)  # haircut-mode band shrink (vol)
    weightScheme: Literal["equal", "tv_density"] = "equal"  # per-quote weights
    # --- per-model optimization / penalty coefficients (Options exposes them
    # all explicitly; every default equals the historical hardcoded constant, so
    # a default fit is byte-identical to before they were tunable) ---
    barrierCenter: float = Field(0.90, gt=0.0, lt=1.0)  # LQD A_R soft-barrier centre
    barrierScale: float = Field(50.0, gt=0.0)  # LQD A_R soft-barrier steepness
    sviPenaltyWeight: float = Field(1e3, ge=0.0)  # SVI no-arb soft-penalty weight
    leeSlopeMax: float = Field(2.0, gt=0.0)  # SVI Lee wing-slope bound
    sigmoidRidge: float = Field(1e-2, ge=0.0)  # Multi-Core SIV hat-amplitude ridge
    midAnchorWeight: float = Field(0.05, ge=0.0)  # band-mode mid anchor (all models)


# ----------------------------------------------------- options (meta) settings
class OptionsSettings(BaseModel):
    """Global meta / UX settings and engine defaults — the Options workspace
    (ROADMAP Phase 10). Distinct from FitSettings (the live per-fit knobs): these
    are app-wide toggles, penalty strengths and seed-defaults the other
    workspaces read.

    Wired to real engine behaviour this phase:
      * ``calendarWeight`` — the quadratic calendar-slack penalty weight folded
        into surface slice fits (volfit.models.lqd.calibrate, eq. slack_calendar);
        the only field that changes calibration output, so it (alone) bumps the
        options version in the fit-cache key.
      * ``enforceCalendar`` — calendar-arbitrage fix: when on, the background
        Calibrate job (volfit.api.workflow.calibrate_all) couples each ticker's lit
        expiries in ascending-T order, threading the previous slice as a convex-
        order floor; the surface-fit endpoint also seeds its default from it.
      * ``eventsEnabled`` — global default for event-time dilation (term view).
      * ``varSwapEnabled`` — whether the var-swap level is surfaced.
      * ``dynamicsRegime`` / ``ssr`` — seed defaults for the spot-vol scenario.
      * ``gridXNodes`` / ``gridTNodes`` / ``gridRegLambda`` — default vertex grid
        and roughness of the local-vol-affine fit (AffineFitRequest seeds them).
      * ``autoLoadPrior`` — when on (and a prior has been fetched), the active
        spot-updated prior anchors the calibration at delta-locations with a
        data-gap precision (volfit.calib.prior): dense-quote zones ignore the
        prior, sparse wings lean on it. Strength ``priorAnchorWeightPct``.

    Stubbed this phase (persisted UI state only; behaviour is a documented TODO):
      * ``autoCalibrate`` — auto-refit on every quote edit (True, today's
        behaviour) vs a manual "Calibrate" trigger gating refits.
      * ``spotMode`` — stream live spot and re-price ("realtime") vs freeze spot
        at load ("static"); pairs with the existing As-of selector.
    """

    #: Default fit target (Mid / Bid-Ask band / Haircut band). The live fit target
    #: is a per-request param; this is the persisted DEFAULT the frontend seeds the
    #: session from on load, so "Save as default" remembers it. Backend stores it
    #: only (each fit still receives its mode per request), so it never bumps the
    #: options version.
    fitMode: FitMode = "mid"
    # arbitrage / events / var-swap (wired as global defaults)
    enforceCalendar: bool = True
    #: Master switch for the event-weighted variance clock (volfit.calib.
    #: weighted_time): when on, the ticker's event calendar augments day-weights
    #: so an event before an expiry lowers the working IV at fixed price. Now
    #: affects calibration, so it bumps the options version.
    eventsEnabled: bool = True
    #: Normalize the variance clock so the 1Y weight budget stays 365 (rescale
    #: ALL days, events included): events redistribute variance within the year
    #: and 1Y vols are unchanged. Off by default (cumulative weight > calendar
    #: days). Affects calibration -> bumps the options version.
    normalizeEvents: bool = False
    varSwapEnabled: bool = True
    #: Var-swap penalty weight as a PERCENTAGE of the summed option-quote weights
    #: of the same (asset, expiry) node (volfit.api.varswap.varswap_target): at
    #: 100% an active var-swap quote weighs as much as all option quotes combined.
    #: Changes calibration output, so it bumps the options version (set_options),
    #: and only matters while ``varSwapEnabled`` is on.
    varSwapWeightPct: float = Field(10.0, ge=0.0, le=1000.0)
    # prior default
    autoLoadPrior: bool = False
    #: Prior-anchor budget as a PERCENTAGE of the summed option-quote weights of the
    #: node (like the var-swap penalty): the total weight given to the data-gap
    #: prior anchor (volfit.calib.prior), distributed across the delta-locations in
    #: proportion to the observed-vs-desired quote-density deficit. Only bites while
    #: ``autoLoadPrior`` is on and a prior is active; changes calibration output, so
    #: it bumps the options version (set_options).
    priorAnchorWeightPct: float = Field(50.0, ge=0.0, le=1000.0)
    #: Per-side delta-locations the prior anchor is placed at (the wing shape it
    #: pins); ATM is always added, and the var-swap prior carries the aggregate tail
    #: below the smallest delta. Each value is a forward Black delta in (0, 0.5).
    priorAnchorDeltas: list[float] = Field(default=[0.02, 0.05, 0.10, 0.25, 0.40])

    @field_validator("priorAnchorDeltas")
    @classmethod
    def _clean_deltas(cls, v: list[float]) -> list[float]:
        """Keep deltas strictly in (0, 0.5), dedup + sort; fall back to the default
        set if nothing valid is given (so the anchor always has placements)."""
        cleaned = sorted({round(float(d), 4) for d in v if 0.0 < float(d) < 0.5})
        return cleaned or [0.02, 0.05, 0.10, 0.25, 0.40]
    # local-vol-affine vertex grid + roughness (the single source of truth: the
    # affine fit reads these directly; the Local-Vol workspace has no own knobs).
    gridXNodes: int = Field(7, ge=3, le=200)  # strike vertices (much larger max now)
    #: Time vertices: 0 = auto (one vertex per OBSERVED expiry, recommended);
    #: > 0 caps/subsamples the expiries to that many. Default auto.
    gridTNodes: int = Field(0, ge=0, le=120)
    gridRegLambda: float = Field(1e-2, ge=0.0, le=1e4)
    gridRegRho: float = Field(1.0, ge=0.0, le=10.0)  # affine time-vs-strike roughness
    # editable penalty strength (changes calibration output)
    calendarWeight: float = Field(1e6, ge=0.0)
    # graph-solver prior defaults (the Graph SolverPanel seeds from these):
    # kappa = prior strength (local precision toward baseline), eta = reach,
    # lambda = OT flux weight (0 = off), nu = OT source allowance.
    graphKappaScale: float = Field(1.0, gt=0.0)
    graphEtaScale: float = Field(1.0, ge=0.0)
    graphLambdaScale: float = Field(0.0, ge=0.0)
    graphNu: float = Field(0.1, gt=0.0)
    # spot-vol dynamics defaults — the Parametric spot-scenario reads these
    # (the regime selector moved entirely to Options). "custom" uses ``ssr``.
    dynamicsRegime: Literal[
        "sticky_moneyness",
        "sticky_strike",
        "sticky_local_vol",
        "sticky_local_vol_grid",
        "custom",
    ] = "sticky_strike"
    ssr: float = Field(2.0, ge=0.0)
    # ---- calibration / data-fetch workflow (the trigger model) ----
    #: After options are fetched: ON = calibrate all lit nodes in the background;
    #: OFF = leave nodes stale until the user presses Calibrate. Also gates whether
    #: a quote edit / parameter change refits (ON) or just marks stale (OFF).
    autoCalibrate: bool = True
    #: Local-Vol (affine) calibration master switch. OFF = the background Calibrate
    #: job skips every ticker's LV surface (only the parametric nodes fit, so test
    #: cycles are fast) AND the Local Vol workspace tab is disabled. Pure
    #: workflow/UI gate — does not affect parametric fits, so it never busts caches.
    localVolEnabled: bool = True
    #: Spot updates: "realtime" = the backend scheduler polls the provider spot
    #: every ``spotPollSeconds`` and transports the surface; "static" = on-demand
    #: only (the "Fetch spots" button).
    spotMode: Literal["realtime", "static"] = "static"
    spotPollSeconds: float = Field(5.0, gt=0.0, le=3600.0)
    #: Options chains: "auto" = the scheduler refetches every
    #: ``optionsFetchMinutes``; "on_demand" = only the "Fetch Options Quotes" button.
    optionsFetchMode: Literal["auto", "on_demand"] = "on_demand"
    optionsFetchMinutes: float = Field(5.0, gt=0.0, le=1440.0)
    #: While a real-time WS book is streaming (Massive realtime), the scheduler
    #: refetches the chain from the book and recalibrates all lit nodes every
    #: ``streamRefitSeconds`` — a faster, book-driven loop distinct from the
    #: minutes-cadence ``optionsFetchMode == "auto"`` REST refetch.
    streamRefitSeconds: float = Field(5.0, gt=0.0, le=600.0)


# --------------------------------------------------- persisted settings defaults
class SettingsDefaultsStatus(BaseModel):
    """Whether the Fit/Options "Save as default" persistence is available and used.

    ``storeEnabled`` is False when no app store is configured (VOLFIT_DB unset /
    restart.ps1 -NoDb) — the Options tab then disables its Save button.
    ``hasSaved`` reports whether the user has saved defaults to the store.
    """

    storeEnabled: bool
    hasSaved: bool


class SettingsDefaultsReset(SettingsDefaultsStatus):
    """Reset response: the status plus the reverted (code-default) settings, so
    the Options drafts can re-sync without a second round-trip."""

    fit: FitSettings
    options: OptionsSettings


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
    rmsError: float  # weighted RMS vol error of the fit (decimal vol; UI shows %)


class VarSwapInfo(BaseModel):
    """Variance-swap quote state of a node (volfit.api.varswap_session).

    ``level`` is the quoted var-swap *volatility* (None when no quote exists);
    ``modelVol`` is the model's own fair var-swap vol (the diagnostics value, so
    the UI can seed a new quote at the model level and show the gap). ``enabled``
    mirrors OptionsSettings.varSwapEnabled so the frontend can gate the affordance
    without a second fetch. ``canUndo``/``canRedo`` cover the SEPARATE var-swap
    edit history (independent of the option-quote session)."""

    level: float | None
    excluded: bool
    modelVol: float
    enabled: bool
    canUndo: bool
    canRedo: bool


class SmileData(BaseModel):
    """Everything the Smile Viewer needs for one (underlying, expiry) node."""

    ticker: str
    expiry: str  # ISO date
    T: float  # year fraction to expiry
    forward: float
    model: list[SmilePoint]
    prior: list[SmilePoint]
    #: True when ``prior`` is the ACTIVE fetched prior, transported to the current
    #: forward under the dynamics regime (drawn dotted as a spot-updated prior);
    #: False when it is a saved per-node prior or the current fit fallback.
    priorTransported: bool = False
    quotes: list[QuoteBand]
    kMin: float
    kMax: float
    diagnostics: SmileDiagnostics
    varSwap: VarSwapInfo  # variance-swap quote + model level for this node
    canUndo: bool  # quote-edit session undo/redo availability
    canRedo: bool  # (both False when the node has no edit session yet)
    stale: bool = False  # inputs drifted since the last calibration (needs Calibrate)
    #: The pre-transport calibration curve, set only while a spot move is active,
    #: so the viewer can overlay the original fit (dimmed) under the transported
    #: smile. Each curve is in its own log-moneyness (sticky-strike => a lateral
    #: shift; sticky-moneyness => the two coincide). None when no spot move.
    anchorModel: list[SmilePoint] | None = None


# ------------------------------------------------------------------ universe
class ExpiryInfo(BaseModel):
    """One listed expiry of a ticker with its year fraction and type tag
    (daily/weekly/monthly/quarterly/leaps — volfit.data.expiries), the
    handle for bulk expiry selection in the universe screen."""

    expiry: str
    t: float
    expiryType: str


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


class VarSwapEditRequest(BaseModel):
    """One variance-swap quote edit on a smile node (volfit.api.varswap_session).

    ``set`` adds or adjusts the quote and requires a positive ``level`` (var-swap
    *volatility*, e.g. 0.185); ``exclude``/``include`` toggle an existing quote in
    or out of the fit; ``remove``/``reset`` delete it. Semantic validation lives
    in VarSwapSession.apply (router maps ValueError to HTTP 422)."""

    action: Literal["set", "exclude", "include", "remove", "reset"]
    level: float | None = None


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


# ---------------------------------------------------------------- 3D surface
class SurfaceResponse(BaseModel):
    """sigma(k, T) mesh for the 3D vol-surface chart (volfit.api.surface).

    Every expiry's fitted slice is sampled on ONE shared log-moneyness grid
    (the union of the per-expiry quoted ranges), so ``vol`` is a full
    rectangular mesh: ``vol[i][j]`` is the implied vol of expiry i at k[j].
    """

    ticker: str
    expiries: list[str]  # ISO dates, nearest first
    t: list[float]  # year fractions, same order
    k: list[float]  # shared log-moneyness grid (length N_SURFACE_POINTS)
    vol: list[list[float]]  # one row per expiry, one column per k
    atmVol: list[float]  # exact ATM handle per expiry (lqd.atm)
    forward: list[float]  # active forward per expiry


# --------------------------------------------------------------- quote table
class TableRow(BaseModel):
    """One prepared quote of a slice as a table/export row (volfit.api.table).

    IVs are the displayed band (an amended quote shows its overridden mid);
    prices are *discounted* OTM option prices reconstructed by Black at the
    band IVs (puts by parity), in the same conventions as volfit.api.quotes.
    """

    index: int
    strike: float
    type: str  # "C"/"P" — the OTM side convention (call iff k >= 0)
    k: float
    bidIv: float
    midIv: float
    askIv: float
    modelIv: float  # fitted vol at this k
    bidPrice: float
    midPrice: float
    askPrice: float
    excluded: bool
    amended: bool


class TableResponse(BaseModel):
    """The full quote/price/IV table of one fitted (ticker, expiry) node."""

    ticker: str
    expiry: str
    t: float
    forward: float
    discount: float
    rows: list[TableRow]


# --------------------------------------------------------------- graph solve
class GraphObservation(BaseModel):
    """One observed handle shift on a smile node, in absolute handle units."""

    ticker: str
    expiry: str
    dAtmVol: float
    dSkew: float = 0.0
    dCurv: float = 0.0


class GraphSolverParams(BaseModel):
    """Tunable hyperparameters of the increment prior Q_Delta and the graph.

    The three scales multiply the per-handle base regime (service.py
    GRAPH_PRIOR_HYPER): ``etaScale`` the directed-smoothness weight eta,
    ``kappaScale`` the local precision kappa (stiffness toward the baseline —
    higher means less propagation), ``lambdaScale`` the optimal-transport flux
    weight lambda (0 disables the OT term, preserving the legacy regime).
    ``nu`` is the OT source/sink allowance, used only when lambdaScale > 0.
    ``calendarWeight`` / ``crossWeight`` override the same-ticker and
    cross-ticker edge weights; null keeps the service defaults.
    """

    etaScale: float = Field(default=1.0, ge=0.0)
    kappaScale: float = Field(default=1.0, gt=0.0)
    lambdaScale: float = Field(default=0.0, ge=0.0)
    nu: float = Field(default=0.1, gt=0.0)
    calendarWeight: float | None = Field(default=None, gt=0.0)
    crossWeight: float | None = Field(default=None, gt=0.0)


class GraphSolveRequest(GraphSolverParams):
    """Propagate sparse handle observations through the smile universe."""

    observations: list[GraphObservation] = Field(min_length=1)


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


class GraphAutotuneRequest(GraphSolverParams):
    """Pick the propagation reach etaScale by leave-one-out cross-validation.

    Needs at least two observations (LOO holds one out at a time). The other
    solver knobs are held fixed at the supplied values while eta is tuned;
    ``etaScale`` on this request is ignored (it is the quantity being chosen).
    """

    observations: list[GraphObservation] = Field(min_length=2)


class AutotuneCandidate(BaseModel):
    """One grid point of the auto-tune sweep and its LOO error."""

    etaScale: float
    rmseBp: float  # RMS leave-one-out ATM-vol prediction error, basis points


class GraphAutotuneResponse(BaseModel):
    """Chosen etaScale (LOO-RMSE minimizer) plus the full scored grid."""

    etaScale: float
    rmseBp: float
    candidates: list[AutotuneCandidate]


class GraphNodeInfo(BaseModel):
    """Baseline (pre-solve) fitted handles of one universe node."""

    ticker: str
    expiry: str
    t: float
    atmVol: float
    skew: float
    curvature: float
    lit: bool = True  # lit/dark designation (volfit.api.state); lit by default


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


# ------------------------------------------------------- fast spot-move state
class SpotShiftRequest(BaseModel):
    """Set a ticker's hypothetical/live spot move (no recalibration).

    ``spotReturn`` is the proportional move vs the anchor spot the fits were
    calibrated at (e.g. 0.02 for +2%); 0 returns to the anchor. The whole
    surface (smile, term, LV grid) is transported analytically on the next read
    via volfit.dynamics.transport — calibration only happens on an explicit
    "Calibrate" (POST /spot/{ticker}/calibrate).
    """

    spotReturn: float = 0.0


class SpotState(BaseModel):
    """The active spot-move state of a ticker (the no-recal transport view)."""

    ticker: str
    anchorSpot: float  # spot the cached fits were calibrated at
    spotReturn: float  # active proportional shift (0 = anchored)
    shiftedSpot: float  # anchorSpot * (1 + spotReturn)
    regime: str  # active vol-spot dynamics regime label
    regimeSsr: float  # its skew-stickiness ratio (transport strength R)


class LiveSpot(BaseModel):
    """A real-time spot probe versus the anchor (for spotMode='realtime')."""

    ticker: str
    anchorSpot: float
    liveSpot: float
    spotReturn: float  # implied liveSpot / anchorSpot - 1


# ------------------------------------------------------ calibration workflow
class CalibrationStatus(BaseModel):
    """State of the background calibration job + stale-node accounting."""

    running: bool
    total: int  # nodes in the current/last job
    done: int  # nodes calibrated so far
    current: str  # "TICKER EXPIRY" in flight, "" when idle
    phase: str = ""  # coarse phase of the in-flight item: "Parametric" | "LV"
    error: str  # last per-node error (the job never aborts on one bad node)
    cancelled: bool
    litNodes: int  # total lit (calibratable) nodes in the universe
    staleNodes: int  # lit nodes whose displayed fit has drifted from its last fit
    spotVersion: int  # global spot-move counter (bumps on any transported move)


class FetchRequest(BaseModel):
    """Optional ticker subset for a fetch / calibrate action (None = all active)."""

    tickers: list[str] | None = None


class FetchResult(BaseModel):
    """Outcome of a spots / options fetch action."""

    tickers: list[str]  # tickers actually fetched
    spots: dict[str, float]  # ticker -> spot (live for spots, chain for options)
    calibrationStarted: bool  # whether auto-calibrate kicked off a background job


class SchedulerStatus(BaseModel):
    """Backend scheduler state for the TopBar fetch controls."""

    running: bool  # the scheduler thread is alive
    spotMode: str  # "realtime" | "static"
    optionsFetchMode: str  # "auto" | "on_demand"
    autoCalibrate: bool
    localVolEnabled: bool  # whether LV is calibrated + the Local Vol tab is usable
    #: Seconds to the next auto options fetch / spot poll, or -1 when that mode
    #: is on-demand/static (so the UI shows a button instead of a countdown).
    secondsToNextOptions: float
    secondsToNextSpot: float


# ------------------------------------------------------------------ local vol
class LocalVolGridResponse(BaseModel):
    """Extracted Dupire local-vol grid of a ticker plus no-arb diagnostics.

    ``sigma[i][j]`` is the local vol of forward-variance bucket i (between
    listed expiries, sampled at the bucket midpoint) at log-moneyness k[j];
    ``minDensity``/``calendarViolation`` are the discrete PDE residuals of
    volfit.models.localvol.model (scheme noise, gated by ``arbitrageFree``),
    ``nNan``/``nClipped`` count extraction repairs (Dupire denominator <= 0,
    variance floored).
    """

    ticker: str
    expiries: list[str]
    t: list[float]  # expiry year fractions (bucket right edges)
    k: list[float]  # log-moneyness nodes
    sigma: list[list[float]]  # local vols, one row per bucket
    nNan: int
    nClipped: int
    minDensity: list[float]
    calendarViolation: list[float]
    arbitrageFree: bool


# ------------------------------------------------------------ term structure
class EventSpec(BaseModel):
    """One scheduled event of the dilated clock: ``weight`` years of extra
    diffusion time lumped at year-fraction ``time`` (volfit.calib.event_time).
    Pydantic enforces time > 0 and weight >= 0, so bad specs are 422s."""

    time: float = Field(gt=0)
    weight: float = Field(ge=0)
    label: str = ""


class EventCalendar(BaseModel):
    """A ticker's persisted event calendar (GET/PUT /events/{ticker}).

    The event list is shared per-ticker state so it survives Parametric tab
    switches and ticker changes (volfit.api.state.AppState), instead of living
    only in the Term sub-tab's view-local state."""

    events: list[EventSpec] = Field(default_factory=list)


class EventAutocalibrateRequest(BaseModel):
    """Auto-calibrate the event calendar from the ATM term structure.

    ``maxExpiry`` is the horizon: one candidate event is placed before each
    expiry at or before it, and their day-weights are solved (all at once) so the
    weighted forward variance up to the interval just past the horizon is as flat
    and monotone-increasing as possible, with events as small and sparse as
    possible (volfit.calib.event_autocalibrate). Replaces the existing calendar."""

    maxExpiry: str  # ISO date: no events are added beyond this expiry
    fitMode: FitMode = "mid"


class TermStructureRequest(BaseModel):
    """ATM term structure of one ticker under an optional event calendar."""

    fitMode: FitMode = "mid"
    events: list[EventSpec] = Field(default_factory=list)
    eventsEnabled: bool = True


class TermPoint(BaseModel):
    """One fitted expiry on the term structure (calendar and dilated time)."""

    expiry: str  # ISO date
    t: float  # calendar year fraction
    tau: float  # event-dilated time tau(t)
    atmVol: float  # exact ATM handle sigma_0 (same fit as GET /smiles)
    w0: float  # ATM total implied variance
    varSwapVol: float  # model fair var-swap vol = sqrt(var-swap strike / t)
    varSwapQuote: float | None = None  # user-quoted var-swap vol (None if unset)
    varSwapExcluded: bool = False  # quote present but excluded from the fit
    maxIvErrorBp: float
    #: Active fetched prior's ATM vol at this expiry, transported to the current
    #: forward (dotted spot-updated prior term line); None when no active prior.
    priorVol: float | None = None


class TermCurve(BaseModel):
    """Dense ATM total-variance curve, linear in event-dilated time."""

    t: list[float]
    tau: list[float]
    w: list[float]
    vol: list[float]  # sqrt(w / t)


class DividendMarker(BaseModel):
    """One discrete dividend ex-date positioned on the term-structure axis.

    Emitted only when the ticker's dividend mode uses the discrete schedule
    (volfit.data.dividends): the forward already drops across each ex-date, so
    these are drawn as informational markers on both the real-time (``t``) and
    event-dilated (``tau``) maturity axes.
    """

    exDate: str  # ISO date
    t: float  # ex-date year fraction
    tau: float  # event-dilated position of the ex-date
    amount: float  # cash amount or proportional fraction (per the active mode)


class TermStructureResponse(BaseModel):
    """Per-expiry points plus the dense interpolated curve, nearest first."""

    ticker: str
    points: list[TermPoint]
    curve: TermCurve
    calendarViolations: int  # adjacent expiry pairs with w0 strictly falling
    dividends: list[DividendMarker] = []  # discrete ex-dates within the range


# ------------------------------------------------------------------- density
class DistributionArrays(BaseModel):
    """Risk-neutral log-return density and quantile function of one slice.

    (x, density) chart f_X on x = Q(z); (u, quantile) chart Q(u). All four
    arrays live on the same trimmed/strided quadrature grid, so they share
    one length and align point-for-point.
    """

    x: list[float]
    density: list[float]
    u: list[float]
    quantile: list[float]


class DensityResponse(BaseModel):
    """Current fit's distribution plus the saved prior's (null if unsaved)."""

    current: DistributionArrays
    prior: DistributionArrays | None = None


class StackedDensityItem(BaseModel):
    """One expiry's risk-neutral density for the stacked-densities view: the
    pdf f_X on the log-return grid x (the displayed model's own density)."""

    expiry: str
    t: float
    x: list[float]
    density: list[float]


class StackedDensityResponse(BaseModel):
    """Risk-neutral densities of every fitted expiry of a ticker, nearest first
    (the Parametric 'Stacked densities' view — all curves overlaid show they
    stay non-negative, i.e. no butterfly arbitrage)."""

    ticker: str
    expiries: list[StackedDensityItem]

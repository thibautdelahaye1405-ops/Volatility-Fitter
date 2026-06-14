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

from pydantic import BaseModel, Field

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
      * ``enforceCalendar`` — global default for the calendar-arbitrage fix the
        surface fit applies (SurfaceFitRequest seeds from it).
      * ``eventsEnabled`` — global default for event-time dilation (term view).
      * ``varSwapEnabled`` — whether the var-swap level is surfaced.
      * ``dynamicsRegime`` / ``ssr`` — seed defaults for the spot-vol scenario.
      * ``gridXNodes`` / ``gridTNodes`` / ``gridRegLambda`` — default vertex grid
        and roughness of the local-vol-affine fit (AffineFitRequest seeds them).
      * ``autoLoadPrior`` — seed the saved prior as the fit prior on node load.

    Stubbed this phase (persisted UI state only; behaviour is a documented TODO):
      * ``autoCalibrate`` — auto-refit on every quote edit (True, today's
        behaviour) vs a manual "Calibrate" trigger gating refits.
      * ``spotMode`` — stream live spot and re-price ("realtime") vs freeze spot
        at load ("static"); pairs with the existing As-of selector.
    """

    # arbitrage / events / var-swap (wired as global defaults)
    enforceCalendar: bool = True
    eventsEnabled: bool = True
    varSwapEnabled: bool = True
    # prior default
    autoLoadPrior: bool = False
    # local-vol-affine vertex grid + roughness defaults
    gridXNodes: int = Field(7, ge=3, le=15)
    gridTNodes: int = Field(4, ge=2, le=8)
    gridRegLambda: float = Field(1e-2, ge=0.0, le=1e4)
    # editable penalty strength (changes calibration output)
    calendarWeight: float = Field(1e6, ge=0.0)
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
    # stubbed this phase (UI state only; behaviour TODO)
    autoCalibrate: bool = True
    spotMode: Literal["realtime", "static"] = "static"


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


class SmileData(BaseModel):
    """Everything the Smile Viewer needs for one (underlying, expiry) node."""

    ticker: str
    expiry: str  # ISO date
    T: float  # year fraction to expiry
    forward: float
    model: list[SmilePoint]
    prior: list[SmilePoint]
    quotes: list[QuoteBand]
    kMin: float
    kMax: float
    diagnostics: SmileDiagnostics
    canUndo: bool  # quote-edit session undo/redo availability
    canRedo: bool  # (both False when the node has no edit session yet)


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
    varSwapVol: float  # sqrt(var-swap strike / t)
    maxIvErrorBp: float


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

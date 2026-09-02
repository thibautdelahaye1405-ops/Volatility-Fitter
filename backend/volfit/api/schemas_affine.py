"""Schemas for the direct local-vol-affine surface fit (ROADMAP next-up #1).

POST /fit/affine/{ticker} calibrates the piecewise-affine local-VARIANCE
surface of Docs/piecewise_affine_local_variance_calibration.tex straight to
the ticker's option quotes (volfit.api.affine_fit) — distinct from
GET /localvol/{ticker}, which *extracts* a Dupire grid from the fitted LQD
smiles. The response carries the calibrated nodal surface (for the heatmap),
the per-expiry arbitrage-free smiles reconstructed by inverting the Dupire
PDE call prices (for charting vs quotes), and the option-fit / no-arbitrage
diagnostics. Field names are camelCase to match the frontend contract; the
smile points/quote bands reuse volfit.api.schemas.SmilePoint / QuoteBand.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from volfit.api.schemas import DistributionArrays, FitMode, QuoteBand, SmilePoint, VarSwapInfo


class AffineFitRequest(BaseModel):
    """Affine surface fit request. The vertex grid + roughness are NO LONGER on
    the request: they are global hyperparameters in OptionsSettings (gridXNodes /
    gridTNodes / gridRegLambda / gridRegRho), the single source of truth read by
    the fit (volfit.api.affine_fit). Only the fit mode and the nodal-variance
    bounds remain per-request. ``varLo``/``varHi`` bound the nodal local variances
    (vol bounds sqrt of these)."""

    fitMode: FitMode = "mid"
    varLo: float = Field(0.0025, gt=0.0, le=0.1)  # vol floor 5%
    varHi: float = Field(0.36, gt=0.0, le=4.0)  # vol cap 60%


class OptimalGridSize(BaseModel):
    """Suggested vertex-grid size for a ticker's observed quotes.

    ``gridTNodes = 0`` means one time vertex per observed expiry (auto); the
    strike count is ~ the average quotes per expiry, so total vertices
    (gridXNodes * #expiries) approximates the total observed quotes."""

    gridXNodes: int
    gridTNodes: int  # 0 = auto (one per observed expiry)
    nQuotes: int
    nExpiries: int


class GridInfo(BaseModel):
    """The ACTUAL local-vol vertex grid the current Options produce for a ticker.

    Lets the Options panel show the resolved grid (time x strike vertices) so the
    floor / delta-axis / convex-wing hyperparameters are visible and consistent
    with what the fit will build (volfit.api.affine_fit.grid_info)."""

    nTNodes: int  # time vertices (incl. t = 0 and the pre-first-expiry node)
    nXNodes: int  # strike vertices (incl. the ATM x = 1 node)
    nVertices: int  # nTNodes * nXNodes (the calibrated parameter count)
    convexWingNodes: int  # strike vertices in the convex-wing region (0 if off)
    strikeMode: str  # "delta" | "linear"
    nExpiries: int  # quotable lit expiries the grid was sized to
    capVol: float = 0.0  # resolved adaptive local-vol CAP (vol, e.g. 2.7 = 270%)
    floorVol: float = 0.0  # resolved local-vol FLOOR (vol)


class AffineSmile(BaseModel):
    """One expiry's reconstructed arbitrage-free smile plus its quotes."""

    expiry: str  # ISO date
    t: float  # CALENDAR year fraction (maturity axis)
    tau: float = 0.0  # event-weighted variance years the smile is quoted in (= t with no events)
    forward: float = 0.0  # active forward (for the strike / %ATM axis transforms)
    model: list[SmilePoint]  # reconstructed IV curve (Dupire PDE -> Black inv)
    #: The same reconstructed curve UNTRUNCATED to the shared display grid
    #: (V3.3 item 3): [min(K_DISPLAY_LO, k_obs_lo - pad), min(max(K_DISPLAY_HI,
    #: k_obs_hi + pad), ln(x_max) - eps)] — the right edge clamped inside the
    #: PDE lattice so clamped prices are never inverted. Inversion is guarded
    #: by a normalized time-value floor; below it the total variance extends
    #: flat-in-k from the last reliable point (volfit.api.affine_views_ext).
    #: Contains ``model``'s grid points bit-for-bit; ``model`` itself (five
    #: consumers couple to its quoted-range x-domain) is UNTOUCHED. Empty on
    #: older cached payloads / degenerate expiries.
    modelExt: list[SmilePoint] = []
    #: The active fetched prior, transported to the current forward and sampled on
    #: this smile's k grid (dotted spot-updated overlay); empty when no active prior.
    prior: list[SmilePoint] = []
    priorTransported: bool = False
    quotes: list[QuoteBand]  # the calibrated quote band at each strike
    varSwap: VarSwapInfo  # var-swap quote (shared with Parametric) + model level
    maxIvErrorBp: float  # worst |model - quote mid| IV over the quotes, bp
    #: Weighted RMS vol error of THIS expiry, on the calibration-consistent basis
    #: shared with the Parametric workspace (distance to the chosen fit-target
    #: band, the active weighting scheme, the var-swap quote). Decimal vol.
    rmsError: float = 0.0
    #: HONEST per-expiry IV residual RMS (bp): the calibrated surface repriced on
    #: a CONVERGED operator (models.localvol.reprice, dt/4 + dx/2). In-operator
    #: residuals are blind to time-discretization error (the optimizer cancels
    #: it), so this is the number to judge the fit by — a large gap to the
    #: in-operator rms flags an operator-compensated (untrustworthy) surface.
    rmsConvergedBp: float = 0.0
    #: Risk-neutral density from the Dupire PDE call prices directly (d2C/dx2),
    #: which is smooth and non-negative by construction — far cleaner than the
    #: Breeden-Litzenberger-via-implied-vol density (which clamps to 0 at short
    #: maturities). Powers the per-expiry Local-Vol density.
    density: DistributionArrays | None = None
    #: The stacked "Densities" overlay curve: the SAME lattice density as
    #: ``density`` but evaluated on the converged-operator reprice (dx/2, dt/4),
    #: left-extended to the display lower bound (k_min = -1.4; ~0 out there,
    #: drawn for range) and trimmed on the right to the central mass. Since
    #: 2026-09-03 this is the model's own density — the former Breeden-
    #: Litzenberger rebuild from the reconstructed IV curve drew a sawtooth on
    #: long maturities and a smoothed, misplaced curve on short ones.
    densityExt: DistributionArrays | None = None


class AffineFitResponse(BaseModel):
    """Calibrated local-variance surface + reconstructed smiles + diagnostics."""

    ticker: str
    tNodes: list[float]  # vertex times (rows of the heatmap)
    xNodes: list[float]  # vertex normalized strikes x = K/F (columns)
    localVol: list[list[float]]  # sqrt(nodal variance), one row per t-node
    #: Per-cell diagonal of the model's own (qhull) triangulation: True =
    #: cell (i, j) splits along (t_i, x_j)--(t_{i+1}, x_{j+1}).  Shape
    #: (len(tNodes)-1) x (len(xNodes)-1).  Lets the viewer draw the PRICING
    #: triangulation instead of a display convention (Note 04, the
    #: degenerate-Delaunay remark).  Empty for older payloads / no fit.
    cellDiagMain: list[list[bool]] = []
    smiles: list[AffineSmile]  # nearest expiry first
    rmsPriceError: float  # normalized-price residual RMS / max over all quotes
    maxPriceError: float
    rmsIvErrorBp: float  # implied-vol residual RMS / max over all quotes, bp
    maxIvErrorBp: float
    #: Converged-operator reprice metrics (models.localvol.reprice): the SAME
    #: per-quote IV residuals as rmsIvErrorBp/maxIvErrorBp but priced on a
    #: refined march (dt/4, dx/2) of the calibrated surface. The honest fit
    #: quality — in-operator rms cannot see operator error (fix-#3 lesson).
    rmsConvergedBp: float = 0.0
    maxConvergedBp: float = 0.0
    #: Whole-surface weighted RMS vol error (all expiries pooled), the same
    #: calibration-consistent basis as AffineSmile.rmsError. Decimal vol.
    surfaceRmsError: float = 0.0
    minDensity: list[float]  # per-expiry butterfly proxy (min 2nd diff in x)
    calendarViolations: int  # adjacent-maturity price decreases on the PDE grid
    # --- worst-crossing LOCATION (V3.3 item 10): where the deepest adjacent-
    # maturity price decrease sits on the PDE lattice. Both None when
    # calendarViolations == 0 (the count keeps its own -1e-9 lattice tolerance).
    #: Index i of the violating pair: expiries[i] (near) -> expiries[i+1] (far).
    calendarWorstPair: int | None = None
    #: Log-moneyness k = ln(x) of the worst crossing on the PDE strike grid.
    calendarWorstK: float | None = None
    arbitrageFree: bool
    nEvals: int  # calibration PDE solves
    message: str  # optimizer termination message
    stale: bool = False  # inputs drifted since the last LV calibration (needs Calibrate)
    #: False when the LV surface has never been calibrated (gated workflow, before
    #: the Calibrate button): all arrays empty, the UI shows a "Calibrate" cue.
    hasFit: bool = True


class AffineTraceFrameOut(BaseModel):
    """One accepted-step checkpoint of the LV calibration replay (V3.5 item 13)."""

    nEvals: int  # objective evaluations spent when this iterate was accepted
    cost: float  # total LSQ cost 0.5*||r||^2 at the iterate
    #: sqrt(nodal variance) grid at the iterate — same shape/orientation as
    #: AffineFitResponse.localVol (rows = tNodes, columns = xNodes), so the
    #: heatmap can be driven frame by frame.
    localVol: list[list[float]]
    #: Per-expiry option-residual RMS (weighted price units, the LSQ's own
    #: normalization) — one entry per ``expiries`` column, descending over the
    #: replay as the prices converge.
    expiryRms: list[float]


class AffineTraceResponse(BaseModel):
    """GET /fit/affine/{ticker}/trace — post-hoc replay of the last TRACED fit.

    Honest numbers only: every frame is an iterate the solver actually accepted
    (volfit.models.localvol.affine_trace); nothing is recomputed per frame.
    Served read-only from a side channel (never triggers a fit); 404 until a
    traced fit has completed this session.
    """

    ticker: str
    tNodes: list[float]  # vertex times of every frame's grid (rows)
    xNodes: list[float]  # vertex strikes x = K/F (columns)
    expiries: list[float]  # tau per expiryRms column (real fitted expiries only)
    frames: list[AffineTraceFrameOut]  # ascending nEvals; LAST = converged surface

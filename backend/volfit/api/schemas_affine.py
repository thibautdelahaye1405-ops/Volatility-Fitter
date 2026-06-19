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
    #: Risk-neutral density from the Dupire PDE call prices directly (d2C/dx2),
    #: which is smooth and non-negative by construction — far cleaner than the
    #: Breeden-Litzenberger-via-implied-vol density (which clamps to 0 at short
    #: maturities). Powers the per-expiry Local-Vol density.
    density: DistributionArrays | None = None
    #: Density left-extended to the display lower bound (k_min = -1.4) for the
    #: stacked "Densities" overlay (Breeden-Litzenberger on the reconstructed
    #: smile; allowed to taper to ~0 in the deep tail, unlike ``density``).
    densityExt: DistributionArrays | None = None


class AffineFitResponse(BaseModel):
    """Calibrated local-variance surface + reconstructed smiles + diagnostics."""

    ticker: str
    tNodes: list[float]  # vertex times (rows of the heatmap)
    xNodes: list[float]  # vertex normalized strikes x = K/F (columns)
    localVol: list[list[float]]  # sqrt(nodal variance), one row per t-node
    smiles: list[AffineSmile]  # nearest expiry first
    rmsPriceError: float  # normalized-price residual RMS / max over all quotes
    maxPriceError: float
    rmsIvErrorBp: float  # implied-vol residual RMS / max over all quotes, bp
    maxIvErrorBp: float
    #: Whole-surface weighted RMS vol error (all expiries pooled), the same
    #: calibration-consistent basis as AffineSmile.rmsError. Decimal vol.
    surfaceRmsError: float = 0.0
    minDensity: list[float]  # per-expiry butterfly proxy (min 2nd diff in x)
    calendarViolations: int  # adjacent-maturity price decreases on the PDE grid
    arbitrageFree: bool
    nEvals: int  # calibration PDE solves
    message: str  # optimizer termination message
    stale: bool = False  # inputs drifted since the last LV calibration (needs Calibrate)
    #: False when the LV surface has never been calibrated (gated workflow, before
    #: the Calibrate button): all arrays empty, the UI shows a "Calibrate" cue.
    hasFit: bool = True

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


class AffineSmile(BaseModel):
    """One expiry's reconstructed arbitrage-free smile plus its quotes."""

    expiry: str  # ISO date
    t: float  # CALENDAR year fraction (maturity axis)
    tau: float = 0.0  # event-weighted variance years the smile is quoted in (= t with no events)
    model: list[SmilePoint]  # reconstructed IV curve (Dupire PDE -> Black inv)
    #: The active fetched prior, transported to the current forward and sampled on
    #: this smile's k grid (dotted spot-updated overlay); empty when no active prior.
    prior: list[SmilePoint] = []
    priorTransported: bool = False
    quotes: list[QuoteBand]  # the calibrated quote band at each strike
    varSwap: VarSwapInfo  # var-swap quote (shared with Parametric) + model level
    maxIvErrorBp: float  # worst |model - quote mid| IV over the quotes, bp
    #: Risk-neutral density from the Dupire PDE call prices directly (d2C/dx2),
    #: which is smooth and non-negative by construction — far cleaner than the
    #: Breeden-Litzenberger-via-implied-vol density (which clamps to 0 at short
    #: maturities). Powers the Local-Vol Density sub-tab.
    density: DistributionArrays | None = None


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
    minDensity: list[float]  # per-expiry butterfly proxy (min 2nd diff in x)
    calendarViolations: int  # adjacent-maturity price decreases on the PDE grid
    arbitrageFree: bool
    nEvals: int  # calibration PDE solves
    message: str  # optimizer termination message
    stale: bool = False  # inputs drifted since the last LV calibration (needs Calibrate)

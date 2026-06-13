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

from volfit.api.schemas import FitMode, QuoteBand, SmilePoint


class AffineFitRequest(BaseModel):
    """Vertex grid and regularization of the affine surface calibration.

    The vertex set is a tensor grid: ``nTNodes`` times (0 plus a spread of the
    listed expiries) by ``nXNodes`` normalized strikes x = K/F spanning the
    quoted range (the ATM node x = 1 is always included). ``regLambda`` weights
    the second-difference roughness penalty, ``regRho`` its time-vs-strike
    balance; ``varLo``/``varHi`` bound the nodal local variances (vol bounds
    sqrt of these). Defaults give a fast, gently smoothed live fit.
    """

    fitMode: FitMode = "mid"
    nXNodes: int = Field(7, ge=3, le=15)
    nTNodes: int = Field(4, ge=2, le=8)
    regLambda: float = Field(1e-2, ge=0.0, le=1e4)
    regRho: float = Field(1.0, ge=0.0, le=10.0)
    varLo: float = Field(0.0025, gt=0.0, le=0.1)  # vol floor 5%
    varHi: float = Field(0.36, gt=0.0, le=4.0)  # vol cap 60%


class AffineSmile(BaseModel):
    """One expiry's reconstructed arbitrage-free smile plus its quotes."""

    expiry: str  # ISO date
    t: float  # year fraction
    model: list[SmilePoint]  # reconstructed IV curve (Dupire PDE -> Black inv)
    quotes: list[QuoteBand]  # the calibrated quote band at each strike
    maxIvErrorBp: float  # worst |model - quote mid| IV over the quotes, bp


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

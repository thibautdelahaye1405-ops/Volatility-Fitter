"""Full local-volatility grid model (Dupire): grid, PDE pricer, extraction.

The arbitrage gate is structural: LocalVolGrid only holds strictly positive
local vols, the Dupire forward PDE then produces butterfly- and calendar-
clean prices up to scheme noise, and LocalVolModel.diagnostics measures that
noise instead of assuming it away (roadmap risk #4: gate the model behind
diagnostics).
"""

from volfit.models.localvol.affine import (
    AffinePDESolution,
    AffineVarianceSurface,
    DupireSteps,
    precompute_dupire_steps,
    solve_affine_dupire,
)
from volfit.models.localvol.affine_calib import (
    AffineCalibration,
    AffineFitDiagnostics,
    OptionQuote,
    VarSwapQuote,
    calibrate_affine,
    varswap_const,
    varswap_weights,
)
from volfit.models.localvol.affine_gn import (
    GNResult,
    LinearizedJacobian,
    gauss_newton,
)
from volfit.models.localvol.dupire import (
    ExtractionResult,
    dupire_local_variance,
    extract_grid,
)
from volfit.models.localvol.grid import LocalVolGrid
from volfit.models.localvol.model import (
    LocalVolDiagnostics,
    LocalVolModel,
    LocalVolSlice,
)
from volfit.models.localvol.pde import PDESolution, solve_dupire
from volfit.models.localvol.varswap_pde import (
    VarSwapSteps,
    precompute_varswap_steps,
    solve_varswap_source,
)

__all__ = [
    "AffineCalibration",
    "AffineFitDiagnostics",
    "AffinePDESolution",
    "AffineVarianceSurface",
    "DupireSteps",
    "ExtractionResult",
    "GNResult",
    "LinearizedJacobian",
    "gauss_newton",
    "LocalVolDiagnostics",
    "LocalVolGrid",
    "LocalVolModel",
    "LocalVolSlice",
    "OptionQuote",
    "PDESolution",
    "VarSwapQuote",
    "VarSwapSteps",
    "precompute_varswap_steps",
    "solve_varswap_source",
    "calibrate_affine",
    "dupire_local_variance",
    "extract_grid",
    "precompute_dupire_steps",
    "solve_affine_dupire",
    "solve_dupire",
    "varswap_const",
    "varswap_weights",
]

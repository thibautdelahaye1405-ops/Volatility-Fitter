"""P1 piecewise-affine local-variance surface and its Dupire pricer — the façade.

Implements the parameterization and pricing map of
Docs/piecewise_affine_local_variance_calibration.tex, in three modules since
2026-09-10 (the 400-line policy; a pure move, byte-identical numerics):

- ``affine_surface``: ``AffineVarianceSurface`` (eq. (p1_lv)), the
  triangulations, the nodal-bound positivity, the row-sparse contractions
  ``sparse_dot`` / ``_sequential_nu``;
- ``affine_precompute``: ``AffinePDESolution``, ``DupireSteps`` and the
  theta-independent ``precompute_dupire_steps``;
- ``affine_dupire``: ``solve_affine_dupire``, the forward Dupire march
  (eq. (forward_dupire_normalized)) with its sensitivities.

Every public name is re-exported here, so ``from volfit.models.localvol.affine
import ...`` keeps working; new code may import the module it needs directly.
"""

from __future__ import annotations

from volfit.models.localvol.affine_dupire import solve_affine_dupire
from volfit.models.localvol.affine_precompute import (
    AffinePDESolution,
    DupireSteps,
    _precompute_dense,
    precompute_dupire_steps,
)
from volfit.models.localvol.affine_surface import (
    _INTERP_MODES,
    AffineVarianceSurface,
    _sequential_nu,
    sparse_dot,
)

__all__ = [
    "AffinePDESolution",
    "AffineVarianceSurface",
    "DupireSteps",
    "precompute_dupire_steps",
    "solve_affine_dupire",
    "sparse_dot",
]

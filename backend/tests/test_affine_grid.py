"""Regression: the affine PDE strike grid keeps the var-swap anchor x = 1.

A real ticker's strike range pushes the fine grid's x_max above the 2.5 floor and
off the 0.01 lattice; a linspace there lands x = 1 between nodes and
affine_calib.varswap_weights (called for EVERY smile via _model_varswap_vol)
422s the whole fit. The grid must be a uniform 0.01 lattice from 0 so 1.0 is
always node 100. (Synthetic's range floors at 2.5, which aligned — hence the
original miss.)
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.api.affine_fit import _pde_grids
from volfit.models.localvol.affine_calib import varswap_const, varswap_weights


@pytest.mark.parametrize("k_hi", [0.0, 0.336, 0.6, 0.8, 1.0, 1.25])
def test_pde_grid_keeps_x1_node_and_uniform(k_hi):
    x_grid, _ = _pde_grids(np.array([0.1, 0.5]), k_hi)
    assert np.any(x_grid == 1.0)  # exact float node (searchsorted equality)
    step = x_grid[1] - x_grid[0]
    assert np.allclose(np.diff(x_grid), step)  # uniform spacing for the PDE
    assert step == pytest.approx(0.01)
    # The var-swap replication must accept the grid (this raised the 422 live).
    varswap_weights(x_grid, 0.01)
    varswap_const(x_grid, 0.01)


def test_wide_range_grid_does_not_reject():
    """A SPY-like wide range (x_max well above 2.5, off the lattice) is fine."""
    x_grid, _ = _pde_grids(np.array([0.25, 1.0]), k_hi=0.95)
    assert x_grid[-1] > 2.5
    i = int(np.searchsorted(x_grid, 1.0))
    assert x_grid[i] == 1.0

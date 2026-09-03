"""Row-sparse local-variance evaluation (2026-09-03 perf fix).

``AffineVarianceSurface.variance`` used to build the dense (n_x × m) hat
basis every time step of a value-only reprice — on a wide SPY ladder with a
1-day front rung (1655 lattice nodes, 352 vertices, the converged reprice's
1088 steps) that was ~16 s of a 41 s LV fit: 40 % of the wall for display
and diagnostics. It now gathers each point's (<= 8) hat weights row-sparsely
and accumulates them in ascending column order from 0.0 — the sequential
sum the Numba march kernels perform — and the value-only banded march sums
the same way, so:

  * every sparse weight equals the dense basis entry it replaces (all four
    interpolation modes, with and without the left-wing linear continuation);
  * ``variance`` matches the dense ``basis() @ theta`` to round-off;
  * a value-only ``solve_affine_dupire`` and ``reprice_affine_dupire`` of the
    same surface agree bit-for-bit (the test_lv_wing_inversion lock, kept).
"""

import numpy as np
import pytest

from volfit.models.localvol.affine import AffineVarianceSurface, solve_affine_dupire
from volfit.models.localvol.reprice import reprice_affine_dupire

T_NODES = np.array([0.0, 0.5, 1.0])
X_NODES = np.array([0.5, 0.8, 1.0, 1.2, 2.0])
THETA = np.array([
    [0.09, 0.05, 0.04, 0.045, 0.06],
    [0.08, 0.05, 0.04, 0.045, 0.07],
    [0.07, 0.05, 0.04, 0.045, 0.08],
])
X = 0.01 * np.arange(251)


def _dense_from_sparse(surface: AffineVarianceSurface, x: np.ndarray, t: float) -> np.ndarray:
    cols, vals = surface._sparse_weights(x, t)
    out = np.zeros((x.size, surface.n_params))
    rows = np.repeat(np.arange(x.size), cols.shape[1])
    np.add.at(out, (rows, cols.ravel()), vals.ravel())
    return out


@pytest.mark.parametrize("interp", ["delaunay", "tri_lower", "tri_upper", "bilinear"])
@pytest.mark.parametrize("left_a", [0.0, 1.5])
@pytest.mark.parametrize("t", [0.0, 0.3, 0.5, 0.77, 1.0])
def test_sparse_weights_equal_dense_basis_entries(interp, left_a, t):
    surf = AffineVarianceSurface(T_NODES, X_NODES, THETA, interp=interp, left_extrap_a=left_a)
    dense = surf.basis(X, t)
    assert np.array_equal(_dense_from_sparse(surf, X, t), dense)
    nu = surf.variance(X, t)
    np.testing.assert_allclose(nu, dense @ THETA.ravel(), rtol=0.0, atol=1e-15)
    # Below x_nodes[0] the continuation is linear in x with slope a x the
    # first cell's slope (flat when a = 0).
    below = X < X_NODES[0]
    slope = (nu[below][1:] - nu[below][:-1]) / 0.01
    if left_a == 0.0:
        np.testing.assert_allclose(slope, 0.0, atol=1e-14)
    else:
        assert np.allclose(slope, slope[0], atol=1e-10)


def test_value_only_solve_and_reprice_agree_bit_for_bit_with_left_slope():
    surf = AffineVarianceSurface(T_NODES, X_NODES, THETA, left_extrap_a=1.5)
    t_grid = np.linspace(0.0, 0.5, 51)
    a = solve_affine_dupire(surf, X, t_grid, [0.5])
    b = reprice_affine_dupire(surf, X, t_grid, [0.5])
    assert np.array_equal(a.prices, b.prices)

"""Cubic Hermite interpolation on the uniform logit grid.

The LQD quadrature knows the *exact* derivatives of both curves at every
node — dQ/dz = e^{g(Lambda(z))} and dA/dz = -e^{Q(z)} u(1-u) — so cubic
Hermite interpolation achieves O(h^4) accuracy without any spline solve.
This is what makes finite-difference Greeks of the priced smile clean.
"""

from __future__ import annotations

import numpy as np


def hermite_eval(
    x: np.ndarray,
    x0: float,
    step: float,
    values: np.ndarray,
    derivs: np.ndarray,
) -> np.ndarray:
    """Evaluate the piecewise cubic Hermite interpolant on a uniform grid.

    ``values``/``derivs`` are nodal values and exact nodal derivatives of the
    interpolated function on the grid x0 + step * j. Queries are clamped to
    the grid range.
    """
    x = np.asarray(x, dtype=float)
    n_seg = values.size - 1
    pos = np.clip((x - x0) / step, 0.0, n_seg)
    idx = np.minimum(pos.astype(int), n_seg - 1)
    t = pos - idx

    t2 = t * t
    t3 = t2 * t
    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2

    return (
        h00 * values[idx]
        + h10 * step * derivs[idx]
        + h01 * values[idx + 1]
        + h11 * step * derivs[idx + 1]
    )


def hermite_invert(
    y: np.ndarray,
    x0: float,
    step: float,
    values: np.ndarray,
    derivs: np.ndarray,
    n_newton: int = 4,
) -> np.ndarray:
    """Solve interpolant(x) = y for a strictly increasing Hermite interpolant.

    A linear-interpolation seed (already O(h^2) accurate) followed by a few
    Newton steps reaches machine precision; the Newton slope uses the exact
    nodal derivative field, linearly interpolated, which is ample for
    convergence of the residual to round-off.
    """
    y = np.asarray(y, dtype=float)
    grid = x0 + step * np.arange(values.size)
    x = np.interp(y, values, grid)
    for _ in range(n_newton):
        residual = hermite_eval(x, x0, step, values, derivs) - y
        slope = np.maximum(np.interp(x, grid, derivs), 1e-300)
        x = np.clip(x - residual / slope, grid[0], grid[-1])
    return x

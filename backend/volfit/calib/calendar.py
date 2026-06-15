"""Calendar-arbitrage constraints via integrated upper-quantile curves.

Note section 10 (Docs/lqd_model_note.tex): with all expiries normalized by
their forwards, absence of calendar arbitrage is the convex order
Y_{T_i} <=_cx Y_{T_j}, equivalent to

    G_i(alpha) = int_alpha^1 e^{Q_i(u)} du  <=  G_j(alpha)   for all alpha
                                                  (eq. lqd_calendar).

Because du = u(1-u) dz in the logit coordinate, G(alpha) is exactly the
asset-share integral A(z) at z = logit(alpha) — which every built LQDSlice
already carries on the shared quadrature grid. Constraint evaluation is
therefore an elementwise comparison of ``a_z`` arrays: no quantile inversion,
no per-strike call comparison, and the grid is uniform in z, which allocates
points to the wings exactly as the note recommends (section 10.2).
"""

from __future__ import annotations

import numpy as np

from volfit.models.lqd.quadrature import LQDSlice

# Constraint subsampling stride on the default 8001-point grid: every 25th
# node gives ~320 constraint points, dense enough for smooth quantiles while
# keeping the optimizer's residual vector small.
CAL_STRIDE = 25


def calendar_grid_indices(n_points: int, stride: int = CAL_STRIDE) -> np.ndarray:
    """Indices of the constraint subgrid (always includes the last node)."""
    idx = np.arange(0, n_points, stride)
    if idx[-1] != n_points - 1:
        idx = np.append(idx, n_points - 1)
    return idx


def calendar_violation(near: LQDSlice, far: LQDSlice) -> float:
    """Worst violation max_alpha (G_near - G_far), >= 0 means arbitrage.

    Both slices must be built on the same logit grid (the default), so the
    curves align node by node.
    """
    if near.z.shape != far.z.shape:
        raise ValueError("slices must share the same quadrature grid")
    return float(np.max(near.a_z - far.a_z))


def calendar_floor(near: LQDSlice, stride: int = CAL_STRIDE, tol: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Constraint data (indices, floor values) for fitting the *next* expiry:
    the later slice must satisfy a_z[idx] >= floor (eq. grid_calendar)."""
    idx = calendar_grid_indices(near.a_z.size, stride)
    return idx, near.a_z[idx] - tol


def calendar_floor_targets(
    near: LQDSlice, stride: int = CAL_STRIDE, tol: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Calendar floor as (z-values, floor) for fitting the *next* expiry.

    Identical information to ``calendar_floor`` but keyed on the constraint
    z-*coordinates* rather than grid indices, so the next slice can enforce
    A(z) >= floor by Hermite-evaluating its own curve at those z — valid even
    when it is calibrated on a coarser optimization grid than ``near``. On the
    native grid the two forms are bit-for-bit equivalent (Hermite at a node).
    """
    idx = calendar_grid_indices(near.a_z.size, stride)
    return near.z[idx], near.a_z[idx] - tol

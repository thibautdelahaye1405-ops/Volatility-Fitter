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

from volfit.models.base import SmileModel
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


# --------------------------------------------------------------------------
# Model-agnostic calendar floor (SVI / Multi-Core SIV overlays)
# --------------------------------------------------------------------------
# The asset-share form above is exact but LQD-specific (only LQDSlice carries
# the integrated upper-quantile curve a_z). The SVI and sigmoid overlays carry
# no such curve, so they use Gatheral's equivalent surface condition: absence of
# calendar arbitrage <=> total implied variance is non-decreasing in maturity at
# every fixed log-moneyness, w_far(k) >= w_near(k). This is enforced as a soft
# floor on a uniform log-moneyness grid spanning the drawn wing range.

#: Default log-moneyness span and resolution for the total-variance floor. The
#: range matches the curves the viewers draw (k in [-1, 1]); ~161 nodes parallels
#: the ~320-point LQD constraint subgrid while keeping the residual vector small.
VAR_FLOOR_KMIN = -1.0
VAR_FLOOR_KMAX = 1.0
VAR_FLOOR_N = 161


def variance_floor_grid(
    kmin: float = VAR_FLOOR_KMIN, kmax: float = VAR_FLOOR_KMAX, n: int = VAR_FLOOR_N
) -> np.ndarray:
    """Uniform log-moneyness grid for the model-agnostic calendar floor."""
    return np.linspace(kmin, kmax, n)


#: Resolution of the data-confined floor grid (see variance_floor_grid_from).
VAR_FLOOR_N_DATA = 41


def variance_floor_grid_from(k_quotes: np.ndarray, n: int = VAR_FLOOR_N_DATA) -> np.ndarray:
    """Floor grid confined to the *observed* quote range [min k, max k].

    Calendar arbitrage is only meaningful where prices are observable; enforcing
    the floor on the fixed wide grid (k in [-1, 1]) compares pure model
    extrapolation between expiries, and for families with linear wings (SVI) a
    steep short-dated slice extrapolates to far higher wing variance than a
    flatter long-dated one, manufacturing a phantom violation that wrecks the
    in-data fit. Restricting to the traded span keeps the constraint where the
    fit and the data both live. Empty quotes fall back to the wide grid.
    """
    k = np.asarray(k_quotes, dtype=float)
    if k.size == 0:
        return variance_floor_grid()
    return np.linspace(float(k.min()), float(k.max()), n)


def variance_floor_targets(
    prev: SmileModel, k_grid: np.ndarray | None = None, tol: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Calendar floor (k, w_floor) for fitting the *next* (longer) expiry's overlay.

    Reads only ``prev.implied_w`` (the previous, shorter slice's total variance),
    so it applies to any SmileModel — RawSVI or MultiCoreSiv alike — unlike the
    LQD-only ``calendar_floor_targets`` above. The next slice penalizes
    ``max(w_floor - w_model(k), 0)`` so its total variance stays at or above the
    nearer expiry's at every k (Gatheral's no-calendar-arbitrage condition).
    """
    k = variance_floor_grid() if k_grid is None else np.asarray(k_grid, dtype=float)
    w_floor = np.asarray(prev.implied_w(k), dtype=float) - tol
    return k, w_floor

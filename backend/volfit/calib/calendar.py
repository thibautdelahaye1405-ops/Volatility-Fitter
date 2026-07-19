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

Support confinement (the symmetric-surface redesign, Phase 0). Calendar
arbitrage is only *identified* where both adjacent expiries have quotes: on
the full tail-dense z grid the comparison pits one slice's extrapolated wing
against the other's, and an acutely convex short-dated slice (whose LQD wing
continues the observed curvature) manufactures a phantom floor that drags the
later expiry's wing up and its in-data fit off the quotes (the SPY/NVDA
phantom-calendar case, Note 10).

Crucially, confinement CANNOT happen in the G(alpha) coordinate: G integrates
the exponentiated quantile over the whole upper tail [alpha, 1], so even at
an in-support alpha the comparison is contaminated by the extrapolated tail
(measured: windowing the a_z floor removes only ~half the phantom drag). The
support-confined constraint therefore lives in PRICE space at fixed strike —
the equivalent no-calendar-arbitrage statement C_far(k) >= C_near(k) on
forward-normalized calls — evaluated only on the intersection of the two
retained quote spans (``common_support`` / ``confined_calendar_floor``), with
a smooth taper fading the rows to zero over a small margin beyond it (so the
active set does not flip discontinuously as spans move between refits). The
published extrapolated wing is governed separately by the Notes 09/10
machinery (volfit.calib.extrap + publish-time projection), not by this floor.
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


# --------------------------------------------------------------------------
# Support confinement (symmetric-surface Phase 0)
# --------------------------------------------------------------------------
#: Taper margin beyond the common quote support, in log-moneyness: the floor
#: rows fade smoothly (cos^2) from full weight at the support edge to zero at
#: edge +/- margin. Fraction of the support width, floored/capped so very
#: narrow (0DTE pin) and very wide (LEAP) supports both get a sane margin.
TAPER_FRAC = 0.15
TAPER_MIN = 0.05
TAPER_MAX = 0.25


def common_support(
    k_near: np.ndarray, k_far: np.ndarray
) -> tuple[float, float] | None:
    """Intersection [max of mins, min of maxes] of two retained quote spans.

    Returns None when either span is empty or the intersection is — in which
    case there is NO strike where both expiries are observed and no pointwise
    calendar constraint is identified (only the low-dimensional tail contract
    applies there).
    """
    kn = np.asarray(k_near, dtype=float)
    kf = np.asarray(k_far, dtype=float)
    if kn.size == 0 or kf.size == 0:
        return None
    lo = max(float(kn.min()), float(kf.min()))
    hi = min(float(kn.max()), float(kf.max()))
    if not (hi > lo):
        return None
    return lo, hi


def _taper_margin(lo: float, hi: float) -> float:
    """Smooth-fade width beyond the support edges (see TAPER_* above)."""
    return float(np.clip(TAPER_FRAC * (hi - lo), TAPER_MIN, TAPER_MAX))


def support_taper(k: np.ndarray, window: tuple[float, float]) -> np.ndarray:
    """Per-point weight in [0, 1]: 1 inside ``window``, cos^2 falloff over the
    taper margin beyond each edge, 0 outside. Smooth (C^1) in k."""
    lo, hi = window
    margin = _taper_margin(lo, hi)
    k = np.asarray(k, dtype=float)
    # Signed distance beyond the window, normalized by the margin.
    d = np.maximum(np.maximum(lo - k, k - hi), 0.0) / margin
    return np.where(d >= 1.0, 0.0, np.cos(0.5 * np.pi * np.minimum(d, 1.0)) ** 2)


#: Node count of the confined price-space floor across the common support
#: (plus its taper margins); parallels VAR_FLOOR_N_DATA on the overlay side.
CAL_PRICE_N = 49

#: Node count of the windowed violation diagnostic grid.
CAL_VIOLATION_N = 201


def tapered_support_grid(
    window: tuple[float, float], n: int
) -> tuple[np.ndarray, np.ndarray]:
    """Uniform strike grid across ``window`` plus its taper margins, with the
    per-node fade weights; zero-weight nodes are dropped."""
    lo, hi = window
    margin = _taper_margin(lo, hi)
    k = np.linspace(lo - margin, hi + margin, n)
    taper = support_taper(k, window)
    keep = taper > 0.0
    return k[keep], taper[keep]


def confined_calendar_floor(
    near: LQDSlice,
    window: tuple[float, float],
    n: int = CAL_PRICE_N,
    tol: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Support-confined price-space floor: (k, price_floor, taper) for the
    *next* expiry, which must keep its normalized call at or above the near
    slice's, C_far(k) >= C_near(k), on the common quote support.

    NOT expressible as a windowed a_z floor: G(alpha) integrates the whole
    upper tail, so any G-space comparison leaks the extrapolated wing back in
    (module docstring). ``taper`` fades the rows over the margin beyond the
    support so the active set moves smoothly as spans shift between refits.
    Returns None when nothing survives the taper (degenerate window).
    """
    k, taper = tapered_support_grid(window, n)
    if k.size == 0:
        return None
    return k, np.asarray(near.call_price(k), dtype=float) - tol, taper


def calendar_violation_windowed(
    near: LQDSlice, far: LQDSlice, window: tuple[float, float] | None
) -> float:
    """Worst identified calendar violation on the common quote support:
    max over k in ``window`` of C_near(k) - C_far(k) (normalized calls; >= 0
    means arbitrage). None falls back to the full-grid a_z diagnostic
    ``calendar_violation``. Both measures share the (normalized) price scale,
    so tolerances are comparable.
    """
    if window is None:
        return calendar_violation(near, far)
    k = np.linspace(window[0], window[1], CAL_VIOLATION_N)
    return float(np.max(near.call_price(k) - far.call_price(k)))


def calendar_violation_argmax(
    near: LQDSlice, far: LQDSlice, window: tuple[float, float] | None
) -> tuple[float, float | None]:
    """``calendar_violation_windowed`` plus WHERE it is worst (R5: the
    cheapest offending calendar trade).  Returns ``(violation, k_star)``:
    the worst identified normalized-price violation and the log-moneyness of
    the strike where selling the near call against the far one pays most.
    ``k_star`` is None when there is no window (full-grid diagnostic) or no
    positive violation — no trade to name."""
    if window is None:
        return calendar_violation(near, far), None
    k = np.linspace(window[0], window[1], CAL_VIOLATION_N)
    gap = np.asarray(near.call_price(k) - far.call_price(k), dtype=float)
    j = int(np.argmax(gap))
    viol = float(gap[j])
    return viol, (float(k[j]) if viol > 0.0 else None)


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


def variance_floor_grid_common(
    k_near: np.ndarray, k_far: np.ndarray, n: int = VAR_FLOOR_N_DATA
) -> np.ndarray | None:
    """Floor grid confined to the COMMON quote support of both expiries.

    ``variance_floor_grid_from`` confines the model-agnostic floor to the
    later expiry's traded span — but a later expiry quoted WIDER than the near
    one still samples the near slice's extrapolated wing there (the same
    phantom-violation mechanism, from the other side). The constraint is only
    identified on the intersection of the two retained spans; None (empty
    intersection, or an unknown near span) means no pointwise floor at all.
    """
    window = common_support(k_near, k_far)
    if window is None:
        return None
    return np.linspace(window[0], window[1], n)


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

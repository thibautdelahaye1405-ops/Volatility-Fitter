"""Untruncated per-expiry LV smile extension (roadmap V3.3, item 3).

The parametric stacked-variance view is full-width (surface.py evaluates every
expiry on one union display grid and LQD extrapolates arb-free wings); the LV
view was not — each expiry's ``model`` curve is reconstructed only on its own
quoted range ±pad (affine_fit._reconstruct_smile), so short expiries draw as
stubs. This module builds ``AffineSmile.modelExt``: the SAME Dupire-price →
Black inversion on the SHARED display grid

    [min(K_DISPLAY_LO, k_obs_lo - pad), max(K_DISPLAY_HI, k_obs_hi + pad)]

Guards, in order:

  * the display grid CONTAINS ``_reconstruct_smile``'s own linspace bit-for-bit
    (same endpoints, same count), so modelExt ≡ model on the quoted-range grid
    points — one inversion, two truncations;
  * inversion only where the normalized OTM time value clears ``_EXT_TV_FLOOR``
    (mirrors service._WING_TV_FLOOR — the book-ch.2 publication rule: remote
    wings are never read off prices this small);
  * the right wing beyond the core is read off a DISPLAY lattice that carries
    the calibration lattice past the display cap by a buffer (``display_
    lattice``), and never inside the Dirichlet boundary layer of whichever
    lattice serves it (``clean_right_edge``) — see "The right-edge layer";
  * below the floor / past the clean edge the total variance w extends FLAT
    in k from the outermost reliable point (the _InterpSlice doctrine:
    np.interp's constant extrapolation) — honest "no information past here",
    never a fabricated wing slope, and vol = sqrt(w/t) stays bounded by the
    reliable curve.

The right-edge layer (2026-09-02). The forward Dupire march closes its lattice
with the Dirichlet condition C(., x_max) = 0. The exact call there is tiny but
not zero, and by the method of images the marched price is the free price
minus its mirror in the boundary:

    C_march(x) ≈ C_free(x) · (1 − exp(−2 c (x_max − x))),   c = −d ln C_free/dx.

So the last ~1/c of the lattice carries a linear-to-zero profile
(C_j ∝ x_max − x_j: the price ratios 1/2, 2/3, 3/4, … of the last nodes) and
inverting it collapses the implied vol toward the edge — 2 vol points over
the last dozen nodes and a cliff on the very last display point, which the
historical cap ln(x_max) − ε put ON the boundary node. Short-dated slices
show it most sharply because their wing prices are the SCHEME's exponential
tail (steep c, a narrow violent layer); long-dated slices have a wider,
gentler one. The cure is two-fold: the display march runs on a lattice that
reaches past the display cap by ``δk = ln(1/tol) · w / (2 k_cap)`` (the image
estimate for a Gaussian tail of total variance w, clamped to a sane band), and
the guard measures the local decay rate c on the marched prices and drops
every node whose image term exp(−2 c (x_max − x)) exceeds ``_LAYER_TOL`` —
the estimate is exact to first order where it matters (p^{(1+p)/(1−p)} ≈ p
for small p) and only over-lenient deep inside the layer, where both are far
above the tolerance.

Display/payload-only: ``model``, the calibration lattice and every calibrated
number are untouched (byte-identity of fits); the extension march is one
value-only call march (the put twin's precedent). Lives outside affine_fit.py
purely for the 400-line file policy (affine_fit is far past it).
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import SmilePoint
from volfit.core.black import black_otm, implied_total_variance_otm

#: Normalized time-value floor below which a Black inversion is numerically
#: meaningless — mirrors volfit.api.service._WING_TV_FLOOR (kept private
#: there; the doctrine is the book's, the value is shared).
_EXT_TV_FLOOR = 1e-14
#: Wing-extension grid step in k beyond the quoted-range core (the smooth
#: extrapolated wing reads fine coarser than the core — the service.py
#: N_CORE_POINTS precedent). 0.02 matches affine_fit._K_PAD.
_DK_EXT = 0.02
#: Right-edge safety margin inside the PDE lattice (log-x space): never invert
#: at the outermost lattice node itself.
_EDGE_EPS = 1e-6
#: Dirichlet-image pollution tolerance on the marched RIGHT-wing price: a node
#: whose estimated image term exp(-2 c (x_max - x)) exceeds this is inside the
#: boundary layer and is never inverted. 1e-3 in price is < 0.01 vol point at
#: any depth where the time value clears _EXT_TV_FLOOR.
_LAYER_TOL = 1e-3
#: Display-lattice buffer beyond the display cap, in k: the image estimate
#: ln(1/tol) · w / (2 k_cap) for the surface's slowest (largest-w) right tail,
#: clamped to [_EXT_DK_MIN, _EXT_DK_MAX] — the floor covers the scheme-tail
#: regime (steep, narrow layers), the ceiling bounds the march cost; the
#: guard stays the arbiter either way.
_EXT_DK_MIN = 0.25
_EXT_DK_MAX = 1.0
#: The display lattice never exceeds this multiple of the calibration lattice
#: (node budget for the one extra value march).
_EXT_X_MULT_MAX = 2.0


def _display_grid(
    k_lo: float, k_hi: float, core_lo: float, core_hi: float, n_core: int
) -> np.ndarray:
    """Shared display grid: the exact ``_reconstruct_smile`` core linspace plus
    coarser wing points out to [k_lo, k_hi]. The core endpoints/count are the
    caller's (affine_fit) own, so the core samples are bit-identical to
    ``model``'s grid — the modelExt ≡ model lock rides on this."""
    core = np.linspace(core_lo, core_hi, n_core)
    parts = [core]
    if k_lo < core_lo - 1e-12:
        n_left = int(np.ceil((core_lo - k_lo) / _DK_EXT))
        parts.insert(0, np.linspace(k_lo, core_lo, n_left + 1)[:-1])
    if k_hi > core_hi + 1e-12:
        n_right = int(np.ceil((k_hi - core_hi) / _DK_EXT))
        parts.append(np.linspace(core_hi, k_hi, n_right + 1)[1:])
    return np.concatenate(parts) if len(parts) > 1 else core


def display_lattice(
    x_grid: np.ndarray, k_hi_obs: float, w_tail: float
) -> np.ndarray | None:
    """The display march's strike lattice: the calibration lattice ``x_grid``
    (uniform ``dx · arange``, so every calibration node is reused and the seam
    at the core edge is round-off) carried past the display cap
    max(K_DISPLAY_HI, k_hi_obs) by the image-estimate buffer for a Gaussian
    tail of total variance ``w_tail`` (the surface's largest right-wing nodal
    variance × its longest maturity — an upper bound on any slice's w there).
    None when ``x_grid`` already reaches that far (no extra march needed)."""
    from volfit.api.service import K_DISPLAY_HI  # heavy module: lazy

    x = np.asarray(x_grid, dtype=float)
    dx = float(x[1] - x[0])
    k_cap = max(float(K_DISPLAY_HI), float(k_hi_obs))
    dk = np.log(1.0 / _LAYER_TOL) * max(float(w_tail), 0.0) / (2.0 * max(k_cap, 0.1))
    dk = float(np.clip(dk, _EXT_DK_MIN, _EXT_DK_MAX))
    x_max = min(float(np.exp(k_cap + dk)), _EXT_X_MULT_MAX * float(x[-1]))
    if x_max <= float(x[-1]) + 1e-12:
        return None
    n = int(np.ceil(round(x_max / dx, 6)))
    return dx * np.arange(n + 1)


def clean_right_edge(
    x: np.ndarray, prices: np.ndarray, tol: float = _LAYER_TOL
) -> float:
    """Log-moneyness of the outermost call-side lattice node OUTSIDE the
    Dirichlet boundary layer of a marched price row — -inf when none is.

    Per node j (x > 1, price finite, positive and above the inversion floor,
    with a usable left neighbour) the image term is estimated two ways and
    the smaller kept:

      * from the local decay rate c_j = −Δ ln C / Δx: p = exp(−2 c_j (x_max −
        x_j)) — exact for an exponential (scheme) tail and an UPPER bound for
        any log-concave one (the rate only grows outward), which makes it far
        too conservative near the money of a long-dated slice;
      * from the node's own implied total variance w_j: p = B(2 k_max − k_j,
        w_j) / C_j — the Black mirror, exact for a Gaussian tail and lenient
        for a heavier one only by a factor that costs < 0.01 vol point at the
        crossing.

    A non-decaying row (c_j ≤ 0) counts as polluted. The clean edge is the
    node before the first (innermost) polluted one — p grows monotonically
    toward the edge where it matters, and the first-order accuracy of the
    estimate at p ≈ tol is what the module docstring derives.
    """
    x = np.asarray(x, dtype=float)
    c = np.asarray(prices, dtype=float)
    ok = (x > 1.0) & np.isfinite(c) & (c >= _EXT_TV_FLOOR)
    ok[-1] = False  # the Dirichlet node itself
    idx = np.flatnonzero(ok)
    idx = idx[idx > 0]
    j = idx[ok[idx - 1]]  # nodes whose left neighbour is usable too
    if j.size == 0:
        return -np.inf
    rate = (np.log(c[j - 1]) - np.log(c[j])) / (x[j] - x[j - 1])
    p_rate = np.where(
        rate > 0.0, np.exp(-2.0 * np.maximum(rate, 0.0) * (x[-1] - x[j])), 1.0
    )
    k = np.log(x[j])
    w = np.asarray(implied_total_variance_otm(k, c[j]), dtype=float)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        mirror = black_otm(2.0 * float(np.log(x[-1])) - k, np.where(w > 0.0, w, 1.0))
        p_black = np.where(np.isfinite(w) & (w > 0.0), mirror / c[j], 1.0)
    p = np.minimum(p_rate, p_black)
    bad = ~np.isfinite(p) | (p > tol)
    if not np.any(bad):
        return float(np.log(x[j[-1]]))
    clean = j[: int(np.argmax(bad))]
    return float(np.log(x[clean[-1]])) if clean.size else -np.inf


def otm_implied_w(
    solution, put_solution, i_exp: int, grid: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """``(w, otm_price)`` on ``grid`` by OTM-side Black inversion: the call
    march above the forward (k >= 0), the put march below.

    ``put_solution`` is the value-only put twin of the calibrated march
    (reprice_affine_dupire(payoff="put"), same grids and time scheme): 1 - x
    lies in the exact kernel of the central stencil, so discrete parity
    C - P = 1 - x holds to round-off, the k = 0 seam is exact, and the left
    wing's time value keeps full relative accuracy instead of dying at the
    ~1e-16 absolute floor of ``price - intrinsic`` (the short-dated flat-left
    LV display bug — the LQD fix's mirror, see models.lqd.putside). None
    falls back to that parity conversion (the historical floor).
    """
    price = np.asarray(solution.price_at(i_exp, np.exp(grid)), dtype=float)
    otm = price
    neg = grid < 0.0
    if np.any(neg):
        if put_solution is not None:
            put = np.asarray(put_solution.price_at(i_exp, np.exp(grid)), dtype=float)
        else:
            put = price - (1.0 - np.exp(grid))
        otm = np.where(neg, put, price)
    w = np.asarray(implied_total_variance_otm(grid, otm), dtype=float)
    return w, otm


def extended_model(
    solution,
    i_exp: int,
    t: float,
    k_lo_obs: float,
    k_hi_obs: float,
    x_grid: np.ndarray,
    k_pad: float,
    n_core: int,
    put_solution=None,
    ext_call_solution=None,
) -> list[SmilePoint]:
    """One expiry's reconstructed IV curve on the shared display grid.

    ``solution`` is the calibrated Dupire march (has ``price_at``); ``t`` is
    the expiry's variance-time maturity (the clock its vols are quoted in);
    ``k_lo_obs``/``k_hi_obs`` the observed quote range; ``x_grid`` the PDE
    strike lattice; ``k_pad``/``n_core`` are affine_fit's own ``_K_PAD`` /
    ``_N_SMILE`` (passed in, not imported — no circular import, and the core
    grid provably matches ``_reconstruct_smile``'s). ``ext_call_solution`` is
    the value-only call march of the same surface on ``display_lattice``: it
    serves the right wing BEYOND the core (the core stays the calibrated
    march's own prices — the modelExt ≡ model lock); None keeps the right
    wing on ``solution``, capped inside its lattice and guarded all the same.
    Empty list when the expiry is degenerate or nothing is reliably invertible.
    """
    from volfit.api.service import K_DISPLAY_HI, K_DISPLAY_LO  # heavy module: lazy

    core_lo, core_hi = float(k_lo_obs) - k_pad, float(k_hi_obs) + k_pad
    right_sol = ext_call_solution if ext_call_solution is not None else solution
    x_right = np.asarray(right_sol.x_grid, dtype=float)
    k_right_cap = float(np.log(float(x_right[-1]))) - _EDGE_EPS
    k_lo = min(K_DISPLAY_LO, core_lo)
    k_hi = min(max(K_DISPLAY_HI, core_hi), k_right_cap)
    if not (np.isfinite(k_lo) and np.isfinite(k_hi)) or k_hi <= k_lo or t <= 0.0:
        return []

    # core_hi < ln(x_max) always (x_max pads the GLOBAL quote max by 1.4x while
    # the core pads this expiry's by +0.02), so the core is never clipped and
    # stays the exact _reconstruct_smile linspace.
    grid = _display_grid(k_lo, k_hi, core_lo, core_hi, n_core)
    # OTM-side inversion; the OTM price IS the time value (intrinsic 0) — the
    # reliability currency of the inversion guard, now measured honestly on
    # the left from the put march instead of the cancelled call intrinsic.
    w, time_value = otm_implied_w(solution, put_solution, i_exp, grid)
    right = grid > core_hi + 1e-12
    if ext_call_solution is not None and np.any(right):
        # The wing beyond the core off the buffered display lattice (same dx,
        # same nodes, same scheme: the seam at core_hi is round-off).
        price_r = np.asarray(
            ext_call_solution.price_at(i_exp, np.exp(grid[right])), dtype=float
        )
        w[right] = np.asarray(implied_total_variance_otm(grid[right], price_r), dtype=float)
        time_value[right] = price_r
    # Never invert inside the serving lattice's Dirichlet boundary layer.
    k_clean = clean_right_edge(x_right, right_sol.prices[i_exp])
    reliable = (
        np.isfinite(time_value)
        & (time_value >= _EXT_TV_FLOOR)
        & np.isfinite(w)
        & (w > 0.0)
        & ~(right & (grid > k_clean))
    )
    if int(reliable.sum()) < 2:
        return []
    # Flat-in-k extension of w beyond (and interpolation across) the reliable
    # set — np.interp's constant extrapolation IS the _InterpSlice doctrine.
    w_ext = np.interp(grid, grid[reliable], w[reliable])
    vol = np.sqrt(np.maximum(w_ext, 0.0) / t)
    return [
        SmilePoint(k=float(kv), vol=float(v))
        for kv, v in zip(grid, vol)
        if np.isfinite(v)
    ]

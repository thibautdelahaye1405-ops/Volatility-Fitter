"""Untruncated per-expiry LV smile extension (roadmap V3.3, item 3).

The parametric stacked-variance view is full-width (surface.py evaluates every
expiry on one union display grid and LQD extrapolates arb-free wings); the LV
view was not — each expiry's ``model`` curve is reconstructed only on its own
quoted range ±pad (affine_fit._reconstruct_smile), so short expiries draw as
stubs. This module builds ``AffineSmile.modelExt``: the SAME Dupire-price →
Black inversion on the SHARED display grid

    [min(K_DISPLAY_LO, k_obs_lo - pad),
     min(max(K_DISPLAY_HI, k_obs_hi + pad), ln(x_max) - eps)]

with the right edge clamped INSIDE the PDE lattice (``price_at`` np.interp-
clamps beyond it — inverting clamped prices manufactures garbage vols).
Guards, in order:

  * the display grid CONTAINS ``_reconstruct_smile``'s own linspace bit-for-bit
    (same endpoints, same count), so modelExt ≡ model on the quoted-range grid
    points — one inversion, two truncations;
  * inversion only where the normalized OTM time value clears ``_EXT_TV_FLOOR``
    (mirrors service._WING_TV_FLOOR — the book-ch.2 publication rule: remote
    wings are never read off prices this small);
  * below the floor the total variance w extends FLAT in k from the outermost
    reliable point (the _InterpSlice doctrine: np.interp's constant
    extrapolation) — honest "no information past here", never a fabricated
    wing slope, and vol = sqrt(w/t) stays bounded by the reliable curve.

Display/payload-only: ``model``, the PDE lattice and every calibrated number
are untouched (byte-identity of fits). Lives outside affine_fit.py purely for
the 400-line file policy (affine_fit is far past it).
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import SmilePoint
from volfit.core.black import implied_total_variance_otm

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
) -> list[SmilePoint]:
    """One expiry's reconstructed IV curve on the shared display grid.

    ``solution`` is the calibrated Dupire march (has ``price_at``); ``t`` is
    the expiry's variance-time maturity (the clock its vols are quoted in);
    ``k_lo_obs``/``k_hi_obs`` the observed quote range; ``x_grid`` the PDE
    strike lattice; ``k_pad``/``n_core`` are affine_fit's own ``_K_PAD`` /
    ``_N_SMILE`` (passed in, not imported — no circular import, and the core
    grid provably matches ``_reconstruct_smile``'s). Empty list when the
    expiry is degenerate or nothing is reliably invertible.
    """
    from volfit.api.service import K_DISPLAY_HI, K_DISPLAY_LO  # heavy module: lazy

    core_lo, core_hi = float(k_lo_obs) - k_pad, float(k_hi_obs) + k_pad
    k_right_cap = float(np.log(float(x_grid[-1]))) - _EDGE_EPS
    k_lo = min(K_DISPLAY_LO, core_lo)
    k_hi = min(max(K_DISPLAY_HI, core_hi), k_right_cap)
    if not (np.isfinite(k_lo) and np.isfinite(k_hi)) or k_hi <= k_lo or t <= 0.0:
        return []

    # core_hi < ln(x_max) always (x_max pads the GLOBAL quote max by 1.4x while
    # the core pads this expiry's by +0.02), so the core is never clipped and
    # stays the exact _reconstruct_smile linspace. x_max is floored by the
    # Options setting lvXMaxMin (default 2.5 -> k_right_cap ≈ +0.92, the
    # historical constant); raising it (2.72 -> +1.0) is what extends this
    # right edge when the quoted range does not reach K_DISPLAY_HI.
    grid = _display_grid(k_lo, k_hi, core_lo, core_hi, n_core)
    # OTM-side inversion; the OTM price IS the time value (intrinsic 0) — the
    # reliability currency of the inversion guard, now measured honestly on
    # the left from the put march instead of the cancelled call intrinsic.
    w, time_value = otm_implied_w(solution, put_solution, i_exp, grid)
    reliable = (
        np.isfinite(time_value)
        & (time_value >= _EXT_TV_FLOOR)
        & np.isfinite(w)
        & (w > 0.0)
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

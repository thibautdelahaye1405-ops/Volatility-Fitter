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
from volfit.core.black import implied_total_variance

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


def extended_model(
    solution,
    i_exp: int,
    t: float,
    k_lo_obs: float,
    k_hi_obs: float,
    x_grid: np.ndarray,
    k_pad: float,
    n_core: int,
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
    # stays the exact _reconstruct_smile linspace.
    grid = _display_grid(k_lo, k_hi, core_lo, core_hi, n_core)
    price = np.asarray(solution.price_at(i_exp, np.exp(grid)), dtype=float)
    # Normalized OTM time value: the call price for k >= 0, price - intrinsic
    # below the forward — the reliability currency of the inversion guard.
    time_value = price - np.maximum(1.0 - np.exp(grid), 0.0)
    w = np.asarray(implied_total_variance(grid, price), dtype=float)
    reliable = (
        np.isfinite(price)
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

"""Dupire local-variance extraction from an implied total-variance surface.

Gatheral's formula (The Volatility Surface, eq. 1.10) in log-moneyness k and
total implied variance w(k, T):

    sigma_loc^2(k, T) = w_T / g(k, w),
    g = 1 - (k/w) w_k + 1/4 (-1/4 - 1/w + k^2/w^2) w_k^2 + 1/2 w_kk.

The denominator g is the butterfly function: g <= 0 means the *implied*
surface itself carries strike arbitrage, so no positive local vol can
reproduce it.  ``dupire_local_variance`` returns nan there (np.where, never
an exception) and otherwise returns raw values -- a negative w_T (calendar
arbitrage) flows through as a negative variance for the caller to mask.

``extract_grid`` is the practical path "fitted implied surface -> LV grid":
central finite differences in (k, T), nan cells filled from the nearest valid
strike, local variance floored at ``var_floor`` before the square root, and
the nan/clip counts surfaced in the result -- extraction must never silently
manufacture a clean grid out of a bad surface.

Caution on FD steps: dk and dt must resolve the smoothness of ``w_surface``.
For piecewise-linear interpolants (e.g. a surface bilinear-interpolated off a
price mesh) choose dk/dt at least as large as the interpolation mesh spacing,
otherwise w_kk sees the interpolant's kinks instead of the surface curvature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from volfit.models.localvol.grid import LocalVolGrid

VAR_FLOOR = 1e-6  # local-variance floor applied before the square root


def dupire_local_variance(
    k: np.ndarray | float,
    w: np.ndarray | float,
    wk: np.ndarray | float,
    wkk: np.ndarray | float,
    wt: np.ndarray | float,
) -> np.ndarray:
    """Pointwise Gatheral local variance; nan where the butterfly g <= 0.

    Inputs broadcast; w must be positive (w <= 0 also yields nan).  Values
    are returned raw otherwise -- in particular wt < 0 (calendar arbitrage)
    produces a negative local variance for the caller to mask or floor.
    """
    k = np.asarray(k, dtype=float)
    w = np.asarray(w, dtype=float)
    wk = np.asarray(wk, dtype=float)
    wkk = np.asarray(wkk, dtype=float)
    wt = np.asarray(wt, dtype=float)

    w_safe = np.where(w > 0.0, w, 1.0)
    r = k / w_safe
    g = 1.0 - r * wk + 0.25 * (-0.25 - 1.0 / w_safe + r * r) * wk * wk + 0.5 * wkk
    valid = (w > 0.0) & (g > 0.0)
    return np.where(valid, wt / np.where(valid, g, 1.0), np.nan)


@dataclass(frozen=True)
class ExtractionResult:
    """Extracted grid plus honesty counters for masked/repaired cells."""

    grid: LocalVolGrid
    n_nan: int  # cells where g <= 0 (or w <= 0), filled from nearest valid k
    n_clipped: int  # cells (post-fill) floored at var_floor before sqrt


def _fill_nearest(values: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Replace non-finite entries by the value at the nearest (in x) finite one."""
    valid = np.isfinite(values)
    if valid.all():
        return values
    if not valid.any():
        raise ValueError("Dupire extraction failed at every strike of a maturity row")
    xv, vv = x[valid], values[valid]
    pos = np.searchsorted(xv, x)
    left = np.clip(pos - 1, 0, xv.size - 1)
    right = np.clip(pos, 0, xv.size - 1)
    use_right = np.abs(xv[right] - x) < np.abs(x - xv[left])
    filled = np.where(use_right, vv[right], vv[left])
    return np.where(valid, values, filled)


def extract_grid(
    w_surface: Callable[[np.ndarray, float], np.ndarray],
    k_grid: np.ndarray,
    t_grid: np.ndarray,
    dk: float = 1e-3,
    dt: float = 1e-3,
    var_floor: float = VAR_FLOOR,
) -> ExtractionResult:
    """Extract a LocalVolGrid from a total-variance surface by central FD.

    ``w_surface(k_array, t_scalar) -> w_array`` is any fitted implied surface
    (vectorized in k).  Derivatives are second-order central differences with
    steps ``dk``, ``dt`` -- see the module docstring for how to choose them
    when the surface is an interpolant.  Cells where the Dupire denominator
    is nonpositive come back nan and are replaced by the nearest valid value
    along k; everything below ``var_floor`` is floored.  Both repair counts
    are reported in the result so callers can gate on extraction quality.
    """
    k = np.asarray(k_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    sigma = np.empty((t.size, k.size))
    n_nan = 0
    n_clipped = 0

    for i, ti in enumerate(t):
        ti = float(ti)
        w0 = np.asarray(w_surface(k, ti), dtype=float)
        wp = np.asarray(w_surface(k + dk, ti), dtype=float)
        wm = np.asarray(w_surface(k - dk, ti), dtype=float)
        wk = (wp - wm) / (2.0 * dk)
        wkk = (wp - 2.0 * w0 + wm) / (dk * dk)
        wt = (
            np.asarray(w_surface(k, ti + dt), dtype=float)
            - np.asarray(w_surface(k, ti - dt), dtype=float)
        ) / (2.0 * dt)

        var = dupire_local_variance(k, w0, wk, wkk, wt)
        bad = ~np.isfinite(var)
        n_nan += int(bad.sum())
        if bad.any():
            var = _fill_nearest(var, k)
        n_clipped += int(np.sum(var < var_floor))
        sigma[i] = np.sqrt(np.maximum(var, var_floor))

    return ExtractionResult(
        grid=LocalVolGrid(k=k, t=t, sigma=sigma, interp="bilinear"),
        n_nan=n_nan,
        n_clipped=n_clipped,
    )

"""Tapered no-arbitrage enforcement in the extrapolated strike region
(Notes 09/10, Phase 2 of the softer-enforcement design).

Phase 1 (volfit.models.diagnostics.extrapolated_arb) MEASURES arbitrage
beyond the traded strikes; this module lets the SVI / Multi-Core Sigmoid
(MCS) overlay calibrations LEAN on that region — softly, and only where
options are demonstrably not worthless. Three ingredients, all gated behind
``OptionsSettings.extrapEnforce`` (default OFF, byte-identical when off):

  * **the time-value envelope** — points beyond each traded edge kept while
    a flat-``w`` extension of the EDGE QUOTE still prices the OTM option at
    or above ``EXTRAP_TV_FLOOR`` (1 bp of forward). The envelope is built
    from the QUOTES, not the moving iterate, so it is fixed during a solve;
  * **the taper** — per-point weight ``value(k) / value(edge)`` in (0, 1]:
    full strength at the traded edge, decaying to nothing where options
    become worthless. Enforcement can never outvote the data region — the
    lesson of the phantom-calendar case file (Note 10) kept by construction;
  * **the residual blocks** — a one-curve butterfly hinge (Durrleman g of
    the iterate's own curve), a two-curve tapered calendar hinge against the
    previous DISPLAYED slice, and the scalar asymptotic wing-slope-order
    hinge (far slope >= near slope) that guarantees far-field calendar order
    without ever differencing two extrapolations pointwise.

The target carries GEOMETRY only (grids, tapers, floors, previous slopes);
each calibrator applies its own weight conventions, exactly as it does for
its other penalty blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from volfit.models.diagnostics import EXTRAP_TV_FLOOR, _otm_value, durrleman_g

#: Enforcement grid: points per wing (coarser than Phase 1's measurement grid —
#: these rows sit inside every optimizer iteration).
_POINTS = 25
#: Reach past the traded edge, in units of the edge quote's total-variance
#: sd (sqrt w): the OTM value decays on exactly this scale, so the grid
#: resolves the taper for any tenor/vol level. Bounded to sane absolutes.
_REACH_SD = 2.0
_REACH_MIN = 0.05
_REACH_MAX = 4.0
#: Every enforcement row is expressed in VOL units and weighted as a FRACTION
#: of one average data quote (the var-swap block's budget pattern): the whole
#: extrap block can lean on the fit like a handful of extra quotes, never
#: dominate it — "softer" enforcement by construction, on top of the taper.
_ROW_FRAC = 0.25  # each row = quarter of an average quote's weight
#: Vol-equivalent scales for the dimensionless hinges: one unit of butterfly
#: violation (-g = 1) / slope-order violation reads as this many vol points.
_G_SCALE = 0.05
_SLOPE_SCALE = 0.05


class WFn:
    """Adapter giving a bare ``w(k)`` callable the SmileModel ``implied_w``."""

    def __init__(self, fn: Callable[[np.ndarray], np.ndarray]):
        self.implied_w = fn


@dataclass(frozen=True)
class ExtrapTarget:
    """Fixed enforcement geometry for one slice fit (picklable — rides the
    overlay dict through the fit pool)."""

    k_left: np.ndarray  # left-wing envelope grid, edge -> outward (may be empty)
    taper_left: np.ndarray
    k_right: np.ndarray
    taper_right: np.ndarray
    cal_floor_left: np.ndarray | None  # previous DISPLAYED w(k) on the grids
    cal_floor_right: np.ndarray | None
    prev_lee: tuple[float, float] | None  # previous displayed asymptotic slopes


def _wing(edge: float, sign: float, w_edge: float, tv_floor: float) -> tuple[np.ndarray, np.ndarray]:
    """(grid, taper) for one wing: flat-``w_edge`` extension of the edge quote,
    cut where the OTM value drops below ``tv_floor``, taper normalized to the
    edge value so enforcement is full-strength at the boundary and fades out."""
    reach = float(np.clip(_REACH_SD * np.sqrt(max(w_edge, 0.0)), _REACH_MIN, _REACH_MAX))
    k = edge + sign * np.linspace(0.0, reach, _POINTS + 1)[1:]
    flat = WFn(lambda kk: np.full_like(np.asarray(kk, float), w_edge))
    value = _otm_value(flat, k)
    edge_value = float(_otm_value(flat, np.array([edge]))[0])
    alive = np.isfinite(value) & (value >= tv_floor)
    if not alive[0] or edge_value <= 0.0:
        return k[:0], k[:0]
    cut = int(np.argmin(alive)) if not alive.all() else alive.size
    return k[:cut], np.clip(value[:cut] / edge_value, 0.0, 1.0)


def build_extrap_target(
    k: np.ndarray,
    w_quotes: np.ndarray,
    prev_slice=None,
    prev_lee: tuple[float, float] | None = None,
    tv_floor: float = EXTRAP_TV_FLOOR,
) -> ExtrapTarget | None:
    """The enforcement geometry for one node, from its quotes and (optionally)
    the previous expiry's displayed slice. None when there is nothing to
    enforce (no quotes, or worthless past both edges and no slope info)."""
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    if k.size == 0:
        return None
    lo, hi = int(np.argmin(k)), int(np.argmax(k))
    k_l, tap_l = _wing(float(k[lo]), -1.0, float(w_quotes[lo]), tv_floor)
    k_r, tap_r = _wing(float(k[hi]), +1.0, float(w_quotes[hi]), tv_floor)
    if k_l.size == 0 and k_r.size == 0 and (prev_slice is None or prev_lee is None):
        return None

    def _floor(grid: np.ndarray) -> np.ndarray | None:
        if prev_slice is None or grid.size == 0:
            return None
        f = np.asarray(prev_slice.implied_w(grid), dtype=float)
        return np.where(np.isfinite(f), f, 0.0)

    return ExtrapTarget(
        k_left=k_l, taper_left=tap_l, k_right=k_r, taper_right=tap_r,
        cal_floor_left=_floor(k_l), cal_floor_right=_floor(k_r),
        prev_lee=prev_lee,
    )


def extrap_residuals(
    w_fn: Callable[[np.ndarray], np.ndarray],
    target: ExtrapTarget,
    t: float,
    mean_weight: float = 1.0,
    lee_fn: Callable[[], tuple[float, float]] | None = None,
) -> np.ndarray:
    """The Phase-2 residual rows for one iterate — all zero on a slice that is
    butterfly-clean over the envelope, calendar-ordered above the previous
    displayed slice, and wing-slope-ordered (inactive on admissible fits,
    the house penalty invariant).

    ``w_fn`` maps k -> total variance for the CURRENT iterate; ``t`` converts
    the calendar gap to vol units; ``mean_weight`` is the fit's average
    per-quote LSQ weight, so the block's strength tracks the data term's
    (each row = ``_ROW_FRAC`` of an average quote). ``lee_fn`` returns the
    iterate's asymptotic (left, right) slopes when the slope-order block is
    wanted (None skips it even if the target carries ``prev_lee``)."""
    rows: list[np.ndarray] = []
    shim = WFn(w_fn)
    sqrt_row = np.sqrt(max(_ROW_FRAC * mean_weight, 0.0))
    for grid, taper, floor in (
        (target.k_left, target.taper_left, target.cal_floor_left),
        (target.k_right, target.taper_right, target.cal_floor_right),
    ):
        if grid.size >= 3:
            g = durrleman_g(shim, grid)
            g = np.where(np.isfinite(g), g, 0.0)  # overflowing wing: no signal
            rows.append(sqrt_row * _G_SCALE * taper * np.maximum(-g, 0.0))
        if floor is not None and grid.size:
            w_model = np.asarray(w_fn(grid), dtype=float)
            sig_model = np.sqrt(np.maximum(w_model, 1e-12) / t)
            sig_floor = np.sqrt(np.maximum(floor, 0.0) / t)
            gap = np.where(np.isfinite(sig_model), sig_floor - sig_model, 0.0)
            rows.append(sqrt_row * taper * np.maximum(gap, 0.0))
    if target.prev_lee is not None and lee_fn is not None:
        left, right = lee_fn()
        rows.append(sqrt_row * _SLOPE_SCALE * np.array([
            max(target.prev_lee[0] - left, 0.0),
            max(target.prev_lee[1] - right, 0.0),
        ]))
    return np.concatenate(rows) if rows else np.empty(0)

"""Sequential calendar-arbitrage-free surface construction (note 10.2).

Expiries are fitted nearest to farthest. Each fit after the first carries the
soft integrated-quantile constraint G_i(alpha) >= G_{i-1}(alpha) against the
previously fitted slice, and is warm-started from the previous parameters.
The per-expiry worst calendar residual is reported so that genuinely
inconsistent input quotes are *visible* rather than silently absorbed
(the slack interpretation of note eq. slack_calendar).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from volfit.calib.calendar import calendar_floor_targets, calendar_violation
from volfit.models.lqd.calibrate import CalibrationResult, calibrate_slice


@dataclass(frozen=True)
class ExpiryQuotes:
    """Calibration input for one expiry: total-variance quotes on log-moneyness."""

    t: float
    k: np.ndarray
    w: np.ndarray
    weights: np.ndarray | None = None


@dataclass(frozen=True)
class SurfaceFit:
    """Per-expiry fits (sorted by expiry) plus calendar diagnostics.

    ``calendar_residuals[i]`` is max_alpha (G_{i-1} - G_i) between consecutive
    fitted slices (first entry is 0); positive values flag remaining calendar
    violations — with enforcement on they should sit at numerical-slack level.
    """

    expiries: list[float]
    results: list[CalibrationResult]
    calendar_residuals: list[float] = field(default_factory=list)

    @property
    def max_calendar_violation(self) -> float:
        return max(self.calendar_residuals) if self.calendar_residuals else 0.0


def calibrate_surface(
    quotes: list[ExpiryQuotes],
    n_order: int = 6,
    enforce_calendar: bool = True,
    calendar_weight: float = 1e6,
    reg_lambda: float = 0.0,
    reg_power: float = 1.0,
) -> SurfaceFit:
    """Fit all expiries sequentially, nearest to farthest.

    ``enforce_calendar`` toggles the convex-order constraint (per the
    product's "calendar arbitrage prevention" switch); when off, slices are
    fitted independently and the diagnostics still report any violations.
    """
    ordered = sorted(quotes, key=lambda q: q.t)
    results: list[CalibrationResult] = []
    residuals: list[float] = [0.0]

    prev = None
    for slice_quotes in ordered:
        cal_z = cal_floor = None
        if enforce_calendar and prev is not None:
            cal_z, cal_floor = calendar_floor_targets(prev.slice)
        result = calibrate_slice(
            slice_quotes.k,
            slice_quotes.w,
            t=slice_quotes.t,
            n_order=n_order,
            weights=slice_quotes.weights,
            reg_lambda=reg_lambda,
            reg_power=reg_power,
            init=prev.params if prev is not None else None,
            calendar_z=cal_z,
            calendar_floor=cal_floor,
            calendar_weight=calendar_weight,
        )
        if prev is not None:
            residuals.append(calendar_violation(prev.slice, result.slice))
        results.append(result)
        prev = result

    return SurfaceFit(
        expiries=[q.t for q in ordered],
        results=results,
        calendar_residuals=residuals,
    )

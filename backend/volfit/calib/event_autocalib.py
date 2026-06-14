"""Auto-calibration of an event calendar from the ATM term structure.

Given the per-expiry ATM total variances w0_i (calendar, price-derived and so
event-INVARIANT) and maturities t_i, this places one candidate event before each
expiry up to a chosen horizon T and solves for its extra day-weights N_i >= 0 so
that the *weighted* forward variance between consecutive expiries,

    fv_i = (w0_i - w0_{i-1}) / (tau_i - tau_{i-1}),
    tau_i - tau_{i-1} = (t_i - t_{i-1}) + N_i / 365,

is as flat and as monotonically increasing as possible while the events stay as
small and sparse as possible. Events can only LENGTHEN an interval's weighted
time, so they pull DOWN forward-variance spikes (e.g. an earnings-packed
interval) toward their neighbours — the diffusive forward variance is smoothed.
Real-time forward variance (Delta w / Delta t) is event-invariant, which is why
the objective is the weighted (dilated) forward variance, the one events move.

The objective over the intervals up to the one just following T (so the first
post-T interval, with no event, anchors the tail) is

    J(N) = sum_i (fv_i - fv_{i-1})^2                     # (i) flat
         + mono_w * sum_i max(fv_{i-1} - fv_i, 0)^2      # (ii) monotone-increasing
         + sparse_w * sum_i N_i/365 + ridge_w * sum_i (N_i/365)^2   # (iii) small & sparse

minimized by bounded L-BFGS-B; tiny events are thresholded to zero so the result
is sparse (up to n events for n expiries <= T, often fewer).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

DAYS_PER_YEAR = 365.0


def autocalibrate_events(
    t: np.ndarray,
    w0: np.ndarray,
    n_events: int,
    *,
    mono_weight: float = 1.0,
    sparse_weight: float = 1e-3,
    ridge_weight: float = 1e-4,
    min_event_days: float = 0.5,
    max_event_days: float = 5.0 * DAYS_PER_YEAR,
    days_per_year: float = DAYS_PER_YEAR,
) -> list[tuple[float, float]]:
    """Solve for events (time_years, extra_days) flattening the forward variance.

    ``t`` (ascending expiry years) and ``w0`` (ATM total variance, same length)
    describe the term structure; ``n_events`` is the number of leading expiries
    at or before the horizon T (one candidate event per interval). Returns the
    non-negligible events placed at each interval's midpoint (before its expiry),
    nearest first — at most ``n_events`` of them.
    """
    t = np.asarray(t, dtype=float)
    w0 = np.asarray(w0, dtype=float)
    total = t.size
    n = max(0, min(int(n_events), total))
    if n == 0:
        return []
    # Objective spans intervals 0..m-1; the interval just past T (index n, no
    # event) anchors the tail when it exists.
    m = min(n + 1, total)
    prev_t = np.concatenate([[0.0], t[: m - 1]])
    prev_w = np.concatenate([[0.0], w0[: m - 1]])
    dt = t[:m] - prev_t
    dw = w0[:m] - prev_w

    def forward_var(x: np.ndarray) -> np.ndarray:
        extra = np.zeros(m)
        extra[:n] = x  # events only on the first n intervals
        return dw / (dt + extra / days_per_year)

    def objective(x: np.ndarray) -> float:
        fv = forward_var(x)
        d = np.diff(fv)
        flat = float(np.sum(d * d))
        mono = float(np.sum(np.minimum(d, 0.0) ** 2))  # decreases are penalized
        yrs = x / days_per_year
        return flat + mono_weight * mono + sparse_weight * float(np.sum(yrs)) + ridge_weight * float(
            np.sum(yrs * yrs)
        )

    result = minimize(
        objective,
        np.zeros(n),
        method="L-BFGS-B",
        bounds=[(0.0, max_event_days)] * n,
    )
    x = np.maximum(result.x, 0.0)
    x[x < min_event_days] = 0.0  # sparsity threshold

    events: list[tuple[float, float]] = []
    for i in range(n):
        if x[i] > 0.0:
            lo = 0.0 if i == 0 else float(t[i - 1])
            events.append((0.5 * (lo + float(t[i])), float(x[i])))  # midpoint, before t_i
    return events

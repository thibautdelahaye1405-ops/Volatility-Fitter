"""Event-weighted variance time (the variance clock).

Variance does not accrue uniformly in calendar time: scheduled events
(earnings, macro prints) pack extra variance onto single days. We model this
with a per-day *weight* (default 1) that events augment, and measure variance
time in those weighted days:

    tau_days(T) = (calendar days to T) + sum_{t_e <= T} N_e,

where ``N_e`` is the event's EXTRA equivalent days (an earnings day with
N_e = 4 counts as 5 normal days of variance). The smile is then calibrated and
quoted in weighted *years* tau = tau_days / 365: total variance w(k) is fixed by
the observed price (clock-independent), so the working implied vol is the
diffusive vol on the weighted clock,

    sigma_work(k) = sqrt( w(k) / tau ),

which DROPS when an event is added before the expiry (tau rises at fixed w).

Normalization (an Options toggle): by default no normalization occurs, so the
cumulative weight exceeds the calendar-day count (tau > T). With normalization
ON, ALL days (event days included) are rescaled by a single factor so the
one-year weight budget is unchanged (= 365), hence the 1Y variance time — and
the 1Y implied vol — are identical to a no-event year; events only
*redistribute* variance within the year.

With no events (or an empty calendar) tau == t exactly, so every downstream
fit is byte-identical to the calendar-time pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

DAYS_PER_YEAR = 365.0


def weighted_variance_years(
    t_cal: float,
    events: Sequence[tuple[float, float]],
    normalize: bool = False,
    days_per_year: float = DAYS_PER_YEAR,
) -> float:
    """Weighted variance years tau to a calendar maturity ``t_cal``.

    ``events`` is a sequence of ``(time_years, extra_days)`` pairs; only events
    at or before ``t_cal`` add weight. ``normalize`` rescales all days uniformly
    so the one-year weight budget stays ``days_per_year`` (1Y vols unchanged).
    Returns ``t_cal`` exactly when there are no events at or before it and no
    normalization is in force.
    """
    if t_cal <= 0.0:
        return float(t_cal)
    extra_before = sum(n for te, n in events if te <= t_cal and n > 0.0)
    tau_days = t_cal * days_per_year + extra_before
    if normalize:
        # Uniform factor pinning the 1Y weighted budget to a no-event year.
        extra_1y = sum(n for te, n in events if te <= 1.0 and n > 0.0)
        budget_1y = days_per_year + extra_1y
        if budget_1y > 0.0:
            tau_days *= days_per_year / budget_1y
    return tau_days / days_per_year


def interp_total_variance(
    tau_q: np.ndarray, tau_nodes: np.ndarray, w_nodes: np.ndarray
) -> np.ndarray:
    """Interpolate total variance w linearly in the weighted clock tau.

    Flat forward variance per weighted-time unit between the quoted nodes;
    extrapolation keeps the variance *rate* (from the origin at the short end,
    from the last segment at the long end), so the dense vol curve sqrt(w/tau)
    stays bounded near 0 and sensible past the last expiry. ``tau_nodes`` must be
    ascending; arrays are aligned (node tau and node total variance)."""
    tau_nodes = np.asarray(tau_nodes, dtype=float)
    w_nodes = np.asarray(w_nodes, dtype=float)
    out = np.interp(tau_q, tau_nodes, w_nodes)
    low = tau_q < tau_nodes[0]
    if np.any(low):
        out[low] = w_nodes[0] * tau_q[low] / tau_nodes[0]
    high = tau_q > tau_nodes[-1]
    if np.any(high):
        rate = (
            (w_nodes[-1] - w_nodes[-2]) / (tau_nodes[-1] - tau_nodes[-2])
            if w_nodes.size > 1
            else w_nodes[-1] / tau_nodes[-1]
        )
        out[high] = w_nodes[-1] + rate * (tau_q[high] - tau_nodes[-1])
    return out

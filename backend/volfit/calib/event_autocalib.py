"""Auto-calibration of an event calendar from the ATM term structure.

Given the per-expiry ATM total variances w0_i (price-derived, so clock-
INVARIANT) and their maturities, this reads scheduled events off the forward-
variance ladder: an interval whose forward variance per day-weight,

    f_i = (w0_i - w0_{i-1}) / d_i,        d_i = day-weights of interval i,

runs hotter than BOTH of its neighbours carries more variance than its share
of days — the signature of an event inside it. An event can only LENGTHEN its
interval's weighted time, so it can only pull that peak DOWN; the solver
attributes exactly the excess over the higher neighbour to one event of

    N_i = d_i * (f_i / r_i - 1)   extra days,     r_i = max(g_{i-1}, g_{i+1}),

where g is the ladder after events (g_i = f_i * d_i / (d_i + N_i)). This is a
DETECTOR, not a smoother: a monotone ramp (contango), a smooth backwardation
and an isolated dip are all shapes an event cannot produce, so they yield no
events at all, and the sizes of the events it does find are exact rather than
shrunk by a penalty. Two adjacent events of equal size form a plateau with no
peak and are invisible to it — the one limitation of a local rule.

The reference r_i is the higher of the two adjacent intervals (a conservative
bracket: never fabricate an event out of an ordinary slope). The FIRST interval
has no left neighbour; its reference is the second interval's level continued
by the back ladder's own log-slope when that ladder is backwardated (a mean-
reverting vol-spike front decays smoothly and is not an event), and just the
second interval's level otherwise. The LAST interval of the whole ladder has no
right neighbour and is never a candidate: it is the tail reference, whatever
horizon the caller chooses; intervals past the horizon are references too.

Because clipping one peak lowers the reference of its neighbours, the rule is
applied as a monotone fixed point: start from the calendar ladder and clip
until no candidate exceeds its reference. The feasible set is closed under the
componentwise maximum, so the iteration converges to its greatest element —
the smallest events that leave no peak — in at most one pass per interval.

Materiality: an event counts only when it adds at least ``min_event_days`` and
at least ``min_rel_excess`` of its interval's variance; fit noise between
adjacent expiries sits below both floors, a real earnings day far above.
"""

from __future__ import annotations

import numpy as np

DAYS_PER_YEAR = 365.0
#: Materiality floors (defaults): an event must add at least this many extra
#: days AND at least this fraction of its interval's variance.
MIN_EVENT_DAYS = 0.5
MIN_REL_EXCESS = 0.03


def _front_reference(g: np.ndarray, mids: np.ndarray, valid: np.ndarray) -> float:
    """Reference level of the first interval: its right neighbour's level,
    continued by the back ladder's log-slope when that slope is downward.

    ``mids`` are the intervals' midpoints in day-weights. With fewer than three
    valid intervals (or a contango back), the reference is the neighbour alone.
    A non-positive neighbour is no reference (returns 0.0: never clip).
    """
    if g.size < 2 or not valid[1] or g[1] <= 0.0:
        return 0.0
    ref = float(g[1])
    if g.size >= 3 and valid[2] and g[2] > 0.0 and g[1] > g[2]:
        # Log-linear continuation of (g2 -> g1) over one more step, measured
        # in interval midpoints so uneven ladders extrapolate the right span.
        span_back = mids[2] - mids[1]
        if span_back > 0.0:
            ratio = g[1] / g[2]
            ref = float(g[1] * ratio ** ((mids[1] - mids[0]) / span_back))
    return ref


def autocalibrate_events(
    t: np.ndarray,
    w0: np.ndarray,
    n_events: int,
    *,
    base_days: np.ndarray | None = None,
    min_event_days: float = MIN_EVENT_DAYS,
    min_rel_excess: float = MIN_REL_EXCESS,
    days_per_year: float = DAYS_PER_YEAR,
) -> list[tuple[float, float]]:
    """Solve for events (time_years, extra_days) that remove every peak of the
    forward-variance ladder up to the horizon.

    ``t`` (ascending calendar years) and ``w0`` (ATM total variance, same
    length) describe the term structure; ``n_events`` is the number of leading
    expiries at or before the horizon (candidate intervals). ``base_days`` are
    the day-weights accrued to each expiry (the intraday session clock's base
    when it is on); by default an expiry's base is its calendar days, so a
    weekend counts as three days. Events are returned at their interval's
    calendar midpoint (before its expiry), nearest first; the last interval of
    the ladder never carries one.
    """
    t = np.asarray(t, dtype=float)
    w0 = np.asarray(w0, dtype=float)
    total = t.size
    n = max(0, min(int(n_events), total))
    if total < 2 or n == 0:
        return []
    base = t * days_per_year if base_days is None else np.asarray(base_days, dtype=float)
    d = np.diff(np.concatenate([[0.0], base]))  # day-weights per interval
    dw = np.diff(np.concatenate([[0.0], w0]))  # total variance per interval
    valid = (d > 0.0) & np.isfinite(dw)
    f = np.where(valid, dw / np.where(valid, d, 1.0), 0.0)  # per day-weight
    mids = np.concatenate([[0.0], base])[:-1] + 0.5 * d  # interval midpoints
    candidates = [i for i in range(min(n, total - 1)) if valid[i] and f[i] > 0.0]

    def reference(g: np.ndarray, i: int) -> float:
        if i == 0:
            return _front_reference(g, mids, valid)
        left = g[i - 1] if valid[i - 1] else -np.inf
        right = g[i + 1] if valid[i + 1] else -np.inf
        return float(max(left, right))

    # Monotone fixed point: clip every peak to its reference until none is left.
    g = f.copy()
    for _ in range(total + 1):
        changed = False
        for i in candidates:
            ref = reference(g, i)
            if ref <= 0.0 or g[i] <= ref:
                continue
            excess = f[i] / ref - 1.0  # relative excess of the calendar ladder
            if excess < min_rel_excess or excess * d[i] < min_event_days:
                continue  # immaterial: fit noise, not an event
            g[i] = ref
            changed = True
        if not changed:
            break

    events: list[tuple[float, float]] = []
    for i in candidates:
        if g[i] < f[i]:
            extra = float(d[i] * (f[i] / g[i] - 1.0))
            lo = 0.0 if i == 0 else float(t[i - 1])
            events.append((0.5 * (lo + float(t[i])), extra))  # midpoint, before t_i
    return events

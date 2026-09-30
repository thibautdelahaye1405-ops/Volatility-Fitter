"""The chapter's clock and its event detector, self-contained.

Implements exactly the objects the chapter's equations define -- the
day-weighted variance clock tau(t), interval forward variances F_i =
dw_i/dtau_i, and the peak rule that reads event sizes off a ladder
(section 8.6): an interval carries an event when its forward variance
exceeds the higher of its neighbours by a material margin, and the size
is exactly what brings it down to that neighbour.  Constants are the
reference values stated in appendix 8.A.
"""

from __future__ import annotations

import numpy as np

DPY = 365.0            # calendar days per year (the clock's day convention)

# Reference detector constants (appendix 8.A).
MIN_DAYS = 0.5         # an event must be worth at least half a day ...
MIN_REL_EXCESS = 0.03  # ... and at least 3% of its interval's variance
MAX_SWEEPS = 64        # safety cap on the clip sweeps (n + 1 suffice)


def tau_years(t, events, normalize: bool = False):
    """The day-weighted variance clock tau(t), in years (eq. clock).

    ``events`` is a list of (t_e, N_e) pairs: date as a calendar year
    fraction, size in extra equivalent days.  Vectorized over ``t``.
    """
    t = np.asarray(t, dtype=float)
    tau_days = t * DPY
    for t_e, n_e in events:
        if n_e > 0.0:
            tau_days = tau_days + np.where(t >= t_e - 1e-12, n_e, 0.0)
    if normalize:
        e1 = sum(n for te, n in events if te <= 1.0 and n > 0.0)
        tau_days = tau_days * DPY / (DPY + e1)
    return tau_days / DPY


def fwd_var(t, w, N):
    """Interval forward variances F_i = dw_i / dtau_i and the tau ladder.

    ``t``/``w`` are the quoted expiry ladder (year fractions, ATM total
    variances); ``N[i]`` is the extra-day total assigned to the interval
    ENDING at expiry i.  Intervals run (0, t_1], (t_1, t_2], ...
    """
    t = np.asarray(t, dtype=float)
    w = np.asarray(w, dtype=float)
    N = np.asarray(N, dtype=float)
    tau = (t * DPY + np.cumsum(N)) / DPY
    tt = np.concatenate([[0.0], tau])
    ww = np.concatenate([[0.0], w])
    return np.diff(ww) / np.diff(tt), tau


def _reference(g, i, mid, valid):
    """The reference level of interval i on the current ladder g.

    The higher valid neighbour; for the first interval, its right
    neighbour -- continued one step forward at the back's log-linear
    decay rate (in interval midpoints) when the ladder falls further out.
    """
    n = len(g)
    if i >= 1:
        cands = []
        if valid[i - 1]:
            cands.append(g[i - 1])
        if i + 1 < n and valid[i + 1]:
            cands.append(g[i + 1])
        return max(cands) if cands else 0.0
    # First interval: no left neighbour.
    if n < 2 or not valid[1] or g[1] <= 0.0:
        return 0.0
    if n >= 3 and valid[2] and g[2] > 0.0 and g[1] > g[2]:
        rate = (mid[1] - mid[0]) / (mid[2] - mid[1])
        return g[1] * (g[1] / g[2]) ** rate
    return g[1]


def detect(t, w, horizon: float | None = None):
    """Read event sizes off a ladder by the peak rule (section 8.6).

    Candidates are the intervals ending at or before ``horizon`` (all but
    the last interval when None); the ladder's last interval is never a
    candidate.  Sweep the candidates in ascending order, clipping each
    interval whose forward variance exceeds its reference by at least
    MIN_REL_EXCESS and by at least MIN_DAYS worth of days, and repeat
    until a sweep changes nothing.  Returns the full-length N vector of
    extra days per interval (zero where no event).
    """
    t = np.asarray(t, dtype=float)
    w = np.asarray(w, dtype=float)
    n = len(t)
    f0, _ = fwd_var(t, w, np.zeros(n))
    tt = np.concatenate([[0.0], t])
    d = np.diff(tt) * DPY                    # interval widths in days
    mid = 0.5 * (tt[:-1] + tt[1:]) * DPY     # interval midpoints in days
    valid = (d > 0.0) & np.isfinite(f0)
    h = n - 1 if horizon is None else int(np.sum(t <= horizon + 1e-12))
    h = min(h, n - 1)
    cands = [i for i in range(h) if valid[i] and f0[i] > 0.0]

    g = f0.copy()
    for _ in range(MAX_SWEEPS):
        changed = False
        for i in cands:
            ref = _reference(g, i, mid, valid)
            if ref <= 0.0 or g[i] <= ref:
                continue
            excess = f0[i] / ref - 1.0   # excess of the calendar ladder
            if excess < MIN_REL_EXCESS or excess * d[i] < MIN_DAYS:
                continue
            g[i] = ref
            changed = True
        if not changed:
            break

    N = np.zeros(n)
    for i in cands:
        if g[i] < f0[i]:
            N[i] = d[i] * (f0[i] / g[i] - 1.0)
    return N


def floor_days(width_days: float) -> float:
    """The smallest event the rule can report on an interval of that width."""
    return max(MIN_DAYS, MIN_REL_EXCESS * width_days)


def spread_bp(f) -> float:
    """Max-minus-min of a forward-variance ladder, in variance bp."""
    f = np.asarray(f, dtype=float)
    return float((f.max() - f.min()) * 1e4)

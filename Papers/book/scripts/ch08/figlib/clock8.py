"""The chapter's clock and clock-calibration solver, self-contained.

Implements exactly the objects the chapter's equations define -- the
day-weighted variance clock tau(t), interval forward variances F_i =
dw_i/dtau_i, and the calibration objective J(N) with its flatness,
monotonicity, sparsity and ridge terms -- so every figure exercises the
displayed mathematics and nothing else.  Constants are the reference
values stated in appendix 8.A.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

DPY = 365.0            # calendar days per year (the clock's day convention)

# Reference solver constants (appendix 8.A).
LAM_MONO = 1.0         # extra charge on DECREASES of forward variance
LAM_SPARSE = 1e-3      # l1 charge per solved event-year (keeps events few)
LAM_RIDGE = 1e-4       # small l2 term (keeps the solve well conditioned)
MIN_DAYS = 0.5         # solved events smaller than this are dropped
MAX_DAYS = 1825.0      # box bound per event


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


def objective(N_active, t, w, active):
    """The calibration objective J(N) (eq. autocal)."""
    N = np.zeros(len(t))
    N[active] = N_active
    f, _ = fwd_var(t, w, N)
    d = np.diff(f)
    yrs = N / DPY
    return (
        np.sum(d**2)
        + LAM_MONO * np.sum(np.minimum(d, 0.0) ** 2)
        + LAM_SPARSE * np.sum(yrs)
        + LAM_RIDGE * np.sum(yrs**2)
    )


def solve(t, w, horizon: float | None = None):
    """Minimize J over non-negative extra days, one candidate per expiry.

    ``horizon`` limits candidates to expiries at or before it (the first
    interval past the horizon then anchors the tail); solved events below
    MIN_DAYS are dropped, as stated.  Returns the full-length N vector.
    """
    t = np.asarray(t, dtype=float)
    active = (
        np.arange(len(t))
        if horizon is None
        else np.where(t <= horizon + 1e-12)[0]
    )
    res = minimize(
        objective,
        np.zeros(len(active)),
        args=(t, np.asarray(w, dtype=float), active),
        method="L-BFGS-B",
        bounds=[(0.0, MAX_DAYS)] * len(active),
        options={"maxiter": 500, "ftol": 1e-14, "gtol": 1e-12},
    )
    N = np.zeros(len(t))
    N[active] = np.where(res.x >= MIN_DAYS, res.x, 0.0)
    return N


def spread_bp(f) -> float:
    """Max-minus-min of a forward-variance ladder, in variance bp."""
    f = np.asarray(f, dtype=float)
    return float((f.max() - f.min()) * 1e4)

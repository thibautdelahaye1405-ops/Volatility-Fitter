"""A small, self-contained forward-Dupire marcher on a dense uniform grid.

Used where the chapter needs a pricer INDEPENDENT of the P1 model: pricing
the smooth synthetic truth surface (so the round trip is not an inverse
crime), and the implicit-vs-Crank-Nicolson monotonicity comparison.  Fully
implicit Euler and (undamped or Rannacher-damped) Crank-Nicolson steps on
the same operator; Dirichlet boundaries c(., 0) = 1, c(., y_max) = 0.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import solve_banded


def _operator(y: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interior three-point stencil of (1/2) v y^2 d_yy on a (possibly
    non-uniform) grid: returns (sub, diag, sup) for the interior nodes."""
    hm = y[1:-1] - y[:-2]
    hp = y[2:] - y[1:-1]
    yi2 = y[1:-1] ** 2
    a_m = v[1:-1] * yi2 / ((hm + hp) * hm)
    a_p = v[1:-1] * yi2 / ((hm + hp) * hp)
    return a_m, -(a_m + a_p), a_p


def march(
    v_fn,
    y: np.ndarray,
    t_grid: np.ndarray,
    scheme: str = "implicit",
    rannacher_steps: int = 0,
    snapshots: list[float] | None = None,
) -> dict[float, np.ndarray]:
    """March c(tau, y) from the payoff (1 - y)^+ over ``t_grid``.

    ``v_fn(tau, y)`` is the local-variance field, evaluated at the NEW time
    level of each step.  ``scheme`` is "implicit" (fully implicit Euler) or
    "cn" (Crank-Nicolson after ``rannacher_steps`` implicit start-up steps;
    0 = undamped CN from the payoff).  Returns {tau: c(tau, .)} at the
    requested snapshot times (default: the final time only).
    """
    y = np.asarray(y, dtype=float)
    t_grid = np.asarray(t_grid, dtype=float)
    want = sorted(snapshots) if snapshots is not None else [float(t_grid[-1])]
    out: dict[float, np.ndarray] = {}
    u = np.maximum(1.0 - y, 0.0)
    for n in range(1, t_grid.size):
        t_new = float(t_grid[n])
        dt = t_new - float(t_grid[n - 1])
        v_new = np.asarray(v_fn(t_new, y), dtype=float)
        sub, dia, sup = _operator(y, v_new)
        use_cn = scheme == "cn" and (n - 1) >= rannacher_steps
        w = 0.5 if use_cn else 1.0
        # rhs: interior explicit part + boundary contributions of the implicit part
        rhs = u[1:-1].copy()
        if use_cn:
            v_old = np.asarray(v_fn(float(t_grid[n - 1]), y), dtype=float)
            sub0, dia0, sup0 = _operator(y, v_old)
            rhs += 0.5 * dt * (sub0 * u[:-2] + dia0 * u[1:-1] + sup0 * u[2:])
        # banded implicit factor I - w dt L
        n_i = y.size - 2
        ab = np.zeros((3, n_i))
        ab[0, 1:] = -w * dt * sup[:-1]
        ab[1, :] = 1.0 - w * dt * dia
        ab[2, :-1] = -w * dt * sub[1:]
        rhs[0] += w * dt * sub[0] * 1.0    # left boundary c = 1
        # right boundary c = 0 contributes nothing
        u_int = solve_banded((1, 1), ab, rhs)
        u = np.concatenate([[1.0], u_int, [0.0]])
        for tau in want:
            if abs(t_new - tau) < 1e-12 and tau not in out:
                out[tau] = u.copy()
    return out


def uniform_grid(y_max: float, dy: float) -> np.ndarray:
    """Uniform strike grid [0, y_max] containing y = 1 exactly."""
    n = int(round(y_max / dy))
    y = np.linspace(0.0, y_max, n + 1)
    j = int(np.argmin(np.abs(y - 1.0)))
    y[j] = 1.0
    return y

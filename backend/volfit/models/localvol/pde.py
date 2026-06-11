"""Dupire forward PDE pricer for the local-volatility grid.

For *normalized undiscounted forward* call prices C(k, T) (conventions of
volfit.core.black: k = log(K/F), zero rates) under local volatility, the
Dupire forward equation in log-strike reads

    dC/dT = 1/2 sigma_loc(k, T)^2 (d2C/dk2 - dC/dk),
    C(k, 0)      = (1 - e^k)^+,
    C(k_min, T)  = 1 - e^{k_min}   (deep ITM: parity, vanishing put),
    C(k_max, T)  = 0               (deep OTM).

One forward sweep prices every strike at every requested expiry at once --
this is the round-trip validator for the grid model: positive sigma_loc in,
arbitrage-free call surface out (up to scheme noise, which the diagnostics in
volfit.models.localvol.model measure explicitly).

Discretization: central differences on a uniform k mesh; Crank-Nicolson
(theta = 1/2) with Rannacher startup -- the first time step is replaced by
four fully implicit quarter-steps (theta = 1) to damp the spurious CN
oscillation seeded by the payoff kink at k = 0.  sigma_loc is frozen at each
step's midpoint time, and each tridiagonal system is solved with
scipy.linalg.solve_banded.  Everything is vectorized over k; the only Python
loop is over time steps, so a 501 x 200 solve runs in milliseconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np
from scipy.linalg import solve_banded

#: Default resolution: with the adaptive span below this prices a two-expiry
#: flat-vol benchmark to < 0.5 vol bp inside 3 sd in ~20 ms.
DEFAULT_N_K = 1201
DEFAULT_DT_MAX = 1.0 / 400.0
N_RANNACHER = 4  # implicit quarter-steps replacing the first CN step

#: Auto mesh span in terminal standard deviations: Dirichlet boundary error
#: at 7.5 sd is ~1e-13, far below scheme noise, while keeping mesh points
#: where the density actually lives (a fixed +-2.5 span is 25 sd for a 3M
#: expiry at 20% vol and starves the ATM region of resolution).
SPAN_SD = 7.5
SPAN_MIN = 0.6  # never narrower than this, whatever sigma*sqrt(T) says


@dataclass(frozen=True)
class PDESolution:
    """Call prices C(k, T) on the solver mesh at the requested expiries."""

    k_mesh: np.ndarray  # uniform log-strike mesh, shape (n_k,)
    expiries: np.ndarray  # sorted unique expiries, shape (n_exp,)
    prices: np.ndarray  # normalized call prices, shape (n_exp, n_k)

    def density(self, i: int) -> np.ndarray:
        """Log-strike density d2C/dk2 - dC/dk at expiry i (central FD).

        This is the risk-neutral density of log(S_T / F_T) at k; its
        nonnegativity is the butterfly no-arbitrage condition.  Endpoints
        copy the adjacent interior value (one-sided stencils there would add
        noise, not information).
        """
        c = self.prices[i]
        h = self.k_mesh[1] - self.k_mesh[0]
        interior = (c[2:] - 2.0 * c[1:-1] + c[:-2]) / (h * h) - (c[2:] - c[:-2]) / (2.0 * h)
        out = np.empty_like(c)
        out[1:-1] = interior
        out[0] = interior[0]
        out[-1] = interior[-1]
        return out


def solve_dupire(
    grid,
    expiries,
    *,
    k_lo: float | None = None,
    k_hi: float | None = None,
    n_k: int = DEFAULT_N_K,
    dt_max: float = DEFAULT_DT_MAX,
) -> PDESolution:
    """March the Dupire forward PDE through all requested expiries.

    ``grid`` is anything exposing ``vol(k_array, t_scalar) -> array`` of local
    vols (LocalVolGrid in practice).  Time stepping subdivides each interval
    between consecutive expiries into equal steps no longer than ``dt_max``;
    duplicates in ``expiries`` are collapsed and the output is sorted.

    ``k_lo``/``k_hi`` default to an adaptive span of SPAN_SD terminal standard
    deviations, sigma_max * sqrt(T_max), read off the grid when it exposes a
    ``sigma`` array (LocalVolGrid does); pass both explicitly to pin the mesh.
    """
    exps = np.array(sorted({float(t) for t in expiries}))
    if exps.size == 0:
        raise ValueError("at least one expiry is required")
    if exps[0] <= 0.0:
        raise ValueError(f"expiries must be positive, got {exps[0]}")

    if k_lo is None or k_hi is None:
        sigma_max = float(np.max(getattr(grid, "sigma", 0.4)))
        span = max(SPAN_MIN, SPAN_SD * sigma_max * np.sqrt(exps[-1]))
        k_lo = -span if k_lo is None else k_lo
        k_hi = span if k_hi is None else k_hi

    k_mesh = np.linspace(k_lo, k_hi, n_k)
    h = (k_hi - k_lo) / (n_k - 1)
    k_int = k_mesh[1:-1]
    inv_h2 = 1.0 / (h * h)
    inv_2h = 1.0 / (2.0 * h)
    bc_lo = 1.0 - np.exp(k_lo)  # Dirichlet boundary values (time-independent)

    c = np.maximum(1.0 - np.exp(k_mesh), 0.0)  # payoff at T = 0
    c[-1] = 0.0

    def step(c_old: np.ndarray, t0: float, dt: float, theta: float) -> np.ndarray:
        """One theta-scheme step from t0 to t0 + dt; sigma at midpoint time."""
        sig = grid.vol(k_int, t0 + 0.5 * dt)
        s = 0.5 * sig * sig
        # Spatial operator L: lower / diag / upper coefficients on interior nodes.
        lo = s * (inv_h2 + inv_2h)
        di = -2.0 * s * inv_h2
        up = s * (inv_h2 - inv_2h)

        if theta < 1.0:
            w = (1.0 - theta) * dt
            rhs = c_old[1:-1] + w * (lo * c_old[:-2] + di * c_old[1:-1] + up * c_old[2:])
        else:
            rhs = c_old[1:-1].copy()
        # Implicit boundary contribution (right boundary value is 0).
        rhs[0] += theta * dt * lo[0] * bc_lo

        # Banded form of I - theta*dt*L for solve_banded((1, 1), ...).
        ab = np.zeros((3, n_k - 2))
        ab[0, 1:] = -theta * dt * up[:-1]
        ab[1, :] = 1.0 - theta * dt * di
        ab[2, :-1] = -theta * dt * lo[1:]
        sol = solve_banded(
            (1, 1), ab, rhs, overwrite_ab=True, overwrite_b=True, check_finite=False
        )
        c_new = np.empty_like(c_old)
        c_new[0] = bc_lo
        c_new[-1] = 0.0
        c_new[1:-1] = sol
        return c_new

    prices = np.empty((exps.size, n_k))
    t_start = 0.0
    first = True
    for i_exp, t_exp in enumerate(exps):
        n_sub = max(1, ceil((t_exp - t_start) / dt_max - 1e-12))
        dt = (t_exp - t_start) / n_sub
        for j in range(n_sub):
            t0 = t_start + j * dt
            if first:
                # Rannacher startup: damp the payoff-kink oscillation.
                dq = dt / N_RANNACHER
                for m in range(N_RANNACHER):
                    c = step(c, t0 + m * dq, dq, theta=1.0)
                first = False
            else:
                c = step(c, t0, dt, theta=0.5)
        prices[i_exp] = c
        t_start = t_exp

    return PDESolution(k_mesh=k_mesh, expiries=exps, prices=prices)

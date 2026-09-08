"""The PDE grids the affine LV fit marches on, from the gathered rows + Options.

One entry point, ``pde_lattice``, so the fit (affine_fit), the Compare tab's
twin (lv_compare) and the benchmark agree on the lattice for a given surface:

* **time** — ``timeScheme = "implicit"`` keeps the per-interval uniform rule
  of ``affine_fit._pde_grids`` (dt ≤ 0.01, short intervals lifted to 32
  steps: the byte-identical legacy); "bdf2" / "rannacher" march the graded
  time grid of ``pde_grids.graded_time_grid`` (geometric from the kink, every
  vertex row a mark, ≥ 8 steps per slab, cap 0.05 — roadmap O0);
* **strike** — ``lvLattice = "uniform"`` keeps ``dx · arange`` at the
  shortest rung's step (``affine_fit._pde_dx``); "graded" builds
  ``pde_grids.graded_strike_grid`` from one region per expiry: its traded
  range widened to ±REGION_SD σ√τ, at its own step
  clip(_PDE_DX_SHORT_FRAC σ√τ, 1/_PDE_N_MAX, _X_DX); the wings at WING_DX.

Lives beside affine_fit (which is far past the 400-line policy); the
constants are read from it lazily to avoid an import cycle.
"""

from __future__ import annotations

import numpy as np

from volfit.models.localvol.pde_grids import (
    REGION_SD,
    graded_strike_grid,
    graded_time_grid,
)


def strike_regions(rows) -> list[tuple[float, float, float]]:
    """One ``(x_lo, x_hi, step)`` requirement per row (expiry): the traded
    range ∪ ±REGION_SD ATM standard deviations, at the row's own step."""
    from volfit.api import affine_fit as af  # lazy: affine_fit imports this module

    regions = []
    for _, tau, k, w, _, _ in rows:
        k = np.asarray(k, dtype=float)
        w = np.asarray(w, dtype=float)
        order = np.argsort(k)
        w_atm = float(np.interp(0.0, k[order], w[order]))
        s = float(np.sqrt(max(w_atm, 1e-12)))  # sigma * sqrt(tau) at the money
        step = float(np.clip(af._PDE_DX_SHORT_FRAC * s, 1.0 / af._PDE_N_MAX, af._X_DX))
        lo = min(float(np.exp(k.min())), float(np.exp(-REGION_SD * s)))
        hi = max(float(np.exp(k.max())), float(np.exp(REGION_SD * s)))
        regions.append((lo, hi, step))
    return regions


def pde_lattice(
    rows,
    march_expiries: np.ndarray,
    t_nodes: np.ndarray,
    k_hi: float,
    time_scheme: str,
    lattice: str,
    x_max_min: float,
) -> tuple[np.ndarray, np.ndarray]:
    """``(x_grid, t_grid)`` for the fit's scheme and lattice mode (module docstring)."""
    from volfit.api import affine_fit as af  # lazy: affine_fit imports this module

    dt_max = af._DT_MAX_RANNACHER if time_scheme == "rannacher" else af._DT_MAX
    x_legacy, t_legacy = af._pde_grids(
        march_expiries, k_hi, dt_max, af._pde_dx(rows), x_max_min=x_max_min
    )
    if time_scheme == "implicit":
        t_grid = t_legacy
    else:
        t_grid = graded_time_grid(march_expiries, marks=np.asarray(t_nodes, dtype=float))
    if lattice == "uniform":
        x_grid = x_legacy
    else:
        x_max = float(x_legacy[-1])  # the same right edge (pad × quote max, floored)
        x_grid = graded_strike_grid(strike_regions(rows), x_max)
    return x_grid, t_grid

"""Dupire march ingredients: the solution record and the theta-independent
per-step precompute (Docs/piecewise_affine_local_variance_calibration.tex).

``AffinePDESolution`` is what ``affine_dupire.solve_affine_dupire`` returns;
``DupireSteps`` / ``precompute_dupire_steps`` hold everything of a march that
does not depend on theta (the basis at every time level, row-sparse where the
dense basis would not fit the phi memory budget), so a calibration reuses one
precompute across every objective evaluation.

Split out of ``affine.py`` on 2026-09-10 (the 400-line policy); ``affine``
re-exports every name.  Not to be confused with ``affine_steps`` (the step
kernels of the Numba march).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.models.localvol.affine_surface import AffineVarianceSurface


@dataclass(frozen=True)
class AffinePDESolution:
    """Forward solution U(t_req, x) (and sensitivities) at requested expiries."""

    x_grid: np.ndarray  # full strike grid incl. boundaries, shape (n_x,)
    expiries: np.ndarray  # sorted unique requested expiries, shape (n_exp,)
    prices: np.ndarray  # normalized calls, shape (n_exp, n_x)
    sens: np.ndarray | None  # dU/dtheta, shape (n_exp, n_x, m), or None

    def price_at(self, i_exp: int, x: np.ndarray | float) -> np.ndarray:
        """Observation operator R_j: linear interpolation in strike."""
        return np.interp(np.asarray(x, dtype=float), self.x_grid, self.prices[i_exp])

    def sens_at(self, i_exp: int, x: np.ndarray) -> np.ndarray:
        """d(price_at)/dtheta, shape (len(x), m), by the same linear rows."""
        if self.sens is None:
            raise ValueError("solution was computed without sensitivities")
        x = np.asarray(x, dtype=float)
        j = np.clip(np.searchsorted(self.x_grid, x) - 1, 0, self.x_grid.size - 2)
        wgt = (x - self.x_grid[j]) / (self.x_grid[j + 1] - self.x_grid[j])
        s = self.sens[i_exp]
        return (1.0 - wgt)[:, None] * s[j] + wgt[:, None] * s[j + 1]


@dataclass(frozen=True)
class DupireSteps:
    """Theta-INDEPENDENT per-step data for the forward Dupire march.

    The hat-basis weights ``phi`` at each new time level depend only on the
    vertex set, the triangulation and the strike/time grids — never on the nodal
    values — so a calibration that solves the PDE for hundreds of trial thetas
    can build these once and reuse them every evaluation (see calibrate_affine).

    ``active_k[n]`` is the number of leading sensitivity columns that can be
    non-zero after step ``n``. A vertex's sensitivity column stays exactly zero
    until the march reaches the support of its hat, and the time vertices
    activate in increasing order, so the live columns are always a prefix
    ``[0:active_k]``; solving only that prefix is bit-for-bit identical to the
    full multi-RHS solve while skipping the structurally-zero tail.
    """

    interior_x: np.ndarray  # x[1:-1], the PDE interior nodes
    phi: list | np.ndarray | None  # phi[n] = hat weights (n_interior x m) at level t[n+1]
    active_k: np.ndarray  # active_k[n] = live sensitivity-column count after step n
    #: When the left-wing slope ``a`` is a free parameter, ``phi`` holds the
    #: flat-extrap base (a = 0) and ``phi_lin[n]`` the linear-continuation delta,
    #: so the solver forms phi(a) = phi + a * phi_lin per step (and an analytic
    #: a-sensitivity = phi_lin @ theta). None ⇒ ``a`` is baked into ``phi``.
    phi_lin: list | None = None
    #: Over-budget SPARSE store (affine_steps.build_sparse_phi): ``phi`` is None
    #: and each step's basis lives in (n_steps, n_int, nnz) value/column slabs —
    #: bit-identical rows at a fraction of the dense footprint.
    phi_vals: np.ndarray | None = None
    phi_cols: np.ndarray | None = None
    #: Over-budget LAZY mode (left-lin split only): ``phi``/``phi_lin`` are None
    #: and the solver re-evaluates ``surface.basis_components`` per step — the
    #: basis is theta-independent, so holding the ORIGINAL surface keeps its
    #: cached triangulation across every trial theta.
    surface: "AffineVarianceSurface | None" = None
    lazy_left_lin: bool = False


def precompute_dupire_steps(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    with_left_lin: bool = False,
) -> DupireSteps:
    """Build the theta-independent per-step basis + active-column schedule.

    ``active_k`` is the running maximum of "highest non-zero basis column + 1"
    over the steps so far — derived from the actual basis sparsity, so it stays
    correct for every interpolation mode (delaunay/triangle/bilinear).

    ``with_left_lin`` splits the basis into the flat-extrap base + the left-wing
    linear-continuation delta (``basis_components``) so the solver can treat the
    slope multiple ``a`` as a free parameter; otherwise ``a`` is baked into the
    stored basis via ``surface.basis`` (the default / fixed-a path).

    Memory guard: the dense store is (n_steps x n_int x m) float64 — on a
    worst-case universe (short-front dx cap x sub-stepped weekly ladder x dense
    vertex grid) that is GiB-scale and the allocation fails. Above the budget
    (affine_steps.phi_budget_bytes, VOLFIT_LV_PHI_DENSE_MB) — or on an actual
    MemoryError — the common path switches to the exact row-sparse store and
    the left-lin split to per-step lazy re-evaluation. At or below budget the
    dense build runs unchanged (byte-identical).
    """
    from volfit.models.localvol.affine_steps import (
        build_sparse_phi, lazy_active_schedule, phi_budget_bytes,
    )

    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    interior = x[1:-1]
    m = surface.n_params
    n_steps = t.size - 1
    est_bytes = n_steps * interior.size * m * 8 * (2 if with_left_lin else 1)
    if est_bytes <= phi_budget_bytes():
        try:
            return _precompute_dense(surface, interior, t, m, n_steps, with_left_lin)
        except MemoryError:
            pass  # budget met but the box could not serve it: degrade gracefully
    if with_left_lin:
        return DupireSteps(
            interior_x=interior, phi=None, phi_lin=None,
            active_k=lazy_active_schedule(surface, interior, t),
            surface=surface, lazy_left_lin=True,
        )
    vals, cols, active_k = build_sparse_phi(surface, interior, t)
    return DupireSteps(
        interior_x=interior, phi=None, active_k=active_k, phi_vals=vals, phi_cols=cols
    )


def _precompute_dense(
    surface: AffineVarianceSurface,
    interior: np.ndarray,
    t: np.ndarray,
    m: int,
    n_steps: int,
    with_left_lin: bool,
) -> DupireSteps:
    """The historical dense build (unchanged — the in-budget byte-identical path)."""
    # Without the left-wing split, store the per-step basis as ONE contiguous
    # (n_steps, n_int, m) array: the banded march indexes ``phi[n]`` (a 2-D view, so
    # byte-identical), and the Numba vectorized-Thomas march (affine_march) consumes
    # the whole array directly. With the split (fit_left_a) keep the legacy lists.
    phi: list | np.ndarray = [] if with_left_lin else np.empty((n_steps, interior.size, m))
    phi_lin: list | None = [] if with_left_lin else None
    active_k = np.empty(n_steps, dtype=int)
    running_max = -1
    for n in range(n_steps):
        if with_left_lin:
            pb, pl = surface.basis_components(interior, float(t[n + 1]))
            phi.append(pb)
            phi_lin.append(pl)
            touched_arr = (pb != 0.0) | (pl != 0.0)
        else:
            pb = surface.basis(interior, float(t[n + 1]))
            phi[n] = pb
            touched_arr = pb != 0.0
        touched = np.flatnonzero(np.any(touched_arr, axis=0))
        if touched.size:
            running_max = max(running_max, int(touched[-1]))
        active_k[n] = min(running_max + 1, m)
    return DupireSteps(interior_x=interior, phi=phi, active_k=active_k, phi_lin=phi_lin)



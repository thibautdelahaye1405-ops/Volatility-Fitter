"""Over-budget fallbacks for the theta-independent Dupire step basis (phi).

``precompute_dupire_steps`` stores the per-step hat basis as ONE dense
``(n_steps, n_interior, m)`` float64 tensor — the fastest layout for the Numba
march, but on a worst-case universe (short front expiry -> dx at the 1/800 cap,
weekly ladder -> ~250 sub-stepped time levels, dense chain -> ~400 vertices) it
is gigabytes and the allocation fails outright ("Unable to allocate 1.66 GiB").

This module provides the memory-guarded alternatives:

- ``phi_budget_bytes``: the dense-tensor budget (``VOLFIT_LV_PHI_DENSE_MB``,
  default 512 MB). At or below it the dense path is used unchanged
  (byte-identical to the historical behavior); above it the compact builds
  below kick in — cases that previously CRASHED, so they carry no
  byte-identity obligation (they match the dense results to solver rounding).
- ``build_sparse_phi``: exact row-sparse store of the same basis. A basis row
  touches <= 4 vertices (barycentric / bilinear hats), and a left-wing
  linearly-extrapolated row blends two such rows, so 8 value/column slots per
  interior node always suffice — ~30-60x smaller than dense. Exact for EVERY
  interp mode (a time-slab endpoint blend would NOT be: the delaunay /
  triangle hats are only piecewise-linear in t inside a slab).
- ``densify_step``: rebuild one step's dense (n_interior, m) matrix from the
  sparse slabs — bit-identical to the stored rows — for the scipy banded march.
- ``lazy_active_schedule``: the active-column schedule for the lazy
  (re-evaluate-per-step) mode used by the rarer free-left-slope and var-swap
  paths, where the basis is split in two parts and sparsity is less regular.
"""

from __future__ import annotations

import os

import numpy as np

#: Value/column slots per interior node in the sparse per-step store. In-hull
#: rows touch <= 4 vertices (3 barycentric, 4 bilinear); a left-wing
#: extrapolated row is a blend of the rows at x_nodes[0] and x_nodes[1], so the
#: union stays <= 8. ``build_sparse_phi`` verifies per step.
_NNZ_MAX = 8

_BUDGET_ENV = "VOLFIT_LV_PHI_DENSE_MB"
_BUDGET_DEFAULT_MB = 512.0


def phi_budget_bytes() -> float:
    """Dense per-step-basis budget in bytes (env-overridable, default 512 MB)."""
    raw = os.environ.get(_BUDGET_ENV, "")
    try:
        mb = float(raw) if raw else _BUDGET_DEFAULT_MB
    except ValueError:
        mb = _BUDGET_DEFAULT_MB
    return mb * 1024.0 * 1024.0


def build_sparse_phi(
    surface, interior: np.ndarray, t_grid: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Row-sparse per-step basis: ``(vals, cols, active_k)``.

    ``vals``/``cols`` are ``(n_steps, n_interior, nnz)`` slabs; unused slots are
    (0.0, col 0), which contribute exactly nothing to any accumulation. Each
    step's dense matrix is built transiently (a few MB) and discarded — only
    the nonzeros are kept, so the values are bit-identical to the dense store.
    ``active_k`` is the same running live-column schedule as the dense build.
    """
    t = np.asarray(t_grid, dtype=float)
    n_steps = t.size - 1
    n_int = int(interior.size)
    m = surface.n_params
    nnz = min(_NNZ_MAX, m)
    vals = np.zeros((n_steps, n_int, nnz))
    cols = np.zeros((n_steps, n_int, nnz), dtype=np.int64)
    active_k = np.empty(n_steps, dtype=int)
    running_max = -1
    for n in range(n_steps):
        pb = surface.basis(interior, float(t[n + 1]))  # transient (n_int, m)
        r, c = np.nonzero(pb)  # row-major, so ascending column within each row
        counts = np.bincount(r, minlength=n_int)
        if counts.max(initial=0) > nnz:
            raise RuntimeError(
                f"basis row has {int(counts.max())} nonzeros > the {nnz} sparse slots"
            )
        starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
        slot = np.arange(r.size) - starts[r]  # rank of each nonzero within its row
        vals[n, r, slot] = pb[r, c]
        cols[n, r, slot] = c
        touched = np.flatnonzero(np.any(pb != 0.0, axis=0))
        if touched.size:
            running_max = max(running_max, int(touched[-1]))
        active_k[n] = min(running_max + 1, m)
    return vals, cols, active_k


def densify_step(vals: np.ndarray, cols: np.ndarray, m: int) -> np.ndarray:
    """One step's dense (n_interior, m) basis from its sparse slabs.

    Accumulating slot by slot keeps duplicate padding (0.0 at col 0) harmless;
    real columns are unique per row, so the result is bit-identical to the
    matrix ``build_sparse_phi`` extracted from.
    """
    n_int, nnz = vals.shape
    out = np.zeros((n_int, m))
    rows = np.arange(n_int)
    for j in range(nnz):
        out[rows, cols[:, j]] += vals[:, j]
    return out


def lazy_active_schedule(surface, interior: np.ndarray, t_grid: np.ndarray) -> np.ndarray:
    """Active-column schedule for the lazy (left-lin split) mode, one transient pass."""
    t = np.asarray(t_grid, dtype=float)
    n_steps = t.size - 1
    m = surface.n_params
    active_k = np.empty(n_steps, dtype=int)
    running_max = -1
    for n in range(n_steps):
        pb, pl = surface.basis_components(interior, float(t[n + 1]))
        touched = np.flatnonzero(np.any((pb != 0.0) | (pl != 0.0), axis=0))
        if touched.size:
            running_max = max(running_max, int(touched[-1]))
        active_k[n] = min(running_max + 1, m)
    return active_k

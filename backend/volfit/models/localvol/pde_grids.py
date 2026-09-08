"""The affine LV calibration's PDE grids (LV operator arc, O3 + O4).

Two graded grids replace the uniform ones of ``affine_fit._pde_grids`` (kept
for the byte-identical implicit legacy):

**Time** (``graded_time_grid``) — the hybrid rule of the arc's O0
measurements. The payoff kink at t = 0 sets a solution whose time scale IS t
(ATM: ∂_t C ∝ t^{-1/2}), so the steps grow geometrically from a tiny first
one, dt ≤ c·t; the local variance is piecewise-affine in t with kinks at the
VERTEX ROWS, so every row (and every expiry) is a grid point and every slab
between consecutive marks gets at least ``slab_steps`` steps; an absolute
ceiling closes it. Marks are hit exactly by splitting a slab's remainder
evenly, so a step never grows by more than 1 + c (BDF2 never restarts after
its first step). Measured on the fitted surfaces (roadmap O0): ≤ 5 bp of
operator error per expiry at 98–116 steps under BDF2, where the uniform
per-interval rule marched 51–271 and left 15–170 bp.

**Strike** (``graded_strike_grid``) — each expiry needs a step of
``_PDE_DX_SHORT_FRAC`` × its ATM σ√τ over its own density support (the fix-#6
rule: the lattice must out-resolve the quotes near the money); a uniform
lattice takes the SHORTEST rung's step everywhere (a 2-day SPY daily: 1/800
over [0, 2.5], ~1700 nodes). Here every expiry contributes a REGION — its
traded range widened to ±``REGION_SD`` σ√τ in log-moneyness — with its own
step; outside every region the step is the wing step. The target step
function is smoothed into a Lipschitz envelope (the step may change by at
most a factor ``ratio`` per cell, so the nonuniform central stencil of the
note's eq. (nonuniform_second_derivative) keeps its accuracy) and integrated
OUTWARD from x = 1, which is therefore a node by construction (the var-swap
anchor and the ATM row need it exactly); 0 and x_max close the lattice.

``refine_cells`` subdivides any lattice (the converged-operator reprice, the
twin's display operator) and ``second_difference`` differentiates prices on
any lattice — both keep the historical uniform formulas bit-for-bit on a
uniform lattice, so every implicit-legacy number is unchanged.
"""

from __future__ import annotations

import numpy as np

# ------------------------------------------------------------------ time grid
#: dt ≤ GROWTH × t: the geometric growth rate from the kink (ratio 1 + c per step).
TIME_GROWTH = 0.25
#: The first step as a fraction of the first mark (kink resolution).
TIME_FIRST_FRAC = 0.01
#: Absolute step ceiling (years).
TIME_DT_MAX = 0.05
#: Minimum steps per slab between consecutive marks (expiries ∪ vertex rows).
TIME_SLAB_STEPS = 8

# --------------------------------------------------------------- strike grid
#: Half-width of an expiry's region in ATM standard deviations (log-moneyness):
#: the density beyond 6 σ√τ is < e^{-18} of its peak — nothing to resolve.
REGION_SD = 6.0
#: The step outside every region (the wings, where prices are intrinsic or ~0).
#: 0.02 keeps the display wing's linear interpolation between nodes honest;
#: the wings hold few nodes at any step, the savings are in the fine region.
WING_DX = 0.02
#: Max step growth per cell of the smoothed lattice.
STRIKE_RATIO = 1.15


def graded_time_grid(
    expiries,
    marks=(),
    growth: float = TIME_GROWTH,
    first_frac: float = TIME_FIRST_FRAC,
    dt_max: float = TIME_DT_MAX,
    slab_steps: int = TIME_SLAB_STEPS,
) -> np.ndarray:
    """The hybrid time grid: 0, then steps min(growth·t, dt_max, (1+growth)·dt_last,
    slab/slab_steps) from dt_0 = first_frac × the first mark, every expiry and
    every mark hit exactly (the remainder of a slab is split evenly)."""
    ex = np.asarray(expiries, dtype=float)
    mk = np.asarray(marks, dtype=float) if len(marks) else np.zeros(0)
    all_marks = np.unique(np.concatenate([ex, mk]))
    all_marks = all_marks[all_marks > 0.0]
    if all_marks.size == 0:
        raise ValueError("graded_time_grid needs at least one positive expiry")
    pts = [0.0]
    t = 0.0
    prev = 0.0
    dt_last = first_frac * float(all_marks[0])
    n_slab = max(int(slab_steps), 1)
    for e in all_marks:
        e = float(e)
        slab = e - prev
        while True:
            cap = slab / n_slab
            if t > 0.0:
                dt = min(growth * t, dt_max, (1.0 + growth) * dt_last, cap)
            else:
                dt = min(dt_last, cap)
            gap = e - t
            m = int(np.ceil(gap / dt - 1e-9))
            if m <= 2:  # finish the slab with equal steps (ratios <= 1: no restart)
                m = max(m, 1)
                step = gap / m
                for j in range(1, m + 1):
                    pts.append(t + j * step)
                pts[-1] = e  # the mark exactly (float identity with the caller's)
                t = e
                dt_last = step
                break
            t += dt
            pts.append(t)
            dt_last = dt
        prev = e
    return np.array(pts)


def graded_strike_grid(
    regions,
    x_max: float,
    wing_dx: float = WING_DX,
    ratio: float = STRIKE_RATIO,
) -> np.ndarray:
    """Nodes from 0 to ``x_max`` with x = 1 a node, step ≤ h_j inside each region
    ``(x_lo_j, x_hi_j, h_j)``, ``wing_dx`` outside all, growth ≤ ``ratio`` per cell.

    The envelope h(x) = min(wing_dx, min_j h_j + (ratio − 1)·dist(x, region_j))
    is the largest step function below every requirement whose slope is at
    most ratio − 1 (geometric growth per cell); walking outward from 1 with
    step h(x) realises it. Both ends close on the boundary node.
    """
    if not (x_max > 1.0):
        raise ValueError("x_max must exceed 1")
    regs = [(float(lo), float(hi), float(h)) for lo, hi, h in regions if h > 0.0]
    slope = max(float(ratio) - 1.0, 1e-6)

    def h_at(x: float) -> float:
        h = float(wing_dx)
        for lo, hi, hj in regs:
            d = lo - x if x < lo else (x - hi if x > hi else 0.0)
            h = min(h, hj + slope * d)
        return h

    right = [1.0]
    x = 1.0
    while True:
        h = h_at(x)
        if x + h >= x_max - 0.5 * h:  # close on the boundary (a cell of 0.5–1.5 h)
            right.append(float(x_max))
            break
        x += h
        right.append(x)
    left = []
    x = 1.0
    while True:
        h = h_at(x)
        if x - h <= 0.5 * h:
            left.append(0.0)
            break
        x -= h
        left.append(x)
    return np.array(left[::-1] + right)


def is_uniform(x: np.ndarray, rtol: float = 1e-9) -> bool:
    """True when every cell has the same width (to relative rounding)."""
    x = np.asarray(x, dtype=float)
    h = np.diff(x)
    return bool(h.size > 0 and np.all(np.abs(h - h[0]) <= rtol * abs(h[0])))


def refine_cells(x: np.ndarray, factor: int) -> np.ndarray:
    """Subdivide every cell of ``x`` into ``factor`` equal cells (every node kept).

    A uniform lattice takes the historical ``linspace`` route (bit-identical to
    ``reprice.refined_grids`` before the arc); a graded one is refined cell by
    cell, so x = 1 and every original node stay nodes.
    """
    x = np.asarray(x, dtype=float)
    f = int(factor)
    if f <= 1:
        return x.copy()
    if is_uniform(x):
        return np.linspace(x[0], x[-1], f * (x.size - 1) + 1)
    h = np.diff(x)
    inner = x[:-1, None] + h[:, None] * (np.arange(f) / f)[None, :]
    return np.concatenate([inner.ravel(), [x[-1]]])


def second_difference(x: np.ndarray, c: np.ndarray) -> np.ndarray:
    """d²c/dx² at the interior nodes of ``x`` (last axis of ``c``).

    Uniform lattice: the historical ``(c[j+1] − 2c[j] + c[j−1]) / dx²``
    (bit-identical). Graded lattice: the nonuniform central difference of the
    note's eq. (nonuniform_second_derivative),
    2/(h_{j−1} + h_j) · ((c[j+1] − c[j])/h_j − (c[j] − c[j−1])/h_{j−1}).
    """
    x = np.asarray(x, dtype=float)
    c = np.asarray(c, dtype=float)
    if is_uniform(x):
        dx = float(x[1] - x[0])
        return (c[..., 2:] - 2.0 * c[..., 1:-1] + c[..., :-2]) / (dx * dx)
    h = np.diff(x)
    hm, hp = h[:-1], h[1:]
    fwd = (c[..., 2:] - c[..., 1:-1]) / hp
    bwd = (c[..., 1:-1] - c[..., :-2]) / hm
    return 2.0 * (fwd - bwd) / (hm + hp)


def local_step(x: np.ndarray, j: np.ndarray) -> np.ndarray:
    """The cell width just above node(s) ``j`` (the step a stencil at j sees)."""
    x = np.asarray(x, dtype=float)
    jj = np.clip(np.asarray(j, dtype=int), 0, x.size - 2)
    return x[jj + 1] - x[jj]


def third_difference_weights(x: np.ndarray, j: np.ndarray) -> np.ndarray:
    """Weights ``w`` (len(j) × 4) with Σ_k w_k c[j+k] = 6 h_j³ · c[x_j, …, x_{j+3}]
    — six times the third divided difference, scaled by the first cell's width
    cubed — so the row is (−1, 3, −3, 1) on a uniform stretch (the density-
    smoothness rows' historical stencil) and EXACT for a cubic on any lattice:
    a smooth price curve costs nothing where the step changes, which the raw
    third difference does not give (it reads the lattice's own grading as
    density slope — the graded-lattice campaign finding of 2026-09-08)."""
    x = np.asarray(x, dtype=float)
    j = np.asarray(j, dtype=int)
    pts = np.stack([x[j], x[j + 1], x[j + 2], x[j + 3]], axis=1)
    h3 = (x[j + 1] - x[j]) ** 3
    w = np.empty((j.size, 4))
    for k in range(4):
        prod = np.ones(j.size)
        for l in range(4):
            if l != k:
                prod = prod * (pts[:, k] - pts[:, l])
        w[:, k] = 6.0 * h3 / prod
    return w

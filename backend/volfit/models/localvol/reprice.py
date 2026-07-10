"""Converged-operator reprice of a calibrated affine LV surface.

The calibration's own residuals are computed THROUGH the operator the
optimizer used — and the optimizer bends theta to cancel that operator's
time-discretization error, so in-operator RMS is structurally blind to it
(the fix-#3 lesson: a true weekly marched with 2 implicit-Euler steps
mis-prices even a FLAT surface by ~240 bp at the ATM, the fit "absorbs" it,
and the error only surfaces on a converged reprice or as floor-pinned nodes).
The honest fit metric therefore reprices the CALIBRATED surface once on a
refined operator and scores the quotes against that.

``reprice_affine_dupire`` is a value-only implicit-Euler march that mirrors
``affine.solve_affine_dupire``'s numerics exactly (same nonuniform central
stencil with the 1/2 folded in, Dirichlet U(0)=1 / U(x_max)=0, local variance
at the NEW time level) but evaluates ``surface.variance`` directly per step
instead of precomputing the per-step hat-basis array — O(n_x) memory, so a
grid refined 4x in time and 2x in strike stays a few-ms march instead of a
multi-hundred-MB basis allocation. On the SAME grid (implicit scheme, same
left slope) it reproduces ``solve_affine_dupire``'s value path bit-for-bit
(test-locked), which is what makes the refined-grid number attributable to
the OPERATOR, not to a different discretization scheme.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import solve_banded

from volfit.models.localvol.affine import AffinePDESolution, AffineVarianceSurface

#: Refinement factors defining the "converged" operator: every calibration
#: time step is subdivided by ``CONV_DT_FACTOR`` (so the front weekly interval
#: that fix #3 marches with 32 steps gets 128) and the strike step is halved.
#: Chosen so the reprice sits past the discretization knee measured in the
#: short-dated diagnosis (dt refinement plateaued well before 4x; dx gains
#: plateaued at ~half the adaptive step).
CONV_DT_FACTOR = 4
CONV_DX_FACTOR = 2


def refined_grids(
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    dx_factor: int = CONV_DX_FACTOR,
    dt_factor: int = CONV_DT_FACTOR,
) -> tuple[np.ndarray, np.ndarray]:
    """The converged-operator grids: subdivide every calibration step.

    Refining the CALIBRATION grids (rather than rebuilding from a smaller
    ``dt_max``) guarantees the reprice is at least ``dt_factor`` finer on
    every interval — including the fix-#3-refined front interval — and keeps
    every quoted expiry exactly on a time node. The strike grid is uniform by
    construction (``_pde_grids``), so ``linspace`` preserves the lattice and
    x = 1 stays a node.
    """
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    x_fine = np.linspace(x[0], x[-1], dx_factor * (x.size - 1) + 1)
    pts = [float(t[0])]
    for a, b in zip(t[:-1], t[1:]):
        pts.extend(np.linspace(a, b, dt_factor + 1)[1:].tolist())
    return x_fine, np.array(pts)


def reprice_affine_dupire(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    expiries,
) -> AffinePDESolution:
    """Value-only implicit-Euler forward Dupire march (no sensitivities).

    Numerics identical to ``solve_affine_dupire``'s implicit value path; the
    local variance is evaluated from the surface per step (new time level),
    so memory stays O(n_x) at any refinement. The surface's own
    ``left_extrap_a`` is used — callers reprice ``cal.surface.
    with_left_extrap_a(cal.left_extrap_a)`` so the FITTED slope applies.
    """
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    if t[0] != 0.0 or np.any(np.diff(t) <= 0):
        raise ValueError("t_grid must start at 0 and increase strictly")
    exps = np.array(sorted({float(e) for e in expiries}))
    pos = np.searchsorted(t, exps)
    if np.any(pos >= t.size) or not np.allclose(t[pos], exps, rtol=0.0, atol=1e-12):
        raise ValueError("every requested expiry must be a t_grid point")
    if np.any(exps <= 0.0):
        raise ValueError("expiries must be positive")
    want = {int(p): i for i, p in enumerate(pos)}

    n_x = x.size
    h = np.diff(x)
    hm, hp = h[:-1], h[1:]
    xi2 = x[1:-1] ** 2
    a_m = xi2 / ((hm + hp) * hm)  # nonuniform central stencil, 1/2 folded in
    a_p = xi2 / ((hm + hp) * hp)
    a_0 = -(a_m + a_p)
    x_int = x[1:-1]

    u = np.maximum(1.0 - x, 0.0)  # payoff (1 - x)^+ incl. boundaries
    prices = np.empty((exps.size, n_x))
    for n in range(t.size - 1):
        dt = t[n + 1] - t[n]
        nu = surface.variance(x_int, float(t[n + 1]))  # NEW time level, as the note
        lo, di, up = nu * a_m, nu * a_0, nu * a_p
        ab = np.zeros((3, n_x - 2))  # banded (I - dt*A^{n+1}) for solve_banded
        ab[0, 1:] = -dt * up[:-1]
        ab[1, :] = 1.0 - dt * di
        ab[2, :-1] = -dt * lo[1:]
        rhs = u[1:-1].copy()
        rhs[0] += dt * lo[0] * 1.0  # Dirichlet U_0 = 1
        sol_u = solve_banded((1, 1), ab, rhs, overwrite_b=True, check_finite=False)
        u = np.concatenate(([1.0], sol_u, [0.0]))
        i_out = want.get(n + 1)
        if i_out is not None:
            prices[i_out] = u
    return AffinePDESolution(x_grid=x, expiries=exps, prices=prices, sens=None)

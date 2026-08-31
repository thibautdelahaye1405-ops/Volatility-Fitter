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
    payoff: str = "call",
    time_scheme: str = "implicit",
    rannacher_steps: int = 2,
) -> AffinePDESolution:
    """Value-only forward Dupire march (no sensitivities).

    Numerics identical to ``solve_affine_dupire``'s value path; the local
    variance is evaluated from the surface per step (new time level), so
    memory stays O(n_x) at any refinement. The surface's own
    ``left_extrap_a`` is used — callers reprice ``cal.surface.
    with_left_extrap_a(cal.left_extrap_a)`` so the FITTED slope applies.

    ``payoff="put"`` marches the normalized put P(0, x) = (x - 1)^+ with
    Dirichlet P(., 0) = 0 and P(., x_max) = x_max - 1 through the SAME
    operator — 1 - x lies in the exact kernel of the central stencil, so the
    discrete parity C - P = 1 - x holds to round-off and the marched put IS
    the call's time value computed WITHOUT the intrinsic-leg cancellation
    (the short-dated left-display-wing fix; see api.affine_views_ext).
    ``time_scheme``/``rannacher_steps`` mirror ``solve_affine_dupire`` so a
    display put march can ride the exact scheme its call march used — a
    scheme mismatch would put the seam kink at k = 0. The default arguments
    reproduce the historical implicit call march bit-for-bit (test-locked).
    """
    if payoff not in ("call", "put"):
        raise ValueError(f"payoff must be 'call' or 'put', got {payoff!r}")
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

    is_put = payoff == "put"
    # Dirichlet boundary values; for the call these are the historical (1, 0).
    bc_lo = 0.0 if is_put else 1.0
    bc_hi = float(x[-1] - 1.0) if is_put else 0.0
    cn_enabled = time_scheme == "rannacher"
    rann = max(int(rannacher_steps), 1)

    if is_put:
        u = np.maximum(x - 1.0, 0.0)  # payoff (x - 1)^+ incl. boundaries
    else:
        u = np.maximum(1.0 - x, 0.0)  # payoff (1 - x)^+ incl. boundaries
    prices = np.empty((exps.size, n_x))
    nu_prev = None  # old-level nu, for the Crank-Nicolson explicit half
    for n in range(t.size - 1):
        dt = t[n + 1] - t[n]
        # NEW time level, as the note; floored at 0 — the left-wing linear
        # continuation is "linear until zero, then flat" (negative variance is
        # anti-diffusion and explodes the march; see solve_affine_dupire).
        nu = np.maximum(surface.variance(x_int, float(t[n + 1])), 0.0)
        is_cn = cn_enabled and n >= rann  # Rannacher: implicit start-up steps
        frac = 0.5 if is_cn else 1.0  # theta-weight on the implicit operator
        lo, di, up = nu * a_m, nu * a_0, nu * a_p
        ab = np.zeros((3, n_x - 2))  # banded (I - frac*dt*A^{n+1}) for solve_banded
        ab[0, 1:] = -frac * dt * up[:-1]
        ab[1, :] = 1.0 - frac * dt * di
        ab[2, :-1] = -frac * dt * lo[1:]
        rhs = u[1:-1].copy()
        if is_cn:
            # explicit (old-level) half on the full stencil, boundaries included.
            au_old = a_m * u[:-2] + a_0 * u[1:-1] + a_p * u[2:]
            rhs += (1.0 - frac) * dt * nu_prev * au_old
        if is_put:
            rhs[-1] += frac * dt * up[-1] * bc_hi  # Dirichlet P(x_max) = x_max - 1
        else:
            rhs[0] += frac * dt * lo[0] * 1.0  # Dirichlet U_0 = 1
        sol_u = solve_banded((1, 1), ab, rhs, overwrite_b=True, check_finite=False)
        u = np.concatenate(([bc_lo], sol_u, [bc_hi]))
        nu_prev = nu
        i_out = want.get(n + 1)
        if i_out is not None:
            prices[i_out] = u
    return AffinePDESolution(x_grid=x, expiries=exps, prices=prices, sens=None)

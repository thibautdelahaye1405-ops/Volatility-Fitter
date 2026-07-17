"""Backward source-PDE pricing of the variance swap (note eq. (variance_swap_source_pde)).

The fair total variance of an expiry is I(T) = E[int_0^T nu(t,X_t) dt]. Rather than
the static log-contract replication of the computed option surface (the k^-2-weighted
strike integral of affine_calib.varswap_weights, which is sensitive to truncating /
coarsening the strike grid in the wings), this prices it as a LOCAL PDE quantity:

    d_t g + 1/2 nu(t,x) x^2 d_xx g + nu(t,x) = 0,    g(T, x) = 0,     I(T) = g(0, 1),

where g(t,x) = E_{t,x}[int_t^T nu(s,X_s) ds].  g(0,1) is determined by the diffusion
AROUND x = 1, so it barely depends on the far strike boundary — the property Stage 3
(a coarse calibration grid) needs.  Same implicit-Euler operator and tridiagonal
solve as the forward Dupire march (volfit.models.localvol.affine), marched BACKWARD
from T with a +nu source; the degenerate boundaries (x^2 -> 0 at x = 0, far-field
d_xx g = 0 at x_max) just accumulate the local variance.

Sensitivities follow the note's eq. (var_sensitivity_pde): h_l = dg/dtheta_l solves the
same operator with source 1/2 phi_l x^2 d_xx g + phi_l, propagated as a multi-RHS solve
against the shared per-step factor (exactly like the forward sensitivity sweep), so the
optimiser gets an analytic dI/dtheta.  When the left-wing slope ``a`` is a free
parameter (var-swap present) an extra dI/da column is appended (d nu/da = phi_lin @ theta
in the extrapolation region).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve_banded

from volfit.models.localvol.affine import AffineVarianceSurface


@dataclass(frozen=True)
class VarSwapSteps:
    """Theta-independent per-level basis for the backward source march.

    ``phi_full[n]`` is the hat basis at every strike node (boundaries included) at
    time level ``t[n]`` — the level the n-th backward step solves for. ``phi_lin_full``
    is the left-wing linear-continuation delta (basis_components) when the slope ``a``
    is fitted, else None (``a`` baked into ``phi_full``).
    """

    phi_full: list | None  # phi_full[n] = (n_x, m) basis at t[n]
    phi_lin_full: list | None = None
    #: Over-budget LAZY mode: ``phi_full`` is None and the solver re-evaluates
    #: the (theta-independent) basis per level from this surface — holding the
    #: ORIGINAL instance keeps its cached triangulation across trial thetas.
    surface: AffineVarianceSurface | None = None
    lazy_left_lin: bool = False


def precompute_varswap_steps(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    with_left_lin: bool = False,
) -> VarSwapSteps:
    """Build the theta-independent full-grid basis at every time level (reused across
    trial thetas, like precompute_dupire_steps for the forward march).

    Same memory guard as the forward march: above the dense-store budget
    (affine_steps.phi_budget_bytes) — or on an actual MemoryError — return the
    lazy steps instead of a GiB-scale list of per-level matrices; the solver
    then computes each level's basis on the fly (identical floats, slower)."""
    from volfit.models.localvol.affine_steps import phi_budget_bytes

    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    est_bytes = t.size * x.size * surface.n_params * 8 * (2 if with_left_lin else 1)
    if est_bytes > phi_budget_bytes():
        return VarSwapSteps(phi_full=None, surface=surface, lazy_left_lin=with_left_lin)
    phi_full: list = []
    phi_lin_full: list | None = [] if with_left_lin else None
    try:
        for n in range(t.size):
            if with_left_lin:
                pb, pl = surface.basis_components(x, float(t[n]))
                phi_full.append(pb)
                phi_lin_full.append(pl)
            else:
                phi_full.append(surface.basis(x, float(t[n])))
    except MemoryError:  # budget met but the box could not serve it
        return VarSwapSteps(phi_full=None, surface=surface, lazy_left_lin=with_left_lin)
    return VarSwapSteps(phi_full=phi_full, phi_lin_full=phi_lin_full)


def solve_varswap_source(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    *,
    sensitivities: bool = False,
    steps: VarSwapSteps | None = None,
    left_a: float | None = None,
    fit_left_a: bool = False,
) -> tuple[float, np.ndarray | None]:
    """Model total variance I(T) = g(0, 1) by the backward source PDE.

    ``t_grid`` starts at 0 and ends at the expiry T (every step at most the forward
    march's dt).  Returns ``(I, dI)`` where ``dI`` (when ``sensitivities``) is
    dI/dtheta over the m nodal variances, plus a trailing dI/da column when
    ``fit_left_a``; None otherwise.
    """
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    if t[0] != 0.0 or np.any(np.diff(t) <= 0):
        raise ValueError("t_grid must start at 0 and increase strictly")
    a = float(left_a) if left_a is not None else surface.left_extrap_a
    if steps is None:
        steps = precompute_varswap_steps(surface, x, t, with_left_lin=fit_left_a)
    use_lin = steps.phi_lin_full is not None or steps.lazy_left_lin

    n_x = x.size
    h = np.diff(x)
    hm, hp = h[:-1], h[1:]
    xi2 = x[1:-1] ** 2
    a_m = xi2 / ((hm + hp) * hm)  # same 1/2 x^2 d_xx stencil as the forward march
    a_p = xi2 / ((hm + hp) * hp)
    a_0 = -(a_m + a_p)

    theta = surface.theta.ravel()
    m = surface.n_params
    n_cols = m + 1 if fit_left_a else m
    g = np.zeros(n_x)  # terminal condition g(T, .) = 0
    sens = np.zeros((n_x, n_cols)) if sensitivities else None

    for n in range(t.size - 2, -1, -1):  # solve g^n (time t[n]) from g^{n+1}
        dt = t[n + 1] - t[n]
        phi_lin_n = None
        if steps.phi_full is not None:  # precomputed (the in-budget hot path)
            phi_base = steps.phi_full[n]
            if use_lin:
                phi_lin_n = steps.phi_lin_full[n]
        elif use_lin:  # over-budget lazy: same floats, computed per level
            phi_base, phi_lin_n = steps.surface.basis_components(x, float(t[n]))
        else:
            phi_base = steps.surface.basis(x, float(t[n]))
        phi = phi_base + a * phi_lin_n if use_lin else phi_base
        nu_full = phi @ theta
        # Left-wing positivity clamp ("linear until zero, then flat"): negative
        # extrapolated variance destabilizes the solve and corrupts the
        # accumulated total variance; clamped rows get dnu/dtheta = dnu/da = 0
        # (see solve_affine_dupire). Healthy surfaces never clamp.
        neg = nu_full < 0.0
        if np.any(neg):
            nu_full = np.where(neg, 0.0, nu_full)
            phi = np.where(neg[:, None], 0.0, phi)
        nu = nu_full[1:-1]
        lo, di, up = nu * a_m, nu * a_0, nu * a_p
        ab = np.zeros((3, n_x - 2))  # I - dt A (same banded form as the forward step)
        ab[0, 1:] = -dt * up[:-1]
        ab[1, :] = 1.0 - dt * di
        ab[2, :-1] = -dt * lo[1:]

        # Degenerate boundaries: x^2 d_xx -> 0, so g just accumulates the local variance.
        g0 = g[0] + dt * nu_full[0]
        gN = g[-1] + dt * nu_full[-1]
        rhs = g[1:-1] + dt * nu  # the +nu source of the variance PDE
        rhs[0] += dt * lo[0] * g0  # known boundary g0 / gN fold into the interior RHS
        rhs[-1] += dt * up[-1] * gN

        if sensitivities:
            g_int = solve_banded((1, 1), ab.copy(), rhs, check_finite=False)
            g_new = np.concatenate(([g0], g_int, [gN]))
            # source of the sensitivity PDE: phi_l * (1/2 x^2 d_xx g + 1), discretely
            # phi_l_i * (a- g_{i-1} + a0 g_i + a+ g_{i+1} + 1).
            stencil_g = a_m * g_new[:-2] + a_0 * g_new[1:-1] + a_p * g_new[2:]
            phi_int = phi[1:-1]
            src = phi_int * (stencil_g[:, None] + 1.0)  # (n_int, m)
            # boundary sensitivity accumulation: dg0/dtheta_l += dt * phi_l(0).
            sens[0, :m] = sens[0, :m] + dt * phi[0]
            sens[-1, :m] = sens[-1, :m] + dt * phi[-1]
            rhs_s = sens[1:-1, :m] + dt * src
            rhs_s[0] += dt * lo[0] * sens[0, :m]
            rhs_s[-1] += dt * up[-1] * sens[-1, :m]
            if fit_left_a:
                # d nu / da on the full grid; 0 on positivity-clamped rows.
                glin = np.where(neg, 0.0, phi_lin_n @ theta)
                src_a = glin[1:-1] * (stencil_g + 1.0)
                sens[0, m] += dt * glin[0]
                sens[-1, m] += dt * glin[-1]
                rhs_a = sens[1:-1, m] + dt * src_a
                rhs_a[0] += dt * lo[0] * sens[0, m]
                rhs_a[-1] += dt * up[-1] * sens[-1, m]
                rhs_s = np.column_stack([rhs_s, rhs_a])
            sens[1:-1] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            g = g_new
        else:
            g_int = solve_banded(
                (1, 1), ab, rhs, overwrite_ab=True, overwrite_b=True, check_finite=False
            )
            g = np.concatenate(([g0], g_int, [gN]))

    i1 = int(np.searchsorted(x, 1.0))  # the x = 1 (ATM) node; I(T) = g(0, 1)
    if abs(x[i1] - 1.0) > 1e-12:
        raise ValueError("the var-swap anchor x = 1 must be a grid point")
    return float(g[i1]), (sens[i1].copy() if sensitivities else None)

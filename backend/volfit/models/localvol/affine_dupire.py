"""The forward Dupire march of the piecewise-affine local-variance surface
(Docs/piecewise_affine_local_variance_calibration.tex).

``solve_affine_dupire``: the march of the forward Dupire equation in
normalized strike x = K/F (eq. (forward_dupire_normalized)),
dC/dT = 1/2 nu(T,x) x^2 d2C/dx2, C(0,x) = (1-x)^+, Dirichlet C(.,0) = 1 and
C(., x_max) = 0, on a (possibly nonuniform) x grid with the central stencil
of eq. (nonuniform_second_derivative); the time scheme is the plan of
volfit.models.localvol.time_schemes (implicit Euler = eq. (implicit_step),
BDF2 the default since the LV operator arc, Rannacher opt-in).  Optional
forward sensitivities dU/dtheta per eq. (discrete_sensitivity) -- every
column shares the step's tridiagonal factor via a multi-RHS solve.

Split out of ``affine.py`` on 2026-09-10 (the 400-line policy); ``affine``
re-exports every name.  Not to be confused with ``affine_march`` (the Numba
step kernels this march calls).
"""

from __future__ import annotations

from time import perf_counter

import numpy as np
from scipy.linalg import solve_banded

from volfit.models.localvol.affine_precompute import AffinePDESolution, DupireSteps, precompute_dupire_steps
from volfit.models.localvol.affine_surface import AffineVarianceSurface, _sequential_nu
from volfit.models.localvol.time_schemes import build_plan


def solve_affine_dupire(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    expiries,
    *,
    sensitivities: bool = False,
    steps: DupireSteps | None = None,
    left_a: float | None = None,
    fit_left_a: bool = False,
    timing: dict | None = None,
    time_scheme: str = "implicit",
    rannacher_steps: int = 2,
    engine: str = "banded",
) -> AffinePDESolution:
    """Fully implicit Euler march of eq. (implicit_step) on the given grids.

    ``t_grid`` must start at 0 and contain every requested expiry exactly
    (the note: "force all quoted expiries to be time steps").  The local
    variance enters each step at the *new* time level t_{n+1} (matrix
    A^{n+1}), exactly as written in the note.  With ``sensitivities`` the
    full dU/dtheta is propagated per eq. (discrete_sensitivity); the source
    term uses the just-solved U^{n+1} including its boundary values, which
    folds the boundary derivative b^{n+1} contribution in for free.

    ``steps`` supplies precomputed theta-independent per-step basis weights and
    the active-column schedule (precompute_dupire_steps); a calibration reuses
    one ``DupireSteps`` across every trial theta. When omitted it is built here,
    so a standalone solve is unchanged. The sensitivity solve is restricted to
    the live column prefix ``[:active_k]`` — the tail columns are provably zero,
    so the result is bit-for-bit identical to solving all m columns.

    ``left_a`` overrides the surface's left-wing slope multiple for this solve;
    with ``fit_left_a`` an extra sensitivity column dU/da is propagated
    (analytically, source = (phi_lin @ theta) * gamma), appended after the m theta
    columns — so the calibration can optimise ``a`` jointly. Both need a
    ``steps`` built with ``with_left_lin=True`` (or steps=None here, which builds
    one); otherwise ``a`` is whatever is baked into ``steps.phi``.

    ``timing``, when a dict, accumulates wall seconds of the per-step banded
    solves into ``timing["value_s"]`` (the value march) and ``timing["sens_s"]``
    (the multi-RHS sensitivity march) — the Stage-0 instrumentation split. None
    (the default) is the zero-overhead hot path; standalone callers pass nothing.

    ``time_scheme`` (Stage 7) selects the time discretisation: "implicit" (the
    default — fully implicit Euler, 1st order, the byte-identical golden scheme),
    or "rannacher" — Crank-Nicolson (2nd order) after ``rannacher_steps`` implicit-
    Euler start-up steps that damp the payoff kink at x = 1 (plain CN would
    oscillate). 2nd order means a given accuracy is reached at a several-fold larger
    dt, so the live fit marches far fewer time steps per evaluation at equal
    accuracy (note "higher-order time stepping"). Rannacher is only applied when
    ``fit_left_a`` is False (the free-left-slope dU/da column keeps the implicit
    recursion); a "rannacher" request with ``fit_left_a`` falls back to implicit.

    "bdf2" (2026-09-08, the LV operator arc) marches the variable-step BDF2 step
    of ``time_schemes.build_plan`` — second order like Crank–Nicolson but
    L-stable, and its sensitivity recursion has the implicit step's shape
    (α S^n − β S^{n−1} + γΔt ∂A^{n+1} U^{n+1}), so it carries the dU/da column
    too. The first step and every restart (a step growing > BDF2_MAX_RATIO×)
    are implicit Euler steps. Every scheme is the generic two-level step of
    the note's eq. (generic_two_level_step); the implicit and Rannacher
    branches below keep their historical expressions (byte-identical).
    """
    timed = timing is not None
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    if t[0] != 0.0 or np.any(np.diff(t) <= 0):
        raise ValueError("t_grid must start at 0 and increase strictly")
    if steps is None:
        steps = precompute_dupire_steps(surface, x, t, with_left_lin=fit_left_a)
    a = float(left_a) if left_a is not None else surface.left_extrap_a
    use_lin = steps.phi_lin is not None or steps.lazy_left_lin
    # Crank-Nicolson is used only without the free-left-slope column (which keeps the
    # implicit dU/da recursion); the first ``rann`` steps stay implicit Euler to damp
    # the payoff kink (Rannacher start-up), so CN begins at step index ``rann`` >= 1.
    # BDF2 carries the dU/da column (same recursion shape), so it needs no fallback.
    scheme = "implicit" if (time_scheme == "rannacher" and fit_left_a) else time_scheme
    plan = build_plan(t, scheme, rannacher_steps)  # per-step (γ, α, β, ε)
    exps = np.array(sorted({float(e) for e in expiries}))
    pos = np.searchsorted(t, exps)
    if np.any(pos >= t.size) or not np.allclose(t[pos], exps, rtol=0.0, atol=1e-12):
        raise ValueError("every requested expiry must be a t_grid point")
    want = {int(p): i for i, p in enumerate(pos)}

    n_x = x.size
    h = np.diff(x)  # h[i] = x[i+1] - x[i]
    hm, hp = h[:-1], h[1:]  # spacings around interior node i = 1..n_x-2
    xi2 = x[1:-1] ** 2
    a_m = xi2 / ((hm + hp) * hm)  # eq. (nonuniform_second_derivative) coeffs
    a_p = xi2 / ((hm + hp) * hp)
    a_0 = -(a_m + a_p)

    m = surface.n_params
    n_cols = m + 1 if fit_left_a else m  # extra dU/da sensitivity column
    theta = surface.theta.ravel()
    u = np.maximum(1.0 - x, 0.0)  # payoff (1 - x)^+, includes boundary values
    sens = np.zeros((n_x, n_cols)) if sensitivities else None
    prices = np.empty((exps.size, n_x))
    out_sens = np.empty((exps.size, n_x, n_cols)) if sensitivities else None
    if 0 in want:  # expiry 0 is not allowed by searchsorted above (t[0]=0 < exps)
        raise ValueError("expiries must be positive")

    # Stage 6′: the Numba vectorized-Thomas march (~6× the banded path) handles the
    # common hot path — value + theta-sensitivities, implicit Euler, no free left
    # slope, with the contiguous (n_steps, n_int, m) basis (or its over-budget
    # sparse slabs). Everything else (value-only, Rannacher CN, fit_left_a, or
    # numba unavailable) keeps the banded march.
    sparse_phi = steps.phi_vals is not None
    if engine == "numba" and sensitivities and not fit_left_a and not use_lin \
            and plan.is_implicit \
            and (sparse_phi or isinstance(steps.phi, np.ndarray)):
        from volfit.models.localvol.affine_march import (
            march_value_sens, march_value_sens_sparse, numba_available,
        )

        if numba_available():
            want_step = np.full(t.size - 1, -1, dtype=np.int64)
            for p, i in want.items():
                want_step[p - 1] = i
            if sparse_phi:
                pr, se = march_value_sens_sparse(
                    steps.phi_vals, steps.phi_cols, theta, a_m, a_p, a_0,
                    np.diff(t), steps.active_k, want_step, u, exps.size, m,
                )
            else:
                pr, se = march_value_sens(
                    steps.phi, theta, a_m, a_p, a_0, np.diff(t), steps.active_k,
                    want_step, u, exps.size,
                )
            return AffinePDESolution(x_grid=x, expiries=exps, prices=pr, sens=se)

    # LV operator arc (O2): every OTHER plan (Rannacher, BDF2) runs the generic
    # compiled kernels of affine_march2 under the same conditions; the implicit
    # kernels above keep their own bits. Banded fallback below otherwise.
    if engine == "numba" and sensitivities and not fit_left_a and not use_lin             and not plan.is_implicit             and (sparse_phi or isinstance(steps.phi, np.ndarray)):
        from volfit.models.localvol.affine_march import numba_available
        from volfit.models.localvol.affine_march2 import march_plan, march_plan_sparse

        if numba_available():
            want_step = np.full(t.size - 1, -1, dtype=np.int64)
            for p, i in want.items():
                want_step[p - 1] = i
            if sparse_phi:
                pr, se = march_plan_sparse(
                    steps.phi_vals, steps.phi_cols, theta, a_m, a_p, a_0, np.diff(t), plan,
                    steps.active_k, want_step, u, exps.size, m,
                )
            else:
                pr, se = march_plan(
                    steps.phi, theta, a_m, a_p, a_0, np.diff(t), plan, steps.active_k,
                    want_step, u, exps.size,
                )
            return AffinePDESolution(x_grid=x, expiries=exps, prices=pr, sens=se)

    if sparse_phi:
        from volfit.models.localvol.affine_steps import densify_step

    phis = steps.phi
    active_k = steps.active_k
    nu_prev = None  # nu at the current (old) time level, carried for the CN explicit half
    phi_prev = None  # basis at the old level (= phis[n-1]), for the CN dA^n source
    u_prev = None  # U^{n-1}, the level before the old one (BDF2's two-level step)
    sens_prev = None  # dU^{n-1}/dtheta, likewise
    for n in range(t.size - 1):
        dt = t[n + 1] - t[n]
        # This step's coefficients: implicit (1, 1, 0, 0), CN (½, 1, 0, ½), BDF2's
        # (γ, α, β, 0). ``frac`` is the historical name of the implicit weight.
        is_cn = plan.eps[n] > 0.0
        two_level = plan.beta[n] > 0.0
        frac = float(plan.gamma[n])
        alpha, beta = float(plan.alpha[n]), float(plan.beta[n])
        phi_lin_n = None
        if phis is not None:  # precomputed dense (the in-budget hot path)
            phi_base = phis[n]  # cached hat weights at the new level (flat-extrap base)
            if use_lin:
                phi_lin_n = steps.phi_lin[n]
        elif sparse_phi:  # over-budget sparse store: rebuild this step bit-identically
            phi_base = densify_step(steps.phi_vals[n], steps.phi_cols[n], m)
        elif use_lin:  # over-budget lazy left-lin split: same floats, computed per step
            phi_base, phi_lin_n = steps.surface.basis_components(
                steps.interior_x, float(t[n + 1])
            )
        else:
            phi_base = steps.surface.basis(steps.interior_x, float(t[n + 1]))
        phi = phi_base + a * phi_lin_n if use_lin else phi_base
        # Sensitivity marches keep the BLAS dot (their own historical bits, and
        # the multi-RHS solve dwarfs it); a value-only march sums each row's
        # nonzeros sequentially in column order — the Numba kernels' and
        # AffineVarianceSurface.variance's summation — so a value-only solve and
        # a reprice of the same surface agree bit-for-bit (test-locked).
        nu = phi @ theta if sensitivities else _sequential_nu(phi, theta)
        # LEFT-WING POSITIVITY: the linear continuation below x_nodes[0] is
        # "linear until it hits zero, then flat at zero". A bottom cell whose
        # variance INCREASES with x (short-dated rows whose lowest vertices sit
        # far below the traded range, shaped by regularization alone)
        # extrapolates to nu << 0 at small x, and a negative diffusion
        # coefficient blows the march up exponentially (SPY live, 2026-07-17:
        # nu(0) ~ -24 over ~500 fine-grid nodes -> prices ~ 1e52). Clamped
        # rows get dnu/dtheta = dnu/da = 0, keeping the sensitivities exact
        # for the clamped surface; healthy fits never clamp (byte-identical).
        neg = nu < 0.0
        if np.any(neg):
            nu = np.where(neg, 0.0, nu)
            phi = np.where(neg[:, None], 0.0, phi)
        lo, di, up = nu * a_m, nu * a_0, nu * a_p

        ab = np.zeros((3, n_x - 2))  # banded (I - frac*dt*A^{n+1}) for solve_banded
        ab[0, 1:] = -frac * dt * up[:-1]
        ab[1, :] = 1.0 - frac * dt * di
        ab[2, :-1] = -frac * dt * lo[1:]

        u_old = u  # full array at the old level (boundaries included), for the CN half
        if two_level:  # BDF2: α U^n − β U^{n−1} on the interior (eq. (bdf2_step))
            rhs = alpha * u[1:-1] - beta * u_prev[1:-1]
        else:
            rhs = u[1:-1].copy()
        au_old = None
        if is_cn:
            # explicit (old-level) half: + (1-frac)*dt * A^n U^n on the full stencil
            # (au_old[0] already carries the U_0 = 1 left boundary at level n).
            au_old = a_m * u_old[:-2] + a_0 * u_old[1:-1] + a_p * u_old[2:]
            rhs += (1.0 - frac) * dt * nu_prev * au_old
        rhs[0] += frac * dt * lo[0] * 1.0  # implicit (new-level) U_0 = 1 boundary
        if sensitivities:
            _t0 = perf_counter() if timed else 0.0
            sol_u = solve_banded((1, 1), ab.copy(), rhs, check_finite=False)
            if timed:
                timing["value_s"] += perf_counter() - _t0
            u_new = np.concatenate(([1.0], sol_u, [0.0]))
            # A BDF2 step after this one needs S^n: snapshot before the in-place update.
            sens_now = sens.copy() if plan.uses_two_levels else None
            # Source G[i, l] = phi_l(t_{n+1}, x_i) * (a- U_{i-1} + a0 U_i + a+ U_{i+1}).
            # Only the first ``k`` sensitivity columns can be non-zero so far
            # (the rest stay at their zero initialization); solving the prefix
            # against the single step factorization is identical but cheaper.
            k = int(active_k[n])
            au = a_m * u_new[:-2] + a_0 * u_new[1:-1] + a_p * u_new[2:]
            _t0 = perf_counter() if timed else 0.0
            if two_level:
                # BDF2's sensitivity step: the same relation differentiated —
                # (I − γΔt A^{n+1}) S^{n+1} = α S^n − β S^{n−1} + γΔt (∂A^{n+1}) U^{n+1}
                # (eq. (generic_sensitivity_step) with ε = 0); the dU/da column
                # rides along. ``sens_prev`` is the copy taken before the previous
                # update (S^{n−1}); a restart step ahead of this one was implicit.
                if fit_left_a:
                    glin = np.where(neg, 0.0, phi_lin_n @ theta)
                    idx = np.concatenate([np.arange(k), [m]])
                    src = np.concatenate(
                        [phi[:, :k] * au[:, None], (glin * au)[:, None]], axis=1
                    )
                    rhs_s = alpha * sens[1:-1, idx] - beta * sens_prev[1:-1, idx] + (frac * dt) * src
                    sens[1:-1, idx] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
                else:
                    rhs_s = (
                        alpha * sens[1:-1, :k] - beta * sens_prev[1:-1, :k]
                        + (frac * dt) * phi[:, :k] * au[:, None]
                    )
                    sens[1:-1, :k] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            elif fit_left_a:
                # dU/da: same recursion, source (phi_lin @ theta) * gamma; appended
                # as the m-th column (always live once the wing region is touched).
                # Positivity-clamped rows have dnu/da = 0 (matching the theta rows).
                glin = np.where(neg, 0.0, phi_lin_n @ theta)
                idx = np.concatenate([np.arange(k), [m]])
                src = np.concatenate(
                    [phi[:, :k] * au[:, None], (glin * au)[:, None]], axis=1
                )
                rhs_s = sens[1:-1, idx] + dt * src
                sens[1:-1, idx] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            elif is_cn:
                # Differentiate the CN step: (I - frac dt A^{n+1}) dU^{n+1} =
                #   (I + (1-frac) dt A^n) dU^n          [explicit half on the old sens]
                #   + frac dt (dA^{n+1}_l) U^{n+1}      [new-level source, phi @ au]
                #   + (1-frac) dt (dA^n_l) U^n          [old-level source, phi_prev @ au_old]
                old = sens[:, :k]
                expl = old[1:-1] + (1.0 - frac) * dt * nu_prev[:, None] * (
                    a_m[:, None] * old[:-2] + a_0[:, None] * old[1:-1] + a_p[:, None] * old[2:]
                )
                rhs_s = (
                    expl
                    + frac * dt * phi[:, :k] * au[:, None]
                    + (1.0 - frac) * dt * phi_prev[:, :k] * au_old[:, None]
                )
                sens[1:-1, :k] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            else:
                rhs_s = sens[1:-1, :k] + dt * phi[:, :k] * au[:, None]
                sens[1:-1, :k] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            if timed:
                timing["sens_s"] += perf_counter() - _t0
            sens_prev = sens_now  # S^n becomes the next step's S^{n−1} (BDF2 plans only)
            u_prev = u
            u = u_new
        else:
            _t0 = perf_counter() if timed else 0.0
            sol_u = solve_banded(
                (1, 1), ab, rhs, overwrite_ab=True, overwrite_b=True, check_finite=False
            )
            if timed:
                timing["value_s"] += perf_counter() - _t0
            u_prev = u
            u = np.concatenate(([1.0], sol_u, [0.0]))

        nu_prev = nu  # becomes the old-level nu for the next step's CN half
        phi_prev = phi
        i_out = want.get(n + 1)
        if i_out is not None:
            prices[i_out] = u
            if sensitivities:
                out_sens[i_out] = sens

    return AffinePDESolution(x_grid=x, expiries=exps, prices=prices, sens=out_sens)

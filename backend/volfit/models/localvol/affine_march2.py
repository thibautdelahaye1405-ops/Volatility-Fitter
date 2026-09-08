"""Numba vectorized-Thomas Dupire march for ANY time-stepping plan (LV operator arc, O2).

``affine_march`` compiles the implicit-Euler march only; Rannacher (Crank–
Nicolson) fell back to the LAPACK banded march, which is why the second-order
scheme measured 268 s against 29 s implicit on a SPY dailies surface
(2026-09-03). These kernels take the per-step plan (γ, α, β, ε) of
``time_schemes.build_plan`` and march the generic two-level step of the note's
eq. (generic_two_level_step) with its sensitivities, eq.
(generic_sensitivity_step):

    (I − γΔt A^{n+1}) U^{n+1} = α U^n − β U^{n−1} + εΔt A^n U^n + boundary,
    (I − γΔt A^{n+1}) S^{n+1} = α S^n − β S^{n−1} + εΔt A^n S^n
                                 + γΔt (∂A^{n+1}) U^{n+1} + εΔt (∂A^n) U^n.

Same structure as ``affine_march._march`` (no-pivot Thomas factored once per
step, the k live sensitivity columns as the contiguous inner loop, the source
fused into the forward sweep, the positivity clamp with dν/dθ = 0 on clamped
rows); the two-level terms (BDF2) are one extra axpy per row, the old-level
operator terms (Crank–Nicolson) one extra three-point stencil on S^n and one
extra source — both skipped by a per-step branch when their weight is zero,
so a BDF2 march costs an implicit march plus the axpy. Three sensitivity
buffers rotate (S^{n−1}, S^n, S^{n+1}) instead of copying.

The implicit kernels of ``affine_march`` are NOT replaced: their fastmath bit
patterns are the goldens' bits. ``solve_affine_dupire`` sends every plan that
is not pure implicit here (when numba is importable); output matches the
banded march to solver rounding (``tests/test_affine_march2``).
"""

from __future__ import annotations

import numpy as np

from volfit.models.localvol.affine_march import NUMBA_AVAILABLE, njit


@njit(cache=True, nogil=True, fastmath=True)
def _march_plan(
    phi3d, theta, a_m, a_p, a_0, dt, gamma, alpha, beta, eps, active_k, want_step, u0, n_exp
):
    """Value + theta-sensitivity march of the generic step; returns (prices, sens).

    ``phi3d`` is (n_steps, n_int, m) C-contiguous; ``gamma/alpha/beta/eps`` the
    per-step plan. Mirrors ``solve_affine_dupire``'s banded loop step for step.
    """
    n_steps = phi3d.shape[0]
    n_int = phi3d.shape[1]
    m = phi3d.shape[2]
    n_x = n_int + 2

    u = u0.copy()  # U^n (boundaries included)
    u_prev = u0.copy()  # U^{n-1}
    u_new = np.empty(n_x)
    s_prev = np.zeros((n_x, m))  # S^{n-1}
    s_cur = np.zeros((n_x, m))  # S^n
    s_new = np.zeros((n_x, m))  # S^{n+1}
    prices = np.zeros((n_exp, n_x))
    out_sens = np.zeros((n_exp, n_x, m))
    nu = np.empty(n_int)
    nu_prev = np.zeros(n_int)
    live = np.empty(n_int)
    live_prev = np.zeros(n_int)
    sub = np.empty(n_int)
    diag = np.empty(n_int)
    sup = np.empty(n_int)
    cp = np.empty(n_int)
    inv = np.empty(n_int)
    dpv = np.empty(n_int)
    au = np.empty(n_int)  # stencil @ U^{n+1}
    au_old = np.empty(n_int)  # stencil @ U^n
    dp = np.empty((n_int, m))

    for n in range(n_steps):
        dtn = dt[n]
        gd = gamma[n] * dtn  # implicit weight x dt
        al = alpha[n]
        be = beta[n]
        ed = eps[n] * dtn  # explicit (old-level) weight x dt; 0 except Crank–Nicolson
        has_old = ed != 0.0
        # nu = phi @ theta at the new level, floored at 0 (the left-wing clamp;
        # clamped rows zero their sensitivity source — see solve_affine_dupire).
        for i in range(n_int):
            s = 0.0
            row = phi3d[n, i]
            for j in range(m):
                s += row[j] * theta[j]
            if s < 0.0:
                nu[i] = 0.0
                live[i] = 0.0
            else:
                nu[i] = s
                live[i] = 1.0
        # tridiagonal (I − γ dt A^{n+1}) and its no-pivot Thomas factorisation
        for i in range(n_int):
            sub[i] = -gd * nu[i] * a_m[i]
            diag[i] = 1.0 - gd * nu[i] * a_0[i]
            sup[i] = -gd * nu[i] * a_p[i]
        inv[0] = 1.0 / diag[0]
        cp[0] = sup[0] * inv[0]
        for i in range(1, n_int):
            inv[i] = 1.0 / (diag[i] - sub[i] * cp[i - 1])
            cp[i] = sup[i] * inv[i]
        # old-level operator on U^n (boundaries included: u[0] = 1 carries the
        # left Dirichlet value at level n), only when the plan has ε > 0
        if has_old:
            for i in range(n_int):
                au_old[i] = a_m[i] * u[i] + a_0[i] * u[i + 1] + a_p[i] * u[i + 2]
        # value right-hand side: α U^n − β U^{n−1} + ε dt ν^n (A U^n) + boundary
        for i in range(n_int):
            r = al * u[i + 1] - be * u_prev[i + 1]
            if has_old:
                r += ed * nu_prev[i] * au_old[i]
            dpv[i] = r
        dpv[0] += gd * nu[0] * a_m[0]  # implicit U_0 = 1 boundary into row 0
        dpv[0] = dpv[0] * inv[0]
        for i in range(1, n_int):
            dpv[i] = (dpv[i] - sub[i] * dpv[i - 1]) * inv[i]
        u_new[0] = 1.0
        u_new[n_x - 1] = 0.0
        u_new[n_x - 2] = dpv[n_int - 1]
        for i in range(n_int - 2, -1, -1):
            u_new[i + 1] = dpv[i] - cp[i] * u_new[i + 2]

        # sensitivities: multi-RHS Thomas, columns as the contiguous inner loop;
        # the new-level source γ dt φ (A U^{n+1}) is fused into the forward sweep,
        # as are the two-level combination and the old-level terms.
        k = active_k[n]
        for i in range(n_int):
            au[i] = a_m[i] * u_new[i] + a_0[i] * u_new[i + 1] + a_p[i] * u_new[i + 2]
        for i in range(n_int):
            invi = inv[i]
            src = gd * au[i] * live[i]
            prow = phi3d[n, i]
            scur = s_cur[i + 1]
            sprev = s_prev[i + 1]
            drow = dp[i]
            if has_old:
                edn = ed * nu_prev[i]
                srco = ed * au_old[i] * live_prev[i]
                pold = phi3d[n - 1, i] if n > 0 else phi3d[n, i]
                slo = s_cur[i]
                shi = s_cur[i + 2]
                for col in range(k):
                    r = (
                        al * scur[col] - be * sprev[col]
                        + edn * (a_m[i] * slo[col] + a_0[i] * scur[col] + a_p[i] * shi[col])
                        + src * prow[col] + srco * pold[col]
                    )
                    drow[col] = r
            else:
                for col in range(k):
                    drow[col] = al * scur[col] - be * sprev[col] + src * prow[col]
            if i == 0:
                for col in range(k):
                    drow[col] = drow[col] * invi
            else:
                sbi = sub[i]
                dprev = dp[i - 1]
                for col in range(k):
                    drow[col] = (drow[col] - sbi * dprev[col]) * invi
        # back substitution into S^{n+1}
        last = s_new[n_int]
        dlast = dp[n_int - 1]
        for col in range(k):
            last[col] = dlast[col]
        for col in range(k, m):
            last[col] = 0.0
        for i in range(n_int - 2, -1, -1):
            cpi = cp[i]
            drow = dp[i]
            snext = s_new[i + 2]
            scur = s_new[i + 1]
            for col in range(k):
                scur[col] = drow[col] - cpi * snext[col]
            for col in range(k, m):
                scur[col] = 0.0

        # rotate the levels: (S^{n-1}, S^n, S^{n+1}) -> (S^n, S^{n+1}, free)
        tmp = s_prev
        s_prev = s_cur
        s_cur = s_new
        s_new = tmp
        for i in range(n_x):
            u_prev[i] = u[i]
            u[i] = u_new[i]
        for i in range(n_int):
            nu_prev[i] = nu[i]
            live_prev[i] = live[i]
        out = want_step[n]
        if out >= 0:
            for i in range(n_x):
                prices[out, i] = u[i]
            for i in range(n_x):
                srow = s_cur[i]
                orow = out_sens[out, i]
                for col in range(m):
                    orow[col] = srow[col]
    return prices, out_sens


@njit(cache=True, nogil=True, fastmath=True)
def _march_plan_sparse(
    vals3d, cols3d, theta, a_m, a_p, a_0, dt, gamma, alpha, beta, eps, active_k, want_step,
    u0, n_exp, m,
):
    """Sparse-basis twin of ``_march_plan`` (the over-budget phi store): the
    sources scatter over each row's <= nnz live columns."""
    n_steps = vals3d.shape[0]
    n_int = vals3d.shape[1]
    nnz = vals3d.shape[2]
    n_x = n_int + 2

    u = u0.copy()
    u_prev = u0.copy()
    u_new = np.empty(n_x)
    s_prev = np.zeros((n_x, m))
    s_cur = np.zeros((n_x, m))
    s_new = np.zeros((n_x, m))
    prices = np.zeros((n_exp, n_x))
    out_sens = np.zeros((n_exp, n_x, m))
    nu = np.empty(n_int)
    nu_prev = np.zeros(n_int)
    live = np.empty(n_int)
    live_prev = np.zeros(n_int)
    sub = np.empty(n_int)
    diag = np.empty(n_int)
    sup = np.empty(n_int)
    cp = np.empty(n_int)
    inv = np.empty(n_int)
    dpv = np.empty(n_int)
    au = np.empty(n_int)
    au_old = np.empty(n_int)
    dp = np.empty((n_int, m))

    for n in range(n_steps):
        dtn = dt[n]
        gd = gamma[n] * dtn
        al = alpha[n]
        be = beta[n]
        ed = eps[n] * dtn
        has_old = ed != 0.0
        for i in range(n_int):
            s = 0.0
            for j in range(nnz):
                s += vals3d[n, i, j] * theta[cols3d[n, i, j]]
            if s < 0.0:
                nu[i] = 0.0
                live[i] = 0.0
            else:
                nu[i] = s
                live[i] = 1.0
        for i in range(n_int):
            sub[i] = -gd * nu[i] * a_m[i]
            diag[i] = 1.0 - gd * nu[i] * a_0[i]
            sup[i] = -gd * nu[i] * a_p[i]
        inv[0] = 1.0 / diag[0]
        cp[0] = sup[0] * inv[0]
        for i in range(1, n_int):
            inv[i] = 1.0 / (diag[i] - sub[i] * cp[i - 1])
            cp[i] = sup[i] * inv[i]
        if has_old:
            for i in range(n_int):
                au_old[i] = a_m[i] * u[i] + a_0[i] * u[i + 1] + a_p[i] * u[i + 2]
        for i in range(n_int):
            r = al * u[i + 1] - be * u_prev[i + 1]
            if has_old:
                r += ed * nu_prev[i] * au_old[i]
            dpv[i] = r
        dpv[0] += gd * nu[0] * a_m[0]
        dpv[0] = dpv[0] * inv[0]
        for i in range(1, n_int):
            dpv[i] = (dpv[i] - sub[i] * dpv[i - 1]) * inv[i]
        u_new[0] = 1.0
        u_new[n_x - 1] = 0.0
        u_new[n_x - 2] = dpv[n_int - 1]
        for i in range(n_int - 2, -1, -1):
            u_new[i + 1] = dpv[i] - cp[i] * u_new[i + 2]

        k = active_k[n]
        for i in range(n_int):
            au[i] = a_m[i] * u_new[i] + a_0[i] * u_new[i + 1] + a_p[i] * u_new[i + 2]
        for i in range(n_int):
            invi = inv[i]
            src = gd * au[i] * live[i]
            scur = s_cur[i + 1]
            sprev = s_prev[i + 1]
            drow = dp[i]
            if has_old:
                edn = ed * nu_prev[i]
                slo = s_cur[i]
                shi = s_cur[i + 2]
                for col in range(k):
                    drow[col] = (
                        al * scur[col] - be * sprev[col]
                        + edn * (a_m[i] * slo[col] + a_0[i] * scur[col] + a_p[i] * shi[col])
                    )
            else:
                for col in range(k):
                    drow[col] = al * scur[col] - be * sprev[col]
            for j in range(nnz):  # new-level source over the live slots
                drow[cols3d[n, i, j]] += src * vals3d[n, i, j]
            if has_old and n > 0:  # old-level source over the previous level's slots
                srco = ed * au_old[i] * live_prev[i]
                for j in range(nnz):
                    drow[cols3d[n - 1, i, j]] += srco * vals3d[n - 1, i, j]
            if i == 0:
                for col in range(k):
                    drow[col] = drow[col] * invi
            else:
                sbi = sub[i]
                dprev = dp[i - 1]
                for col in range(k):
                    drow[col] = (drow[col] - sbi * dprev[col]) * invi
        last = s_new[n_int]
        dlast = dp[n_int - 1]
        for col in range(k):
            last[col] = dlast[col]
        for col in range(k, m):
            last[col] = 0.0
        for i in range(n_int - 2, -1, -1):
            cpi = cp[i]
            drow = dp[i]
            snext = s_new[i + 2]
            scur = s_new[i + 1]
            for col in range(k):
                scur[col] = drow[col] - cpi * snext[col]
            for col in range(k, m):
                scur[col] = 0.0

        tmp = s_prev
        s_prev = s_cur
        s_cur = s_new
        s_new = tmp
        for i in range(n_x):
            u_prev[i] = u[i]
            u[i] = u_new[i]
        for i in range(n_int):
            nu_prev[i] = nu[i]
            live_prev[i] = live[i]
        out = want_step[n]
        if out >= 0:
            for i in range(n_x):
                prices[out, i] = u[i]
            for i in range(n_x):
                srow = s_cur[i]
                orow = out_sens[out, i]
                for col in range(m):
                    orow[col] = srow[col]
    return prices, out_sens


def _c(a, dtype=np.float64):
    return np.ascontiguousarray(a, dtype=dtype)


def march_plan(phi3d, theta, a_m, a_p, a_0, dt, plan, active_k, want_step, u0, n_exp):
    """Python entry for the dense-basis kernel: coerce and run."""
    return _march_plan(
        _c(phi3d), _c(theta), _c(a_m), _c(a_p), _c(a_0), _c(dt),
        _c(plan.gamma), _c(plan.alpha), _c(plan.beta), _c(plan.eps),
        _c(active_k, np.int64), _c(want_step, np.int64), _c(u0), int(n_exp),
    )


def march_plan_sparse(
    vals3d, cols3d, theta, a_m, a_p, a_0, dt, plan, active_k, want_step, u0, n_exp, m
):
    """Python entry for the sparse-basis kernel (over-budget phi store)."""
    return _march_plan_sparse(
        _c(vals3d), _c(cols3d, np.int64), _c(theta), _c(a_m), _c(a_p), _c(a_0), _c(dt),
        _c(plan.gamma), _c(plan.alpha), _c(plan.beta), _c(plan.eps),
        _c(active_k, np.int64), _c(want_step, np.int64), _c(u0), int(n_exp), int(m),
    )


_WARMED = False


def warmup() -> None:
    """Trigger JIT compilation (cached to disk) off the fit's critical path."""
    global _WARMED
    if _WARMED or not NUMBA_AVAILABLE:
        return
    from volfit.models.localvol.time_schemes import build_plan

    plan = build_plan(np.array([0.0, 0.5, 1.0]), "bdf2")
    phi = np.zeros((2, 1, 1))
    phi[:, 0, 0] = 1.0
    args = (
        np.array([0.04]), np.array([1.0]), np.array([1.0]), np.array([-2.0]),
        np.array([0.5, 0.5]), plan, np.array([1, 1]), np.array([-1, 0]),
        np.array([1.0, 0.0, 0.0]), 1,
    )
    march_plan(phi, *args)
    march_plan_sparse(np.ones((2, 1, 1)), np.zeros((2, 1, 1), dtype=np.int64), *args, 1)
    _WARMED = True

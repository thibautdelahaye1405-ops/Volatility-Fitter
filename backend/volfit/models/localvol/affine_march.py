"""Numba vectorized-Thomas forward Dupire march (Stage 6′) — the per-eval hot path.

The calibration's dominant cost is the forward-sensitivity PDE march of
``solve_affine_dupire``: per time step a tridiagonal value solve plus a multi-RHS
sensitivity solve, repeated for every trial theta. Profiling shows ~74 % of the
march is the **multi-RHS sensitivity solve**, which scipy routes through LAPACK
``dgbsv`` (general band, partial pivoting + fill) — wasteful for our strictly
diagonally-dominant tridiagonal M-matrix (note App. B), which needs no pivoting.

This module replaces the whole march with one ``@njit(nogil=True, cache=True)``
kernel that beats LAPACK ~6× on the march by exploiting structure the general band
solver cannot:

  * **no-pivot Thomas** (factor-once: the same tridiagonal serves the value and
    every sensitivity column) — about a third of ``dgbsv``'s flops;
  * the **k right-hand-side columns are the CONTIGUOUS INNER loop** of the
    forward/back sweeps, so the sweeps SIMD-vectorise across columns (the sweeps
    are sequential only in the strike direction, fully parallel across columns);
  * the sensitivity **source is fused into the forward sweep** (no dense
    ``rhs_s`` temporary, no per-step ``scipy`` call, no per-step allocations);
  * the live-column prefix ``active_k`` (a vertex's column is structurally zero
    until the march reaches its hat support) bounds the inner loop.

Output is bit-comparable to the banded march (Thomas vs LAPACK rounding ≈ 1e-15;
``test_affine_march`` gates it). Scope: the value + theta-sensitivity march for the
common ``fit_left_a=False`` + implicit-Euler path that drives every calibration
without a var-swap quote; the free-left-slope and Rannacher paths keep the banded
march (``solve_affine_dupire`` dispatches and falls back automatically, including
when numba is unavailable).
"""

from __future__ import annotations

import numpy as np

try:  # numba is the accelerator; the banded path is the always-available fallback
    from numba import njit

    NUMBA_AVAILABLE = True
except Exception:  # pragma: no cover - only where numba fails to import
    NUMBA_AVAILABLE = False

    def njit(*args, **kwargs):  # type: ignore
        def deco(fn):
            return fn

        return deco if not (len(args) == 1 and callable(args[0])) else args[0]


@njit(cache=True, nogil=True, fastmath=True)
def _march(phi3d, theta, a_m, a_p, a_0, dt, active_k, want_step, u0, n_exp):
    """Value + theta-sensitivity implicit-Euler march; returns (prices, sens).

    ``phi3d`` is (n_steps, n_int, m) C-contiguous (the per-step hat basis at the new
    level); ``sens`` rows are (·, m) C-contiguous so the column sweeps are unit-stride.
    Mirrors ``solve_affine_dupire`` (fit_left_a=False, implicit) step for step.
    """
    n_steps = phi3d.shape[0]
    n_int = phi3d.shape[1]
    m = phi3d.shape[2]
    n_x = n_int + 2

    u = u0.copy()
    sens = np.zeros((n_x, m))
    prices = np.zeros((n_exp, n_x))
    out_sens = np.zeros((n_exp, n_x, m))
    nu = np.empty(n_int)
    sub = np.empty(n_int)
    diag = np.empty(n_int)
    sup = np.empty(n_int)
    cp = np.empty(n_int)
    inv = np.empty(n_int)
    dpv = np.empty(n_int)
    u_new = np.empty(n_x)
    au = np.empty(n_int)
    dp = np.empty((n_int, m))
    live = np.empty(n_int)  # 0.0 where nu was positivity-clamped (dnu/dtheta = 0)

    for n in range(n_steps):
        dtn = dt[n]
        # nu = phi @ theta  (dense; ~6% of the march, kept simple), floored at 0:
        # the left-wing linear continuation is "linear until zero, then flat" —
        # negative local variance is anti-diffusion and blows the march up
        # (see solve_affine_dupire). Clamped rows zero their sensitivity source.
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
        # tridiagonal (I - dt A^{n+1})
        for i in range(n_int):
            sub[i] = -dtn * nu[i] * a_m[i]
            diag[i] = 1.0 - dtn * nu[i] * a_0[i]
            sup[i] = -dtn * nu[i] * a_p[i]
        # no-pivot Thomas factorisation (shared by value + every sensitivity column)
        inv[0] = 1.0 / diag[0]
        cp[0] = sup[0] * inv[0]
        for i in range(1, n_int):
            inv[i] = 1.0 / (diag[i] - sub[i] * cp[i - 1])
            cp[i] = sup[i] * inv[i]
        # value solve: rhs_i = u_{i+1}, plus the U_0 = 1 boundary into row 0
        dpv[0] = (u[1] + dtn * nu[0] * a_m[0]) * inv[0]
        for i in range(1, n_int):
            dpv[i] = (u[i + 1] - sub[i] * dpv[i - 1]) * inv[i]
        u_new[0] = 1.0
        u_new[n_x - 1] = 0.0
        u_new[n_x - 2] = dpv[n_int - 1]
        for i in range(n_int - 2, -1, -1):
            u_new[i + 1] = dpv[i] - cp[i] * u_new[i + 2]

        # sensitivity multi-RHS Thomas, columns as the contiguous inner (SIMD) loop;
        # the source phi_l * (stencil @ U^{n+1}) is fused into the forward sweep.
        k = active_k[n]
        for i in range(n_int):
            au[i] = a_m[i] * u_new[i] + a_0[i] * u_new[i + 1] + a_p[i] * u_new[i + 2]
        invi = inv[0]
        au0 = dtn * au[0] * live[0]
        prow = phi3d[n, 0]
        srow = sens[1]
        drow = dp[0]
        for col in range(k):
            drow[col] = (srow[col] + au0 * prow[col]) * invi
        for i in range(1, n_int):
            invi = inv[i]
            sbi = sub[i]
            aui = dtn * au[i] * live[i]
            prow = phi3d[n, i]
            srow = sens[i + 1]
            dprev = dp[i - 1]
            drow = dp[i]
            for col in range(k):
                drow[col] = (srow[col] + aui * prow[col] - sbi * dprev[col]) * invi
        last = sens[n_int]
        dlast = dp[n_int - 1]
        for col in range(k):
            last[col] = dlast[col]
        for i in range(n_int - 2, -1, -1):
            cpi = cp[i]
            drow = dp[i]
            snext = sens[i + 2]
            scur = sens[i + 1]
            for col in range(k):
                scur[col] = drow[col] - cpi * snext[col]

        for i in range(n_x):
            u[i] = u_new[i]
        out = want_step[n]
        if out >= 0:
            for i in range(n_x):
                prices[out, i] = u_new[i]
            for i in range(n_x):
                srow = sens[i]
                orow = out_sens[out, i]
                for col in range(m):
                    orow[col] = srow[col]
    return prices, out_sens


@njit(cache=True, nogil=True, fastmath=True)
def _march_sparse(vals3d, cols3d, theta, a_m, a_p, a_0, dt, active_k, want_step, u0, n_exp, m):
    """Sparse-basis variant of ``_march`` for the over-budget store.

    ``vals3d``/``cols3d`` are the (n_steps, n_int, nnz) row-sparse slabs of
    ``affine_steps.build_sparse_phi`` (padding slots hold (0.0, col 0), which
    add exactly nothing). Same Thomas sweeps as ``_march``; the sensitivity
    source is applied as a per-row scatter over the <= nnz live columns instead
    of the dense fused term, so results match the dense kernel to rounding.
    """
    n_steps = vals3d.shape[0]
    n_int = vals3d.shape[1]
    nnz = vals3d.shape[2]
    n_x = n_int + 2

    u = u0.copy()
    sens = np.zeros((n_x, m))
    prices = np.zeros((n_exp, n_x))
    out_sens = np.zeros((n_exp, n_x, m))
    nu = np.empty(n_int)
    sub = np.empty(n_int)
    diag = np.empty(n_int)
    sup = np.empty(n_int)
    cp = np.empty(n_int)
    inv = np.empty(n_int)
    dpv = np.empty(n_int)
    u_new = np.empty(n_x)
    au = np.empty(n_int)
    dp = np.empty((n_int, m))
    live = np.empty(n_int)  # 0.0 where nu was positivity-clamped (dnu/dtheta = 0)

    for n in range(n_steps):
        dtn = dt[n]
        # nu = phi @ theta over the sparse slots only, floored at 0 (the
        # left-wing "linear until zero, then flat" clamp — see _march).
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
        # tridiagonal (I - dt A^{n+1})
        for i in range(n_int):
            sub[i] = -dtn * nu[i] * a_m[i]
            diag[i] = 1.0 - dtn * nu[i] * a_0[i]
            sup[i] = -dtn * nu[i] * a_p[i]
        # no-pivot Thomas factorisation (shared by value + every sensitivity column)
        inv[0] = 1.0 / diag[0]
        cp[0] = sup[0] * inv[0]
        for i in range(1, n_int):
            inv[i] = 1.0 / (diag[i] - sub[i] * cp[i - 1])
            cp[i] = sup[i] * inv[i]
        # value solve: rhs_i = u_{i+1}, plus the U_0 = 1 boundary into row 0
        dpv[0] = (u[1] + dtn * nu[0] * a_m[0]) * inv[0]
        for i in range(1, n_int):
            dpv[i] = (u[i + 1] - sub[i] * dpv[i - 1]) * inv[i]
        u_new[0] = 1.0
        u_new[n_x - 1] = 0.0
        u_new[n_x - 2] = dpv[n_int - 1]
        for i in range(n_int - 2, -1, -1):
            u_new[i + 1] = dpv[i] - cp[i] * u_new[i + 2]

        # sensitivity multi-RHS Thomas; the source dt * phi_l * (stencil @ U^{n+1})
        # enters as a scatter over each row's <= nnz live columns (all < active_k).
        k = active_k[n]
        for i in range(n_int):
            au[i] = a_m[i] * u_new[i] + a_0[i] * u_new[i + 1] + a_p[i] * u_new[i + 2]
        invi = inv[0]
        au0 = dtn * au[0] * live[0]
        srow = sens[1]
        drow = dp[0]
        for col in range(k):
            drow[col] = srow[col] * invi
        for j in range(nnz):
            drow[cols3d[n, 0, j]] += au0 * vals3d[n, 0, j] * invi
        for i in range(1, n_int):
            invi = inv[i]
            sbi = sub[i]
            aui = dtn * au[i] * live[i]
            srow = sens[i + 1]
            dprev = dp[i - 1]
            drow = dp[i]
            for col in range(k):
                drow[col] = (srow[col] - sbi * dprev[col]) * invi
            for j in range(nnz):
                drow[cols3d[n, i, j]] += aui * vals3d[n, i, j] * invi
        last = sens[n_int]
        dlast = dp[n_int - 1]
        for col in range(k):
            last[col] = dlast[col]
        for i in range(n_int - 2, -1, -1):
            cpi = cp[i]
            drow = dp[i]
            snext = sens[i + 2]
            scur = sens[i + 1]
            for col in range(k):
                scur[col] = drow[col] - cpi * snext[col]

        for i in range(n_x):
            u[i] = u_new[i]
        out = want_step[n]
        if out >= 0:
            for i in range(n_x):
                prices[out, i] = u_new[i]
            for i in range(n_x):
                srow = sens[i]
                orow = out_sens[out, i]
                for col in range(m):
                    orow[col] = srow[col]
    return prices, out_sens


def numba_available() -> bool:
    return NUMBA_AVAILABLE


_WARMED = False


def warmup() -> None:
    """Trigger JIT compilation (cached to disk) off the fit's critical path."""
    global _WARMED
    if _WARMED or not NUMBA_AVAILABLE:
        return
    phi = np.zeros((2, 1, 1))
    phi[:, 0, 0] = 1.0
    _march(
        phi, np.array([0.04]), np.array([1.0]), np.array([1.0]), np.array([-2.0]),
        np.array([0.5, 0.5]), np.array([1, 1]), np.array([-1, 0]),
        np.array([1.0, 0.0, 0.0]), 1,
    )
    _march_sparse(
        np.ones((2, 1, 1)), np.zeros((2, 1, 1), dtype=np.int64), np.array([0.04]),
        np.array([1.0]), np.array([1.0]), np.array([-2.0]),
        np.array([0.5, 0.5]), np.array([1, 1]), np.array([-1, 0]),
        np.array([1.0, 0.0, 0.0]), 1, 1,
    )
    _WARMED = True


def march_value_sens(phi3d, theta, a_m, a_p, a_0, dt, active_k, want_step, u0, n_exp):
    """Python entry: coerce to contiguous float64/int64 and run the kernel."""
    return _march(
        np.ascontiguousarray(phi3d, dtype=np.float64),
        np.ascontiguousarray(theta, dtype=np.float64),
        np.ascontiguousarray(a_m, dtype=np.float64),
        np.ascontiguousarray(a_p, dtype=np.float64),
        np.ascontiguousarray(a_0, dtype=np.float64),
        np.ascontiguousarray(dt, dtype=np.float64),
        np.ascontiguousarray(active_k, dtype=np.int64),
        np.ascontiguousarray(want_step, dtype=np.int64),
        np.ascontiguousarray(u0, dtype=np.float64),
        int(n_exp),
    )


def march_value_sens_sparse(
    vals3d, cols3d, theta, a_m, a_p, a_0, dt, active_k, want_step, u0, n_exp, m
):
    """Python entry for the sparse-basis kernel (over-budget phi store)."""
    return _march_sparse(
        np.ascontiguousarray(vals3d, dtype=np.float64),
        np.ascontiguousarray(cols3d, dtype=np.int64),
        np.ascontiguousarray(theta, dtype=np.float64),
        np.ascontiguousarray(a_m, dtype=np.float64),
        np.ascontiguousarray(a_p, dtype=np.float64),
        np.ascontiguousarray(a_0, dtype=np.float64),
        np.ascontiguousarray(dt, dtype=np.float64),
        np.ascontiguousarray(active_k, dtype=np.int64),
        np.ascontiguousarray(want_step, dtype=np.int64),
        np.ascontiguousarray(u0, dtype=np.float64),
        int(n_exp),
        int(m),
    )

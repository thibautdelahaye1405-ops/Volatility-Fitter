"""Stacked joint problem for one violation component (symmetric surface).

Lower layer of volfit.calib.symmetric: the frozen per-slice/interface types
and the block-bidiagonal stacked residual + Jacobian + trf solve. The screen,
component detection and repair orchestration live in volfit.calib.symmetric;
import the public names from there.

Row layout of the stacked problem: [slice 0 block, ..., slice m-1 block,
interface 0 rows, ...]; columns are the concatenated per-slice theta vectors.
Data rows touch one slice, interface rows two adjacent slices, so the
Jacobian is block-bidiagonal; a component is 2-5 slices ~ 20-60 parameters
and the dense trf solve is trivial next to the residual evaluations.

Import discipline: pool-worker importable — depends only on volfit.calib /
volfit.models / volfit.core (see volfit.calib.fit_task).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.calib.rms import max_quote_error
from scipy.optimize import least_squares

from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import (
    CalibrationResult,
    _residuals,
    prepare_residual_args,
)
from volfit.models.lqd.jacobian import (
    asset_share_rows,
    call_price_rows,
    residual_jacobian,
    slice_sensitivities,
)
from volfit.models.lqd.quadrature import build_slice

#: Tail-contract row weight, as a fraction of an average quote (a nudge on an
#: unquoted region, never a bulldozer — the tail-dense full-grid floor is
#: exactly what the confinement phase removed).
TAIL_ROW_FRAC = 0.25
#: Wing-slope ordering tolerance in log endpoint-scale units (log A_L/log A_R
#: are linear in theta; LQD's Lee slopes are monotone in the endpoint scales,
#: so A-ordering IS asymptotic-slope ordering). Generalized tails: with the
#: COMMON per-underlier exponents of the arc's ratified policy, the wing-law
#: coefficient (eq. rightsublinearwing) is monotone in the tail scale at
#: every alpha, so these same rows ARE the eq. tailscalecalendar lambda_+-/
#: monotonicity rows — no alpha-specific rows are needed; exact ties are
#: delegated to the full-line calendar certificate (Phase 0).
SLOPE_TOL = 1e-6


def _spec_params(theta: np.ndarray, fit_kwargs: dict) -> LQDParams:
    """theta -> LQDParams carrying the spec's fixed tail exponents."""
    return LQDParams(
        L=float(theta[0]), R=float(theta[1]), a=theta[2:].copy(),
        alpha_left=fit_kwargs.get("alpha_left", 0.0),
        alpha_right=fit_kwargs.get("alpha_right", 0.0),
    )


@dataclass(frozen=True)
class SliceSpec:
    """One expiry's standalone objective, frozen for the symmetric solve.

    ``fit_kwargs`` are the calibrate_slice keyword arguments for THIS slice
    (n_order, weights, reg, band, priors, ...) minus ``init`` and minus any
    calendar_* rows — the interface rows replace the one-sided floor.
    """

    t: float
    k: np.ndarray
    w: np.ndarray
    fit_kwargs: dict


@dataclass(frozen=True)
class Interface:
    """Frozen constraint geometry between two adjacent slices."""

    grid: np.ndarray  # constraint strikes (common support + taper margins)
    taper: np.ndarray
    inv_vega: np.ndarray  # vega normalizer at the grid (far slice, frozen)
    weight: float  # mean per-quote LSQ weight of the pair
    #: Tail contract (None when off): the two seam strikes [left, right] just
    #: beyond the union of the quoted spans, with their vega normalizers.
    seam_k: np.ndarray | None = None
    seam_inv_vega: np.ndarray | None = None


def endpoint_rows(order: int) -> tuple[np.ndarray, np.ndarray]:
    """(c_L, c_R) with log A_L = c_L . theta and log A_R = c_R . theta —
    LINEAR in theta = (L, R, a_2..a_N) (volfit.models.lqd.basis)."""
    n = np.arange(2, order + 1)
    c_l = np.concatenate(([1.0, 0.0], np.ones(n.size)))
    c_r = np.concatenate(([0.0, 1.0], (-1.0) ** n))
    return c_l, c_r


def _try_build(theta: np.ndarray, n_points: int, alphas: tuple[float, float]):
    try:
        return build_slice(
            LQDParams(
                L=float(theta[0]), R=float(theta[1]), a=theta[2:].copy(),
                alpha_left=alphas[0], alpha_right=alphas[1],
            ),
            n_points=n_points,
        )
    except ValueError:  # infeasible tail: the slice's own block pushes back
        return None


def _fd_block(theta: np.ndarray, args: tuple) -> np.ndarray:
    """2-point FD Jacobian of one slice's own residual block (used when the
    slice carries var-swap / prior terms the analytic Jacobian doesn't cover)."""
    f0 = _residuals(theta, *args)
    jac = np.empty((f0.size, theta.size))
    step = np.sqrt(np.finfo(float).eps)
    for j in range(theta.size):
        h = step * max(1.0, abs(theta[j]))
        tp = theta.copy()
        tp[j] += h
        jac[:, j] = (_residuals(tp, *args) - f0) / h
    return jac


def stacked_functions(
    specs: list[SliceSpec],
    thetas0: list[np.ndarray],
    ifaces: list[Interface | None],
    iface_weight: float,
    active_ranks: list[np.ndarray | None] | None = None,
    rank_weight: float = 1.0,
):
    """Build (fun, jac, split) for one component's stacked joint problem.

    Per-slice data blocks use the analytic single-slice Jacobian when the
    slice's configuration allows, per-slice FD otherwise; interface rows are
    always analytic via the dC/dtheta identity. Exposed separately from
    ``joint_refit`` so tests can check jac against finite differences.

    ``active_ranks`` (tails+calendar arc Phase 4 — the active-set exchange,
    volfit.calib.symmetric_exchange): per adjacent pair j, the active ranks
    z_r at which the FULL-LINE ledger order (book ch. 2,
    eq. globalledgerconstraint) is enforced as hard rows
    sqrt(rank_weight) * max(A_near(z_r) - A_far(z_r), 0) in LEDGER space —
    the exact object the calendar certificate compares — with the analytic
    ``asset_share_rows`` Jacobian. None / empty entries add nothing: the
    default row layout is byte-identical to the pre-exchange stack.
    """
    m = len(specs)
    ranks = [
        None
        if active_ranks is None
        or active_ranks[j] is None
        or np.asarray(active_ranks[j]).size == 0
        else np.asarray(active_ranks[j], dtype=float)
        for j in range(m - 1)
    ]
    rank_scale = float(np.sqrt(rank_weight))
    prepared = [
        prepare_residual_args(s.k, s.w, s.t, **s.fit_kwargs) for s in specs
    ]
    args = [p[0] for p in prepared]
    analytic = [p[1] for p in prepared]
    opt_n = [a[-1] for a in args]  # opt_n_points is the last prepared arg
    alphas = [a[-2] for a in args]  # (alpha_left, alpha_right), second-to-last
    n_rows = [int(_residuals(thetas0[i], *args[i]).size) for i in range(m)]
    p_len = [t.size for t in thetas0]
    row_off = np.concatenate(([0], np.cumsum(n_rows)))
    col_off = np.concatenate(([0], np.cumsum(p_len)))
    iface_scales = [
        None
        if f is None
        else np.sqrt(f.weight * iface_weight) * f.taper * f.inv_vega
        for f in ifaces
    ]
    # Tail-contract rows per interface (opt-in): 2 seam price rows + 2 linear
    # wing-slope rows, weighted as a fraction of an average quote.
    seam_scales = [
        None
        if (f is None or f.seam_k is None)
        else np.sqrt(f.weight * iface_weight * TAIL_ROW_FRAC) * f.seam_inv_vega
        for f in ifaces
    ]
    slope_scales = [
        None
        if (f is None or f.seam_k is None)
        else float(np.sqrt(f.weight * iface_weight * TAIL_ROW_FRAC))
        for f in ifaces
    ]
    endpoint_c = [endpoint_rows(p - 1) for p in p_len]  # theta size = order + 1

    def _iface_nrows(f: Interface | None) -> int:
        return 0 if f is None else f.grid.size + (0 if f.seam_k is None else 4)

    total_rows = (
        int(row_off[-1])
        + sum(_iface_nrows(f) for f in ifaces)
        + sum(r.size for r in ranks if r is not None)
    )
    total_cols = int(col_off[-1])

    def _slope_gaps(th_n: np.ndarray, th_f: np.ndarray, j: int) -> np.ndarray:
        """(log A_L, log A_R) ordering gaps between local slices j and j+1."""
        (cl_n, cr_n), (cl_f, cr_f) = endpoint_c[j], endpoint_c[j + 1]
        return np.array(
            [cl_n @ th_n - cl_f @ th_f - SLOPE_TOL,
             cr_n @ th_n - cr_f @ th_f - SLOPE_TOL]
        )

    def split(x: np.ndarray) -> list[np.ndarray]:
        return [x[col_off[i]: col_off[i + 1]] for i in range(m)]

    def fun(x: np.ndarray) -> np.ndarray:
        thetas = split(x)
        parts = [_residuals(thetas[i], *args[i]) for i in range(m)]
        slices = [_try_build(thetas[i], opt_n[i], alphas[i]) for i in range(m)]
        for j, iface in enumerate(ifaces):
            s_n, s_f = slices[j], slices[j + 1]
            if iface is not None:
                if s_n is None or s_f is None:
                    parts.append(np.zeros(iface.grid.size))
                else:
                    gap = np.asarray(s_n.call_price(iface.grid)) - np.asarray(
                        s_f.call_price(iface.grid)
                    )
                    parts.append(iface_scales[j] * np.maximum(gap, 0.0))
                if iface.seam_k is not None:
                    if s_n is None or s_f is None:
                        parts.append(np.zeros(2))
                    else:
                        sgap = np.asarray(s_n.call_price(iface.seam_k)) - np.asarray(
                            s_f.call_price(iface.seam_k)
                        )
                        parts.append(seam_scales[j] * np.maximum(sgap, 0.0))
                    # Slope rows are linear in theta — always computable.
                    parts.append(
                        slope_scales[j]
                        * np.maximum(_slope_gaps(thetas[j], thetas[j + 1], j), 0.0)
                    )
            # Per-rank ledger rows (the exchange's active set): hard hinge on
            # the ledger gap at each active rank, eq. globalledgerconstraint.
            if ranks[j] is not None:
                if s_n is None or s_f is None:
                    parts.append(np.zeros(ranks[j].size))
                else:
                    lgap = np.asarray(s_n.asset_share_at(ranks[j])) - np.asarray(
                        s_f.asset_share_at(ranks[j])
                    )
                    parts.append(rank_scale * np.maximum(lgap, 0.0))
        return np.concatenate(parts)

    def jac(x: np.ndarray) -> np.ndarray:
        thetas = split(x)
        out = np.zeros((total_rows, total_cols))
        sens: list[tuple | None] = []
        for i in range(m):
            block = (
                residual_jacobian(thetas[i], *args[i])
                if analytic[i]
                else _fd_block(thetas[i], args[i])
            )
            out[row_off[i]: row_off[i + 1], col_off[i]: col_off[i + 1]] = block
            try:
                sens.append(slice_sensitivities(
                    LQDParams(
                        L=float(thetas[i][0]), R=float(thetas[i][1]),
                        a=thetas[i][2:].copy(),
                        alpha_left=alphas[i][0], alpha_right=alphas[i][1],
                    ),
                    opt_n[i],
                ))
            except ValueError:
                sens.append(None)
        r = int(row_off[-1])
        for j, iface in enumerate(ifaces):
            ok = sens[j] is not None and sens[j + 1] is not None
            if iface is not None:
                n = iface.grid.size
                if ok:
                    c_n, d_n = call_price_rows(*sens[j], iface.grid)
                    c_f, d_f = call_price_rows(*sens[j + 1], iface.grid)
                    act = (iface_scales[j] * ((c_n - c_f) > 0.0))[:, None]
                    out[r: r + n, col_off[j]: col_off[j + 1]] = act * d_n
                    out[r: r + n, col_off[j + 1]: col_off[j + 2]] = -act * d_f
                r += n
                if iface.seam_k is not None:
                    if ok:
                        cs_n, ds_n = call_price_rows(*sens[j], iface.seam_k)
                        cs_f, ds_f = call_price_rows(*sens[j + 1], iface.seam_k)
                        act = (seam_scales[j] * ((cs_n - cs_f) > 0.0))[:, None]
                        out[r: r + 2, col_off[j]: col_off[j + 1]] = act * ds_n
                        out[r: r + 2, col_off[j + 1]: col_off[j + 2]] = -act * ds_f
                    r += 2
                    (cl_n, cr_n), (cl_f, cr_f) = endpoint_c[j], endpoint_c[j + 1]
                    s_act = slope_scales[j] * (
                        _slope_gaps(thetas[j], thetas[j + 1], j) > 0.0
                    )
                    for row, (v_n, v_f) in enumerate(((cl_n, cl_f), (cr_n, cr_f))):
                        out[r + row, col_off[j]: col_off[j + 1]] = s_act[row] * v_n
                        out[r + row, col_off[j + 1]: col_off[j + 2]] = -s_act[row] * v_f
                    r += 2
            # Per-rank ledger rows: +dA_near into the near block, -dA_far into
            # the far block, masked by the active hinge (asset_share_rows).
            if ranks[j] is not None:
                nr = ranks[j].size
                if ok:
                    a_n, da_n = asset_share_rows(*sens[j], ranks[j])
                    a_f, da_f = asset_share_rows(*sens[j + 1], ranks[j])
                    act = (rank_scale * ((a_n - a_f) > 0.0))[:, None]
                    out[r: r + nr, col_off[j]: col_off[j + 1]] = act * da_n
                    out[r: r + nr, col_off[j + 1]: col_off[j + 2]] = -act * da_f
                r += nr
        return out

    return fun, jac, split


def joint_refit(
    specs: list[SliceSpec],
    thetas0: list[np.ndarray],
    ifaces: list[Interface | None],
    iface_weight: float,
    active_ranks: list[np.ndarray | None] | None = None,
    rank_weight: float = 1.0,
) -> tuple[list[np.ndarray], bool]:
    """Solve one component's symmetric joint problem.

    ``specs``/``thetas0`` are the component's slices (warm starts = the
    independent fits); ``ifaces[j]`` couples local slices j and j+1. Returns
    the solved per-slice parameter vectors and the trf success flag.
    ``active_ranks``/``rank_weight`` add the exchange's per-rank ledger rows
    (see ``stacked_functions``); the defaults add nothing.
    """
    fun, jac, split = stacked_functions(
        specs, thetas0, ifaces, iface_weight,
        active_ranks=active_ranks, rank_weight=rank_weight,
    )
    result = least_squares(
        fun,
        np.concatenate(thetas0),
        jac=jac,
        method="trf",
        xtol=1e-10,
        ftol=1e-10,
        gtol=1e-10,
        max_nfev=2000,
    )
    return split(result.x), bool(result.success)


def solver_diag_from_theta(theta: np.ndarray, spec: SliceSpec) -> dict:
    """Solution-point diagnostics for a jointly repaired slice — the same
    side-channel calibrate_slice records (Jacobian / residual / theta / row
    counts) so fit-uncertainty bands and the observation filter keep working
    on re-committed slices. The rows are the slice's OWN objective (no
    interface rows): information comes from the data, as everywhere else."""
    args, analytic = prepare_residual_args(spec.k, spec.w, spec.t, **spec.fit_kwargs)
    theta = np.asarray(theta, dtype=float)
    res = _residuals(theta, *args)
    jac = residual_jacobian(theta, *args) if analytic else _fd_block(theta, args)
    band = spec.fit_kwargs.get("band")
    n_fit = int(spec.k.size if band is None else 2 * spec.k.size)
    return dict(
        jac=np.asarray(jac, dtype=float),
        residual=np.asarray(res, dtype=float),
        theta=theta.copy(),
        n_fit_rows=n_fit,
        n_quotes=int(spec.k.size),
    )


def result_from_theta(theta: np.ndarray, spec: SliceSpec) -> CalibrationResult:
    """Package a jointly solved slice as a standard CalibrationResult (full
    quadrature grid + the same max-IV-error diagnostic calibrate_slice reports)."""
    params = _spec_params(np.asarray(theta, dtype=float), spec.fit_kwargs)
    slice_ = build_slice(params)
    sigma = np.sqrt(np.asarray(spec.w, dtype=float) / spec.t)
    iv_model = np.sqrt(slice_.implied_w(spec.k) / spec.t)
    args, _ = prepare_residual_args(spec.k, spec.w, spec.t, **spec.fit_kwargs)
    res = _residuals(np.asarray(theta, dtype=float), *args)
    return CalibrationResult(
        params=params,
        slice=slice_,
        cost=float(0.5 * np.dot(res, res)),
        n_evaluations=0,
        success=True,
        # vs the fit target (the slice's own band when it was a band fit)
        max_iv_error=max_quote_error(iv_model, sigma, spec.fit_kwargs.get("band")),
    )

"""Symmetric surface calibration: screen, components, joint Gauss-Newton.

The sequential surface loop (volfit.calib.surface) is traversal-order biased:
the first slice is immutable and every later slice absorbs its errors. The
symmetric redesign inverts the pipeline:

1. Fit every expiry INDEPENDENTLY (parallelizable — no cross-expiry data
   dependency; the caller may still seed slice i from slice i-1, which moves
   the trajectory but not the optimum).
2. SCREEN each adjacent interface for an identified calendar violation:
   normalized-call ordering C_near(k) <= C_far(k) on the common quote
   support, vega-normalized so the number reads as a vol gap.
3. Repair only the VIOLATION-CONNECTED COMPONENTS — contiguous runs of
   violated interfaces (the calendar coupling is a chain, so components are
   intervals). Slices outside a component are never touched: a clean ladder
   is exactly its independent fits.
4. Inside a component, solve the SYMMETRIC joint problem: the stacked
   per-slice objectives (the exact standalone residual blocks, via
   lqd.calibrate.prepare_residual_args) plus tapered interface hinge rows on
   the common support. The Jacobian is block-bidiagonal (data rows touch one
   slice, interface rows two adjacent), assembled analytically from
   lqd.jacobian; a component is 2-5 slices ~ 20-60 parameters, so the dense
   trf solve is trivial. Because each slice's rows keep their own quote
   weights, corrections are allocated by information automatically: a liquid
   slice with a large data Hessian barely moves, an unsupported acute tail
   absorbs the correction.
5. If an interface stays violated at convergence, escalate the interface
   weight (continuation) a few times; whatever remains after that is
   IRREDUCIBLE SLACK — genuinely inconsistent inputs — reported per
   interface, never silently flattened into the rest of the ladder.

Import discipline: pool-worker importable — depends only on volfit.calib /
volfit.models / volfit.core (see volfit.calib.fit_task).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.calendar import common_support, tapered_support_grid
from volfit.core.black import black_vega_sigma
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import (
    CalibrationResult,
    _residuals,
    prepare_residual_args,
)
from volfit.models.lqd.jacobian import (
    call_price_rows,
    residual_jacobian,
    slice_sensitivities,
)
from volfit.models.lqd.quadrature import build_slice

#: Identified-violation screen tolerance, in (vega-normalized) vol units:
#: 0.5 vol bp — below any tradable edge, above quadrature noise.
SCREEN_TOL_VOL = 5e-5

#: Constraint nodes per interface (common support + taper margins).
IFACE_N = 33

#: Base interface-row weight relative to an average quote row, and the
#: continuation schedule when an interface stays violated at convergence.
IFACE_BASE_WEIGHT = 1.0
ESCALATION_FACTOR = 10.0
MAX_ESCALATIONS = 3

#: Re-screen passes after component refits (component growth is monotone and
#: components are intervals of the chain, so this bound is generous).
MAX_GROWTH_PASSES = 4

_VEGA_FLOOR = 1e-4  # mirror of lqd.calibrate._VEGA_FLOOR


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


@dataclass(frozen=True)
class SurfaceRepair:
    """Outcome of the screen + component repair over one expiry ladder."""

    thetas: list[np.ndarray]  # final parameter vectors, all slices
    refit: list[bool]  # slices the joint solve touched
    violations_before: list[float]  # per interface, vol units (0.0 = clean)
    violations_after: list[float]
    components: list[tuple[int, int]]  # inclusive slice-index ranges solved
    escalations: int
    success: bool  # every component solve converged

    @property
    def max_slack(self) -> float:
        """Worst irreducible identified violation left after repair."""
        return max(self.violations_after, default=0.0)


def build_interface(near: SliceSpec, far: SliceSpec) -> Interface | None:
    """Constraint geometry for one adjacent pair; None without common support."""
    window = common_support(near.k, far.k)
    if window is None:
        return None
    grid, taper = tapered_support_grid(window, IFACE_N)
    if grid.size == 0:
        return None
    w_far = np.interp(grid, far.k, far.w)
    sigma = np.sqrt(np.maximum(w_far, 1e-12) / far.t)
    inv_vega = 1.0 / (black_vega_sigma(grid, sigma, far.t) + _VEGA_FLOOR)
    mean_w = 0.5 * (_mean_weight(near) + _mean_weight(far))
    return Interface(grid=grid, taper=taper, inv_vega=inv_vega, weight=mean_w)


def _mean_weight(spec: SliceSpec) -> float:
    weights = spec.fit_kwargs.get("weights")
    return 1.0 if weights is None else float(np.mean(weights))


def interface_violation(slice_near, slice_far, iface: Interface | None) -> float:
    """Identified violation in vol units: max taper-weighted, vega-normalized
    call-ordering gap on the interface grid (<= 0 means clean; returns 0.0)."""
    if iface is None:
        return 0.0
    gap = np.asarray(slice_near.call_price(iface.grid)) - np.asarray(
        slice_far.call_price(iface.grid)
    )
    return float(max(np.max(iface.taper * iface.inv_vega * gap), 0.0))


def _components(active: list[bool]) -> list[tuple[int, int]]:
    """Maximal runs of active interfaces -> inclusive slice-index ranges."""
    comps: list[tuple[int, int]] = []
    j = 0
    while j < len(active):
        if active[j]:
            j0 = j
            while j + 1 < len(active) and active[j + 1]:
                j += 1
            comps.append((j0, j + 1))  # interfaces j0..j -> slices j0..j+1
        j += 1
    return comps


def _try_build(theta: np.ndarray, n_points: int):
    try:
        return build_slice(LQDParams.from_vector(theta), n_points=n_points)
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
):
    """Build (fun, jac, split) for one component's stacked joint problem.

    Row layout: [slice 0 block, ..., slice m-1 block, iface 0 rows, ...];
    columns are the concatenated per-slice theta vectors. The Jacobian is
    assembled block-bidiagonally: per-slice data blocks (analytic when the
    slice's configuration allows, per-slice FD otherwise) plus the analytic
    interface rows via the dC/dtheta identity. Exposed separately from
    ``joint_refit`` so tests can check jac against finite differences.
    """
    m = len(specs)
    prepared = [
        prepare_residual_args(s.k, s.w, s.t, **s.fit_kwargs) for s in specs
    ]
    args = [p[0] for p in prepared]
    analytic = [p[1] for p in prepared]
    opt_n = [a[-1] for a in args]  # opt_n_points is the last prepared arg
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
    total_rows = int(row_off[-1]) + sum(
        0 if f is None else f.grid.size for f in ifaces
    )
    total_cols = int(col_off[-1])

    def split(x: np.ndarray) -> list[np.ndarray]:
        return [x[col_off[i]: col_off[i + 1]] for i in range(m)]

    def fun(x: np.ndarray) -> np.ndarray:
        thetas = split(x)
        parts = [_residuals(thetas[i], *args[i]) for i in range(m)]
        slices = [_try_build(thetas[i], opt_n[i]) for i in range(m)]
        for j, iface in enumerate(ifaces):
            if iface is None:
                continue
            s_n, s_f = slices[j], slices[j + 1]
            if s_n is None or s_f is None:
                parts.append(np.zeros(iface.grid.size))
                continue
            gap = np.asarray(s_n.call_price(iface.grid)) - np.asarray(
                s_f.call_price(iface.grid)
            )
            parts.append(iface_scales[j] * np.maximum(gap, 0.0))
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
                sens.append(slice_sensitivities(LQDParams.from_vector(thetas[i]), opt_n[i]))
            except ValueError:
                sens.append(None)
        r = int(row_off[-1])
        for j, iface in enumerate(ifaces):
            if iface is None:
                continue
            n = iface.grid.size
            if sens[j] is not None and sens[j + 1] is not None:
                c_n, d_n = call_price_rows(*sens[j], iface.grid)
                c_f, d_f = call_price_rows(*sens[j + 1], iface.grid)
                act = (iface_scales[j] * ((c_n - c_f) > 0.0))[:, None]
                out[r: r + n, col_off[j]: col_off[j + 1]] = act * d_n
                out[r: r + n, col_off[j + 1]: col_off[j + 2]] = -act * d_f
            r += n
        return out

    return fun, jac, split


def joint_refit(
    specs: list[SliceSpec],
    thetas0: list[np.ndarray],
    ifaces: list[Interface | None],
    iface_weight: float,
) -> tuple[list[np.ndarray], bool]:
    """Solve one component's symmetric joint problem.

    ``specs``/``thetas0`` are the component's slices (warm starts = the
    independent fits); ``ifaces[j]`` couples local slices j and j+1. Returns
    the solved per-slice parameter vectors and the trf success flag.
    """
    fun, jac, split = stacked_functions(specs, thetas0, ifaces, iface_weight)
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


def repair_surface(
    specs: list[SliceSpec],
    thetas0: list[np.ndarray],
    screen_tol: float = SCREEN_TOL_VOL,
) -> SurfaceRepair:
    """Screen the ladder and jointly repair its violation components.

    ``thetas0`` are the independent fits (ascending expiry). The fast path —
    no identified violation anywhere — returns them untouched.
    """
    n = len(specs)
    ifaces = [build_interface(specs[i], specs[i + 1]) for i in range(n - 1)]
    thetas = [np.asarray(t, dtype=float).copy() for t in thetas0]
    # Independent fits are always tail-feasible (calibrate_slice enforces it),
    # so the full-grid screening slices build unconditionally.
    slices = [build_slice(LQDParams.from_vector(t)) for t in thetas]

    def screen() -> list[float]:
        return [
            interface_violation(slices[j], slices[j + 1], ifaces[j])
            for j in range(n - 1)
        ]

    before = screen()
    active = [v > screen_tol for v in before]
    refit = [False] * n
    solved: list[tuple[int, int]] = []
    escalations = 0
    success = True

    if any(active):
        for _pass in range(MAX_GROWTH_PASSES):
            for lo, hi in _components(active):
                weight = IFACE_BASE_WEIGHT
                comp_specs = specs[lo: hi + 1]
                comp_thetas = [thetas[i] for i in range(lo, hi + 1)]
                comp_ifaces = ifaces[lo:hi]
                for attempt in range(MAX_ESCALATIONS + 1):
                    comp_thetas, ok = joint_refit(
                        comp_specs, comp_thetas, comp_ifaces, weight
                    )
                    success = success and ok
                    comp_slices = [
                        build_slice(LQDParams.from_vector(t)) for t in comp_thetas
                    ]
                    worst = max(
                        (
                            interface_violation(
                                comp_slices[j], comp_slices[j + 1], comp_ifaces[j]
                            )
                            for j in range(len(comp_ifaces))
                        ),
                        default=0.0,
                    )
                    if worst <= screen_tol or attempt == MAX_ESCALATIONS:
                        break
                    weight *= ESCALATION_FACTOR
                    escalations += 1
                for i, idx in enumerate(range(lo, hi + 1)):
                    thetas[idx] = comp_thetas[i]
                    slices[idx] = comp_slices[i]
                    refit[idx] = True
                solved.append((lo, hi))
            after = screen()
            grown = [
                v > screen_tol and not was for v, was in zip(after, active)
            ]
            if not any(grown):
                break
            # A repaired component pushed a boundary interface into violation:
            # grow the active set (monotone — bounded by the ladder length).
            active = [a or g for a, g in zip(active, grown)]

    return SurfaceRepair(
        thetas=thetas,
        refit=refit,
        violations_before=before,
        violations_after=screen(),
        components=solved,
        escalations=escalations,
        success=success,
    )


def calibrate_surface_symmetric(
    quotes,
    n_order: int = 6,
    reg_lambda: float = 0.0,
    reg_power: float = 1.0,
    screen_tol: float = SCREEN_TOL_VOL,
):
    """Pure-calib symmetric surface pipeline (the calibrate_surface analogue).

    Independent fits (warm-seeded from the previous expiry — trajectory only,
    the optimum is unchanged) -> screen -> component-wise joint repair.
    Returns ``(SurfaceFit, SurfaceRepair)``; a clean ladder's SurfaceFit holds
    exactly the independent fits.
    """
    from volfit.calib.calendar import calendar_violation_windowed
    from volfit.calib.surface import SurfaceFit
    from volfit.models.lqd.calibrate import calibrate_slice

    ordered = sorted(quotes, key=lambda q: q.t)
    results = []
    prev = None
    for q in ordered:
        r = calibrate_slice(
            q.k, q.w, t=q.t, n_order=n_order, weights=q.weights,
            reg_lambda=reg_lambda, reg_power=reg_power,
            init=prev.params if prev is not None else None,
        )
        results.append(r)
        prev = r
    specs = [
        SliceSpec(
            t=q.t,
            k=np.asarray(q.k, dtype=float),
            w=np.asarray(q.w, dtype=float),
            fit_kwargs=dict(
                n_order=n_order, weights=q.weights,
                reg_lambda=reg_lambda, reg_power=reg_power,
            ),
        )
        for q in ordered
    ]
    repair = repair_surface(specs, [r.params.to_vector() for r in results], screen_tol)
    final = [
        result_from_theta(theta, spec) if touched else res
        for theta, spec, touched, res in zip(
            repair.thetas, specs, repair.refit, results
        )
    ]
    residuals = [0.0] + [
        calendar_violation_windowed(
            final[i].slice,
            final[i + 1].slice,
            common_support(specs[i].k, specs[i + 1].k),
        )
        for i in range(len(final) - 1)
    ]
    fit = SurfaceFit(
        expiries=[q.t for q in ordered],
        results=final,
        calendar_residuals=residuals,
    )
    return fit, repair


def result_from_theta(theta: np.ndarray, spec: SliceSpec) -> CalibrationResult:
    """Package a jointly solved slice as a standard CalibrationResult (full
    quadrature grid + the same max-IV-error diagnostic calibrate_slice reports)."""
    params = LQDParams.from_vector(theta)
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
        max_iv_error=float(np.nanmax(np.abs(iv_model - sigma))),
    )

"""Symmetric surface calibration: screen, components, joint Gauss-Newton.

The sequential surface loop (volfit.calib.surface) is traversal-order biased:
the first slice is immutable and every later slice absorbs its errors. The
symmetric redesign inverts the pipeline:

1. Fit every expiry INDEPENDENTLY (parallelizable — no cross-expiry data
   dependency; the caller may still seed slice i from slice i-1, which moves
   the trajectory but not the optimum).
2. SCREEN each adjacent interface for an identified calendar violation:
   normalized-call ordering C_near(k) <= C_far(k) on the common quote
   support, vega-normalized so the number reads as a vol gap. The opt-in
   TAIL CONTRACT (the extrapolation-guard toggle) adds two low-dimensional
   checks per interface: price ordering at a seam strike just beyond the
   union of the quoted spans, and wing-slope ordering via the linear
   log-endpoint-scale rows (Lee slopes are monotone in A_L/A_R).
3. Repair only the VIOLATION-CONNECTED COMPONENTS — contiguous runs of
   violated interfaces (the calendar coupling is a chain, so components are
   intervals). Slices outside a component are never touched: a clean ladder
   is exactly its independent fits.
4. Inside a component, solve the SYMMETRIC joint problem (the stacked
   machinery in volfit.calib.symmetric_stack): the exact standalone per-slice
   residual blocks plus tapered interface hinge rows on the common support
   (+ the tail rows when armed). Because each slice's rows keep their own
   quote weights, corrections are allocated by information automatically: a
   liquid slice with a large data Hessian barely moves, an unsupported acute
   tail absorbs the correction. The joint solve performs the global
   reconciliation a separate isotonic (PAVA) projection would only
   approximate, so no projection stage is needed.
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

from volfit.calib.calendar import common_support, tapered_support_grid
from volfit.calib.symmetric_stack import (  # noqa: F401 — public re-exports
    SLOPE_TOL,
    TAIL_ROW_FRAC,
    Interface,
    SliceSpec,
    endpoint_rows,
    joint_refit,
    result_from_theta,
    solver_diag_from_theta,
    stacked_functions,
)
from volfit.core.black import black_vega_sigma
from volfit.models.lqd.basis import LQDParams
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

#: Tail contract: the seam strike per side sits this far beyond the UNION of
#: the pair's quoted spans — the edge of the economically relevant wing.
SEAM_PAD = 0.10

_VEGA_FLOOR = 1e-4  # mirror of lqd.calibrate._VEGA_FLOOR


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


def build_interface(
    near: SliceSpec, far: SliceSpec, tail_contract: bool = False
) -> Interface | None:
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
    seam_k = seam_iv = None
    if tail_contract:
        seam_k = np.array(
            [
                min(float(near.k.min()), float(far.k.min())) - SEAM_PAD,
                max(float(near.k.max()), float(far.k.max())) + SEAM_PAD,
            ]
        )
        # Vega normalizer from the far quotes' EDGE vol (np.interp clamps):
        # deep-OTM vega decays, so the normalized price gap reads ~ a vol gap;
        # the shared _VEGA_FLOOR bounds it.
        w_seam = np.interp(seam_k, far.k, far.w)
        sig_seam = np.sqrt(np.maximum(w_seam, 1e-12) / far.t)
        seam_iv = 1.0 / (black_vega_sigma(seam_k, sig_seam, far.t) + _VEGA_FLOOR)
    return Interface(
        grid=grid, taper=taper, inv_vega=inv_vega, weight=mean_w,
        seam_k=seam_k, seam_inv_vega=seam_iv,
    )


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


def tail_violation(slice_near, slice_far, iface: Interface | None) -> float:
    """Worst tail-contract violation for one pair, in comparable (vol-ish)
    units: the vega-normalized seam price-ordering gap and the wing-slope
    (log endpoint-scale) ordering gap. 0.0 when the contract is off/absent.

    Slope order alone is insufficient (equal slopes can still cross in the
    finite wing) and the seam alone is insufficient (rays can re-cross beyond
    it) — the pair together orders the economically relevant wing. LQD's Lee
    slopes are monotone in the endpoint scales A_L/A_R, and log A is linear
    in theta, so the slope check is exact and cheap.
    """
    if iface is None or iface.seam_k is None:
        return 0.0
    gap = np.asarray(slice_near.call_price(iface.seam_k)) - np.asarray(
        slice_far.call_price(iface.seam_k)
    )
    seam = float(np.max(iface.seam_inv_vega * gap))
    c_l, c_r = endpoint_rows(slice_near.params.order)
    th_n = slice_near.params.to_vector()
    th_f = slice_far.params.to_vector()
    slope = max(
        float(c_l @ th_n - c_l @ th_f), float(c_r @ th_n - c_r @ th_f)
    ) - SLOPE_TOL
    return float(max(seam, slope, 0.0))


def _pair_violation(slice_near, slice_far, iface: Interface | None) -> float:
    """Combined screen measure: identified in-support + (armed) tail contract."""
    return max(
        interface_violation(slice_near, slice_far, iface),
        tail_violation(slice_near, slice_far, iface),
    )


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


def repair_surface(
    specs: list[SliceSpec],
    thetas0: list[np.ndarray],
    screen_tol: float = SCREEN_TOL_VOL,
    tail_contract: bool = False,
) -> SurfaceRepair:
    """Screen the ladder and jointly repair its violation components.

    ``thetas0`` are the independent fits (ascending expiry). The fast path —
    no identified violation anywhere — returns them untouched.
    ``tail_contract`` (the extrapolation-guard toggle) adds the seam +
    wing-slope ordering rows per interface and includes their violations in
    the screen; the identified in-support constraint is always on.
    """
    n = len(specs)
    ifaces = [
        build_interface(specs[i], specs[i + 1], tail_contract=tail_contract)
        for i in range(n - 1)
    ]
    thetas = [np.asarray(t, dtype=float).copy() for t in thetas0]
    # Independent fits are always tail-feasible (calibrate_slice enforces it),
    # so the full-grid screening slices build unconditionally.
    slices = [build_slice(LQDParams.from_vector(t)) for t in thetas]

    def screen() -> list[float]:
        return [
            _pair_violation(slices[j], slices[j + 1], ifaces[j])
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
                            _pair_violation(
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
    tail_contract: bool = False,
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
    repair = repair_surface(
        specs, [r.params.to_vector() for r in results], screen_tol, tail_contract
    )
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

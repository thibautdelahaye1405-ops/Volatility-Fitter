"""Symmetric surface pipeline (service layer) — surfaceSolver = "symmetric".

Phase A: fit every expiry INDEPENDENTLY — the LQD backbone without calendar
rows (still warm-seeded from the previous slice, which moves the trajectory
but not the optimum) AND the display overlay without a floor (mirroring the
independent-first principle at the display layer) — and commit each fit as
it lands, same progress granularity and UI behaviour as the sequential path.

Phase B: screen the fitted ladder for IDENTIFIED calendar violations
(normalized-call order on the common quote support, vega-normalized) and
jointly repair the violation-connected components (volfit.calib.symmetric).
Repaired slices are re-committed with fresh solution-point diagnostics. The
overlay chain is then rebuilt TWO-SIDED — floor from the updated previous
display, ceiling from the phase-A next display — whenever the LQD repair
touched anything OR the independent displays themselves cross on common
support, so a violating overlay pair splits the correction instead of the
far fit absorbing it all. A clean ladder — the overwhelmingly common case —
never enters Phase B: the committed fits ARE the result, nothing is touched.

Shared by the POST /fit/surface endpoint, the WS route (via the progress
callback) and the background Calibrate workflow (which runs the same two
phases as per-expiry items plus one repair item per ticker).
"""

from __future__ import annotations

import numpy as np

from volfit.api import fit_pool
from volfit.api.state import AppState, FitRecord
from volfit.calib.calendar import calendar_violation_windowed, common_support
from volfit.calib.fit_task import run_slice_fit
from volfit.calib.symmetric import (
    SliceSpec,
    SurfaceRepair,
    repair_surface,
    result_from_theta,
    solver_diag_from_theta,
)

#: calibrate-dict keys that must NOT enter the joint per-slice objective
#: (interface rows replace the one-sided floor; init is the warm start;
#: coords only changes the standalone solve's chart — the joint solver works
#: in the canonical (L, R, a) coordinates).
_STRIP_KEYS = (
    "init",
    "coords",
    "calendar_z",
    "calendar_floor",
    "calendar_k",
    "calendar_price_floor",
    "calendar_taper",
    "calendar_weight",
)


#: Overlay screen tolerance: worst display-vs-display total-variance drop on
#: common support that still counts as clean (~ sub-vol-bp for equity tenors).
OVERLAY_TOL_W = 1e-4


def new_context() -> dict:
    """Mutable per-ticker pipeline context threaded through the phase-A items."""
    return {
        "plan": [],  # [(iso, prepared)]
        "records": [],  # committed phase-A FitRecords
        "specs": [],  # SliceSpec per slice (joint objective)
        "retained": [],  # retained (edited) quote k per slice
        "prev_params": None,
        "prev_k": None,
    }


def _spec_from_task(task, tau: float) -> SliceSpec:
    """The slice's standalone joint-objective spec from its fit task."""
    cal = dict(task.calibrate)
    for key in _STRIP_KEYS:
        cal.pop(key, None)
    k = np.asarray(cal.pop("k"), dtype=float)
    w = np.asarray(cal.pop("w_quotes"), dtype=float)
    cal.pop("t", None)
    return SliceSpec(t=tau, k=k, w=w, fit_kwargs=cal)


def phase_a_slice(
    state: AppState,
    ticker: str,
    iso: str,
    prepared,
    fit_mode: str,
    ctx: dict,
) -> FitRecord:
    """Fit + commit one expiry independently (LQD decoupled, overlay floored)."""
    from volfit.api import service

    model = service._model_label(state.fit_settings().model)
    with state.activity.activity("calibrate", f"Calibrating {ticker} {iso} ({model})"):
        # prev=None / prev_display=None decouple BOTH the LQD backbone (no
        # floor rows) and the overlay (no variance floor) — independent-first;
        # init still warm-seeds the LQD trajectory. Phase B rebuilds the
        # overlay chain two-sided when anything actually violates.
        task = service._slice_task(
            state, ticker, iso, prepared, fit_mode,
            init=ctx["prev_params"],
            prev=None,
            prev_display=None,
            prev_k=ctx["prev_k"],
            enforce_calendar=True,
        )
        outcome = fit_pool.execute(task)
    record = FitRecord(prepared=prepared, result=outcome.result, display=outcome.display)
    record = service.commit_record(state, ticker, iso, fit_mode, record, outcome.solver_diag)

    ctx["plan"].append((iso, prepared))
    ctx["records"].append(record)
    ctx["specs"].append(_spec_from_task(task, prepared.tau))
    ctx["retained"].append(service.retained_k(state, ticker, iso, prepared))
    ctx["prev_params"] = record.result.params
    ctx["prev_k"] = ctx["retained"][-1]
    return record


def phase_b_repair(
    state: AppState, ticker: str, fit_mode: str, ctx: dict
) -> SurfaceRepair | None:
    """Screen the phase-A ladder; jointly repair + re-commit its components.

    Returns the repair diagnostics, or None for a ladder too short to couple.
    Untouched slices keep their phase-A records byte-identical (their overlays
    are rebuilt only from the first repaired slice onward, where the floor
    chain's inputs changed).
    """
    from volfit.api import service

    records, specs = ctx["records"], ctx["specs"]
    if len(records) < 2:
        return None
    with state.activity.activity(
        "calibrate", f"Calendar screen + repair {ticker}"
    ):
        # The tail contract (seam + wing-slope ordering of the extrapolated
        # wings) rides the extrapolation-guard toggle, like the overlay's
        # Notes-09/10 machinery; the identified in-support screen is always on.
        repair = repair_surface(
            specs,
            [r.result.params.to_vector() for r in records],
            tail_contract=state.options().extrapEnforce,
        )
        overlay_bad = _first_overlay_violation(records, ctx["retained"])
        if not any(repair.refit) and overlay_bad is None:
            return repair

        # Rebuild the overlay chain from ONE slice before the first repaired
        # index (a repaired component moving down can newly bind that slice's
        # ceiling) — or from the first crossing overlay pair when only the
        # independent displays violate — threading the updated floor forward.
        # The ceiling for each overlay comes from the phase-A (pre-rebuild)
        # NEXT display — a one-pass lag, which makes the two-sided target
        # traversal-unbiased to first order without iterating the chain.
        first = repair.refit.index(True) if any(repair.refit) else overlay_bad
        start = max(0, first - 1)
        old_displays = [r.display for r in records]
        prev_display = records[start - 1].display if start else None
        prev_k = ctx["retained"][start - 1] if start else None
        for i in range(start, len(records)):
            iso, prepared = ctx["plan"][i]
            if repair.refit[i]:
                result = result_from_theta(repair.thetas[i], specs[i])
            else:
                result = records[i].result
            last = i + 1 >= len(records)
            overlay_task = service._slice_task(
                state, ticker, iso, prepared, fit_mode,
                prev_display=prev_display, prev_k=prev_k,
                next_display=None if last else old_displays[i + 1],
                next_k=None if last else ctx["retained"][i + 1],
                enforce_calendar=True, with_fit=False,
            )
            display = run_slice_fit(overlay_task).display
            record = FitRecord(prepared=prepared, result=result, display=display)
            diag = solver_diag_from_theta(
                result.params.to_vector(), specs[i]
            )
            records[i] = service.commit_record(
                state, ticker, iso, fit_mode, record, diag
            )
            prev_display = records[i].display
            prev_k = ctx["retained"][i]
    return repair


def _first_overlay_violation(records, retained) -> int | None:
    """Index of the first adjacent pair whose INDEPENDENT displays cross on
    common support (total variance dropping by more than OVERLAY_TOL_W), or
    None — also None for the LQD model (no overlays to screen)."""
    for i in range(len(records) - 1):
        near, far = records[i].display, records[i + 1].display
        if near is None or far is None:
            return None
        window = common_support(retained[i], retained[i + 1])
        if window is None:
            continue
        grid = np.linspace(window[0], window[1], 41)
        gap = float(np.max(near.slice.implied_w(grid) - far.slice.implied_w(grid)))
        if gap > OVERLAY_TOL_W:
            return i
    return None


def surface_residuals(ctx: dict) -> list[float]:
    """Per-interface identified calendar residuals of the final ladder."""
    records, retained = ctx["records"], ctx["retained"]
    out = [0.0]
    for i in range(len(records) - 1):
        out.append(
            calendar_violation_windowed(
                records[i].result.slice,
                records[i + 1].result.slice,
                common_support(retained[i], retained[i + 1]),
            )
        )
    return out if records else []


def _phase_a_parallel(
    state: AppState, ticker: str, plan, fit_mode: str, ctx: dict, progress
) -> None:
    """Fan phase A out over the fit pool (independence makes this legal).

    All tasks are built up-front COLD-STARTED (init=None — the single-node
    path's semantics; the serial loop's warm seed only moves trajectories),
    submitted together, then collected/committed in ascending order so the
    ctx bookkeeping, progress frames and calibrated pointers land exactly as
    in the serial loop. Worker loss falls back to inline per slice."""
    from volfit.api import service

    model = service._model_label(state.fit_settings().model)
    fit_pool.prewarm()
    tasks = [
        service._slice_task(
            state, ticker, iso, prepared, fit_mode, enforce_calendar=True
        )
        for iso, prepared in plan
    ]
    with state.activity.activity(
        "calibrate", f"Calibrating {ticker} surface ({model}, parallel)"
    ), fit_pool.pooled():
        futures = [fit_pool.submit(t) for t in tasks]
        for index, ((iso, prepared), task, future) in enumerate(
            zip(plan, tasks, futures)
        ):
            outcome = fit_pool.collect(future, task)
            record = FitRecord(
                prepared=prepared, result=outcome.result, display=outcome.display
            )
            record = service.commit_record(
                state, ticker, iso, fit_mode, record, outcome.solver_diag
            )
            ctx["plan"].append((iso, prepared))
            ctx["records"].append(record)
            ctx["specs"].append(_spec_from_task(task, prepared.tau))
            ctx["retained"].append(service.retained_k(state, ticker, iso, prepared))
            if progress is not None:
                progress(iso, index, len(plan), record.result.max_iv_error * 1e4)


def fit_surface_symmetric(
    state: AppState, ticker: str, fit_mode: str, progress=None
):
    """The full symmetric pipeline for one ticker (POST /fit/surface shape)."""
    from volfit.api import service

    state.set_spot_shift(ticker, 0.0)  # re-anchor: fit at the chain's own spot
    plan = service.surface_inputs(state, ticker, fit_mode)
    ctx = new_context()
    if fit_pool.configured_workers() >= 2 and len(plan) >= 2:
        _phase_a_parallel(state, ticker, plan, fit_mode, ctx, progress)
    else:
        for index, (iso, prepared) in enumerate(plan):
            record = phase_a_slice(state, ticker, iso, prepared, fit_mode, ctx)
            if progress is not None:
                progress(iso, index, len(plan), record.result.max_iv_error * 1e4)
    phase_b_repair(state, ticker, fit_mode, ctx)
    fitted = [(iso, rec.result) for (iso, _p), rec in zip(ctx["plan"], ctx["records"])]
    return service.assemble_surface_response(
        state, ticker, fit_mode, fitted, surface_residuals(ctx)
    )

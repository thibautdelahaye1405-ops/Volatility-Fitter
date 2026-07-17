"""Symmetric surface pipeline (service layer) — surfaceSolver = "symmetric".

Phase A: fit every expiry INDEPENDENTLY (no LQD calendar rows; still
warm-seeded from the previous slice, which moves the trajectory but not the
optimum) and commit each fit as it lands — same progress granularity and UI
behaviour as the sequential path. The display overlay keeps its confined
variance floor against the previous display (overlay symmetry is a later
phase); only the LQD backbone is decoupled here.

Phase B: screen the fitted ladder for IDENTIFIED calendar violations
(normalized-call order on the common quote support, vega-normalized) and
jointly repair the violation-connected components (volfit.calib.symmetric).
Repaired slices are re-committed with fresh solution-point diagnostics; the
overlay chain is rebuilt from the first repaired slice onward (its floor
inputs changed). A clean ladder — the overwhelmingly common case — never
enters Phase B: the committed fits ARE the result, and nothing is touched.

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


def new_context() -> dict:
    """Mutable per-ticker pipeline context threaded through the phase-A items."""
    return {
        "plan": [],  # [(iso, prepared)]
        "records": [],  # committed phase-A FitRecords
        "specs": [],  # SliceSpec per slice (joint objective)
        "retained": [],  # retained (edited) quote k per slice
        "prev_params": None,
        "prev_display": None,
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
        # prev=None decouples the LQD backbone (no floor rows); init still
        # warm-seeds it, and prev_display/prev_k keep the overlay's confined
        # variance floor exactly as the sequential path builds it.
        task = service._slice_task(
            state, ticker, iso, prepared, fit_mode,
            init=ctx["prev_params"],
            prev=None,
            prev_display=ctx["prev_display"],
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
    ctx["prev_display"] = record.display
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
        if not any(repair.refit):
            return repair

        first = repair.refit.index(True)
        prev_display = records[first - 1].display if first else None
        prev_k = ctx["retained"][first - 1] if first else None
        for i in range(first, len(records)):
            iso, prepared = ctx["plan"][i]
            if repair.refit[i]:
                result = result_from_theta(repair.thetas[i], specs[i])
            else:
                result = records[i].result
            # Rebuild the overlay against the updated display chain.
            overlay_task = service._slice_task(
                state, ticker, iso, prepared, fit_mode,
                prev_display=prev_display, prev_k=prev_k,
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


def fit_surface_symmetric(
    state: AppState, ticker: str, fit_mode: str, progress=None
):
    """The full symmetric pipeline for one ticker (POST /fit/surface shape)."""
    from volfit.api import service

    state.set_spot_shift(ticker, 0.0)  # re-anchor: fit at the chain's own spot
    plan = service.surface_inputs(state, ticker, fit_mode)
    ctx = new_context()
    for index, (iso, prepared) in enumerate(plan):
        record = phase_a_slice(state, ticker, iso, prepared, fit_mode, ctx)
        if progress is not None:
            progress(iso, index, len(plan), record.result.max_iv_error * 1e4)
    phase_b_repair(state, ticker, fit_mode, ctx)
    fitted = [(iso, rec.result) for (iso, _p), rec in zip(ctx["plan"], ctx["records"])]
    return service.assemble_surface_response(
        state, ticker, fit_mode, fitted, surface_residuals(ctx)
    )

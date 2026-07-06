"""One-slice calibration task: a picklable unit of fit work (parallel Calibrate).

The background Calibrate job parallelizes across tickers by shipping each
slice's CPU-bound fit to a worker process (volfit.api.fit_pool). A task
carries ONLY pure data — numpy arrays and the frozen calib/model target
dataclasses — never the AppState: the service layer assembles the inputs
under the state lock (volfit.api.service._slice_task) and commits the outcome
back on the main process, so workers stay stateless and a pooled fit is
byte-identical to an inline one (``run_slice_fit`` is THE slice-fit code
path either way — same function, same inputs).

Import discipline: this module is what a spawned worker imports, so it may
depend only on volfit.calib / volfit.models — never on volfit.api (whose
package __init__ builds the whole FastAPI app).
"""

from __future__ import annotations

from dataclasses import dataclass

from volfit.models.display import DisplayFit, build_display_fit
from volfit.models.lqd.calibrate import CalibrationResult, calibrate_slice


@dataclass(frozen=True)
class OverlaySettings:
    """The FitSettings fields build_display_fit reads — a picklable stand-in so
    workers never import the pydantic schema module under volfit.api."""

    sviPenaltyWeight: float
    leeSlopeMax: float
    midAnchorWeight: float
    nCores: int
    sigmoidRidge: float


@dataclass(frozen=True)
class SliceFitTask:
    """Keyword bundles for one slice's fits; a ``None`` bundle skips that part.

    ``calibrate`` holds the LQD calibrate_slice kwargs with ``init`` already
    resolved by the caller (the warm-start order check is main-side);
    ``prepass`` the data-only two-pass fit whose params seed the main fit
    (single-node priorDataOnlyPrepass path); ``overlay`` the build_display_fit
    kwargs with ``settings`` an OverlaySettings; ``want_diag`` requests the
    solver's solution Jacobian side-channel for the observation filter
    (Note 15) — returned in the outcome, never mutated across processes.
    """

    calibrate: dict | None = None
    prepass: dict | None = None
    overlay: dict | None = None
    want_diag: bool = False


@dataclass(frozen=True)
class SliceFitOutcome:
    """What a task produces: the LQD result, the display overlay (non-LQD
    model choice) and the filter's solver diagnostics ({} when the fit ran
    with the side-channel but nothing was recorded, None when not requested)."""

    result: CalibrationResult | None
    display: DisplayFit | None
    solver_diag: dict | None


def run_slice_fit(task: SliceFitTask) -> SliceFitOutcome:
    """Execute one slice-fit task (in a pool worker or inline — identically)."""
    result: CalibrationResult | None = None
    diag: dict | None = {} if task.want_diag else None
    if task.calibrate is not None:
        kwargs = dict(task.calibrate)
        if task.prepass is not None and kwargs.get("init") is None:
            # Two-pass "don't damp the signal": the data-only fit seeds the
            # prior-carrying main fit (its order always matches by construction).
            kwargs["init"] = calibrate_slice(**task.prepass).params
        result = calibrate_slice(**kwargs, solver_diag=diag)
    display = build_display_fit(**task.overlay) if task.overlay is not None else None
    return SliceFitOutcome(result=result, display=display, solver_diag=diag)

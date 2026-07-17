"""Parallel background calibration (ROADMAP commercial MVP: calibration queue).

Three layers under test:

* the grouped/staged job runner (volfit.api.jobs) — per-ticker groups run
  concurrently, stages are barriers, cancel/error semantics keep per-node
  granularity;
* the picklable slice-fit task (volfit.calib.fit_task) and the process pool
  (volfit.api.fit_pool) — a pooled fit must be byte-identical to an inline
  one, and interactive fits must never touch the pool;
* the end-to-end gate: workflow.calibrate_all with concurrent groups commits
  exactly the same fits as the historical serial runner.

The suite-wide conftest pins VOLFIT_CALIB_WORKERS=1; tests here override it
per-test and reset the module pool in a finally block.
"""

from __future__ import annotations

import pickle
import threading
import time
from datetime import date

import numpy as np

from volfit.api import fit_pool, service
from volfit.api.jobs import CalibrationJobs
from volfit.api.state import AppState
from volfit.calib.fit_task import run_slice_fit

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


# ------------------------------------------------------------- job runner
def test_stage_groups_run_concurrently():
    """With workers=2, two single-item groups must be in flight TOGETHER: each
    item waits on a shared barrier that only opens when both have started."""
    jobs = CalibrationJobs()
    barrier = threading.Barrier(2, timeout=5.0)
    hits: list[str] = []

    def item(name: str):
        def thunk() -> None:
            barrier.wait()  # times out (-> item error) if the runner is serial
            hits.append(name)

        return (name, "Parametric", thunk)

    assert jobs.start_stages([[("g1", [item("a")]), ("g2", [item("b")])]], workers=2)
    jobs.join(10.0)
    status = jobs.status()
    assert status.error == "" and status.done == 2 and not status.running
    assert sorted(hits) == ["a", "b"]


def test_stages_are_a_barrier():
    """Stage 2 (the LV stage in production) starts only after EVERY group of
    stage 1 finished, even when stage 1 groups have unequal durations."""
    jobs = CalibrationJobs()
    finished: list[str] = []
    seen_at_stage2: dict[str, int] = {}

    def slow(name: str, delay: float):
        def thunk() -> None:
            time.sleep(delay)
            finished.append(name)

        return (name, "Parametric", thunk)

    def check() -> None:
        seen_at_stage2["count"] = len(finished)

    stages = [
        [("g1", [slow("fast", 0.01)]), ("g2", [slow("slow", 0.15)])],
        [("LV", [("lv", "LV", check)])],
    ]
    assert jobs.start_stages(stages, workers=2)
    jobs.join(10.0)
    assert seen_at_stage2["count"] == 2  # both parametric groups were done first
    assert jobs.status().done == 3


def test_cancel_stops_every_group_between_items():
    """Cancellation keeps per-node granularity in every concurrent group: the
    in-flight items finish, the queued second items never run."""
    jobs = CalibrationJobs()
    started = threading.Barrier(3, timeout=5.0)  # both firsts + the test thread
    release = threading.Event()
    ran_second: list[str] = []

    def first(name: str):
        def thunk() -> None:
            started.wait()
            release.wait(5.0)

        return (f"{name}-1", "Parametric", thunk)

    def second(name: str):
        def thunk() -> None:
            ran_second.append(name)

        return (f"{name}-2", "Parametric", thunk)

    groups = [("g1", [first("a"), second("a")]), ("g2", [first("b"), second("b")])]
    assert jobs.start_stages([groups], workers=2)
    started.wait()  # both groups are inside their first item
    jobs.cancel()
    release.set()
    jobs.join(10.0)
    status = jobs.status()
    assert status.cancelled is True and status.done == 2
    assert ran_second == []


def test_item_error_is_isolated_across_and_within_groups():
    """One bad node never kills the run: the same group's later items and the
    other groups all still execute; the error is recorded per item."""
    jobs = CalibrationJobs()
    ran: list[str] = []

    def boom() -> None:
        raise RuntimeError("kaboom")

    groups = [
        ("g1", [("bad", "Parametric", boom), ("g1-next", "Parametric", lambda: ran.append("g1"))]),
        ("g2", [("g2-item", "Parametric", lambda: ran.append("g2"))]),
    ]
    assert jobs.start_stages([groups], workers=2)
    jobs.join(10.0)
    status = jobs.status()
    assert status.error.startswith("bad:") and status.done == 3
    assert sorted(ran) == ["g1", "g2"]


def test_legacy_start_runs_items_sequentially_in_order():
    """The historical single-lane contract is unchanged: strict input order."""
    jobs = CalibrationJobs()
    seq: list[int] = []
    items = [(f"i{n}", "Parametric", (lambda n=n: seq.append(n))) for n in range(5)]
    assert jobs.start(items)
    jobs.join(10.0)
    assert seq == list(range(5))
    assert jobs.status().total == 5 and jobs.status().done == 5


def test_second_start_rejected_while_running():
    jobs = CalibrationJobs()
    release = threading.Event()
    assert jobs.start([("hold", "Parametric", lambda: release.wait(5.0))])
    try:
        assert jobs.start_stages([[("g", [("x", "Parametric", lambda: None)])]]) is False
    finally:
        release.set()
        jobs.join(10.0)


# ------------------------------------------------------ slice task + pool
def _node_task(state: AppState, **kw):
    """A production slice-fit task for one synthetic ALPHA node."""
    plan = service.surface_inputs(state, TICKER, "mid")
    iso, prepared = plan[1]
    return service._slice_task(state, TICKER, iso, prepared, "mid", **kw)


def test_slice_task_pickles_and_stays_deterministic():
    """The task round-trips through pickle (the process-pool transport) and the
    unpickled copy fits to EXACTLY the same parameters."""
    state = AppState(REF_DATE)
    task = _node_task(state)
    clone = pickle.loads(pickle.dumps(task))
    a = run_slice_fit(task)
    b = run_slice_fit(clone)
    np.testing.assert_array_equal(a.result.params.to_vector(), b.result.params.to_vector())
    assert a.display is None and b.display is None  # default model is LQD
    outcome = pickle.loads(pickle.dumps(a))  # the return leg of the transport
    np.testing.assert_array_equal(outcome.result.params.to_vector(), a.result.params.to_vector())


def test_pooled_execute_matches_inline():
    """A real spawn-pool execution returns byte-identical results to the inline
    path, for both the LQD backbone and a non-LQD display overlay — and it must
    genuinely run in the pool (no silent inline fallback)."""
    import os

    os.environ["VOLFIT_CALIB_WORKERS"] = "2"
    fit_pool._reset_for_tests()
    try:
        state = AppState(REF_DATE)
        task = _node_task(state)
        inline = run_slice_fit(task)
        with fit_pool.pooled():
            pooled = fit_pool.execute(task)
        assert fit_pool._disabled is False and fit_pool._pool is not None
        np.testing.assert_array_equal(
            pooled.result.params.to_vector(), inline.result.params.to_vector()
        )
        assert pooled.result.max_iv_error == inline.result.max_iv_error

        # Non-LQD model: the overlay fit crosses the pool too (same worker).
        state.set_fit_settings(state.fit_settings().model_copy(update={"model": "svi"}))
        task2 = _node_task(state)
        inline2 = run_slice_fit(task2)
        with fit_pool.pooled():
            pooled2 = fit_pool.execute(task2)
        assert pooled2.display is not None and pooled2.display.model == "svi"
        assert pooled2.display.handles.atm_vol == inline2.display.handles.atm_vol
        assert pooled2.display.max_iv_error == inline2.display.max_iv_error
    finally:
        os.environ["VOLFIT_CALIB_WORKERS"] = "1"
        fit_pool._reset_for_tests()


def test_symmetric_surface_phase_a_fans_out_and_matches_inline():
    """The symmetric surface pipeline fans phase A over the pool (workers >= 2)
    and commits byte-identical results to the inline cold-start path — the
    fan-out is pure plumbing (same tasks, same runner), and independence is
    what makes it legal (no warm-seed / floor threading between expiries)."""
    import os

    os.environ["VOLFIT_CALIB_WORKERS"] = "2"
    fit_pool._reset_for_tests()
    try:
        state = AppState(REF_DATE)
        response = service.fit_surface(state, TICKER, "mid", True)
        assert fit_pool._disabled is False and fit_pool._pool is not None

        # Inline cold-start reference: the SAME tasks on a fresh state.
        ref = AppState(REF_DATE)
        plan = service.surface_inputs(ref, TICKER, "mid")
        assert response.expiries == [iso for iso, _ in plan] and len(plan) >= 2
        for iso, prepared in plan:
            task = service._slice_task(
                ref, TICKER, iso, prepared, "mid", enforce_calendar=True
            )
            inline = run_slice_fit(task)
            rec = service.fit_or_get(state, TICKER, iso, "mid")
            np.testing.assert_array_equal(
                rec.result.params.to_vector(), inline.result.params.to_vector()
            )
    finally:
        os.environ["VOLFIT_CALIB_WORKERS"] = "1"
        fit_pool._reset_for_tests()


def test_affine_pooled_matches_inline():
    """The LV (affine) surface calibration crosses the pool byte-identically:
    two fresh states (same cold-start conditions), one fit inline and one via a
    real spawn pool, must produce EXACTLY the same response — and the pooled
    run must genuinely use the pool (no silent inline fallback)."""
    import os

    from volfit.api.affine_fit import calibrate_affine_surface
    from volfit.api.schemas_affine import AffineFitRequest

    inline = calibrate_affine_surface(
        AppState(REF_DATE), TICKER, AffineFitRequest(fitMode="mid")
    )

    os.environ["VOLFIT_CALIB_WORKERS"] = "2"
    fit_pool._reset_for_tests()
    try:
        with fit_pool.pooled():
            pooled = calibrate_affine_surface(
                AppState(REF_DATE), TICKER, AffineFitRequest(fitMode="mid")
            )
        assert fit_pool._disabled is False and fit_pool._pool is not None
        assert pooled.localVol == inline.localVol  # nodal vols, exact
        assert pooled.rmsIvErrorBp == inline.rmsIvErrorBp
        assert pooled.nEvals == inline.nEvals
        assert pooled.model_dump() == inline.model_dump()  # the whole response
    finally:
        os.environ["VOLFIT_CALIB_WORKERS"] = "1"
        fit_pool._reset_for_tests()


def test_interactive_execute_never_touches_the_pool():
    """Outside a ``pooled()`` context (single-node Calibrate on a request
    thread, autoCalibrate refits) the fit runs inline and the pool is never
    even created — an interactive fit can never queue behind a background job."""
    import os

    os.environ["VOLFIT_CALIB_WORKERS"] = "8"
    fit_pool._reset_for_tests()
    try:
        state = AppState(REF_DATE)
        outcome = fit_pool.execute(_node_task(state))
        assert outcome.result is not None and outcome.result.success
        assert fit_pool._pool is None  # never spawned
    finally:
        os.environ["VOLFIT_CALIB_WORKERS"] = "1"
        fit_pool._reset_for_tests()


# --------------------------------------------------------- end-to-end gate
def _fit_vectors(state: AppState) -> dict[tuple[str, str], np.ndarray]:
    from volfit.api import workflow

    out: dict[tuple[str, str], np.ndarray] = {}
    for ticker, iso in workflow.lit_nodes(state):
        record = service.fit_or_get(state, ticker, iso, "mid")
        out[(ticker, iso)] = record.result.params.to_vector()
    return out


def _affine_hits(state: AppState) -> dict[str, object]:
    """Per-ticker committed LV responses (via the calibrated pointer)."""
    from volfit.api import affine_fit, workflow

    out: dict[str, object] = {}
    for ticker in {t for t, _ in workflow.lit_nodes(state)}:
        ptr = state.get_affine_ptr(ticker)
        if ptr is not None:
            out[ticker] = affine_fit._cache(state)[ptr]
    return out


def test_calibrate_all_concurrent_groups_match_serial(monkeypatch):
    """THE identity gate: calibrate_all with concurrent per-ticker groups (3 job
    threads, pool suppressed so fits run inline under the GIL) commits exactly
    the same parametric fits AND LV surfaces as the historical serial runner —
    grouping, warm-start chains and concurrent AppState commits change nothing."""
    from volfit.api import workflow

    def make_state() -> AppState:
        state = AppState(REF_DATE)
        state.set_options(state.options().model_copy(update={"localVolEnabled": True}))
        return state

    monkeypatch.setenv("VOLFIT_CALIB_WORKERS", "1")
    serial = make_state()
    assert workflow.calibrate_all(serial)
    serial.calibration_jobs.join(240.0)
    reference = _fit_vectors(serial)
    lv_reference = _affine_hits(serial)
    assert len(reference) >= 8  # 3 synthetic tickers x 4 expiries
    assert len(lv_reference) == 3  # one LV surface per ticker

    monkeypatch.setenv("VOLFIT_CALIB_WORKERS", "3")
    monkeypatch.setattr(fit_pool, "_get_pool", lambda: None)  # inline, threads only
    parallel = make_state()
    assert workflow.calibrate_all(parallel)
    parallel.calibration_jobs.join(240.0)
    status = parallel.calibration_jobs.status()
    assert status.error == "" and status.done == status.total

    got = _fit_vectors(parallel)
    assert set(got) == set(reference)
    for key, vector in reference.items():
        np.testing.assert_array_equal(got[key], vector)
    lv_got = _affine_hits(parallel)
    assert set(lv_got) == set(lv_reference)
    for ticker, hit in lv_reference.items():
        assert lv_got[ticker].localVol == hit.localVol
        assert lv_got[ticker].model_dump() == hit.model_dump()

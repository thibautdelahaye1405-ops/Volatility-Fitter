"""Process-pool execution of slice-fit tasks (parallel background Calibrate).

Calibrations are CPU-bound scipy work that holds the GIL (thread-parallelism
measured GIL-negative for both the slice and the LV fits), so the background
Calibrate job parallelizes across TICKERS by shipping each slice fit and each
ticker's LV (affine) calibration (volfit.calib.fit_task) to a spawn-context
process pool; the per-ticker warm-start / calendar chain stays sequential
inside its job thread, which mostly blocks on pool futures. Interactive fits — a single-node Calibrate on
a request thread, an autoCalibrate refit on a GET — never touch the pool:
they run inline so they can never queue behind a 25-ticker background job.
The job runner opts in per thunk via ``pooled()`` (a thread-local flag).

Sizing: ``VOLFIT_CALIB_WORKERS`` (0/1 = inline, i.e. the historical serial
behaviour), default cpu_count-1 capped at 8. Any pool INFRASTRUCTURE failure
(spawn, pickling, a killed worker) falls back to the inline path and disables
pooling for the session — parallelism is an optimization, never a correctness
dependency; a genuine fit exception raises through unchanged (the job runner
records it per item exactly as before).
"""

from __future__ import annotations

import atexit
import logging
import multiprocessing
import os
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from pickle import PicklingError

from volfit.calib.fit_task import SliceFitTask, run_fit_task

log = logging.getLogger("volfit.fit_pool")

_ENV = "VOLFIT_CALIB_WORKERS"
_MAX_DEFAULT = 8

_lock = threading.Lock()
_pool: ProcessPoolExecutor | None = None
_disabled = False  # sticky for the session once the pool proves unusable
_use_pool = threading.local()


def configured_workers() -> int:
    """Worker count: VOLFIT_CALIB_WORKERS, else cpu-1 capped at 8 (min 1)."""
    raw = os.environ.get(_ENV, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            log.warning("%s=%r is not an integer; using the default", _ENV, raw)
    cpu = os.cpu_count() or 4
    return max(1, min(cpu - 1, _MAX_DEFAULT))


def _get_pool() -> ProcessPoolExecutor | None:
    """The lazily created shared pool, or None when disabled/unavailable."""
    global _pool, _disabled
    with _lock:
        if _disabled:
            return None
        if _pool is None:
            try:
                _pool = ProcessPoolExecutor(
                    max_workers=configured_workers(),
                    # Explicit spawn on every platform: workers import only the
                    # light calib/models graph, never a fork-copy of AppState.
                    mp_context=multiprocessing.get_context("spawn"),
                )
            except Exception as exc:
                log.warning("calibration pool unavailable (%s); fits run inline", exc)
                _disabled = True
                return None
        return _pool


def _disable(exc: Exception) -> None:
    global _disabled
    with _lock:
        _disabled = True
    log.warning("calibration pool failed (%s); falling back to inline fits", exc)


@contextmanager
def pooled():
    """Mark this thread's slice fits as background work eligible for the pool."""
    prev = getattr(_use_pool, "on", False)
    _use_pool.on = True
    try:
        yield
    finally:
        _use_pool.on = prev


def pooled_thunk(thunk: Callable[[], None]) -> Callable[[], None]:
    """Wrap a job work item so its slice fits route through the pool."""

    def run() -> None:
        with pooled():
            thunk()

    return run


def prewarm() -> None:
    """Start spinning workers up (their volfit import) while the caller
    prepares quotes; best-effort, a no-op when pooling is off."""
    if configured_workers() < 2:
        return
    pool = _get_pool()
    if pool is None:
        return
    try:
        for _ in range(configured_workers()):
            pool.submit(run_fit_task, SliceFitTask())  # empty task: import + return
    except Exception:  # pragma: no cover - prewarm must never break Calibrate
        pass


def execute(task):
    """Run a fit task (SliceFitTask or AffineFitTask) in the pool when this
    thread opted in (``pooled``), else inline. Returns the task runner's result
    (SliceFitOutcome / AffineCalibration) — one code path either way."""
    if not getattr(_use_pool, "on", False) or configured_workers() < 2:
        return run_fit_task(task)
    pool = _get_pool()
    if pool is None:
        return run_fit_task(task)
    try:
        return pool.submit(run_fit_task, task).result()
    except (BrokenProcessPool, PicklingError, OSError) as exc:
        # Pool infrastructure failure — a genuine fit error (e.g. ValueError
        # from an infeasible slice) raises through the future unwrapped.
        _disable(exc)
        return run_fit_task(task)


def shutdown() -> None:
    """Tear the pool down (app lifespan close / interpreter exit)."""
    global _pool
    with _lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _reset_for_tests() -> None:
    """Drop the pool + sticky disable so a test can exercise a fresh config."""
    global _disabled
    shutdown()
    with _lock:
        _disabled = False


atexit.register(shutdown)

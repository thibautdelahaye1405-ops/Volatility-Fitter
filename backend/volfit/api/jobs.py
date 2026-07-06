"""Background calibration job manager (single job, grouped stages, cancellable).

The global "Calibrate" action fits every lit node in the background (ROADMAP
workflow decision). Work is organized as STAGES run in sequence (Parametric,
then LV) of GROUPS run concurrently on a small thread pool — one group per
ticker, because the warm-start / calendar chain must stay sequential inside a
ticker while tickers are independent. Each group is an ordered list of
labelled work items ``(label, phase, thunk)``.

The CPU-heavy slice fits inside the parametric thunks are shipped to the fit
process pool (volfit.api.fit_pool) by the workflow layer, so the job threads
here mostly block on futures and the thread count can track the pool size
without oversubscribing the CPU. Commits run through the normal service path
(lock-guarded AppState), so a concurrent read only ever sees a node's old or
new fit, never a torn one.

One job at a time with a pollable status (running / total / done / current
node) and cooperative cancellation checked between items in every group — the
same per-node granularity as the historical sequential runner. ``start(items)``
keeps the legacy one-group sequential contract for existing callers and tests.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

#: One unit of background work: (display label, coarse UI phase, thunk).
Item = tuple[str, str, Callable[[], None]]
#: An ordered chain of items run sequentially (one ticker's expiries).
Group = tuple[str, list[Item]]


@dataclass
class JobStatus:
    """Snapshot of the current/last calibration job."""

    running: bool = False
    total: int = 0
    done: int = 0
    current: str = ""  # "TICKER EXPIRY" being calibrated, "" when idle
    phase: str = ""  # coarse phase of the in-flight item ("Parametric" | "LV")
    error: str = ""  # last per-node error (calibration never aborts the job)
    cancelled: bool = False


class CalibrationJobs:
    """Runs at most one background calibration over stages of item groups."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = JobStatus()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def status(self) -> JobStatus:
        with self._lock:
            return JobStatus(**vars(self._status))

    def is_running(self) -> bool:
        with self._lock:
            return self._status.running

    def start(self, items: list[Item]) -> bool:
        """Start a background job over labelled work items, run in order.

        The legacy single-lane contract (one group, one worker): each thunk
        calibrates one unit and ``label``/``phase`` drive the status display.
        Returns False (without starting) if a job is already running.
        """
        return self.start_stages([[("", list(items))]], workers=1)

    def start_stages(self, stages: list[list[Group]], workers: int = 1) -> bool:
        """Start a background job over ``stages`` of concurrent ``Group``s.

        Stages run strictly in sequence (a barrier between them — e.g. all
        Parametric groups before the LV stage); within a stage, groups run
        concurrently on up to ``workers`` threads while each group's items run
        in order. Per-item status/error/cancel semantics match ``start``:
        one bad item never kills the run, cancellation stops every group after
        its current item. Returns False if a job is already running.
        """
        with self._lock:
            if self._status.running:
                return False
            self._cancel.clear()
            total = sum(len(items) for groups in stages for _, items in groups)
            self._status = JobStatus(running=True, total=total)

        def run_group(group: Group) -> None:
            _name, items = group
            for label, phase, thunk in items:
                if self._cancel.is_set():
                    with self._lock:
                        self._status.cancelled = True
                    return
                with self._lock:
                    self._status.current = label
                    self._status.phase = phase
                try:
                    thunk()
                except Exception as exc:  # one bad item never kills the run
                    with self._lock:
                        self._status.error = f"{label}: {exc}"
                with self._lock:
                    self._status.done += 1

        def run() -> None:
            try:
                for groups in stages:
                    if self._cancel.is_set():
                        with self._lock:
                            self._status.cancelled = True
                        break
                    if workers <= 1 or len(groups) <= 1:
                        for group in groups:  # deterministic legacy order
                            run_group(group)
                    else:
                        pool = ThreadPoolExecutor(
                            max_workers=min(workers, len(groups)),
                            thread_name_prefix="calib",
                        )
                        with pool:
                            # run_group swallows per-item errors, so consuming
                            # the map only propagates runner bugs, not fits.
                            list(pool.map(run_group, groups))
            finally:
                with self._lock:
                    self._status.running = False
                    self._status.current = ""
                    self._status.phase = ""

        self._thread = threading.Thread(target=run, name="calib-job", daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        """Request cancellation; every group stops after its current node."""
        self._cancel.set()

    def join(self, timeout: float | None = None) -> None:
        """Block until the running job finishes (used by tests/shutdown)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

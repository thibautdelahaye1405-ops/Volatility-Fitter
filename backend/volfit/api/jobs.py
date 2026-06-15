"""Background calibration job manager (single job, sequential, cancellable).

The global "Calibrate" action fits every lit node in succession in the
background (ROADMAP workflow decision). This keeps one job at a time with a
pollable status (running / total / done / current node), so the frontend can
show a progress indicator and the backend scheduler can reuse it for the
auto-calibrate-on-fetch path. Calibrations are CPU-bound scipy work; the job
runs on a daemon thread and each node is calibrated through the normal service
path (which is itself lock-guarded), so a concurrent read only ever sees a
node's old or new fit, never a torn one.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


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
    """Runs at most one background calibration over a list of nodes."""

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

    def start(self, items: list[tuple[str, str, Callable[[], None]]]) -> bool:
        """Start a background job over labelled work items ``(label, phase, thunk)``.

        Each thunk calibrates one unit (a parametric node or a ticker's LV
        surface); ``label`` shows in ``current`` and ``phase`` is the coarse stage
        ("Parametric" | "Local Vol"). Returns False (without starting) if a job is
        already running.
        """
        with self._lock:
            if self._status.running:
                return False
            self._cancel.clear()
            self._status = JobStatus(running=True, total=len(items))

        def run() -> None:
            try:
                for label, phase, thunk in items:
                    if self._cancel.is_set():
                        with self._lock:
                            self._status.cancelled = True
                        break
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
            finally:
                with self._lock:
                    self._status.running = False
                    self._status.current = ""
                    self._status.phase = ""

        self._thread = threading.Thread(target=run, name="calib-job", daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        """Request cancellation; the job stops after the current node."""
        self._cancel.set()

    def join(self, timeout: float | None = None) -> None:
        """Block until the running job finishes (used by tests/shutdown)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

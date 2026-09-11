"""The series job slot (SERIES ARC S2 — D5): one running series, a queue,
pause / resume / cancel, per-frame checkpoints, restart recovery.

Separate from ``CalibrationJobs`` on purpose: the live Calibrate button keeps
its single slot, a series never takes it. The runner is one daemon thread
per run: it harvests the pending frames in order (a live frame waits until
its instant is due), checkpoints each frame in the store as it lands, then
hands the document to ``calibrate_hook`` (S3 plugs the lane calibration in;
None = the run ends after the harvest). Pause and cancel are cooperative —
the loop checks between frames and while waiting — and every state the
runner leaves is persisted (``series.progress``), so a page reload or a
server restart finds the truth in the store: ``recover()`` marks a series
that was running when the process died ``paused`` (the user resumes it).
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel

from volfit.api.schemas_series import SeriesDoc, SeriesProgress
from volfit.api.series_harvest import harvest_frame
from volfit.api.series_store import SeriesStore, now_iso
from volfit.data.store import VolStore

#: Statuses that mean "a run is in flight" (recovered to paused at startup).
RUNNING_STATUSES = frozenset({"queued", "harvesting", "calibrating"})
#: Statuses a start / resume accepts.
STARTABLE = frozenset({"draft", "paused", "failed", "cancelled", "done"})


class SeriesJobStatus(BaseModel):
    """GET /series/{id}/status and the stream: the slot + this series."""

    seriesId: str | None = None
    running: str | None = None  # the series occupying the slot
    queue: list[str] = []
    progress: SeriesProgress | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class SeriesJobs:
    """Runs at most one series at a time; others wait in a FIFO queue."""

    def __init__(self, state, now: Callable[[], datetime] = utcnow) -> None:
        self._state = state
        self._now = now
        self._lock = threading.Lock()
        self._queue: deque[str] = deque()
        self._running: str | None = None
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()  # set on pause / cancel / stop to cut a wait short
        self._pause: set[str] = set()
        self._cancel: set[str] = set()
        self._stopping = False
        #: The lane calibration run after the harvest (``series_lanes.run_lanes``;
        #: ``hook(jobs, doc) -> None``). None = harvest only (tests, scripts).
        from volfit.api.series_lanes import run_lanes  # lazy: lanes pull the fit stack

        self.calibrate_hook: Callable[["SeriesJobs", SeriesDoc], None] | None = run_lanes

    # -------------------------------------------------------------- store
    def _store(self) -> VolStore:
        if self._state.store_path is None:
            raise RuntimeError("series need a store: set VOLFIT_DB")
        return VolStore(self._state.store_path)

    def _load(self, series_id: str) -> SeriesDoc | None:
        with self._store() as store:
            return SeriesStore(store).get(series_id)

    def _checkpoint(self, series_id: str, progress: SeriesProgress, error: str | None = None) -> None:
        with self._store() as store:
            SeriesStore(store).set_progress(series_id, progress, error)

    # ------------------------------------------------------------- status
    def status(self, series_id: str | None = None) -> SeriesJobStatus:
        with self._lock:
            running, queue = self._running, list(self._queue)
        progress = None
        if series_id is not None:
            doc = self._load(series_id)
            progress = doc.progress if doc is not None else None
        return SeriesJobStatus(seriesId=series_id, running=running, queue=queue,
                               progress=progress)

    def is_running(self) -> bool:
        with self._lock:
            return self._running is not None

    # ------------------------------------------------------------ control
    def start(self, series_id: str) -> str:
        """Run the series now, or queue it behind the running one. Returns
        ``started`` | ``queued`` | ``already`` (running or queued) | ``unknown``
        | ``busy`` (the series is not in a startable state)."""
        doc = self._load(series_id)
        if doc is None:
            return "unknown"
        with self._lock:
            if series_id == self._running or series_id in self._queue:
                return "already"
            if doc.progress.status not in STARTABLE:
                return "busy"
            self._pause.discard(series_id)
            self._cancel.discard(series_id)
            if self._running is not None:
                self._queue.append(series_id)
                self._checkpoint(series_id, doc.progress.model_copy(update={"status": "queued"}))
                return "queued"
            self._running = series_id
            # Checkpoint BEFORE the thread runs: a status read right after
            # start never says "draft" (the runner flips it to harvesting at
            # its first checkpoint — a race a busy box once lost).
            self._checkpoint(series_id, doc.progress.model_copy(update={"status": "queued"}))
        self._launch(series_id)
        return "started"

    resume = start

    def pause(self, series_id: str) -> bool:
        with self._lock:
            if series_id in self._queue:
                self._queue.remove(series_id)
                dequeued = True
            else:
                dequeued = False
            if series_id == self._running:
                self._pause.add(series_id)
                self._wake.set()
                return True
        if dequeued:
            doc = self._load(series_id)
            if doc is not None:
                self._checkpoint(series_id, doc.progress.model_copy(update={"status": "paused"}))
        return dequeued

    def cancel(self, series_id: str) -> bool:
        with self._lock:
            if series_id in self._queue:
                self._queue.remove(series_id)
                dequeued = True
            else:
                dequeued = False
            if series_id == self._running:
                self._cancel.add(series_id)
                self._wake.set()
                return True
        if dequeued:
            doc = self._load(series_id)
            if doc is not None:
                self._checkpoint(series_id, doc.progress.model_copy(update={"status": "cancelled"}))
        return dequeued

    def stop(self, timeout: float = 5.0) -> None:
        """Shutdown: pause the running series (it resumes after a restart)."""
        with self._lock:
            self._stopping = True
            if self._running is not None:
                self._pause.add(self._running)
            self._wake.set()
        self.join(timeout)

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def recover(self) -> list[str]:
        """At startup: a series the previous process left running is paused
        (its frames are checkpointed, a resume continues)."""
        if self._state.store_path is None:
            return []
        recovered = []
        with self._store() as store:
            series = SeriesStore(store)
            for row in series.list():
                if row.status in RUNNING_STATUSES:
                    doc = series.get(row.id)
                    if doc is None:
                        continue
                    series.set_progress(row.id, doc.progress.model_copy(update={
                        "status": "paused", "current": "recovered after a restart",
                    }))
                    recovered.append(row.id)
        return recovered

    # ------------------------------------------------------------- runner
    def _launch(self, series_id: str) -> None:
        self._wake.clear()
        thread = threading.Thread(target=self._run, args=(series_id,),
                                  name=f"series-{series_id}", daemon=True)
        thread.start()  # started BEFORE it is published: a join never sees an unstarted thread
        self._thread = thread

    def _interrupted(self, series_id: str) -> str | None:
        with self._lock:
            if series_id in self._cancel:
                return "cancelled"
            if series_id in self._pause or self._stopping:
                return "paused"
        return None

    def _wait_until(self, series_id: str, ts: datetime) -> str | None:
        """Block until ``ts`` is due (live frames); returns the interruption."""
        while True:
            stop = self._interrupted(series_id)
            if stop:
                return stop
            remaining = (ts - self._now()).total_seconds()
            if remaining <= 0:
                return None
            self._wake.wait(min(remaining, 1.0))

    def _run(self, series_id: str) -> None:
        final = "done"
        error: str | None = None
        try:
            doc = self._load(series_id)
            if doc is None:
                return
            # startedTs on the store's local clock, like createdTs / updatedTs /
            # harvestedTs (it was UTC until 2026-09-11 — every run read an
            # hour long on a UTC+1 desk); frame instants stay UTC-naive.
            progress = doc.progress.model_copy(update={
                "status": "harvesting", "framesTotal": len(doc.frames),
                "framesReady": sum(1 for f in doc.frames if f.status == "ready"),
                "startedTs": doc.progress.startedTs or now_iso(), "error": None,
            })
            self._checkpoint(series_id, progress)
            pending = [f for f in doc.frames if f.status in ("pending", "failed")]
            for frame in pending:
                if doc.spec.mode == "live":
                    stop = self._wait_until(series_id, datetime.fromisoformat(frame.ts))
                else:
                    stop = self._interrupted(series_id)
                if stop:
                    final = stop
                    break
                label = (f"Harvesting {doc.spec.ticker} frame {frame.idx + 1}/{len(doc.frames)}"
                         f" · {frame.ts}")
                progress = progress.model_copy(update={"current": label})
                self._checkpoint(series_id, progress)
                done = harvest_frame(self._state, doc, frame, label)
                doc.frames[frame.idx] = done
                progress = progress.model_copy(update={
                    "framesReady": sum(1 for f in doc.frames if f.status == "ready"),
                    "error": done.error if done.status == "failed" else progress.error,
                })
                self._checkpoint(series_id, progress)
            else:
                if self.calibrate_hook is not None:
                    progress = progress.model_copy(update={"status": "calibrating", "current": None})
                    self._checkpoint(series_id, progress)
                    self.calibrate_hook(self, self._load(series_id) or doc)
                    final = self._interrupted(series_id) or "done"
        except Exception as exc:  # noqa: BLE001 — the run ends, the store says why
            final, error = "failed", str(exc)[:300]
        finally:
            try:
                doc = self._load(series_id)
                if doc is not None:
                    # The hook may have checkpointed its own final status.
                    status = doc.progress.status
                    if status in RUNNING_STATUSES or final != "done":
                        self._checkpoint(series_id, doc.progress.model_copy(update={
                            "status": final, "current": None,
                            "error": error or doc.progress.error,
                        }), error)
            except Exception:  # noqa: BLE001
                pass
            self._finish(series_id)

    def _finish(self, series_id: str) -> None:
        with self._lock:
            self._pause.discard(series_id)
            self._cancel.discard(series_id)
            self._running = None
            next_id = None
            if not self._stopping and self._queue:
                next_id = self._queue.popleft()
                self._running = next_id
        if next_id is not None:
            self._launch(next_id)


def series_jobs_of(state) -> SeriesJobs:
    """The state's job slot (created lazily for states built outside
    ``create_app``, e.g. tests and scripts)."""
    jobs = getattr(state, "series_jobs", None)
    if jobs is None:
        jobs = SeriesJobs(state)
        state.series_jobs = jobs
    return jobs


def seconds_until(ts: datetime, now: datetime) -> float:
    """Seconds until a live frame is due (≤ 0 = due now)."""
    return (ts - now).total_seconds()


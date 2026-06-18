"""Engine-activity reporter — what the compute engine is actually doing *now*.

The TopBar workflow gives a coarse picture (a job is running, N of M nodes done).
This reporter is the FINE-GRAINED narration channel the bottom status bar reads:
every long-running step pushes a short, human-readable activity ("Fetching SPY
quotes from Yahoo", "De-americanizing SPY 2026-07-17", "Calibrating SPY
2026-07-17 (LQD)", "Fitting term structure for QQQ", "Computing densities …",
"Calibrating SPY local-vol surface").

Design constraints (CLAUDE.md: compute must stay lightning-fast):
  * A push/update/pop is a single dict mutation under a short lock — it is placed
    only at COARSE boundaries (per fetch, per node, per surface), never inside a
    numeric inner loop, so it adds no measurable cost to a fit.
  * Activities form a stack of frames. The displayed activity is the most recent
    one still in flight, so a nested step (de-am inside a calibrate) narrates the
    inner step and falls back to the outer one when it finishes. This is also how
    cross-thread activity behaves (the background calibration job, the scheduler
    and a synchronous read request can each have a live frame): the most recently
    started one is shown, the rest resume as it pops.
  * A monotonic ``seq`` bumps on every change so the frontend can tell a fresh
    narration from a repeat without diffing strings.

Use the context manager so a frame is always popped, even on error:

    with state.activity.activity("calibrate", f"Calibrating {ticker} {iso}") as act:
        ...
        act.detail("de-americanizing")
        ...
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass
class ActivityEvent:
    """A snapshot of the current top-of-stack engine activity (or idle)."""

    active: bool = False
    stage: str = ""  # coarse kind: fetch | calibrate | localvol | term | density | surface
    message: str = ""  # primary line, e.g. "Calibrating SPY 2026-07-17 (LQD)"
    detail: str = ""  # secondary line, e.g. "de-americanizing"
    done: int = 0  # progress numerator (0 with total 0 => indeterminate)
    total: int = 0  # progress denominator
    seq: int = 0  # monotonic; advances on every change


@dataclass
class _Frame:
    fid: int
    stage: str
    message: str
    detail: str
    done: int
    total: int


class ActivityHandle:
    """Returned by ``activity(...)``; refines the live frame as a step progresses."""

    def __init__(self, reporter: "ActivityReporter", fid: int) -> None:
        self._reporter = reporter
        self._fid = fid

    def update(
        self,
        *,
        message: str | None = None,
        detail: str | None = None,
        done: int | None = None,
        total: int | None = None,
    ) -> None:
        self._reporter._update(self._fid, message, detail, done, total)

    def detail(self, text: str) -> None:
        """Shorthand: set just the secondary line (e.g. 'de-americanizing')."""
        self._reporter._update(self._fid, None, text, None, None)


class ActivityReporter:
    """Thread-safe stack of in-flight engine activities (see module doc)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frames: list[_Frame] = []
        self._seq = 0
        self._next_id = 0

    def push(
        self, stage: str, message: str, detail: str = "", done: int = 0, total: int = 0
    ) -> int:
        with self._lock:
            fid = self._next_id
            self._next_id += 1
            self._frames.append(_Frame(fid, stage, message, detail, done, total))
            self._seq += 1
            return fid

    def _update(
        self,
        fid: int,
        message: str | None,
        detail: str | None,
        done: int | None,
        total: int | None,
    ) -> None:
        with self._lock:
            for f in self._frames:
                if f.fid == fid:
                    if message is not None:
                        f.message = message
                    if detail is not None:
                        f.detail = detail
                    if done is not None:
                        f.done = done
                    if total is not None:
                        f.total = total
                    self._seq += 1
                    return

    def pop(self, fid: int) -> None:
        with self._lock:
            before = len(self._frames)
            self._frames = [f for f in self._frames if f.fid != fid]
            if len(self._frames) != before:
                self._seq += 1

    @contextmanager
    def activity(
        self, stage: str, message: str, detail: str = "", done: int = 0, total: int = 0
    ) -> Iterator[ActivityHandle]:
        """Push a frame for the duration of the block; always pop on exit."""
        fid = self.push(stage, message, detail, done, total)
        try:
            yield ActivityHandle(self, fid)
        finally:
            self.pop(fid)

    def snapshot(self) -> ActivityEvent:
        """The most-recent in-flight activity, or an idle event when nothing runs."""
        with self._lock:
            if not self._frames:
                return ActivityEvent(active=False, seq=self._seq)
            f = self._frames[-1]
            return ActivityEvent(
                active=True,
                stage=f.stage,
                message=f.message,
                detail=f.detail,
                done=f.done,
                total=f.total,
                seq=self._seq,
            )

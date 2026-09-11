"""One series run's state shared by its two threads (SERIES ARC, 2026-09-11b).

The harvest thread PRODUCES frames as their chains land; the lane thread
CONSUMES them in index order — a frame's fits start as soon as it lands, and
an ongoing fit never holds the next fetch: the harvest keeps its own pace
(Massive's ~12 s per frame on the desk, a live series' tick clock) while
the lanes work on what has landed. Before this the runner harvested every
frame and only then ran the lanes: ten frames meant two minutes without a
smile, and a live series fitted nothing until its last instant.

``RunFeed`` also merges the progress the two threads report into ONE
document. Each writes its own fields and its own label (the harvest:
``framesReady`` + "Harvesting …"; the lanes: ``fitsTotal`` / ``fitsDone`` +
"Calibrating …"); the merge composes ``current`` from both labels and
checkpoints the whole progress under one lock, so the store never sees one
thread's fields clobber the other's.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterator

from volfit.api.schemas_series import FrameDoc, SeriesDoc, SeriesProgress

#: Frame statuses the harvest leaves alone in a run (they have already landed).
LANDED = frozenset({"ready", "skipped"})
_KEEP = object()  # "leave this label as it is"


class RunFeed:
    """The landed frames, the harvest-over flag and the merged progress of
    one run. ``checkpoint`` persists a progress document."""

    def __init__(self, doc: SeriesDoc, checkpoint: Callable[[SeriesProgress], None],
                 harvest_over: bool = False) -> None:
        self.series_id = doc.id
        self.n_frames = len(doc.frames)
        self._checkpoint = checkpoint
        self._cond = threading.Condition()
        self._frames: dict[int, FrameDoc] = {f.idx: f for f in doc.frames if f.status in LANDED}
        self._harvest_over = harvest_over
        self._plock = threading.Lock()
        self._progress = doc.progress
        self._labels: dict[str, str | None] = {"harvest": None, "fit": None}

    # ---------------------------------------------------------- producer
    def land(self, frame: FrameDoc) -> None:
        """The harvest thread: this frame's harvest ended (ready or failed)."""
        with self._cond:
            self._frames[frame.idx] = frame
            self._cond.notify_all()

    def harvest_over(self) -> None:
        """The harvest thread is done (finished, paused, cancelled or dead):
        no further frame will land in this run."""
        with self._cond:
            self._harvest_over = True
            self._cond.notify_all()

    # ---------------------------------------------------------- consumer
    def frames_as_ready(self, interrupted: Callable[[], bool] | None = None,
                        poll: float = 0.5) -> Iterator[FrameDoc]:
        """The run's frames in index order as they land — the ready ones;
        failed and skipped frames are passed over. Ends once the harvest is
        over and every landed frame was yielded, or when a frame will never
        land (the harvest stopped before it), or on ``interrupted()``."""
        k = 0
        while k < self.n_frames:
            with self._cond:
                while k not in self._frames and not self._harvest_over:
                    if interrupted is not None and interrupted():
                        return
                    self._cond.wait(poll)
                frame = self._frames.get(k)
            if frame is None:
                return
            k += 1
            if frame.status == "ready":
                yield frame

    def landed(self) -> dict[int, FrameDoc]:
        with self._cond:
            return dict(self._frames)

    # ---------------------------------------------------------- progress
    def advance(self, harvest: str | None | object = _KEEP, fit: str | None | object = _KEEP,
                **fields) -> SeriesProgress:
        """Merge ``fields`` (and either thread's label) into the run's
        progress and checkpoint it. ``current`` = the harvest label · the fit
        label, whichever are set."""
        with self._plock:
            if harvest is not _KEEP:
                self._labels["harvest"] = harvest  # type: ignore[assignment]
            if fit is not _KEEP:
                self._labels["fit"] = fit  # type: ignore[assignment]
            current = " · ".join(v for v in (self._labels["harvest"], self._labels["fit"]) if v)
            self._progress = self._progress.model_copy(update={**fields, "current": current or None})
            self._checkpoint(self._progress)
            return self._progress

    @property
    def progress(self) -> SeriesProgress:
        with self._plock:
            return self._progress


def expected_fits(doc: SeriesDoc, landed: dict[int, FrameDoc]) -> int:
    """The fits a run will store: per frame not skipped / failed, one per
    (lane, rung) plus one per LV lane. A frame not landed yet counts the
    rungs of the last ready frame (else the pinned ladder's, else six), so
    the bar's total settles as frames land instead of growing from zero."""
    known = [len(f.expiries) for f in landed.values() if f.status == "ready"]
    ladder = doc.spec.ladder
    pinned = len(ladder.expiries) or 6
    default = known[-1] if known else min(pinned, ladder.maxExpiries or pinned)
    per_rung = len(doc.spec.lanes)
    lv_rows = sum(1 for lane in doc.spec.lanes if lane.family == "lv")
    total = 0
    for f in doc.frames:
        f = landed.get(f.idx, f)
        if f.status in ("skipped", "failed"):
            continue
        rungs = len(f.expiries) if f.status == "ready" else default
        total += rungs * per_rung + lv_rows
    return total

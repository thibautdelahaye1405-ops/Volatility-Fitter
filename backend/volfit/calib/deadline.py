"""A cooperative wall-clock deadline for one calibration (SERIES ARC, 2026-09-11).

The series lane runner caps every (lane, frame) calibration with a frame
budget (``SeriesSpec.frameBudgetSeconds``). The fit stack has no
interruptible solver, so the budget is enforced at the seams where a solve
is about to start: between the desk's calibration items
(``workflow.calibrate_ticker``) and before every joint refit of the calendar
repair (``calib.symmetric.repair_surface``) — the loop that grinds through
its escalations when a lane's predictions are calendar-inconsistent (the
active-filter finding of 2026-09-10: 17 minutes on one frame, then never).

A deadline is a ``perf_counter`` epoch, or None for no budget — the desk's
live Calibrate never sets one, so every path is byte-identical there. The
clock is read through ``now`` so a test can drive it.
"""

from __future__ import annotations

from time import perf_counter

#: The clock the checks read (tests monkeypatch it).
now = perf_counter


class FitDeadlineExceeded(RuntimeError):
    """Raised at a check point once the deadline has passed. The caller keeps
    whatever the calibration committed before it (the series runner keeps
    the phase-A slice fits and fails the remaining rows with this reason)."""


def check_deadline(deadline: float | None, about_to: str) -> None:
    """Raise ``FitDeadlineExceeded`` when ``deadline`` (a ``perf_counter``
    epoch) has passed; ``about_to`` names the work that would have started
    ("ALPHA calendar repair", "the LV surface") for the error text."""
    if deadline is not None and now() > deadline:
        raise FitDeadlineExceeded(f"frame budget exceeded before {about_to}")

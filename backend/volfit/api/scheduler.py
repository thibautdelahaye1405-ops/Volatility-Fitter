"""Backend scheduler: timed spot polling + options auto-fetch (the workflow).

A single daemon thread wakes every ``TICK`` seconds and, reading the live Options
config each time:

  * when ``spotMode == "realtime"``  — every ``spotPollSeconds``, probe the
    provider spot and transport the surface (``workflow.fetch_spots``, no refit);
  * when ``optionsFetchMode == "auto"`` — every ``optionsFetchMinutes``, refetch
    the option chains (``workflow.fetch_options``), which auto-calibrates the lit
    nodes in the background when ``autoCalibrate`` is on.

Every tick is wrapped in try/except so a transient provider error never kills the
loop. The thread is opt-in (``create_app(enable_scheduler=True)``; serve.py turns
it on) so the test app and the synthetic offline mode never fetch behind your
back. Status (with countdowns) backs the TopBar fetch controls.
"""

from __future__ import annotations

import threading
import time

#: Scheduler wake cadence; the per-mode intervals are multiples of this.
TICK_SECONDS = 1.0


class Scheduler:
    """One daemon thread driving the timed spot / options fetches."""

    def __init__(self, state) -> None:
        self._state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_spot = 0.0  # monotonic stamps of the last fired fetch
        self._last_options = 0.0

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        now = time.monotonic()
        self._last_spot = self._last_options = now  # first fetch waits one interval
        self._thread = threading.Thread(target=self._run, name="volfit-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --------------------------------------------------------------- loop
    def _run(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            try:
                self.tick(time.monotonic())
            except Exception:
                pass  # a bad tick (provider hiccup) never kills the scheduler

    def tick(self, now: float) -> None:
        """One scheduler step (pure of the timer, so it is unit-testable)."""
        from volfit.api import workflow

        opts = self._state.options()
        if opts.spotMode == "realtime" and now - self._last_spot >= opts.spotPollSeconds:
            self._last_spot = now
            workflow.fetch_spots(self._state)
        if (
            opts.optionsFetchMode == "auto"
            and now - self._last_options >= opts.optionsFetchMinutes * 60.0
        ):
            self._last_options = now
            workflow.fetch_options(self._state)

    # ------------------------------------------------------------- status
    def seconds_to_next_options(self, now: float | None = None) -> float:
        opts = self._state.options()
        if opts.optionsFetchMode != "auto":
            return -1.0
        now = time.monotonic() if now is None else now
        return max(0.0, opts.optionsFetchMinutes * 60.0 - (now - self._last_options))

    def seconds_to_next_spot(self, now: float | None = None) -> float:
        opts = self._state.options()
        if opts.spotMode != "realtime":
            return -1.0
        now = time.monotonic() if now is None else now
        return max(0.0, opts.spotPollSeconds - (now - self._last_spot))

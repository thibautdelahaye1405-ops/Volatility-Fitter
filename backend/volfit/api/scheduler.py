"""Backend scheduler: timed spot polling + options auto-fetch (the workflow).

A single daemon thread wakes every ``TICK`` seconds and, reading the live Options
config each time:

  * when ``spotMode == "realtime"``  — every ``spotPollSeconds``, probe the
    provider spot and transport the surface (``workflow.fetch_spots``, no refit);
  * when ``optionsFetchMode == "auto"`` — every ``optionsFetchMinutes``, refetch
    the option chains (``workflow.fetch_options``), which auto-calibrates the lit
    nodes in the background when ``autoCalibrate`` is on;
  * V3.7 rider — when ``schedulerUnifiedFetch`` is ALSO on, that options timer
    runs the unified snapshot verb (``workflow_fetch.fetch_snapshot``: chains →
    spot transport → optional prior roll → optional auto-calibrate, exactly
    ``POST /fetch/snapshot``) instead of the bare chain refetch, and re-arms the
    spot timer (the double-fire guard, see ``Scheduler``). Off (default) = the
    legacy split timers, byte-identical.

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
    """One daemon thread driving the timed spot / options fetches.

    Double-fire guard (``schedulerUnifiedFetch`` on): a unified snapshot tick
    already transports the live spot, so it stamps ``_last_spot`` as well as
    ``_last_options`` and is evaluated BEFORE the realtime spot branch — a spot
    poll due on the same tick is absorbed (never fired twice) and the spot
    countdown restarts from the full ``spotPollSeconds``. Between snapshot
    ticks the spot poll keeps its own cadence untouched.
    """

    def __init__(self, state) -> None:
        self._state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_spot = 0.0  # monotonic stamps of the last fired fetch
        self._last_options = 0.0
        self._last_refit = 0.0  # last streaming full-refit cycle

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        now = time.monotonic()
        # first fetch of each kind waits one interval
        self._last_spot = self._last_options = self._last_refit = now
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

        # Keep the real-time WS stream (Massive) in sync with the active source +
        # spot mode; cheap no-op when already correct.
        self._state.sync_streaming()

        opts = self._state.options()
        # The options timer is read once up front: the branches below never
        # touch ``_last_options``, so this equals the legacy tail-position test.
        options_due = (
            opts.optionsFetchMode == "auto"
            and now - self._last_options >= opts.optionsFetchMinutes * 60.0
        )
        # V3.7 rider — the unified branch goes FIRST so a realtime spot poll due
        # on this same tick is absorbed (the snapshot transports the spot itself;
        # ``_last_spot = now`` is the double-fire guard of the class docstring).
        if options_due and opts.schedulerUnifiedFetch:
            from volfit.api import workflow_fetch  # lazy: workflow_fetch -> workflow

            self._last_options = now
            self._last_spot = now
            workflow_fetch.fetch_snapshot(self._state, fit_mode=self._state.last_fit_mode)
            options_due = False
        if opts.spotMode == "realtime" and now - self._last_spot >= opts.spotPollSeconds:
            self._last_spot = now
            workflow.fetch_spots(self._state)
        # Throttled full refit while a live WS book is streaming (book-driven,
        # seconds cadence) — distinct from the minutes-cadence REST auto-fetch.
        # Gated by autoCalibrate: it is the master switch for unattended refits, so
        # with it OFF the surface only moves via the spot-transport poll above and
        # nodes stay frozen/stale until an explicit Calibrate.
        if (
            opts.spotMode == "realtime"
            and opts.autoCalibrate
            and now - self._last_refit >= opts.streamRefitSeconds
            and self._state.is_streaming()
        ):
            self._last_refit = now
            workflow.stream_refit(self._state, self._state.last_fit_mode)
        if options_due:  # legacy split path (gate off): the bare chain refetch
            self._last_options = now
            workflow.fetch_options(self._state, fit_mode=self._state.last_fit_mode)

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

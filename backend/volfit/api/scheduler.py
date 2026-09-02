"""Backend scheduler: the Auto-update timer (no stream) and the streaming loop.

A single daemon thread wakes every ``TICK`` seconds and, reading the live Options
config each time, applies the data model of 2026-09-02g:

  * a calibration always prices spot and quotes from ONE snapshot (a fetch, or
    a synchronous read of the streaming book); a spot-only update only
    TRANSPORTS the surface — never a refit, in either calibration mode;
  * WITH a live book (``state.is_streaming()``) spot and quotes flow
    continuously and ``autoUpdate`` is inert: every ``STREAM_SYNC_SECONDS`` the
    market-following tickers take the book spot (``workflow.sync_market_shifts``,
    a free read) and, with ``autoCalibrate`` on, every ``streamRefitSeconds`` the
    chains are rebuilt from the book and the lit nodes recalibrated
    (``workflow.stream_refit`` — the stream's own snapshot tick);
    ``streamFreezeFit`` holds both (the fit stays at its calibration spot);
  * WITHOUT a stream, ``autoUpdate`` every ``autoUpdateSeconds``: "spot" probes
    the provider spot and transports (``workflow.fetch_spots``); "snapshot" runs
    the unified Snapshot sequence (``workflow_fetch.fetch_snapshot``: chains →
    spot transport → optional prior roll → auto-calibrate when on, exactly
    ``POST /fetch/snapshot``; the model floors the cadence at 15 s); "off" waits
    for a manual Fetch.

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
#: While a book streams: how often the market-following tickers' shift is moved
#: to the book spot (a free read; the tick stream already frames the chart live).
STREAM_SYNC_SECONDS = 5.0


def exchange_today() -> "date":
    """The current calendar day in exchange time (America/New_York) — the day
    the reference date follows on a live server (``AppState.roll_reference_date``).
    A function (not a constant) so tests can monkeypatch the clock."""
    from datetime import datetime

    from volfit.data.expiry_time import ET

    return datetime.now(ET).date()


class Scheduler:
    """One daemon thread driving the Auto-update timer and the streaming loop.

    One request-path timer (``_last_update``: the spot probe OR the unified
    snapshot, per ``autoUpdate``), one book-spot sync stamp (``_last_spot``) and
    one streaming-refit stamp (``_last_refit``); the streaming branch returns
    before the timer, so a live book never fires a request-path fetch.
    """

    def __init__(self, state) -> None:
        self._state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_spot = 0.0  # monotonic stamps: last book-spot sync
        self._last_update = 0.0  # last Auto-update tick (spot probe / snapshot)
        self._last_refit = 0.0  # last streaming refit cycle

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        now = time.monotonic()
        # first fetch of each kind waits one interval
        self._last_spot = self._last_update = self._last_refit = now
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

        # Calendar-day roll (the 2026-08-25 "reference_date never rolls past
        # midnight" gap): once per exchange-time day, ask the state to advance
        # its reference date — inert unless the app was built with
        # follow_wall_clock (serve.py) and the day really moved. Exchange time
        # (ET), not UTC/local: expiry and session semantics live there.
        today = exchange_today()
        if today != getattr(self, "_last_day", None):
            self._last_day = today
            self._state.roll_reference_date(today)

        # Keep the real-time WS stream (Massive) in sync with the active source +
        # spot mode; cheap no-op when already correct.
        self._state.sync_streaming()

        opts = self._state.options()
        streaming = self._state.streaming_tickers()  # per ticker: a pinned Bloomberg
        request = self._state.request_tickers()  # name streams beside Cboe names
        if streaming and not opts.streamFreezeFit:
            # The live books: spot and quotes flow continuously — the market-
            # following tickers take the book spot at the sync cadence (a free
            # read, pure transport; scenario tickers keep their dial) and, with
            # autoCalibrate on (the master switch for unattended refits), the
            # streaming refit rebuilds THOSE chains from the book and
            # recalibrates the lit nodes every ``streamRefitSeconds``.
            if now - self._last_spot >= STREAM_SYNC_SECONDS:
                self._last_spot = now
                workflow.sync_market_shifts(self._state, streaming)
            if opts.autoCalibrate and now - self._last_refit >= opts.streamRefitSeconds:
                self._last_refit = now
                workflow.stream_refit(self._state, self._state.last_fit_mode, streaming)
        # The request path (the tickers WITHOUT a book): one timer, its verb
        # chosen by ``autoUpdate``; inert while every ticker streams.
        if not request or opts.autoUpdate == "off" or now - self._last_update < opts.autoUpdateSeconds:
            return
        self._last_update = now
        if opts.autoUpdate == "snapshot":
            from volfit.api import workflow_fetch  # lazy: workflow_fetch -> workflow

            # Quotes + spot in one snapshot (then the optional prior roll and, with
            # autoCalibrate on, the background calibration of the lit nodes).
            workflow_fetch.fetch_snapshot(self._state, request, fit_mode=self._state.last_fit_mode)
        else:  # "spot": the probe + transport — never a refit
            workflow.fetch_spots(self._state, request)

    # ------------------------------------------------------------- status
    def seconds_to_next_update(self, now: float | None = None) -> float:
        """Countdown to the next Auto-update tick; -1 when off or while a book
        streams (the timer is inert then — the UI shows a button instead)."""
        opts = self._state.options()
        if opts.autoUpdate == "off" or not self._state.request_tickers():
            return -1.0
        now = time.monotonic() if now is None else now
        return max(0.0, opts.autoUpdateSeconds - (now - self._last_update))

    def seconds_to_next_refit(self, now: float | None = None) -> float:
        """Countdown to the next streaming refit; -1 unless a book streams with
        autoCalibrate on and the fit not frozen."""
        opts = self._state.options()
        if not (self._state.streaming_tickers() and opts.autoCalibrate and not opts.streamFreezeFit):
            return -1.0
        now = time.monotonic() if now is None else now
        return max(0.0, opts.streamRefitSeconds - (now - self._last_refit))

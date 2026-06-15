"""Backend scheduler: timed spot/options fetch ticks (driven deterministically)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.scheduler import Scheduler
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _state(**opts) -> AppState:
    state = AppState(REF_DATE)
    if opts:
        state.set_options(state.options().model_copy(update=opts))
    return state


def test_tick_auto_fetches_options_after_interval():
    state = _state(optionsFetchMode="auto", optionsFetchMinutes=1.0, autoCalibrate=False)
    sched = Scheduler(state)
    v0 = state.data_version(TICKER)
    sched.tick(now=0.0)  # initializes nothing; first fetch waits an interval
    # last_options starts at 0 here (fresh Scheduler), so now=0 -> elapsed 0 < 60.
    assert state.data_version(TICKER) == v0
    sched.tick(now=120.0)  # > 60s elapsed -> fires the options fetch
    assert state.data_version(TICKER) == v0 + 1


def test_tick_stream_refits_only_while_streaming(monkeypatch):
    """The throttled full-refit branch fires on the streamRefitSeconds cadence ONLY
    when realtime + autoCalibrate ON + a live book is streaming; otherwise never."""
    from volfit.api import workflow

    state = _state(
        spotMode="realtime",
        autoCalibrate=True,  # master switch ON
        spotPollSeconds=3600.0,  # park the spot poll so it doesn't fire here
        streamRefitSeconds=2.0,
        optionsFetchMode="on_demand",
    )
    calls = {"refit": 0}
    monkeypatch.setattr(workflow, "stream_refit", lambda s, *a, **k: calls.__setitem__("refit", calls["refit"] + 1))
    monkeypatch.setattr(workflow, "fetch_spots", lambda s, *a, **k: None)

    sched = Scheduler(state)

    state.is_streaming = lambda: False  # not streaming -> no refit even past interval
    sched.tick(now=100.0)
    assert calls["refit"] == 0

    state.is_streaming = lambda: True  # streaming -> refit fires
    sched.tick(now=200.0)
    assert calls["refit"] == 1

    sched.tick(now=201.0)  # within the throttle window -> no second refit
    assert calls["refit"] == 1


def test_tick_no_stream_refit_when_autocalibrate_off(monkeypatch):
    """autoCalibrate OFF suppresses the unattended streaming refit even while a live
    book streams (the surface still tracks spot via the transport poll)."""
    from volfit.api import workflow

    state = _state(
        spotMode="realtime",
        autoCalibrate=False,  # master switch OFF
        spotPollSeconds=3600.0,
        streamRefitSeconds=2.0,
        optionsFetchMode="on_demand",
    )
    calls = {"refit": 0}
    monkeypatch.setattr(workflow, "stream_refit", lambda s, *a, **k: calls.__setitem__("refit", calls["refit"] + 1))
    monkeypatch.setattr(workflow, "fetch_spots", lambda s, *a, **k: None)

    sched = Scheduler(state)
    state.is_streaming = lambda: True
    sched.tick(now=10_000.0)  # well past the interval, streaming, but autocal off
    assert calls["refit"] == 0


def test_tick_does_nothing_on_demand():
    state = _state(optionsFetchMode="on_demand", spotMode="static")
    sched = Scheduler(state)
    v0 = state.data_version(TICKER)
    sched.tick(now=10_000.0)
    assert state.data_version(TICKER) == v0


def test_seconds_to_next_minus_one_when_off():
    state = _state(optionsFetchMode="on_demand", spotMode="static")
    sched = Scheduler(state)
    assert sched.seconds_to_next_options(now=0.0) == -1.0
    assert sched.seconds_to_next_spot(now=0.0) == -1.0


def test_scheduler_endpoint_reports_modes():
    with TestClient(create_app(reference_date=REF_DATE)) as client:
        st = client.get("/scheduler").json()
        assert st["spotMode"] == "static"
        assert st["optionsFetchMode"] == "on_demand"
        assert st["running"] is False  # test app does not start the thread
        assert st["secondsToNextOptions"] == -1.0


def test_scheduler_thread_runs_when_enabled():
    """create_app(enable_scheduler=True) starts the daemon under the lifespan."""
    with TestClient(create_app(reference_date=REF_DATE, enable_scheduler=True)) as client:
        assert client.get("/scheduler").json()["running"] is True

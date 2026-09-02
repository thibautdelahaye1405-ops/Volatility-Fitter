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


def test_tick_syncs_market_followers_to_the_book_in_static_mode(monkeypatch):
    """Static spot mode + a live book: at the spot-poll cadence the scheduler
    moves the MARKET-following tickers to the book spot (a free read, no
    probe); never without a stream, never the realtime probe path."""
    from volfit.api import workflow

    state = _state(spotMode="static", spotPollSeconds=5.0, optionsFetchMode="on_demand")
    calls = {"sync": 0, "probe": 0}
    monkeypatch.setattr(workflow, "sync_market_shifts", lambda s, *a, **k: calls.__setitem__("sync", calls["sync"] + 1))
    monkeypatch.setattr(workflow, "fetch_spots", lambda s, *a, **k: calls.__setitem__("probe", calls["probe"] + 1))
    sched = Scheduler(state)
    state.is_streaming = lambda: False
    sched.tick(now=100.0)  # no book: nothing to sync
    assert calls == {"sync": 0, "probe": 0}
    state.is_streaming = lambda: True
    sched.tick(now=200.0)
    assert calls == {"sync": 1, "probe": 0}
    sched.tick(now=202.0)  # inside the cadence: quiet
    assert calls["sync"] == 1
    sched.tick(now=206.0)
    assert calls["sync"] == 2


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


# ---------------------------------------------------------------------------
# V3.7 rider: scheduler consolidation onto the unified snapshot verb. The gate
# (OptionsSettings.schedulerUnifiedFetch) is OFF by default -> legacy path.
# ---------------------------------------------------------------------------


def _counting(calls: dict, key: str, seen: list | None = None):
    """Monkeypatch stub: counts calls under ``key`` and records the kwargs."""

    def _stub(state, *a, **k):
        calls[key] = calls.get(key, 0) + 1
        if seen is not None:
            seen.append(k)

    return _stub


def test_tick_unified_fetch_runs_snapshot_instead_of_options(monkeypatch):
    """Gate ON + auto mode: after the interval the options timer fires ONE
    unified snapshot (with the session's fit mode); the bare chain refetch
    never runs; the next tick inside the interval fires nothing."""
    from volfit.api import workflow, workflow_fetch

    state = _state(
        optionsFetchMode="auto",
        optionsFetchMinutes=1.0,
        autoCalibrate=False,
        schedulerUnifiedFetch=True,
    )
    calls: dict = {}
    seen: list = []
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", _counting(calls, "snapshot", seen))
    monkeypatch.setattr(workflow, "fetch_options", _counting(calls, "options"))

    sched = Scheduler(state)
    sched.tick(now=0.0)  # first fetch waits one interval
    assert calls == {}
    sched.tick(now=120.0)  # > 60s elapsed -> the unified verb, not fetch_options
    assert calls == {"snapshot": 1}
    assert seen[0]["fit_mode"] == state.last_fit_mode
    sched.tick(now=121.0)  # inside the interval -> nothing
    assert calls == {"snapshot": 1}
    assert sched.seconds_to_next_options(now=121.0) == 59.0


def test_tick_unified_fetch_absorbs_spot_poll_due_on_same_tick(monkeypatch):
    """Gate ON + realtime spots, both timers due on the same tick: the snapshot
    already transported the spot, so fetch_spots is NOT fired separately and
    the spot countdown re-arms to the full spotPollSeconds (the double-fire
    guard). Between snapshot ticks the spot poll keeps its own cadence."""
    from volfit.api import workflow, workflow_fetch

    state = _state(
        optionsFetchMode="auto",
        optionsFetchMinutes=1.0,
        spotMode="realtime",
        spotPollSeconds=5.0,
        autoCalibrate=False,
        schedulerUnifiedFetch=True,
    )
    calls: dict = {}
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", _counting(calls, "snapshot"))
    monkeypatch.setattr(workflow, "fetch_spots", _counting(calls, "spots"))

    sched = Scheduler(state)
    sched.tick(now=120.0)  # both due: one snapshot, no separate spot poll
    assert calls == {"snapshot": 1}
    assert sched.seconds_to_next_spot(now=120.0) == 5.0  # re-armed in full
    sched.tick(now=123.0)  # spot not yet due again (3s < 5s)
    assert calls == {"snapshot": 1}
    sched.tick(now=126.0)  # the spot poll resumes on its own cadence
    assert calls == {"snapshot": 1, "spots": 1}


def test_tick_legacy_path_never_calls_snapshot(monkeypatch):
    """Gate OFF (the default): the split timers each fire on their own — the
    unified verb is never reached, even with both timers due on one tick."""
    from volfit.api import workflow, workflow_fetch

    state = _state(
        optionsFetchMode="auto",
        optionsFetchMinutes=1.0,
        spotMode="realtime",
        spotPollSeconds=5.0,
        autoCalibrate=False,
    )
    assert state.options().schedulerUnifiedFetch is False  # byte-identical default
    calls: dict = {}
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", _counting(calls, "snapshot"))
    monkeypatch.setattr(workflow, "fetch_options", _counting(calls, "options"))
    monkeypatch.setattr(workflow, "fetch_spots", _counting(calls, "spots"))

    sched = Scheduler(state)
    sched.tick(now=120.0)
    assert calls == {"spots": 1, "options": 1}
    assert "snapshot" not in calls


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
        # The unified-fetch gate is echoed so the status bar can label the
        # countdown honestly (default off; flips with the Options PUT).
        assert st["unifiedFetch"] is False
        r = client.put("/settings/options", json={"schedulerUnifiedFetch": True})
        assert r.status_code == 200
        assert client.get("/scheduler").json()["unifiedFetch"] is True


def test_scheduler_thread_runs_when_enabled():
    """create_app(enable_scheduler=True) starts the daemon under the lifespan."""
    with TestClient(create_app(reference_date=REF_DATE, enable_scheduler=True)) as client:
        assert client.get("/scheduler").json()["running"] is True

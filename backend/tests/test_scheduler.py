"""Backend scheduler: the Auto-update timer (no stream) and the streaming loop,
driven deterministically (the 2026-09-02g data model — see scheduler.py).

  * a spot-only update only TRANSPORTS (never a refit, in either mode);
  * without a stream, ``autoUpdate`` = off | spot | snapshot every
    ``autoUpdateSeconds`` (snapshot floored at 15 s);
  * with a live book, Auto-update is inert: the book spot is synced to the
    market followers and, with autoCalibrate on, the streaming refit runs every
    ``streamRefitSeconds``; ``streamFreezeFit`` holds both.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.scheduler import STREAM_SYNC_SECONDS, Scheduler
from volfit.api.schemas import SNAPSHOT_FLOOR_SECONDS, OptionsSettings
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _state(**opts) -> AppState:
    state = AppState(REF_DATE)
    if opts:
        state.set_options(state.options().model_copy(update=opts))
    state.is_streaming = lambda ticker=None: False  # the request path unless a test streams
    return state


def _counting(calls: dict, key: str, seen: list | None = None):
    """Monkeypatch stub: counts calls under ``key`` and records the kwargs."""

    def _stub(state, *a, **k):
        calls[key] = calls.get(key, 0) + 1
        if seen is not None:
            seen.append(k)

    return _stub


# ------------------------------------------------------------ the request path

def test_snapshot_tick_runs_the_unified_snapshot_after_the_interval(monkeypatch):
    """"snapshot": after the interval ONE unified snapshot (with the session's
    fit mode) — never the bare chain refetch nor a separate spot probe; the
    next tick inside the interval fires nothing."""
    from volfit.api import workflow, workflow_fetch

    state = _state(autoUpdate="snapshot", autoUpdateSeconds=60.0, autoCalibrate=False)
    calls: dict = {}
    seen: list = []
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", _counting(calls, "snapshot", seen))
    monkeypatch.setattr(workflow, "fetch_options", _counting(calls, "options"))
    monkeypatch.setattr(workflow, "fetch_spots", _counting(calls, "spots"))
    sched = Scheduler(state)
    sched.tick(now=0.0)  # the first tick waits one interval
    assert calls == {}
    sched.tick(now=120.0)
    assert calls == {"snapshot": 1}
    assert seen[0]["fit_mode"] == state.last_fit_mode
    sched.tick(now=121.0)
    assert calls == {"snapshot": 1}
    assert sched.seconds_to_next_update(now=121.0) == 59.0


def test_snapshot_tick_really_refreshes_the_chain():
    state = _state(autoUpdate="snapshot", autoUpdateSeconds=60.0, autoCalibrate=False)
    sched = Scheduler(state)
    v0 = state.data_version(TICKER)
    sched.tick(now=0.0)
    assert state.data_version(TICKER) == v0
    sched.tick(now=120.0)  # > 60 s elapsed -> quotes + spot refreshed
    assert state.data_version(TICKER) == v0 + 1


def test_spot_tick_probes_and_transports_never_refits(monkeypatch):
    """"spot": the probe + transport at the cadence; no snapshot, no chain
    refetch, no calibration even with autoCalibrate ON (point 6 of the model)."""
    from volfit.api import workflow, workflow_fetch

    state = _state(autoUpdate="spot", autoUpdateSeconds=5.0, autoCalibrate=True)
    calls: dict = {}
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", _counting(calls, "snapshot"))
    monkeypatch.setattr(workflow, "fetch_options", _counting(calls, "options"))
    monkeypatch.setattr(workflow, "stream_refit", _counting(calls, "refit"))
    monkeypatch.setattr(workflow, "calibrate_all", _counting(calls, "calibrate"))
    monkeypatch.setattr(workflow, "fetch_spots", _counting(calls, "spots"))
    sched = Scheduler(state)
    sched.tick(now=120.0)
    assert calls == {"spots": 1}
    sched.tick(now=123.0)  # inside the cadence
    assert calls == {"spots": 1}
    sched.tick(now=126.0)
    assert calls == {"spots": 2}
    assert sched.seconds_to_next_refit(now=126.0) == -1.0  # no stream: no refit loop


def test_spot_tick_transports_the_real_state_without_a_refit():
    """Unmocked: a spot tick never bumps the data version (no chain refetch)."""
    state = _state(autoUpdate="spot", autoUpdateSeconds=5.0, autoCalibrate=True)
    sched = Scheduler(state)
    v0 = state.data_version(TICKER)
    sched.tick(now=120.0)
    assert state.data_version(TICKER) == v0


def test_off_does_nothing():
    state = _state(autoUpdate="off")
    sched = Scheduler(state)
    v0 = state.data_version(TICKER)
    sched.tick(now=10_000.0)
    assert state.data_version(TICKER) == v0
    assert sched.seconds_to_next_update(now=0.0) == -1.0
    assert sched.seconds_to_next_refit(now=0.0) == -1.0


def test_snapshot_cadence_is_floored_by_the_model():
    assert OptionsSettings(autoUpdate="snapshot", autoUpdateSeconds=1.0).autoUpdateSeconds == SNAPSHOT_FLOOR_SECONDS
    assert OptionsSettings(autoUpdate="spot", autoUpdateSeconds=1.0).autoUpdateSeconds == 1.0
    assert OptionsSettings(autoUpdate="snapshot", autoUpdateSeconds=30.0).autoUpdateSeconds == 30.0


# -------------------------------------------------------------- the stream

def test_streaming_makes_auto_update_inert_and_syncs_the_book(monkeypatch):
    """With a live book the request-path timer never fires (whatever
    autoUpdate says); the market followers take the book spot every
    STREAM_SYNC_SECONDS (a free read); no refit with autoCalibrate OFF."""
    from volfit.api import workflow, workflow_fetch

    state = _state(autoUpdate="snapshot", autoUpdateSeconds=15.0, autoCalibrate=False)
    calls: dict = {}
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", _counting(calls, "snapshot"))
    monkeypatch.setattr(workflow, "fetch_spots", _counting(calls, "spots"))
    monkeypatch.setattr(workflow, "sync_market_shifts", _counting(calls, "sync"))
    monkeypatch.setattr(workflow, "stream_refit", _counting(calls, "refit"))
    sched = Scheduler(state)
    state.is_streaming = lambda ticker=None: True
    sched.tick(now=100.0)
    assert calls == {"sync": 1}
    sched.tick(now=100.0 + STREAM_SYNC_SECONDS - 1.0)  # inside the sync cadence
    assert calls == {"sync": 1}
    sched.tick(now=100.0 + STREAM_SYNC_SECONDS + 1.0)
    assert calls == {"sync": 2}
    assert sched.seconds_to_next_update(now=200.0) == -1.0  # inert while streaming
    assert sched.seconds_to_next_refit(now=200.0) == -1.0  # autoCalibrate off
    state.is_streaming = lambda ticker=None: False  # the stream drops: the timer is back
    assert sched.seconds_to_next_update(now=200.0) >= 0.0


def test_streaming_refit_follows_autocalibrate_and_its_cadence(monkeypatch):
    """The streaming refit (the stream's quotes + spot tick) fires every
    streamRefitSeconds ONLY while a book streams with autoCalibrate ON."""
    from volfit.api import workflow

    state = _state(autoCalibrate=True, streamRefitSeconds=2.0)
    calls: dict = {}
    monkeypatch.setattr(workflow, "stream_refit", _counting(calls, "refit"))
    monkeypatch.setattr(workflow, "sync_market_shifts", _counting(calls, "sync"))
    sched = Scheduler(state)
    sched.tick(now=100.0)  # not streaming: nothing
    assert calls == {}
    state.is_streaming = lambda ticker=None: True
    sched.tick(now=200.0)
    assert calls["refit"] == 1
    sched.tick(now=201.0)  # inside the throttle window
    assert calls["refit"] == 1
    assert sched.seconds_to_next_refit(now=201.0) == 1.0
    sched.tick(now=202.5)
    assert calls["refit"] == 2


def test_freeze_holds_transport_and_refit_while_streaming(monkeypatch):
    """streamFreezeFit: the fit stays where it was calibrated — no book-spot
    sync, no streaming refit, no request-path fetch either."""
    from volfit.api import workflow, workflow_fetch

    state = _state(autoCalibrate=True, streamRefitSeconds=2.0, streamFreezeFit=True, autoUpdate="spot")
    calls: dict = {}
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", _counting(calls, "snapshot"))
    monkeypatch.setattr(workflow, "fetch_spots", _counting(calls, "spots"))
    monkeypatch.setattr(workflow, "sync_market_shifts", _counting(calls, "sync"))
    monkeypatch.setattr(workflow, "stream_refit", _counting(calls, "refit"))
    sched = Scheduler(state)
    state.is_streaming = lambda ticker=None: True
    sched.tick(now=10_000.0)
    assert calls == {}
    assert sched.seconds_to_next_refit(now=10_000.0) == -1.0
    assert sched.seconds_to_next_update(now=10_000.0) == -1.0


# -------------------------------------------------------- migration + API

def test_legacy_settings_migrate_into_auto_update():
    """Pre-2026-09-02g blobs keep loading: an auto chain timer -> snapshot at
    its minutes cadence; a realtime spot poll -> spot; else off; the legacy
    keys are dropped; an explicit autoUpdate wins over legacy keys."""
    auto = OptionsSettings(**{"optionsFetchMode": "auto", "optionsFetchMinutes": 2.0,
                              "spotMode": "realtime", "spotPollSeconds": 10.0, "schedulerUnifiedFetch": False})
    assert (auto.autoUpdate, auto.autoUpdateSeconds) == ("snapshot", 120.0)
    rt = OptionsSettings(**{"spotMode": "realtime", "spotPollSeconds": 10.0, "optionsFetchMode": "on_demand"})
    assert (rt.autoUpdate, rt.autoUpdateSeconds) == ("spot", 10.0)
    off = OptionsSettings(**{"spotMode": "static", "optionsFetchMode": "on_demand"})
    assert off.autoUpdate == "off"
    explicit = OptionsSettings(**{"spotMode": "realtime", "autoUpdate": "off"})
    assert explicit.autoUpdate == "off"
    assert not any(k in auto.model_dump() for k in ("spotMode", "optionsFetchMode", "schedulerUnifiedFetch"))


def test_scheduler_endpoint_reports_the_model():
    with TestClient(create_app(reference_date=REF_DATE)) as client:
        st = client.get("/scheduler").json()
        assert st["autoUpdate"] == "off" and st["autoUpdateSeconds"] == 5.0
        assert st["running"] is False  # the test app does not start the thread
        assert st["secondsToNextUpdate"] == -1.0 and st["secondsToNextRefit"] == -1.0
        assert st["streaming"] is False and st["streamFreezeFit"] is False
        assert st["streamRefitSeconds"] == 5.0
        r = client.put("/settings/options", json={"autoUpdate": "snapshot", "autoUpdateSeconds": 3.0})
        assert r.status_code == 200
        assert client.get("/settings/options").json()["autoUpdateSeconds"] == SNAPSHOT_FLOOR_SECONDS
        assert client.get("/scheduler").json()["autoUpdate"] == "snapshot"
        # A client on the old shape still lands (migrated).
        r = client.put("/settings/options", json={"spotMode": "realtime", "spotPollSeconds": 7.0})
        assert r.status_code == 200
        st = client.get("/scheduler").json()
        assert st["autoUpdate"] == "spot" and st["autoUpdateSeconds"] == 7.0
        assert client.put("/settings/options", json={"autoUpdate": "sometimes"}).status_code == 422


def test_scheduler_thread_runs_when_enabled():
    """create_app(enable_scheduler=True) starts the daemon under the lifespan."""
    with TestClient(create_app(reference_date=REF_DATE, enable_scheduler=True)) as client:
        assert client.get("/scheduler").json()["running"] is True

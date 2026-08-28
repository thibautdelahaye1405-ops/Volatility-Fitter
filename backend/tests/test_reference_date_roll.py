"""reference_date rolls past midnight on a live server (the 2026-08-25 gap).

Locks:
  * a pinned state (the default, every test/dev app) NEVER rolls — the method
    returns False and nothing changes;
  * with ``follow_wall_clock`` the roll advances the date, drops the chain
    caches, re-resolves the AUTO expiry ladder on the new day (yesterday's
    0-DTE is gone), keeps MANUAL selections minus the expired rungs, bumps every
    fit-key version (the old fit key is stale), rolls the offline provider's
    own reference date and logs an audit event;
  * a same-day / earlier "today" is a no-op; a pinned historical as-of view is
    not rolled;
  * the scheduler tick drives it once per exchange-time day (clock
    monkeypatched), and never on a pinned state.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from volfit.api import create_app, scheduler as scheduler_mod
from volfit.api.scheduler import Scheduler
from volfit.api.service import fit_key
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 10)  # a Wednesday
NEXT = date(2026, 6, 11)


def _state(follow: bool) -> AppState:
    return AppState(REF, provider=SyntheticProvider(reference_date=REF), follow_wall_clock=follow)


def test_pinned_state_never_rolls():
    state = _state(False)
    ticker = state.active_tickers()[0]
    state.snapshot(ticker)  # warm a chain
    key = fit_key(state, ticker, sorted(state.forwards(ticker))[0].isoformat(), "mid")
    assert state.roll_reference_date(NEXT) is False
    assert state.reference_date == REF
    assert state.loaded_snapshot(ticker) is not None  # caches untouched
    assert fit_key(state, ticker, sorted(state.forwards(ticker))[0].isoformat(), "mid") == key


def test_roll_advances_date_clears_caches_and_re_resolves_the_ladder():
    state = _state(True)
    ticker = state.active_tickers()[0]
    provider = state.provider
    state.snapshot(ticker)
    old_isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
    old_key = fit_key(state, ticker, old_isos[0], "mid")
    n_events = len(state.recent_events()) if hasattr(state, "recent_events") else None

    # Roll far enough that the synthetic ladder (anchored on ITS reference
    # date) visibly moves: the whole ladder shifts with the provider's date.
    far = REF + timedelta(days=30)
    assert state.roll_reference_date(far) is True
    assert state.reference_date == far
    assert provider.reference_date == far  # the offline provider rolled too
    assert state.loaded_snapshot(ticker) is None  # chain caches dropped
    new_isos = [e.isoformat() for e in sorted(state.forwards(ticker))]  # re-resolved
    assert new_isos != old_isos
    assert all(date.fromisoformat(i) > far for i in new_isos)  # nothing expired
    assert fit_key(state, ticker, new_isos[0], "mid") != old_key  # versions advanced
    # Same-day / earlier "today" is a no-op.
    assert state.roll_reference_date(far) is False
    assert state.roll_reference_date(REF) is False
    if n_events is not None:
        assert len(state.recent_events()) == n_events + 1


def test_manual_selection_keeps_unexpired_rungs():
    state = _state(True)
    ticker = state.active_tickers()[0]
    state.snapshot(ticker)
    dates = sorted(state.forwards(ticker))
    assert len(dates) >= 2
    state.set_expiries(ticker, dates)  # a CUSTOM (user-pinned) selection of the full ladder
    assert state._selection_mode.get(ticker) == "custom"
    # Roll onto the first rung's date: it expires, the rest survive verbatim.
    first = dates[0]
    assert state.roll_reference_date(first) is True
    assert state._selected[ticker] == [d for d in dates if d > first]
    assert state._selection_mode.get(ticker) == "custom"


def test_pinned_historical_asof_is_not_rolled():
    state = _state(True)
    from volfit.api.state import AsOfSelection

    # The synthetic provider has no prev_close history, so pin the selection
    # directly — the roll only reads ``as_of.mode``.
    state._asof = AsOfSelection(mode="prev_close", day=REF - timedelta(days=1))
    assert state.as_of.mode != "live"
    assert state.roll_reference_date(NEXT) is False
    assert state.reference_date == REF


def test_scheduler_tick_rolls_once_per_exchange_day(monkeypatch):
    clock = {"today": REF}
    monkeypatch.setattr(scheduler_mod, "exchange_today", lambda: clock["today"])
    state = _state(True)
    sched = Scheduler(state)
    sched.tick(0.0)
    assert state.reference_date == REF  # same day: nothing
    clock["today"] = NEXT
    sched.tick(1.0)
    assert state.reference_date == NEXT
    ver = state.options_version
    sched.tick(2.0)  # the same day again: no second roll, no version churn
    assert state.reference_date == NEXT and state.options_version == ver


def test_live_app_wires_follow_wall_clock_and_pinned_app_does_not(monkeypatch):
    clock = {"today": NEXT}
    monkeypatch.setattr(scheduler_mod, "exchange_today", lambda: clock["today"])
    with TestClient(create_app(reference_date=REF)) as c:  # pinned (tests/dev)
        st = c.app.state.volfit
        Scheduler(st).tick(0.0)
        assert st.reference_date == REF
    with TestClient(create_app(reference_date=REF, follow_wall_clock=True)) as c:
        st = c.app.state.volfit
        Scheduler(st).tick(0.0)
        assert st.reference_date == NEXT
        assert c.get("/universe").json()["asOf"] == NEXT.isoformat()

"""Data-age staleness (volfit.api.data_age) — the Massive-staleness slice.

Locks the semantics that keep the signal honest AND quiet: age applies only
to LIVE, real-feed (ticked) chains; synthetic / historical views never warn;
red-stale data fails quality publish-readiness while amber stays advisory;
and the datasources payload carries the worst age for the TopBar pill.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from volfit.api import quality, service
from volfit.api.data_age import (
    age_level,
    chain_age_minutes,
    format_age,
    ticker_ages,
    universe_age,
)
from volfit.api.datasource import datasources_payload
from volfit.api.state import AppState, AsOfSelection

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _age_chain(state: AppState, ticker: str, hours: float, tick: float | None = 0.01):
    """Re-stamp the ticker's cached chain as a real-feed chain aged ``hours``."""
    snap = state.loaded_snapshot(ticker)
    aged = replace(snap, timestamp=_now() - timedelta(hours=hours), tick_size=tick)
    with state._lock:
        state._snapshots[ticker] = aged


def test_format_age_units():
    assert format_age(4.0) == "4m"
    assert format_age(89.0) == "89m"
    assert format_age(90.0) == "1.5h"
    assert format_age(13.5 * 60) == "13.5h"
    assert format_age(3.2 * 24 * 60) == "3.2d"


def test_age_level_thresholds():
    assert age_level(5.0, 20.0, 120.0) == "fresh"
    assert age_level(20.0, 20.0, 120.0) == "amber"
    assert age_level(120.0, 20.0, 120.0) == "red"


def test_chain_age_only_for_ticked_nonempty_chains():
    state = AppState(REF_DATE)
    state.ensure_chain(TICKER)
    snap = state.loaded_snapshot(TICKER)
    now = _now()
    # Synthetic chain: no tick_size -> no age semantics (else a fixed-reference
    # synthetic chain would read years old).
    assert chain_age_minutes(snap, now) is None
    assert chain_age_minutes(None, now) is None
    assert chain_age_minutes(replace(snap, quotes=[], tick_size=0.01), now) is None
    ticked = replace(snap, tick_size=0.01, timestamp=now - timedelta(minutes=30))
    assert abs(chain_age_minutes(ticked, now) - 30.0) < 1e-9
    # A clock skew (data stamped ahead of the wall clock) clamps to 0, not negative.
    future = replace(snap, tick_size=0.01, timestamp=now + timedelta(minutes=5))
    assert chain_age_minutes(future, now) == 0.0


def test_universe_age_gates_on_live_asof_and_reports_worst():
    state = AppState(REF_DATE)
    for t in state.active_tickers():
        state.ensure_chain(t)
    assert universe_age(state) is None  # synthetic chains: nothing applicable

    _age_chain(state, TICKER, hours=13.0)
    info = universe_age(state)
    assert info is not None
    assert info["worstTicker"] == TICKER
    assert info["level"] == "red" and info["label"] == "13.0h"
    assert abs(info["ageMin"] - 13.0 * 60) < 1.0

    # Historical views are stale by CHOICE: the signal goes quiet off-live.
    with state._lock:
        state._asof = AsOfSelection(mode="prev_close")
    assert ticker_ages(state) == {} and universe_age(state) is None


def test_datasources_payload_carries_data_age():
    state = AppState(REF_DATE)
    state.ensure_chain(TICKER)
    payload = datasources_payload(state)
    assert payload["dataAge"] is None  # synthetic: not applicable
    _age_chain(state, TICKER, hours=0.5)
    payload = datasources_payload(state)
    assert payload["dataAge"]["level"] == "amber"  # 30 min > amber 20, < red 120


def test_red_stale_data_fails_quality_readiness_amber_does_not():
    state = AppState(REF_DATE)
    iso = sorted(state.forwards(TICKER))[0].isoformat()
    service.calibrate_node(state, TICKER, iso, "mid")

    # Amber (30 min): advisory — age is reported, readiness untouched.
    _age_chain(state, TICKER, hours=0.5)
    report = quality.build_quality_report(state)
    row = next(n for n in report.nodes if n.ticker == TICKER and n.expiry == iso)
    assert row.ready and abs(row.dataAgeMin - 30.0) < 1.0
    assert report.summary.staleDataTickers == 0
    ticker_row = next(t for t in report.tickers if t.ticker == TICKER)
    assert abs(ticker_row.dataAgeMin - 30.0) < 1.0

    # Red (13 h): the fit may be perfect, the DATA is the previous session.
    _age_chain(state, TICKER, hours=13.0)
    report = quality.build_quality_report(state)
    row = next(n for n in report.nodes if n.ticker == TICKER and n.expiry == iso)
    assert not row.ready
    assert any(i.startswith("stale data") for i in row.issues)
    assert report.summary.staleDataTickers == 1

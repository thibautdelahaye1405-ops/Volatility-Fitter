"""Intraday variance clock (R2 item 10, volfit.calib.intraday_time).

Contracts: (1) with the UNIFORM default share and nontrading_weight=1 the
clock NESTS the legacy day convention — close-to-close spans integrate to
exact whole day-weights (across weekends and DST alike) and sub-day spans to
wall fractions; (2) a research session share concentrates variance in
trading hours: remaining-minutes 0DTE, cheap overnight, weighted weekend,
scaled half-day sessions, holidays as non-trading days; (3) the integral is
additive and zero past settlement; (4) events compose through
weighted_variance_years(base_days=...) with the cutoff on CALENDAR time.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from volfit.calib.intraday_time import (
    UNIFORM_SESSION_SHARE,
    intraday_variance_days,
)
from volfit.calib.weighted_time import weighted_variance_years
from volfit.data.expiry_time import is_trading_day

ET = ZoneInfo("America/New_York")
APPROX = dict(rel=1e-12, abs=1e-12)


def et(d: date, hh: int, mm: int = 0) -> datetime:
    """An ET wall-clock instant as UTC-naive (the codebase convention)."""
    aware = datetime.combine(d, time(hh, mm), tzinfo=ET)
    return aware.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


# Fixed 2026 calendar facts the tests lean on.
WED = date(2026, 6, 10)  # regular trading Wednesday
FRI = date(2026, 6, 12)
MON = date(2026, 6, 15)
JUL3 = date(2026, 7, 3)  # Independence Day OBSERVED (Jul 4 = Saturday) — closed
BLACK_FRI = date(2026, 11, 27)  # half-day, 13:00 ET close
DST_FRI = date(2026, 3, 6)  # spring-forward transition Sun 2026-03-08
DST_MON = date(2026, 3, 9)


def test_uniform_defaults_nest_the_day_convention():
    # close-to-close = exact whole day-weights, weekends included at 1
    assert intraday_variance_days(et(WED, 16), et(FRI, 16)) == pytest.approx(2.0, **APPROX)
    assert intraday_variance_days(et(FRI, 16), et(MON, 16)) == pytest.approx(3.0, **APPROX)
    # ... even across the DST spring-forward weekend (day-weight convention)
    assert intraday_variance_days(et(DST_FRI, 16), et(DST_MON, 16)) == pytest.approx(3.0, **APPROX)
    # sub-day = the wall fraction on a regular day
    assert intraday_variance_days(et(WED, 10), et(WED, 16)) == pytest.approx(6.0 / 24.0, **APPROX)


def test_additive_and_zero_past_settle():
    a, b, c = et(WED, 15, 30), et(FRI, 11), et(MON, 16)
    whole = intraday_variance_days(a, c, 0.8, 0.3)
    split = intraday_variance_days(a, b, 0.8, 0.3) + intraday_variance_days(b, c, 0.8, 0.3)
    assert whole == pytest.approx(split, **APPROX)
    assert intraday_variance_days(b, b) == 0.0
    assert intraday_variance_days(b, a) == 0.0


def test_0dte_remaining_trading_minutes():
    # 30 trading minutes left of a PM 0DTE
    last_half_hour = intraday_variance_days(et(WED, 15, 30), et(WED, 16), 0.8)
    assert last_half_hour == pytest.approx(0.8 * 0.5 / 6.5, **APPROX)
    # the uniform default is just the wall fraction
    assert intraday_variance_days(et(WED, 15, 30), et(WED, 16)) == pytest.approx(
        0.5 / 24.0, **APPROX
    )


def test_overnight_is_cheap_at_research_share():
    # Tue 20:00 -> Wed 16:00 close, share 0.8: the overnight span burns only
    # its slice of the 20% non-session mass. Tue off-hours = 9.5 pre + 8 post.
    got = intraday_variance_days(et(date(2026, 6, 9), 20), et(WED, 16), 0.8)
    expected = 0.2 * (4.0 + 9.5) / 17.5 + 0.8
    assert got == pytest.approx(expected, **APPROX)


def test_weekend_weight_is_a_lever():
    got = intraday_variance_days(et(FRI, 16), et(MON, 16), 0.8, nontrading_weight=0.3)
    expected = 0.2 * (8.0 + 9.5) / 17.5 + 2 * 0.3 + 0.8
    assert got == pytest.approx(expected, **APPROX)
    # nontrading_weight=0 prices the weekend at zero variance
    got0 = intraday_variance_days(et(FRI, 16), et(MON, 16), 0.8, nontrading_weight=0.0)
    assert got0 == pytest.approx(expected - 0.6, **APPROX)


def test_holiday_and_half_day_sessions():
    assert not is_trading_day(JUL3)  # observed holiday -> a non-trading day
    # the whole observed-holiday day carries exactly the non-trading weight
    assert intraday_variance_days(
        et(JUL3, 0), et(date(2026, 7, 4), 0), 0.8, nontrading_weight=0.25
    ) == pytest.approx(0.25, **APPROX)
    # Black Friday half-day: the 3.5h session carries share * 3.5/6.5
    session = intraday_variance_days(et(BLACK_FRI, 9, 30), et(BLACK_FRI, 13), 0.8)
    assert session == pytest.approx(0.8 * 3.5 / 6.5, **APPROX)
    # and the full day still totals 1.0 (the remainder sits off-session)
    full = intraday_variance_days(et(BLACK_FRI, 0), et(date(2026, 11, 28), 0), 0.8)
    assert full == pytest.approx(1.0, **APPROX)


def test_uniform_share_constant_matches_flat_density():
    # UNIFORM_SESSION_SHARE is exactly the flat-density share: session mass
    # equals the session's wall fraction of the day.
    assert UNIFORM_SESSION_SHARE == pytest.approx(6.5 / 24.0, **APPROX)
    sess = intraday_variance_days(et(WED, 9, 30), et(WED, 16))
    assert sess == pytest.approx(6.5 / 24.0, **APPROX)


def test_events_compose_on_the_calendar_cutoff():
    # base_days substitutes the day base; the event cutoff stays on t_cal
    tau = weighted_variance_years(0.1, [(0.05, 2.0)], base_days=5.0)
    assert tau == pytest.approx(7.0 / 365.0, **APPROX)
    # an event past the calendar maturity never enters, whatever the base
    tau2 = weighted_variance_years(0.1, [(0.2, 2.0)], base_days=5.0)
    assert tau2 == pytest.approx(5.0 / 365.0, **APPROX)
    # no base_days -> byte-identical historical behaviour
    assert weighted_variance_years(0.1, []) == 0.1


# --------------------------------------------------------- app integration
def _intraday_state():
    from volfit.api.state import AppState

    state = AppState(date(2026, 6, 10))
    state.set_options(state.options().model_copy(update={"intradayClock": True}))
    return state


def test_clock_off_is_the_legacy_day_clock():
    from volfit.api import service
    from volfit.api.state import AppState

    state = AppState(date(2026, 6, 10))
    expiry = sorted(state.forwards("ALPHA"))[0]
    prepared = service.prepared_quotes(state, "ALPHA", expiry)
    assert float(prepared.t) == state.year_fraction(expiry)
    assert float(prepared.tau) == state.year_fraction(expiry)


def test_clock_on_prices_to_the_exact_settlement_instant():
    from volfit.api import service
    from volfit.data.expiry_time import exact_year_fraction

    state = _intraday_state()
    expiry = sorted(state.forwards("ALPHA"))[0]
    snap = state.snapshot("ALPHA")
    assert snap.settlement is not None and expiry in snap.settlement
    expected = exact_year_fraction(snap.timestamp, snap.settlement[expiry].settle)
    prepared = service.prepared_quotes(state, "ALPHA", expiry)
    assert float(prepared.t) == pytest.approx(expected, **APPROX)
    assert float(prepared.t) != state.year_fraction(expiry)  # sub-day part
    # uniform default share + weight 1: tau is the same wall-clock day count
    assert float(prepared.tau) == pytest.approx(float(prepared.t), rel=1e-9)


def test_clock_on_fits_converge_and_events_still_add():
    from volfit.api import service
    from volfit.api.schemas import EventSpec

    state = _intraday_state()
    iso = sorted(state.forwards("ALPHA"))[0].isoformat()
    record = service.calibrate_node(state, "ALPHA", iso, "mid")
    assert record is not None
    assert float(record.result.max_iv_error) < 0.05  # sane fit on the exact clock

    expiry = date.fromisoformat(iso)
    state.set_events("ALPHA", [EventSpec(time=1e-4, weight=2.0, label="cpi")])
    prepared = service.prepared_quotes(state, "ALPHA", expiry)
    base = intraday_variance_days(
        state.snapshot("ALPHA").timestamp,
        state.snapshot("ALPHA").settlement[expiry].settle,
    )
    assert float(prepared.tau) == pytest.approx((base + 2.0) / 365.0, **APPROX)


def test_clock_knobs_bust_the_fit_cache():
    state = _intraday_state()  # the toggle flip itself already bumped once
    before = state.options_version
    state.set_options(state.options().model_copy(update={"sessionVarShare": 0.8}))
    state.set_options(state.options().model_copy(update={"nonTradingWeight": 0.3}))
    assert state.options_version == before + 2

"""SERIES ARC S2 — the clock resolver, ladders, servability, estimate.

Locks: sub-day instants walk backward from the latest servable instant
(historical, no start) and skip the overnight gap when session-only; forward
from a start with a count or an end; live walks forward from now; calendar
steps land on trading days only (weekend / holiday skipped) at the close or
at timeOfDay; warm-up frames are prepended and flagged; aware timestamps
normalize to naive UTC; the three ladders + the crop; frame_asof / servable
by provider capability; the estimate's numbers and warnings.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from volfit.api.schemas_series import LaneSpec, SeriesClock, SeriesLadder, SeriesSpec
from volfit.api.series_instants import (
    estimate,
    frame_asof,
    in_session,
    ladder_expiries,
    latest_servable,
    resolve_instants,
    servable,
    to_utc_naive,
)
from volfit.data.provider import SyntheticProvider

# Friday 2026-06-12 14:00 ET = 18:00 UTC (EDT), inside the session.
NOW = datetime(2026, 6, 12, 18, 0)


class _Intraday(SyntheticProvider):
    def intraday_capable(self):
        return True

    def historical_modes(self):
        return {"live", "prev_close", "eod"}


class _EodOnly(SyntheticProvider):
    def historical_modes(self):
        return {"live", "prev_close", "eod"}

    def available_history(self, ticker):
        return [date(2026, 6, 10), date(2026, 6, 11)]


def _prov(cls=SyntheticProvider):
    return cls(reference_date=date(2026, 6, 13), tickers=("ALPHA",))


# ------------------------------------------------------------------ clock

def test_session_helpers():
    assert in_session(NOW)
    assert not in_session(datetime(2026, 6, 12, 13, 0))  # 09:00 ET, pre-open
    assert not in_session(datetime(2026, 6, 13, 18, 0))  # Saturday
    assert latest_servable(NOW) == NOW
    # Saturday evening -> Friday's close (16:00 ET = 20:00 UTC)
    assert latest_servable(datetime(2026, 6, 13, 22, 0)) == datetime(2026, 6, 12, 20, 0)
    aware = datetime(2026, 6, 12, 14, 0, tzinfo=timezone(timedelta(hours=-4)))
    assert to_utc_naive(aware) == NOW and to_utc_naive(NOW) == NOW


def test_historical_without_start_walks_backward_and_skips_the_overnight_gap():
    clock = SeriesClock(step="15m", count=4)
    out = resolve_instants(clock, "historical", NOW)
    assert [ts for ts, _w in out] == [NOW - timedelta(minutes=15 * k) for k in (3, 2, 1, 0)]
    assert all(not w for _ts, w in out)
    # 30 frames of 30 min from 14:00 ET reach back past the open into Thursday
    out = resolve_instants(SeriesClock(step="30m", count=30), "historical", NOW)
    ts = [t for t, _w in out]
    assert len(ts) == 30 and ts[-1] == NOW and ts == sorted(ts)
    assert all(in_session(t) for t in ts)
    # 10 Friday instants (09:30 … 14:00 ET), 14 on Thursday (09:30 … 16:00), 6 on Wednesday
    by_day = {d: sum(1 for t in ts if t.date() == d) for d in {t.date() for t in ts}}
    assert by_day == {date(2026, 6, 12): 10, date(2026, 6, 11): 14, date(2026, 6, 10): 6}
    # session-only off: the walk is a plain grid through the night
    raw = resolve_instants(SeriesClock(step="30m", count=30, sessionOnly=False), "historical", NOW)
    assert [t for t, _w in raw] == [NOW - timedelta(minutes=30 * k) for k in range(29, -1, -1)]


def test_historical_with_start_walks_forward_to_count_or_end():
    start = datetime(2026, 6, 12, 14, 0)  # 10:00 ET
    out = resolve_instants(SeriesClock(step="1h", start=start, count=3), "historical", NOW)
    assert [t for t, _w in out] == [start + timedelta(hours=k) for k in range(3)]
    out = resolve_instants(SeriesClock(step="1h", start=start, end=start + timedelta(hours=2)),
                           "historical", NOW)
    assert [t for t, _w in out] == [start + timedelta(hours=k) for k in range(3)]


def test_live_walks_forward_from_now():
    out = resolve_instants(SeriesClock(step="1m", count=3), "live", NOW)
    assert [t for t, _w in out] == [NOW + timedelta(minutes=k) for k in range(3)]
    past = NOW - timedelta(minutes=2)
    out = resolve_instants(SeriesClock(step="1m", start=past, count=3), "live", NOW)
    assert [t for t, _w in out][0] == past


def test_calendar_steps_land_on_trading_days_only():
    # Backward from Friday 06-12: daily at 15:45 ET -> 06-10, 06-11, 06-12
    out = resolve_instants(SeriesClock(step="daily", count=3), "historical", NOW)
    assert [t for t, _w in out] == [datetime(2026, 6, d, 19, 45) for d in (10, 11, 12)]
    # Forward from Thursday 06-18 over Juneteenth (Fri 06-19, closed) and the weekend
    start = datetime(2026, 6, 18, 12, 0)
    out = resolve_instants(SeriesClock(step="session_close", start=start, count=3), "historical",
                           datetime(2026, 7, 1))
    assert [t.date() for t, _w in out] == [date(2026, 6, 18), date(2026, 6, 22), date(2026, 6, 23)]
    assert out[0][0] == datetime(2026, 6, 18, 20, 0)  # 16:00 ET close
    # Weekly: every seventh day, a closed one rolls to the previous trading day
    out = resolve_instants(SeriesClock(step="weekly", start=datetime(2026, 6, 12, 12, 0), count=2),
                           "historical", datetime(2026, 7, 1))
    assert [t.date() for t, _w in out] == [date(2026, 6, 12), date(2026, 6, 18)]  # 06-19 closed


def test_warmup_frames_are_prepended_and_flagged():
    start = datetime(2026, 6, 12, 15, 0)
    out = resolve_instants(SeriesClock(step="15m", start=start, count=2, warmupFrames=2),
                           "historical", NOW)
    assert [(t, w) for t, w in out] == [
        (start - timedelta(minutes=30), True), (start - timedelta(minutes=15), True),
        (start, False), (start + timedelta(minutes=15), False),
    ]


# ----------------------------------------------------------------- ladder

def test_ladders():
    day = datetime(2026, 6, 12, 18, 0)
    listed = [date(2026, 6, 12), date(2026, 6, 15), date(2026, 6, 19), date(2026, 6, 26),
              date(2026, 7, 17), date(2026, 8, 21), date(2026, 9, 18), date(2026, 12, 18),
              date(2026, 6, 5)]  # the last one is expired
    pinned = ladder_expiries(listed, day, SeriesLadder(expiries=["2026-06-19", "2026-06-05",
                                                                 "2026-12-18"]))
    assert pinned == [date(2026, 6, 19), date(2026, 12, 18)]
    assert ladder_expiries(listed, day, SeriesLadder())[0] == date(2026, 6, 12)  # alive today
    assert ladder_expiries(listed, day, SeriesLadder(maxExpiries=2)) == [date(2026, 6, 12),
                                                                          date(2026, 6, 15)]
    term = ladder_expiries(listed, day, SeriesLadder(policy="term"))
    assert term == [date(2026, 6, 12), date(2026, 6, 15), date(2026, 6, 19), date(2026, 6, 26),
                    date(2026, 7, 17), date(2026, 8, 21)]  # 3 fronts + monthlies ≤ 120 d, ≤ 6
    zero = ladder_expiries(listed, day, SeriesLadder(policy="0dte"))
    assert zero == [date(2026, 6, 12), date(2026, 6, 15), date(2026, 6, 19), date(2026, 7, 17),
                    date(2026, 8, 21)]  # ≤ 7 d + the next two monthlies ≤ 90 d


# ------------------------------------------------------------ servability

def test_frame_asof_and_servable_by_capability():
    ts = datetime(2026, 6, 11, 18, 0)
    live_only = _prov()
    assert frame_asof(live_only, ts, "15m", "historical") is None
    assert frame_asof(live_only, ts, "15m", "live") is None
    assert servable(live_only, "ALPHA", ts, "15m", "historical", NOW) == (
        False, "the source has no history at this cadence")
    assert servable(live_only, "ALPHA", ts, "15m", "live", NOW) == (True, None)

    intraday = _prov(_Intraday)
    asof = frame_asof(intraday, ts, "15m", "historical")
    assert asof is not None and asof.mode == "intraday" and asof.ts == ts
    assert servable(intraday, "ALPHA", ts, "15m", "historical", NOW) == (True, None)
    assert servable(intraday, "ALPHA", NOW + timedelta(hours=1), "15m", "historical", NOW) == (
        False, "in the future")

    eod = _prov(_EodOnly)
    assert frame_asof(eod, ts, "15m", "historical") is None
    asof = frame_asof(eod, ts, "daily", "historical")
    assert asof is not None and asof.mode == "eod" and asof.on == date(2026, 6, 11)
    assert servable(eod, "ALPHA", ts, "daily", "historical", NOW) == (True, None)
    assert servable(eod, "ALPHA", datetime(2026, 6, 9, 19, 45), "daily", "historical", NOW) == (
        False, "the source does not list this day")


# --------------------------------------------------------------- estimate

def test_estimate_numbers_and_warnings():
    spec = SeriesSpec(name="x", ticker="SPY", mode="historical", clock=SeriesClock(step="15m", count=3),
                      lanes=[LaneSpec(id="a", name="a"), LaneSpec(id="lv", name="lv", family="lv")])
    instants = [(NOW - timedelta(minutes=15 * k), False) for k in (2, 1, 0)]
    est = estimate(spec, "massive", instants, [(True, None)] * 3, 8, NOW)
    assert est.nFrames == 3 and est.servable == [True] * 3
    assert est.harvestSeconds == 42.0  # 3 × 14 s
    assert est.perLaneSeconds == {"a": 1.2, "lv": 9.0} and est.calibrateSeconds == 10.2
    assert est.warnings == []
    est = estimate(spec, "yahoo", instants, [(True, None), (False, "in the future"), (True, None)],
                   8, NOW)
    assert est.harvestSeconds == 6.0 and est.warnings == ["1 of 3 instants cannot be served (in the future)"]
    live = spec.model_copy(update={"mode": "live"})
    est = estimate(live, "cboe", [(NOW + timedelta(minutes=k), False) for k in range(3)],
                   [(True, None)] * 3, 8, NOW)
    assert est.harvestSeconds == 120.0 + 6.0

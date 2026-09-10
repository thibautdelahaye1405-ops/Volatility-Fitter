"""Series clock resolution, ladders, servability and the cost estimate
(SERIES ARC S2, Docs/series_replay_roadmap.md §3.1–§3.2).

Instants are timezone-naive UTC (the chain-timestamp convention); the session
calendar is the NYSE one from ``volfit.data.expiry_time`` (holidays,
half-days) with the open at 09:30 ET. A HISTORICAL series without ``start``
ends at the latest servable instant (now inside a session, else the latest
completed session's close) and walks BACKWARD ``count`` steps; with
``start`` it walks forward. A LIVE series walks forward from now. Calendar
steps (``session_close`` / ``daily`` / ``weekly``) put one instant per
trading day at the close or at ``timeOfDay``. Warm-up frames are extra
instants before the first, flagged so lanes can seed on them (D4).

Servability (D7) asks the ticker's provider: a sub-day instant needs
``intraday_capable``; a calendar instant on a source without intraday
history is served as that day's EOD chain when the source lists the day
(Bloomberg: daily series only); a live frame is always a fetch.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from volfit.api.schemas_series import (
    STEP_SECONDS,
    LaneSpec,
    SeriesClock,
    SeriesEstimate,
    SeriesLadder,
    SeriesSpec,
)
from volfit.data.expiry_time import (
    ET,
    is_trading_day,
    latest_completed_session,
    prev_trading_day,
    session_close_utc,
)
from volfit.data.provider import AsOf

UTC = ZoneInfo("UTC")
_OPEN = time(9, 30)

#: Measured harvest cost per frame by source (s): Massive per-contract NBBO
#: history ≈ 14 s per SPY chain (live-verified 2026-09-10c); Bloomberg EOD
#: ≈ 5 s; anything else a plain request.
HARVEST_SECONDS = {"massive": 14.0, "bloomberg": 5.0}
DEFAULT_HARVEST_SECONDS = 3.0
#: Calibration cost per frame per lane: a parametric slice ≈ 15 ms + prep
#: (de-Am dominates American names) ≈ 50 ms per expiry; an LV surface ≈ 3 s.
PARAMETRIC_SECONDS_PER_EXPIRY = 0.05
LV_SECONDS_PER_FRAME = 3.0


# ------------------------------------------------------------------ clock

def to_utc_naive(ts: datetime) -> datetime:
    """Aware → UTC naive; naive → taken as UTC already."""
    if ts.tzinfo is not None:
        return ts.astimezone(UTC).replace(tzinfo=None)
    return ts


def _et_date(ts: datetime) -> date:
    return ts.replace(tzinfo=UTC).astimezone(ET).date()


def _at_et(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=ET).astimezone(UTC).replace(tzinfo=None)


def session_open_utc(d: date) -> datetime:
    return _at_et(d, _OPEN)


def in_session(ts: datetime) -> bool:
    """Inside a regular session: a trading day, open ≤ ts ≤ close."""
    d = _et_date(ts)
    return is_trading_day(d) and session_open_utc(d) <= ts <= session_close_utc(d)


def _parse_tod(s: str) -> time:
    hh, _, mm = s.partition(":")
    return time(int(hh), int(mm))


def _calendar_instant(d: date, clock: SeriesClock) -> datetime:
    if clock.step == "session_close":
        return session_close_utc(d)
    return _at_et(d, _parse_tod(clock.timeOfDay))


def _walk_subday(origin: datetime, seconds: int, count: int, forward: bool,
                 session_only: bool, end: datetime | None) -> list[datetime]:
    """``count`` instants from ``origin`` (inclusive) stepping ``seconds``,
    skipping out-of-session instants when asked; bounded by ``end``."""
    out: list[datetime] = []
    ts = origin
    guard = 0
    limit = count if count else 10_000
    while len(out) < limit and guard < 200_000:
        guard += 1
        if forward and end is not None and ts > end:
            break
        if not session_only or in_session(ts):
            out.append(ts)
        ts = ts + timedelta(seconds=seconds) if forward else ts - timedelta(seconds=seconds)
    return out if forward else list(reversed(out))


def _walk_days(origin: date, clock: SeriesClock, count: int, forward: bool,
               end: datetime | None) -> list[datetime]:
    """One instant per trading day (weekly: every seventh calendar day, the
    previous trading day when it falls on a closed one)."""
    out: list[datetime] = []
    d = origin
    guard = 0
    limit = count if count else 10_000
    step_days = 7 if clock.step == "weekly" else 1
    while len(out) < limit and guard < 20_000:
        guard += 1
        day = d if is_trading_day(d) else (prev_trading_day(d) if step_days == 7 else None)
        if day is not None:
            ts = _calendar_instant(day, clock)
            if forward and end is not None and ts > end:
                break
            if not out or out[-1] != ts:
                out.append(ts)
        d = d + timedelta(days=step_days) if forward else d - timedelta(days=step_days)
    return out if forward else list(reversed(out))


def latest_servable(now_utc: datetime) -> datetime:
    """Now inside a session, else the latest completed session's close."""
    if in_session(now_utc):
        return now_utc.replace(second=0, microsecond=0)
    return session_close_utc(latest_completed_session(now_utc))


def resolve_instants(clock: SeriesClock, mode: str, now_utc: datetime) -> list[tuple[datetime, bool]]:
    """The series' instants oldest first as ``(ts, warmup)``: the warm-up
    frames (``clock.warmupFrames`` extra steps before the first) come first
    and are flagged. Live mode walks forward from now (or ``start``);
    historical walks forward from ``start`` when given, else backward from
    the latest servable instant."""
    seconds = STEP_SECONDS.get(clock.step)
    start = to_utc_naive(clock.start) if clock.start is not None else None
    end = to_utc_naive(clock.end) if clock.end is not None else None
    count = clock.count or 0
    if mode == "live":
        origin = start or now_utc.replace(microsecond=0)
        forward = True
    else:
        forward = start is not None
        origin = start if forward else latest_servable(now_utc)
    if seconds is not None:
        main = _walk_subday(origin, seconds, count, forward, clock.sessionOnly, end)
    else:
        main = _walk_days(_et_date(origin), clock, count, forward, end)
    if not main:
        return []
    warm: list[datetime] = []
    if clock.warmupFrames:
        first = main[0]
        if seconds is not None:
            back = _walk_subday(first - timedelta(seconds=seconds), seconds, clock.warmupFrames,
                                False, clock.sessionOnly, None)
        else:
            step_days = 7 if clock.step == "weekly" else 1
            back = _walk_days(_et_date(first) - timedelta(days=step_days), clock,
                              clock.warmupFrames, False, None)
        warm = [ts for ts in back if ts < first]
    return [(ts, True) for ts in warm] + [(ts, False) for ts in main]


# ----------------------------------------------------------------- ladder

def _third_friday(d: date) -> bool:
    return d.weekday() == 4 and 15 <= d.day <= 21


def ladder_expiries(listed: list[date], ts: datetime, ladder: SeriesLadder) -> list[date]:
    """The frame's expiries under the ladder (D6): alive at the instant, then
    ``pinned`` (∩ the pinned list), ``term`` (front weeklies + monthlies within
    120 days, at most six) or ``0dte`` (within seven days + the next two
    monthlies within 90 days); cropped nearest-first by ``maxExpiries``."""
    day = _et_date(ts)
    alive = sorted(e for e in set(listed) if e >= day)
    if ladder.policy == "pinned":
        if ladder.expiries:
            want = {date.fromisoformat(e) for e in ladder.expiries}
            alive = [e for e in alive if e in want]
    elif ladder.policy == "term":
        monthlies = [e for e in alive if _third_friday(e) and (e - day).days <= 120]
        fronts = [e for e in alive if not _third_friday(e) and (e - day).days <= 120][:3]
        alive = sorted(set(monthlies[:4]) | set(fronts))[:6]
    else:  # 0dte
        near = [e for e in alive if (e - day).days <= 7]
        monthlies = [e for e in alive if _third_friday(e) and 7 < (e - day).days <= 90][:2]
        alive = sorted(set(near) | set(monthlies))
    if ladder.maxExpiries is not None:
        alive = alive[: ladder.maxExpiries]
    return alive


# ------------------------------------------------------------ servability

def frame_asof(provider, ts: datetime, step: str, mode: str) -> AsOf | None:
    """How a frame at ``ts`` is fetched: None = a live fetch; an intraday
    instant when the source serves them; the day's EOD chain for a calendar
    step on an EOD-only source."""
    if mode == "live":
        return None
    if provider.intraday_capable():
        return AsOf(mode="intraday", ts=ts)
    if step in ("session_close", "daily", "weekly") and "eod" in provider.historical_modes():
        return AsOf(mode="eod", on=_et_date(ts))
    return None


def servable(provider, ticker: str, ts: datetime, step: str, mode: str,
             now_utc: datetime) -> tuple[bool, str | None]:
    """(ok, reason): whether the source can serve the frame."""
    if mode == "live":
        return True, None
    if ts > now_utc:
        return False, "in the future"
    asof = frame_asof(provider, ts, step, mode)
    if asof is None:
        return False, "the source has no history at this cadence"
    if asof.mode == "eod":
        days = provider.available_history(ticker)
        if days and asof.on not in days:
            return False, "the source does not list this day"
    return True, None


# --------------------------------------------------------------- estimate

def lane_seconds(lane: LaneSpec, n_expiries: int) -> float:
    if lane.family == "lv":
        return LV_SECONDS_PER_FRAME
    return PARAMETRIC_SECONDS_PER_EXPIRY * max(1, n_expiries)


def estimate(spec: SeriesSpec, source_id: str | None, instants: list[tuple[datetime, bool]],
             flags: list[tuple[bool, str | None]], n_expiries: int,
             now_utc: datetime) -> SeriesEstimate:
    """The dialog's budget (§3.1): harvest seconds by source (live = the wait
    until the last instant plus a request per frame), calibration seconds
    per lane from the rails, warnings for what will not work."""
    n = len(instants)
    n_ok = sum(1 for ok, _r in flags if ok)
    if spec.mode == "live":
        last = instants[-1][0] if instants else now_utc
        harvest = max(0.0, (last - now_utc).total_seconds()) + 2.0 * n
    elif spec.mode == "historical":
        harvest = HARVEST_SECONDS.get(source_id or "", DEFAULT_HARVEST_SECONDS) * n_ok
    else:
        harvest = 0.0
    per_lane = {lane.id: lane_seconds(lane, n_expiries) * n_ok for lane in spec.lanes}
    warnings: list[str] = []
    if n_ok < n:
        reasons = sorted({r for ok, r in flags if not ok and r})
        warnings.append(f"{n - n_ok} of {n} instants cannot be served ({'; '.join(reasons)})")
    if any(lane.family == "lv" for lane in spec.lanes) and n_ok > 60:
        warnings.append("LV lanes dominate the calibration time on long series")
    if n > 390:
        warnings.append("more than one session of minute frames — consider a coarser step")
    return SeriesEstimate(
        instants=[ts.isoformat() for ts, _w in instants],
        servable=[ok for ok, _r in flags],
        nFrames=n,
        harvestSeconds=round(harvest, 1),
        calibrateSeconds=round(sum(per_lane.values()), 1),
        perLaneSeconds={k: round(v, 1) for k, v in per_lane.items()},
        warnings=warnings,
    )

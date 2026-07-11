"""Sub-day (intraday) variance clock — the 0DTE research clock (R2 item 10).

The day-granular clock (`(expiry - today).days / 365`, event-weighted by
volfit.calib.weighted_time) is meaningless at hours-to-expiry: a 0DTE's
remaining life is set by the WALL CLOCK and by HOW variance accrues through
a trading day. This module extends the day-weight convention below one day:

  * every ET calendar day still carries a total *day-weight* (1.0 for a
    trading day — exactly the legacy integer-day convention — and
    ``nontrading_weight`` for weekends/holidays, the close-to-open /
    weekend-effect research lever);
  * WITHIN a trading day the weight is split piecewise-uniformly:
    ``session_share`` of the day's variance accrues during the exchange
    session (09:30 ET to the 16:00/13:00 close, per the NYSE session rules
    of volfit.data.expiry_time) and the remainder over the non-session
    hours of that day. Half-days scale the share by their session length,
    so a 3.5-hour session carries proportionally less;
  * ``UNIFORM_SESSION_SHARE`` (= 6.5/24) makes the intra-day density flat,
    so with ``nontrading_weight=1`` the clock NESTS the legacy convention:
    any close-to-close span of N calendar days integrates to exactly N
    day-weights, and a sub-day remainder is the elapsed fraction of the
    wall day. Research values (~0.7-0.9) concentrate variance in trading
    hours: "remaining trading minutes" for a live 0DTE, a cheap overnight,
    a cheap weekend.

Instants are timezone-naive UTC (the codebase convention); segments are
built in ET wall time, so the session boundaries are exchange-correct
across DST. The in-session profile is uniform in v1 — the U-shaped
open/close seasonality is a documented follow-up, NOT a knob yet.

Scheduled *intraday* events need no machinery here: EventSpec.time is a
year fraction, so once the valuation clock is sub-day an 08:30 CPI print is
just an event whose fractional time sits mid-morning; the existing
weighted_time day-weight add-on applies unchanged (see
``weighted_variance_years(base_days=...)``).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from volfit.data.expiry_time import is_trading_day, session_close

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

_OPEN = time(9, 30)
_FULL_SESSION_HOURS = 6.5  # 09:30-16:00 ET, the share's reference session

#: The session share that makes the intra-day density FLAT (session hours as
#: a fraction of the 24h day): with it (and nontrading_weight=1) the clock
#: reduces to plain wall-clock day fractions — the legacy convention extended
#: below one day. The conservative default; research pushes it up.
UNIFORM_SESSION_SHARE = _FULL_SESSION_HOURS / 24.0


def _to_et(instant: datetime) -> datetime:
    """A UTC-naive instant as an ET-aware datetime."""
    return instant.replace(tzinfo=UTC).astimezone(ET)


def _day_segments(d: date, session_share: float, nontrading_weight: float):
    """One ET calendar day's piecewise-uniform weight profile.

    Returns ``[(start_et, end_et, mass), ...]`` covering [00:00, 24:00) ET,
    aware datetimes; masses sum to the day's weight. A trading day's session
    mass is ``session_share`` scaled by its session length relative to the
    full 6.5h session (a 13:00 half-day carries proportionally less), the
    remainder spread uniformly over the non-session hours.
    """
    start = datetime.combine(d, time(0, 0), tzinfo=ET)
    end = start + timedelta(days=1)
    if not is_trading_day(d):
        return [(start, end, float(nontrading_weight))]
    open_ = datetime.combine(d, _OPEN, tzinfo=ET)
    close = datetime.combine(d, session_close(d), tzinfo=ET)
    session_hours = (close - open_).total_seconds() / 3600.0
    share = float(session_share) * (session_hours / _FULL_SESSION_HOURS)
    share = min(max(share, 0.0), 1.0)
    rest = 1.0 - share
    pre_hours = (open_ - start).total_seconds() / 3600.0
    post_hours = (end - close).total_seconds() / 3600.0
    off_hours = pre_hours + post_hours
    return [
        (start, open_, rest * pre_hours / off_hours),
        (open_, close, share),
        (close, end, rest * post_hours / off_hours),
    ]


def intraday_variance_days(
    t0: datetime,
    t1: datetime,
    session_share: float = UNIFORM_SESSION_SHARE,
    nontrading_weight: float = 1.0,
) -> float:
    """Accrued day-weights between two UTC-naive instants (0 when t1 <= t0).

    The sub-day variance clock: integrates the piecewise-uniform day profile
    (see module docstring) from ``t0`` to ``t1``. With the defaults this is
    the plain wall-clock day count (the legacy convention, made sub-day);
    with a research ``session_share`` it is "remaining trading time".
    """
    if t1 <= t0:
        return 0.0
    a, b = _to_et(t0), _to_et(t1)
    total = 0.0
    d = a.date()
    while d <= b.date():
        for seg_start, seg_end, mass in _day_segments(
            d, session_share, nontrading_weight
        ):
            if mass <= 0.0:
                continue
            lo, hi = max(seg_start, a), min(seg_end, b)
            if hi > lo:
                overlap = (hi - lo).total_seconds()
                length = (seg_end - seg_start).total_seconds()
                total += mass * overlap / length
        d += timedelta(days=1)
    return total

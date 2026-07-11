"""Exact expiry-time conventions: US listed-option settlement instants
(roadmap R1 item 5 — timestamp semantics before the 0DTE calibration path).

Day-granular maturities (`(expiry - today).days / 365`) are fine at a month
and meaningless at a day: a 0DTE contract's remaining life is set by the
CLOCK — when the session closes (16:00 ET, 13:00 on half-days), whether the
contract settles on the open (AM index monthlies: SPX/NDX/RUT) or the close
(PM: everything else), and which days trade at all. This module builds
``ExpirySettlement`` records from exchange-session RULES, not tables:

  * NYSE full holidays are computed per year (New Year's, MLK, Washington's
    Birthday, Good Friday via the Anonymous Gregorian Easter algorithm,
    Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving,
    Christmas), with Saturday->Friday / Sunday->Monday observation shifts;
  * half-days (13:00 ET close): July 3 when a weekday session, the day
    after Thanksgiving, Christmas Eve when a weekday session;
  * all instants are converted America/New_York -> timezone-naive UTC (the
    codebase convention, matching the WS tick-time stamping).

Known v1 simplification, by design: PM equity/ETF options are stamped at the
16:00 ET session close; a handful of ETF/index options (SPY/QQQ, cash SPX)
actually trade to 16:15 ET. The 15-minute nuance matters only intra-final-
session and can ride a per-root override when the 0DTE path consumes it.

Nothing here feeds the fit clock yet: ``prepared.t``/``prepared.tau`` stay
day-granular (byte-identical fits) until the R2 0DTE work switches consumers
to ``exact_year_fraction``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from volfit.data.types import ExpirySettlement

ET = ZoneInfo("America/New_York")
DAYS_PER_YEAR = 365.0  # ACT/365 fixed, matching AppState.year_fraction

#: Option roots that settle on the OPEN (AM) — the index monthly convention.
#: Their weekly/PM siblings (SPXW/NDXP/RUTW) settle on the close like
#: everything else. Mirrors the backtest layer's AssetSpec root split.
AM_SETTLED_ROOTS = frozenset({"SPX", "NDX", "RUT"})

_FULL_CLOSE = time(16, 0)
_HALF_CLOSE = time(13, 0)
_AM_SETTLE = time(9, 30)
#: Index options keep trading 15 minutes past the equity close; an AM-settled
#: monthly's LAST session is the business day before expiry.
_INDEX_LAST_TRADE = time(16, 15)


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th (1-based) given weekday (Mon=0) of a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    """NYSE observation shift: Saturday -> Friday, Sunday -> Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=64)
def nyse_holidays(year: int) -> frozenset[date]:
    """Full-closure NYSE holidays of one year, computed from the rules.

    Memoized: the intraday variance clock (volfit.calib.intraday_time) walks
    day-by-day over year-long horizons per node, so the per-year set is hot."""
    days = {
        _observed(date(year, 1, 1)),  # New Year's Day
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),  # Christmas
    }
    # A New Year's observed on Dec-31 of the PREVIOUS year (Jan 1 on Saturday)
    # belongs to that previous year's set; recompute for next year spillover.
    nyd_next = _observed(date(year + 1, 1, 1))
    if nyd_next.year == year:
        days.add(nyd_next)
    return frozenset(d for d in days if d.year == year)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


def is_half_day(d: date) -> bool:
    """13:00 ET close: Jul 3, the day after Thanksgiving, Christmas Eve —
    when they are trading sessions at all."""
    if not is_trading_day(d):
        return False
    if d.month == 7 and d.day == 3:
        return True
    if d.month == 11 and d == _nth_weekday(d.year, 11, 3, 4) + timedelta(days=1):
        return True
    return d.month == 12 and d.day == 24


def session_close(d: date) -> time:
    """The session's ET close (16:00, or 13:00 on half-days)."""
    return _HALF_CLOSE if is_half_day(d) else _FULL_CLOSE


def prev_trading_day(d: date) -> date:
    out = d - timedelta(days=1)
    while not is_trading_day(out):
        out -= timedelta(days=1)
    return out


def _to_utc_naive(d: date, t: time) -> datetime:
    """An ET wall-clock instant as timezone-naive UTC (codebase convention)."""
    return datetime.combine(d, t, tzinfo=ET).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def default_settlement(expiry: date, root: str | None = None) -> ExpirySettlement:
    """The US listed-option settlement convention for one expiry.

    PM (everything but the AM index roots): last trade and settlement at the
    expiry session's close. AM (SPX/NDX/RUT monthlies): last trade at the
    PREVIOUS session's index close (16:15 ET), settlement at the expiry
    open (09:30 ET). An expiry falling on a non-trading day rolls its
    session back to the previous trading day (defensive: listed expiries
    are trading days, but captured/legacy data may carry Saturdays from the
    pre-2015 convention).
    """
    session = expiry if is_trading_day(expiry) else prev_trading_day(expiry)
    if root is not None and root.upper() in AM_SETTLED_ROOTS:
        last_session = prev_trading_day(session)
        return ExpirySettlement(
            style="am",
            last_trade=_to_utc_naive(last_session, _INDEX_LAST_TRADE),
            settle=_to_utc_naive(session, _AM_SETTLE),
        )
    close = session_close(session)
    instant = _to_utc_naive(session, close)
    return ExpirySettlement(style="pm", last_trade=instant, settle=instant)


def settlement_map(
    expiries, root: str | None = None
) -> dict[date, ExpirySettlement]:
    """Per-expiry settlement records for a chain (the provider one-liner)."""
    return {e: default_settlement(e, root) for e in sorted(set(expiries))}


def exact_year_fraction(valuation: datetime, settle: datetime) -> float:
    """Exact ACT/365 year fraction between two UTC-naive instants (signed —
    negative once past settlement; callers clamp as appropriate)."""
    return (settle - valuation).total_seconds() / 86400.0 / DAYS_PER_YEAR

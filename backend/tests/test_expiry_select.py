"""Expiry buckets, the default selection rule, and bulk filters."""

from datetime import date, timedelta

from volfit.data.expiry_select import (
    QUARTERLY_MAX_DAYS,
    default_selection,
    expiry_bucket,
    filter_expiries,
    matches_filter,
)

REF = date(2026, 6, 8)  # a Monday


def _ladder() -> list[date]:
    """A realistic 2-year ladder: M/W/F weeklies + 3rd-Friday monthlies."""
    out: set[date] = set()
    for w in range(0, 14):  # Mon/Wed/Fri for 14 weeks
        monday = REF + timedelta(weeks=w)
        for off in (0, 2, 4):
            out.add(monday + timedelta(days=off))
    for m in range(0, 24):  # 3rd Friday of each month for 2 years
        y, mo = divmod(REF.month - 1 + m, 12)
        first = date(REF.year + y, mo + 1, 1)
        third_fri = first + timedelta(days=(4 - first.weekday()) % 7 + 14)
        out.add(third_fri)
    return sorted(e for e in out if (e - REF).days > 0)


def test_buckets():
    assert expiry_bucket(REF, REF) == "0dte"  # same day
    assert expiry_bucket(date(2026, 6, 19), REF) == "quarterly"  # 3rd Fri June (Q)
    assert expiry_bucket(date(2026, 7, 17), REF) == "monthly"  # 3rd Fri July
    assert expiry_bucket(date(2026, 6, 10), REF) == "weekly"  # a Wednesday
    assert expiry_bucket(date(2026, 6, 12), REF) == "weekly"  # a non-3rd Friday
    assert expiry_bucket(date(2026, 6, 16), REF) == "daily"  # a Tuesday


def test_default_rule_picks_weeklies_monthlies_quarterlies():
    sel = default_selection(_ladder(), REF)
    days = {e: (e - REF).days for e in sel}
    # First two M/W/F weeklies >= 2 days.
    assert date(2026, 6, 10) in sel and date(2026, 6, 12) in sel
    weeklies = [e for e in sel if expiry_bucket(e, REF) == "weekly"]
    assert len(weeklies) == 2 and all(days[e] >= 2 for e in weeklies)
    # First two monthly expirations (3rd Fridays incl. quarter months).
    third_fris = [e for e in sel if expiry_bucket(e, REF) in ("monthly", "quarterly")]
    assert date(2026, 6, 19) in sel and date(2026, 7, 17) in sel
    # Every quarterly out to ~18M, none beyond.
    quarterlies = [e for e in sel if expiry_bucket(e, REF) == "quarterly"]
    assert quarterlies and all(days[e] <= QUARTERLY_MAX_DAYS for e in quarterlies)
    assert len(third_fris) >= 4  # 2 near monthlies + several quarterlies
    # No 0DTE / sub-2-day rungs slipped into the default.
    assert all(days[e] >= 2 for e in sel)


def test_sparse_ladder_takes_all():
    sparse = [REF + timedelta(days=d) for d in (30, 91, 182, 365)]
    assert default_selection(sparse, REF) == sparse


def test_bulk_filters():
    ladder = _ladder()
    weeklies = filter_expiries(ladder, REF, "weekly")
    assert weeklies and all(expiry_bucket(e, REF) == "weekly" for e in weeklies)
    quarterlies = filter_expiries(ladder, REF, "quarterly")
    assert all(expiry_bucket(e, REF) == "quarterly" for e in quarterlies)
    le1y = filter_expiries(ladder, REF, "le1y")
    assert all((e - REF).days <= 366 for e in le1y)
    assert filter_expiries(ladder, REF, "all") == ladder
    # 0DTE only matches same-day; none in a future-only ladder.
    assert filter_expiries(ladder, REF, "0dte") == []
    assert matches_filter(REF, REF, "0dte") is True


def test_default_selection_falls_back_on_non_us_calendars():
    """A venue whose expiries never hit the US buckets (ASX: Thursdays) still gets
    a seed ladder: the first two rungs >= 2 days out, then the first expiry of
    each further month, capped at 10 within ~18 months."""
    from datetime import date, timedelta

    from volfit.data.expiry_select import FALLBACK_MAX, default_selection

    ref = date(2026, 8, 21)  # a Friday
    thursdays = [date(2026, 8, 27) + timedelta(days=7 * i) for i in range(3)]  # weeklies (Thu)
    # monthly Thursdays out to ~2 years
    monthlies = [date(2026, 9, 17), date(2026, 10, 15), date(2026, 11, 19), date(2026, 12, 17), date(2027, 1, 21),
                 date(2027, 2, 18), date(2027, 3, 18), date(2027, 6, 17), date(2027, 9, 16), date(2027, 12, 16),
                 date(2028, 3, 16), date(2028, 6, 15)]
    sel = default_selection(thursdays + monthlies, ref)
    assert sel[:2] == thursdays[:2]  # near rungs
    assert len(sel) == FALLBACK_MAX and len({(d.year, d.month) for d in sel[2:]}) == len(sel[2:])  # one per month
    assert all((d - ref).days <= 548 for d in sel) and date(2026, 9, 10) not in sel  # Sep already covered
    # a US ladder is untouched by the fallback
    us = [date(2026, 8, 24), date(2026, 8, 26), date(2026, 8, 28), date(2026, 9, 18), date(2026, 10, 16),
          date(2026, 12, 18), date(2027, 3, 19), date(2027, 6, 18), date(2027, 9, 17), date(2027, 12, 17)]
    assert date(2026, 9, 18) in default_selection(us, ref)

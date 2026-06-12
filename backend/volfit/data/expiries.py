"""Listed-expiry classification (ROADMAP Phase 6 [REQ 2026-06-12]).

Backs the universe-selection screen's "bulk select by expiry type" feature:
each listed expiry is tagged daily / weekly / monthly / quarterly / leaps so
the frontend can offer one-click ladders ("all monthlies", "quarterlies
only", ...). Classification follows US listed-options conventions and is
priority-ordered — the FIRST matching rule wins:

1. "leaps":     a monthly (3rd-Friday) expiry in January at least
                LEAPS_MIN_DAYS (270) days past the reference date — the
                listed-options LEAPS convention (long-dated January cycle).
2. "quarterly": the 3rd Friday of March, June, September or December
                (the quarterly cycle months).
3. "monthly":   the 3rd Friday of any other month (standard monthlies).
4. "weekly":    any other Friday (the weekly series).
5. "daily":     everything else (0DTE-style and odd-date listings).

Pure date arithmetic, no market-data dependencies — usable by routers,
universe persistence and tests alike.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

#: The closed set of expiry tags served in /universe payloads.
ExpiryType = Literal["daily", "weekly", "monthly", "quarterly", "leaps"]

#: date.weekday() index of Friday (Monday == 0).
FRIDAY = 4

#: Months of the quarterly listing cycle.
QUARTERLY_MONTHS = (3, 6, 9, 12)

#: Minimum days-to-expiry for a January monthly to count as a LEAPS series.
LEAPS_MIN_DAYS = 270


def third_friday(year: int, month: int) -> date:
    """The 3rd Friday of (year, month) — the standard monthly expiration."""
    first = date(year, month, 1)
    first_friday = first + timedelta(days=(FRIDAY - first.weekday()) % 7)
    return first_friday + timedelta(days=14)


def classify_expiry(expiry: date, reference_date: date) -> str:
    """Tag one listed expiry per the priority rules in the module docstring."""
    if expiry == third_friday(expiry.year, expiry.month):
        if expiry.month == 1 and (expiry - reference_date).days >= LEAPS_MIN_DAYS:
            return "leaps"
        if expiry.month in QUARTERLY_MONTHS:
            return "quarterly"
        return "monthly"
    if expiry.weekday() == FRIDAY:
        return "weekly"
    return "daily"

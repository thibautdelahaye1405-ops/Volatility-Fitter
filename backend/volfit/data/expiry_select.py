"""Per-ticker expiry selection: buckets, the default rule, and bulk filters.

The universe picker chooses which of a ticker's available expiries to actually
fetch and fit. Each expiry falls in one display bucket and the default rule
seeds a sensible curated ladder; bulk filters let the user select a whole
class or window at once. All dates are calendar dates resolved against an
as-of (reference) date — no chains are fetched here.

Buckets (one per expiry, in priority order):
  0dte     same-day (days <= 0)
  quarterly 3rd Friday of Mar/Jun/Sep/Dec
  monthly   3rd Friday of any other month
  weekly    Monday/Wednesday/Friday, not a 3rd Friday
  daily     anything else (Tue/Thu dailies, odd listings)

Default rule (the seed when a ticker is added): the first 2 Mon/Wed/Fri
weeklies at least 2 days out, the first 2 monthly expirations (3rd Friday,
quarter months included), and every quarterly out to 18 months. Sparse ladders
(<= TAKE_ALL_MAX listed expiries, e.g. the synthetic dev provider) just take
everything, so thin chains keep all their rungs. Venues whose expiries never
hit the US buckets (ASX: Thursdays) fall back to a calendar-agnostic ladder
(``_calendar_agnostic_ladder``: two near rungs + the first expiry of each
further month, capped at FALLBACK_MAX) instead of an empty seed.
"""

from __future__ import annotations

from datetime import date

#: Ladders with at most this many expiries skip the rule and take all of them.
TAKE_ALL_MAX = 8
#: Default rule horizon for quarterlies (~18 months).
QUARTERLY_MAX_DAYS = 548
#: Cumulative day windows behind the "<= N" bulk filters.
WINDOW_DAYS = {"le1m": 31, "le3m": 93, "le6m": 184, "le1y": 366, "le2y": 731}


def _is_third_friday(d: date) -> bool:
    """A standard monthly/quarterly expiration: the month's 3rd Friday."""
    return d.weekday() == 4 and 15 <= d.day <= 21


def expiry_bucket(expiry: date, reference_date: date) -> str:
    """The display bucket of one expiry (see module docstring)."""
    days = (expiry - reference_date).days
    if days <= 0:
        return "0dte"
    if _is_third_friday(expiry):
        return "quarterly" if expiry.month in (3, 6, 9, 12) else "monthly"
    if expiry.weekday() in (0, 2, 4):  # Monday / Wednesday / Friday
        return "weekly"
    return "daily"


def default_selection(available: list[date], reference_date: date) -> list[date]:
    """The seed selection for a freshly added ticker (the default rule)."""
    avail = sorted(e for e in available if (e - reference_date).days > 0)
    if len(avail) <= TAKE_ALL_MAX:
        return avail  # sparse ladder: keep everything
    buckets = {e: expiry_bucket(e, reference_date) for e in avail}
    selected: set[date] = set()
    # First 2 Mon/Wed/Fri weeklies at least 2 days out.
    weeklies = [e for e in avail if buckets[e] == "weekly" and (e - reference_date).days >= 2]
    selected.update(weeklies[:2])
    # First 2 monthly expirations (3rd Friday; quarter-month ones count too).
    monthlies = [e for e in avail if buckets[e] in ("monthly", "quarterly")]
    selected.update(monthlies[:2])
    # Every quarterly out to ~18 months.
    selected.update(
        e
        for e in avail
        if buckets[e] == "quarterly" and (e - reference_date).days <= QUARTERLY_MAX_DAYS
    )
    if not selected:
        return _calendar_agnostic_ladder(avail, reference_date)
    return sorted(selected)


#: Size of the fallback ladder (≈ the US rule's typical seed).
FALLBACK_MAX = 10


def _calendar_agnostic_ladder(avail: list[date], reference_date: date) -> list[date]:
    """Seed for a venue whose expiries never hit the US buckets (ASX monthlies
    expire on Thursdays, Eurex on the 3rd Friday but weeklies mid-week, …): the
    first two rungs at least 2 days out, then the FIRST expiry of each further
    calendar month out to ~18 months, capped at ``FALLBACK_MAX`` — a near/term
    ladder in the spirit of the default rule, with no weekday assumption."""
    near = [e for e in avail if (e - reference_date).days >= 2]
    chosen: list[date] = near[:2]
    months_taken = {(e.year, e.month) for e in chosen}
    for e in near[2:]:
        if len(chosen) >= FALLBACK_MAX or (e - reference_date).days > QUARTERLY_MAX_DAYS:
            break
        ym = (e.year, e.month)
        if ym in months_taken:
            continue
        months_taken.add(ym)
        chosen.append(e)
    return sorted(chosen) if chosen else avail[:FALLBACK_MAX]


def matches_filter(expiry: date, reference_date: date, filter_id: str) -> bool:
    """Whether one expiry is selected by a bulk filter chip."""
    days = (expiry - reference_date).days
    if filter_id == "0dte":
        return days <= 0
    if days <= 0:
        return False
    if filter_id in ("weekly", "monthly", "quarterly", "daily"):
        return expiry_bucket(expiry, reference_date) == filter_id
    if filter_id in WINDOW_DAYS:
        return days <= WINDOW_DAYS[filter_id]
    if filter_id == "all":
        return True
    return False


def filter_expiries(
    available: list[date], reference_date: date, filter_id: str
) -> list[date]:
    """Available expiries a bulk filter chip selects, sorted."""
    return [e for e in sorted(available) if matches_filter(e, reference_date, filter_id)]

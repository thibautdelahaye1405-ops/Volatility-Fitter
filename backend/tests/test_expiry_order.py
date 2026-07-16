"""Settlement-instant expiry ordering for the calendar-coupling chains
(service.ordered_expiries — R2 item 10, absolute-timestamp constraints).

Contracts: (1) BYTE-IDENTITY — for every chain whose settlement instants sit
inside their own calendar date (all of them today: settles never cross
dates), the order equals plain date order, settlement map present or not;
(2) the key itself puts an AM settle (09:30 ET) before a PM settle (16:00
ET) on the same date, so a future expiry-key redesign that splits same-date
AM/PM pairs inherits correct ordering with no further change.
"""

from __future__ import annotations

from datetime import date, datetime

from volfit.api import service
from volfit.api.state import AppState
from volfit.data.expiry_time import settlement_map
from volfit.data.types import ChainSnapshot, OptionQuote
from volfit.replay_report import _StoredChains


def _snap(ticker: str, expiries: list[date], settlement) -> ChainSnapshot:
    ts = datetime(2026, 7, 10, 16, 30)
    quotes = [
        OptionQuote(ticker, e, 100.0, cp, bid=1.0, ask=1.2, last=None,
                    volume=None, open_interest=None, timestamp=ts)
        for e in expiries for cp in ("C", "P")
    ]
    return ChainSnapshot(ticker, 100.0, ts, quotes, "american",
                         settlement=settlement)


def test_order_equals_date_order_with_and_without_settlement():
    expiries = [date(2026, 7, 17), date(2026, 7, 13), date(2026, 8, 21),
                date(2026, 7, 10)]
    for settle in (settlement_map(set(expiries), root="SPY"), None):
        snap = _snap("SPY", expiries, settle)
        state = AppState(date(2026, 7, 10), provider=_StoredChains({"SPY": snap}))
        state.set_expiries("SPY", sorted(expiries))
        state.snapshot("SPY")  # load the chain so the settlement map is visible
        assert service.ordered_expiries(state, "SPY", expiries) == sorted(expiries)


def test_am_settle_sorts_before_pm_on_the_same_date():
    """The KEY semantics (the part a future same-date pair split inherits):
    an AM-settled 3rd-Friday index expiry keys before a PM close settle of
    the same date, and both stay inside their date vs neighbors."""
    third_friday = date(2026, 7, 17)  # a 3rd Friday: AM-settled for SPX roots
    am = settlement_map({third_friday}, root="SPX")[third_friday]
    pm = settlement_map({third_friday}, root="SPY")[third_friday]
    assert am.style == "am" and pm.style == "pm"
    assert am.settle < pm.settle  # 09:30 ET before 16:00 ET, same date
    day_before_pm = settlement_map({date(2026, 7, 16)}, root="SPY")[date(2026, 7, 16)]
    assert day_before_pm.settle < am.settle  # never crosses calendar dates

"""Exact expiry-time semantics (volfit.data.expiry_time + store schema v7).

Contracts: the NYSE calendar is computed from RULES (holidays incl. Good
Friday, observation shifts, half-days); settlement conventions produce the
right UTC-naive instants (PM close, AM index open, half-day close, DST both
ways); the settlement map persists through the snapshot store (v7) and
through a universe prune — which must also stop dropping zero_carry and
tick_size (the latent metadata-loss bug this change fixed). Nothing here
feeds prepared.t/tau — fits stay byte-identical (suite-guarded).
"""

from __future__ import annotations

from datetime import date, datetime

from volfit.data.expiry_time import (
    default_settlement,
    exact_year_fraction,
    is_half_day,
    is_trading_day,
    nyse_holidays,
    settlement_map,
)
from volfit.data.types import ChainSnapshot, ExpirySettlement, OptionQuote


# -------------------------------------------------------------------- calendar
def test_nyse_holidays_2026_from_rules():
    days = nyse_holidays(2026)
    assert date(2026, 1, 1) in days  # New Year's (Thursday)
    assert date(2026, 1, 19) in days  # MLK (3rd Monday)
    assert date(2026, 2, 16) in days  # Washington's Birthday
    assert date(2026, 4, 3) in days  # Good Friday (Easter 2026-04-05)
    assert date(2026, 5, 25) in days  # Memorial Day
    assert date(2026, 6, 19) in days  # Juneteenth
    assert date(2026, 7, 3) in days  # Independence Day OBSERVED (Jul 4 = Sat)
    assert date(2026, 7, 4) not in days
    assert date(2026, 9, 7) in days  # Labor Day
    assert date(2026, 11, 26) in days  # Thanksgiving
    assert date(2026, 12, 25) in days  # Christmas


def test_good_friday_across_years():
    assert date(2024, 3, 29) in nyse_holidays(2024)
    assert date(2025, 4, 18) in nyse_holidays(2025)


def test_new_years_saturday_observed_in_prior_year():
    # Jan 1 2028 is a Saturday: observed Friday 2027-12-31, which belongs to
    # 2027's holiday set; 2028 has NO New Year's closure at all.
    assert date(2027, 12, 31) in nyse_holidays(2027)
    assert date(2028, 1, 1) not in nyse_holidays(2028)


def test_half_days():
    assert is_half_day(date(2026, 11, 27))  # day after Thanksgiving
    assert is_half_day(date(2026, 12, 24))  # Christmas Eve (Thursday)
    assert is_half_day(date(2024, 7, 3))  # Jul 3 2024 (Wednesday session)
    assert not is_half_day(date(2026, 7, 3))  # full observed holiday, no session
    assert not is_half_day(date(2026, 6, 18))  # ordinary Thursday
    assert not is_trading_day(date(2026, 7, 4))  # Saturday


# ------------------------------------------------------------------ settlement
def test_pm_settlement_close_instant_edt():
    s = default_settlement(date(2026, 6, 18))  # ordinary June Thursday, EDT
    assert s.style == "pm"
    assert s.last_trade == s.settle == datetime(2026, 6, 18, 20, 0)  # 16:00 ET


def test_pm_settlement_half_day_and_est():
    s = default_settlement(date(2026, 12, 24))  # half-day, December EST
    assert s.settle == datetime(2026, 12, 24, 18, 0)  # 13:00 ET = 18:00 UTC


def test_am_settlement_index_monthly():
    s = default_settlement(date(2026, 6, 18), root="SPX")
    assert s.style == "am"
    assert s.settle == datetime(2026, 6, 18, 13, 30)  # 09:30 ET open
    assert s.last_trade == datetime(2026, 6, 17, 20, 15)  # prev day 16:15 ET
    # The PM weekly sibling settles on the close like everything else.
    assert default_settlement(date(2026, 6, 18), root="SPXW").style == "pm"


def test_non_trading_expiry_rolls_back_to_previous_session():
    s = default_settlement(date(2026, 7, 4))  # Saturday; Jul 3 = observed holiday
    assert s.settle == datetime(2026, 7, 2, 20, 0)  # Thursday close


def test_exact_year_fraction_signed():
    settle = datetime(2026, 6, 18, 20, 0)
    yf = exact_year_fraction(datetime(2026, 6, 18, 14, 0), settle)
    assert abs(yf - 0.25 / 365.0) < 1e-12  # six hours of life left
    assert exact_year_fraction(datetime(2026, 6, 18, 21, 0), settle) < 0.0


# ----------------------------------------------------------- persistence + flow
def _chain(settlement=None) -> ChainSnapshot:
    e = date(2026, 6, 18)
    q = OptionQuote(ticker="ALPHA", expiry=e, strike=100.0, call_put="C",
                    bid=1.0, ask=1.2)
    return ChainSnapshot(
        ticker="ALPHA", spot=100.0, timestamp=datetime(2026, 6, 10, 20, 0),
        quotes=[q], exercise_style="american", zero_carry=True, tick_size=0.01,
        settlement=settlement,
    )


def test_snapshot_round_trip_keeps_settlement(tmp_path):
    from volfit.data.store import VolStore

    stamped = _chain(settlement_map([date(2026, 6, 18)], root="ALPHA"))
    plain = _chain(None)
    with VolStore(tmp_path / "vol.db") as store:
        sid_stamped = store.save_snapshot(stamped)
        sid_plain = store.save_snapshot(plain)
        loaded = store.load_snapshot(sid_stamped)
        assert loaded.settlement == stamped.settlement  # exact round-trip
        assert store.load_snapshot(sid_plain).settlement is None


def test_prune_preserves_chain_metadata():
    """The universe prune must carry zero_carry / tick_size / settlement —
    it silently dropped ALL chain-level metadata before schema v7."""
    from volfit.api.state import AppState

    state = AppState(date(2026, 6, 10))
    tk = state.active_tickers()[0]
    state.ensure_chain(tk)
    snap = state.snapshot(tk)
    expiries = snap.expiries()
    assert snap.settlement is not None  # synthetic provider stamps it now
    flagged = ChainSnapshot(
        ticker=snap.ticker, spot=snap.spot, timestamp=snap.timestamp,
        quotes=snap.quotes, exercise_style=snap.exercise_style,
        zero_carry=True, tick_size=0.05, settlement=snap.settlement,
    )
    state._snapshots[tk] = flagged
    keep = expiries[:2]
    state._reconcile_chain_selection(tk, keep)
    pruned = state.snapshot(tk)
    assert pruned.zero_carry is True
    assert pruned.tick_size == 0.05
    assert set(pruned.settlement) == set(keep)  # filtered, not dropped
    assert all(isinstance(s, ExpirySettlement) for s in pruned.settlement.values())

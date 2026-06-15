"""OCC / OPRA option-symbol parsing (volfit.data.occ)."""

from __future__ import annotations

from datetime import date

import pytest

from volfit.data.occ import (
    OccOption,
    format_option_symbol,
    parse_option_symbol,
    underlying_of,
)


def test_parse_standard_symbol():
    occ = parse_option_symbol("O:SPY260616C00500000")
    assert occ == OccOption(
        underlying="SPY", expiry=date(2026, 6, 16), call_put="C", strike=500.0
    )


def test_parse_put_and_fractional_strike():
    occ = parse_option_symbol("O:AAPL250117P00192500")
    assert occ.underlying == "AAPL"
    assert occ.expiry == date(2025, 1, 17)
    assert occ.call_put == "P"
    assert occ.strike == 192.5


def test_parse_multichar_root():
    # Weekly SPX root SPXW — the root is whatever precedes the fixed 15-char tail.
    occ = parse_option_symbol("O:SPXW260320C05000000")
    assert occ.underlying == "SPXW" and occ.strike == 5000.0


def test_round_trip():
    sym = "O:QQQ260918P00350000"
    occ = parse_option_symbol(sym)
    assert format_option_symbol(occ.underlying, occ.expiry, occ.call_put, occ.strike) == sym


@pytest.mark.parametrize(
    "bad",
    [
        "SPY260616C00500000",  # missing O: prefix
        "O:SPY",  # too short
        "O:SPY260616X00500000",  # bad type letter
        "O:SPY2606XXC00500000",  # non-numeric date
        "O:260616C00500000",  # missing root
        "",
    ],
)
def test_parse_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_option_symbol(bad)


def test_underlying_of_is_safe_filter():
    assert underlying_of("O:SPY260616C00500000") == "SPY"
    assert underlying_of("garbage") is None

"""SGX delayed option chains (volfit.data.sgx) over the generic exchange
provider. Offline: canned API payloads in the shapes captured 2026-08-21
(delivery months, per-month strike rows with call-/put- fields, futures with
last-trading-date and -adj prices); the one live test is VOLFIT_LIVE-gated.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest

from volfit.data.exchange import ExchangeChainProvider
from volfit.data.sgx import (
    SgxAdapter, chain_url, contract_code, delivery_months, futures_url, months_url, parse_rows,
    rule_expiry, second_friday, to_utc,
)


def _row(strike, c=(1500.0, 1520.0, 1510.0, 12.0, 300.0), p=(None, None, None, 0.0, 0.0), ind="2", ts=1787317242545):
    return {
        "strike-price": strike, "price-fractional-indicator": ind, "updated-time": ts, "delivery-month": "2026-09",
        "call-best-bid-price": c[0], "call-best-ask-price": c[1], "call-last-trade-price": c[2], "call-total-volume": c[3], "call-open-interest": c[4],
        "put-best-bid-price": p[0], "put-best-ask-price": p[1], "put-last-trade-price": p[2], "put-total-volume": p[3], "put-open-interest": p[4],
        "call-symbol": f"NKU26_C{int(strike)}", "put-symbol": f"NKU26_P{int(strike)}",
    }


FILES = {
    months_url("NK"): {"data": [{"delivery-month": "2026-09"}, {"delivery-month": "2026-09"}, {"delivery-month": "2026-10"}, {"delivery-month": "2026-12"}]},
    months_url("NK", "futures"): {"data": [{"delivery-month": "2026-09"}, {"delivery-month": "2026-12"}]},
    futures_url("NK", "2026-09"): {"data": [{"symbol": "NKU26", "last-traded-price-adj": 66065.0, "best-ask-price": 6606500.0, "last-trading-date": "2026-09-09", "price-fractional-indicator": "2"}]},
    futures_url("NK", "2026-12"): {"data": [{"symbol": "NKZ26", "last-traded-price-adj": 66200.0, "last-trading-date": "2026-12-09"}]},
    chain_url("NK", "2026-09"): {"data": [_row(66000.0), _row(70000.0, c=(None, None, None, 0.0, 5.0), p=(3800.0, 3850.0, None, 2.0, 40.0))]},
    chain_url("NK", "2026-10"): {"data": [_row(66000.0, c=(150000.0, 152000.0, None, 1.0, 1.0))]},  # scaled x100 (guard)
    chain_url("NK", "2026-12"): {"data": []},
}


class FakeFetch:
    def __init__(self, files):
        self.files = dict(files)
        self.calls: list[str] = []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.files:
            raise ValueError(f"not found: {url}")
        return self.files[url]


def _provider():
    fetch = FakeFetch(FILES)
    ad = SgxAdapter(); ad.workers = 2
    return ExchangeChainProvider(["NK"], ad, fetch_json=fetch), fetch


def test_codes_dates_and_helpers():
    assert contract_code("nikkei") == "NK" and contract_code("^N225") == "NK" and contract_code("FCH") == "FCH" and contract_code("XYZ") == "XYZ"
    assert second_friday(2026, 9) == date(2026, 9, 11) and rule_expiry("NK", "2026-09") == date(2026, 9, 10)
    assert rule_expiry("FCH", "2026-08") == date(2026, 8, 28) and rule_expiry("NK", "bad") is None
    assert to_utc(1787317242545) == datetime(2026, 8, 21, 13, 0, 42) and to_utc("x") is None
    assert delivery_months(FILES[months_url("NK")]) == ["2026-09", "2026-10", "2026-12"]


def test_parse_rows_sides_blanks_and_scale_guard():
    stamp = datetime(2026, 8, 21, 14, 20)
    q = parse_rows("nk", date(2026, 9, 10), FILES[chain_url("NK", "2026-09")]["data"], stamp, spot=66065.0)
    by = {(x.strike, x.call_put): x for x in q}
    assert (by[(66000.0, "C")].bid, by[(66000.0, "C")].ask, by[(66000.0, "C")].last, by[(66000.0, "C")].volume, by[(66000.0, "C")].open_interest) == (1500.0, 1520.0, 1510.0, 12, 300)
    assert (66000.0, "P") not in by and by[(70000.0, "P")].bid == 3800.0 and (70000.0, "C") not in by
    assert all(x.ticker == "NK" and x.timestamp == stamp for x in q)
    scaled = parse_rows("NK", date(2026, 10, 8), FILES[chain_url("NK", "2026-10")]["data"], stamp, spot=66065.0)
    assert scaled[0].bid == 1500.0 and scaled[0].ask == 1520.0  # x100 fractional units de-scaled by the guard


def test_provider_chain_uses_futures_dates_spot_and_rules():
    prov, fetch = _provider()
    assert prov.available_expiries("NK") == [date(2026, 9, 9), date(2026, 10, 8)]  # futures LTD for Sep; rule (day before 2nd Fri) for Oct; Dec empty
    snap = prov.fetch_chain("NK", [date(2026, 9, 9)])
    assert snap.spot == 66065.0 and snap.exercise_style == "european" and snap.timestamp == datetime(2026, 8, 21, 13, 0, 42)
    assert {(q.strike, q.call_put) for q in snap.quotes} == {(66000.0, "C"), (70000.0, "P")}
    assert fetch.calls.count(months_url("NK")) == 1 and all(chain_url("NK", m) in fetch.calls for m in ("2026-09", "2026-10", "2026-12"))


def test_spot_status_and_unknown_code():
    prov, fetch = _provider()
    assert prov.spot("NK") == 66065.0
    assert prov.feed_status() == ("amber", "SGX ~10-min delayed")
    with pytest.raises(ValueError, match="lists no options"):
        prov.fetch_chain("ZZZ")


@pytest.mark.skipif(not os.environ.get("VOLFIT_LIVE"), reason="live SGX API")
def test_live_sgx_nk():
    prov = ExchangeChainProvider(["NK"], SgxAdapter())
    exp = prov.available_expiries("NK")
    assert exp

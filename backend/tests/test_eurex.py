"""Eurex delayed quotes / EOD settlement chains (volfit.data.eurex) over the
generic exchange provider. Offline: canned ``overallstatistics`` payloads in
the shapes captured 2026-08-21 (overview: header + one row per expiry; detail:
dataRowsCall/dataRowsPut with settle / last / vol / OI and, intraday, bid /
ask); the one live test is VOLFIT_LIVE-gated.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest

from volfit.data.eurex import (
    EurexAdapter, cet_close_utc, detail_url, overview_url, parse_busdate, parse_detail, parse_overview, product_id,
)
from volfit.data.exchange import ExchangeChainProvider

HEADER = {"underlyingClosingPrice": 6422.06000000036, "volume": 724871.0, "openInterest": 29411424.0, "putCallRatio": "1.622",
          "tradingDates": ["20-08-2026 12:00", "19-08-2026 12:00", "18-08-2026 12:00"]}
OVERVIEW = {"header": HEADER, "meta": {}, "dataRows": [
    {"date": "20260831", "callVolume": 4209.0, "putVolume": 1867.0, "total": 6076.0, "contractType": "E"},
    {"date": "20260918", "callVolume": 66477.0, "putVolume": 93265.0, "total": 159742.0, "contractType": "M"},
    {"date": "20260918", "callVolume": 0.0, "putVolume": 0.0, "total": 0.0, "contractType": "M"},  # duplicate row
    {"date": "20260819", "callVolume": 1.0, "putVolume": 1.0, "total": 2.0, "contractType": "W"},  # already expired
]}


def _row(strike, settle, last=0.0, vol=0.0, oi=0.0, version=0.0, **extra):
    return {"callOrPut": "Call", "strike": strike, "versionNumber": version, "volume": vol, "openInterest": oi,
            "open": 0.0, "high": 0.0, "low": 0.0, "last": last, "dSettle": settle, **extra}


DETAIL_M = {"meta": {}, "header": {"date": "20260918", "contractType": "M"},
            "dataRowsCall": [_row(6400.0, 173.7, last=170.5, vol=12.0, oi=4500.0),
                             _row(6500.0, 118.2, bid=117.0, ask=119.5, bidVol=20.0, askVol=15.0, lastTraded="10:15:02"),
                             _row(6600.0, 0.0), _row(6700.0, 45.1, version=1.0), _row(0.0, 3.0)],
            "dataRowsPut": [_row(6400.0, 150.9, vol=0.0, oi=12000.0)]}
DETAIL_E = {"meta": {}, "header": {"date": "20260831", "contractType": "E"}, "dataRowsCall": [_row(6400.0, 88.0)], "dataRowsPut": []}
FILES = {
    overview_url(69660): OVERVIEW,
    detail_url(69660, "20260918", "M"): DETAIL_M,
    detail_url(69660, "20260831", "E"): DETAIL_E,
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


def _provider(tickers=("OESX",)):
    fetch = FakeFetch(FILES)
    ad = EurexAdapter(); ad.workers = 2
    return ExchangeChainProvider(list(tickers), ad, fetch_json=fetch), fetch, ad


def test_product_ids_urls_and_date_helpers():
    assert product_id("oesx") == 69660 and product_id("^STOXX50E") == 69660 and product_id("SX5E Index") == 69660
    assert product_id("DAX") == 70044 and product_id("70284") == 70284
    with pytest.raises(ValueError, match="product id unknown"):
        product_id("OSMI")
    assert overview_url(69660) == "https://www.eurex.com/api/v1/overallstatistics/69660?filtertype=overview"
    assert detail_url(69660, "20260918", "M", "20260820").endswith("filtertype=detail&productdate=20260918&contracttype=M&busdate=20260820")
    assert parse_busdate(HEADER) == date(2026, 8, 20) and parse_busdate({}) is None
    assert cet_close_utc(date(2026, 8, 20)) == datetime(2026, 8, 20, 15, 30)  # CEST
    assert cet_close_utc(date(2026, 1, 15)) == datetime(2026, 1, 15, 16, 30)  # CET
    assert cet_close_utc(date(2026, 3, 29)) == datetime(2026, 3, 29, 15, 30) and cet_close_utc(date(2026, 10, 25)) == datetime(2026, 10, 25, 16, 30)


def test_parse_overview_and_detail_tiers():
    spot, busdate, expiries = parse_overview(OVERVIEW)
    assert spot == pytest.approx(6422.06) and busdate == date(2026, 8, 20)
    assert expiries == [(date(2026, 8, 19), "W"), (date(2026, 8, 31), "E"), (date(2026, 9, 18), "M")]
    eod, live = datetime(2026, 8, 20, 15, 30), datetime(2026, 8, 21, 9, 45)
    q, n = parse_detail("oesx", date(2026, 9, 18), DETAIL_M, eod, live)
    by = {(x.strike, x.call_put): x for x in q}
    assert n == 1 and set(by) == {(6400.0, "C"), (6500.0, "C"), (6400.0, "P")}  # zero settle, version 1, zero strike dropped
    s = by[(6400.0, "C")]
    assert (s.bid, s.ask, s.last, s.volume, s.open_interest, s.timestamp) == (173.7, 173.7, 170.5, 12, 4500, eod)
    l = by[(6500.0, "C")]
    assert (l.bid, l.ask, l.last, l.timestamp) == (117.0, 119.5, 118.2, live)  # live book wins; last falls back to settle
    assert by[(6400.0, "P")].last == 150.9 and all(x.ticker == "OESX" for x in q)
    q2, n2 = parse_detail("OESX", date(2026, 9, 18), DETAIL_M, eod, live, settlement_quotes=False)
    assert n2 == 1 and {(x.strike, x.call_put): (x.bid, x.ask) for x in q2}[(6400.0, "C")] == (None, None)


def test_provider_chain_spot_status_and_unknown():
    prov, fetch, ad = _provider()
    assert prov.feed_status() == ("amber", "Eurex ~15-min delayed / EOD settlement")
    assert prov.available_expiries("OESX") == [date(2026, 8, 31), date(2026, 9, 18)]  # the expired weekly is dropped
    snap = prov.fetch_chain("OESX", [date(2026, 9, 18)])
    assert snap.spot == pytest.approx(6422.06) and snap.exercise_style == "european"
    assert {(q.strike, q.call_put) for q in snap.quotes} == {(6400.0, "C"), (6500.0, "C"), (6400.0, "P")}
    assert fetch.calls.count(overview_url(69660)) == 2 and detail_url(69660, "20260831", "E") in fetch.calls  # status probe + chain (then cached)
    assert detail_url(69660, "20260819", "W") not in fetch.calls
    assert ad.status_text() == "Eurex ~15-min delayed"  # one live row in the fixture
    ad._last = ("eod", date(2026, 8, 20))
    assert ad.status_text() == "Eurex EOD settlement (2026-08-20)"
    assert prov.spot("OESX") == pytest.approx(6422.06)
    with pytest.raises(ValueError, match="product id unknown"):
        prov.fetch_chain("OSMI")
    with pytest.raises(ValueError, match="lists no product"):
        prov.fetch_chain("99999")


def test_eod_only_chain_is_stamped_at_the_close():
    files = dict(FILES)
    files[detail_url(69660, "20260918", "M")] = {"dataRowsCall": [_row(6400.0, 173.7)], "dataRowsPut": []}
    ad = EurexAdapter()
    raw = ad.fetch_chain("OESX", FakeFetch(files))
    assert raw.timestamp == datetime(2026, 8, 20, 15, 30) and ad.status_text() == "Eurex EOD settlement (2026-08-20)"
    assert [(q.expiry, q.bid) for q in raw.quotes] == [(date(2026, 8, 31), 88.0), (date(2026, 9, 18), 173.7)]


@pytest.mark.skipif(not os.environ.get("VOLFIT_LIVE"), reason="live Eurex API")
def test_live_eurex_oesx():
    prov = ExchangeChainProvider(["OESX"], EurexAdapter())
    exp = prov.available_expiries("OESX")
    assert exp
    snap = prov.fetch_chain("OESX", exp[:1])
    assert snap.spot > 0 and snap.quotes

"""ASX delayed option chains (volfit.data.asx) over the generic exchange
provider. Offline: canned Markit payloads in the exact shape confirmed live
2026-08-21 (base: datesAvailable + underlyingAsset; expiry-groups: items[] with
exerciseGroups call/put dicts); the one live test is VOLFIT_LIVE-gated.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest

from volfit.data.asx import (
    BASE_URL, AsxAdapter, asx_code, available_dates, build_chain, groups_url, parse_groups, underlying,
)
from volfit.data.exchange import ExchangeChainProvider

TODAY = date.today()
W1 = TODAY + timedelta(days=6)
M1 = TODAY + timedelta(days=27)
M2 = TODAY + timedelta(days=55)


def _series(side: str, strike: float, bid, ask, last, oi, vol, style="European", expiry=M1):
    return {"chainType": side, "contractSize": 10, "dateExpiry": expiry.isoformat(), "name": f"{strike} {side.upper()}",
            "openInterest": oi, "priceAsk": ask, "priceBid": bid, "priceExercise": strike, "priceLast": last,
            "priceTheoretical": 1.0, "periodicity": "Monthly", "style": style, "symbol": "XJO7K9", "volume": vol,
            "xid": "1", "optionRoot": "AXJO"}


def _base(code="XJO", issue="IN", spot=9058.9):
    return {"data": {
        "datesAvailable": {"quarterly": [], "monthly": [M1.isoformat(), M2.isoformat()], "weekly": [W1.isoformat()]},
        "datesIncluded": {"quarterly": [], "monthly": [M1.isoformat()], "weekly": []},
        "expiryGroups": {"items": []},
        "underlyingAsset": {"displayName": "S&P/ASX 200", "issueType": issue, "priceLast": spot, "symbol": code, "xid": "x"},
    }}


def _groups(style="European"):
    return {"data": {"items": [
        {"date": W1.isoformat(), "exerciseGroups": [
            {"priceExercise": 9000, "periodicity": "Weekly",
             "call": _series("Call", 9000, 100, 110, 105, 12, 3, style, W1),
             "put": _series("Put", 9000, 0, 5, 0, 0, 0, style, W1)},  # 0 bid/last -> None
        ]},
        {"date": M1.isoformat(), "exerciseGroups": [
            {"priceExercise": 8375, "periodicity": "Monthly",
             "call": _series("Call", 8375, 602, 647, 0, 0, 0, style),
             "put": _series("Put", 8375, 7, 12, 60, 160, 5, style)},
            {"priceExercise": 9075, "periodicity": "Monthly",
             "call": _series("Call", 9075, 20, 29, 26, 253, 9, style),
             "put": {"priceBid": 0, "priceAsk": 0, "priceLast": 0}},  # dead side: dropped
            {"priceExercise": None, "call": {}, "put": {}},  # no strike: skipped
        ]},
    ]}}


class FakeFetch:
    def __init__(self, files):
        self.files = dict(files)
        self.calls: list[str] = []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.files:
            raise ValueError(f"not found: {url}")
        return self.files[url]


def _provider(**kw):
    files = {
        BASE_URL.format(code="XJO"): _base(),
        groups_url("XJO", [W1, M1, M2]): _groups(),
        BASE_URL.format(code="BHP"): _base("BHP", "EQ", 65.16),
        groups_url("BHP", [W1, M1, M2]): _groups("American"),
    }
    fetch = FakeFetch(files)
    return ExchangeChainProvider(["XJO", "BHP"], AsxAdapter(), fetch_json=fetch, **kw), fetch


def test_code_and_urls():
    assert asx_code("xjo") == "XJO" and asx_code("^XJO") == "XJO" and asx_code("BHP.AX") == "BHP"
    assert groups_url("XJO", [date(2026, 12, 17), "2027-01-21"]).endswith(
        "/XJO/options/expiry-groups?expiryDates=2026-12-17&expiryDates=2027-01-21")


def test_base_payload_readers():
    assert available_dates(_base()) == [W1, M1, M2]
    assert underlying(_base()) == (9058.9, "IN", "XJO")
    assert available_dates({"data": {}}) == [] and underlying({})[0] is None


def test_parse_groups_and_styles():
    stamp = datetime(2026, 8, 21, 12, 0)
    quotes, style = parse_groups("xjo", _groups(), stamp)
    assert style == "european"
    by = {(q.expiry, q.strike, q.call_put): q for q in quotes}
    c = by[(M1, 8375.0, "C")]
    assert (c.bid, c.ask, c.last, c.open_interest, c.volume, c.ticker) == (602.0, 647.0, None, 0, 0, "XJO")
    p = by[(W1, 9000.0, "P")]
    assert p.bid is None and p.ask == 5.0 and p.last is None
    assert (M1, 9075.0, "P") not in by and all(q.timestamp == stamp for q in quotes)
    assert len(quotes) == 5
    assert parse_groups("BHP", _groups("American"), stamp)[1] == "american"


def test_build_chain_stamps_delay_and_falls_back_on_issue_type():
    now = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)
    raw = build_chain("XJO", _base(), _groups(), now=now)
    assert raw.spot == 9058.9 and raw.timestamp == datetime(2026, 8, 21, 13, 40) and raw.exercise_style == "european"
    assert raw.security_type == "index"
    raw2 = build_chain("BHP", _base("BHP", "EQ", 65.16), {"data": {"items": []}}, now=now)
    assert raw2.quotes == [] and raw2.exercise_style == "american" and raw2.security_type == "stock"
    with pytest.raises(ValueError):
        build_chain("XJO", {"data": {}}, _groups())


def test_provider_two_requests_per_chain_and_cache():
    prov, fetch = _provider()
    assert prov.available_expiries("XJO") == [W1, M1]  # M2 has no groups in the fixture
    snap = prov.fetch_chain("XJO", [M1])
    assert snap.exercise_style == "european" and snap.spot == 9058.9 and snap.tick_size is None
    assert {(q.strike, q.call_put) for q in snap.quotes} == {(8375.0, "C"), (8375.0, "P"), (9075.0, "C")}
    assert fetch.calls == [BASE_URL.format(code="XJO"), groups_url("XJO", [W1, M1, M2])]  # base + groups, once
    bhp = prov.fetch_chain("BHP", [W1])
    assert bhp.exercise_style == "american" and bhp.spot == 65.16 and len(bhp.quotes) == 2


def test_spot_status_and_unknown_code():
    prov, fetch = _provider()
    assert prov.spot("XJO") == 9058.9
    assert prov.feed_status() == ("amber", "ASX ~20-min delayed")
    with pytest.raises(ValueError, match="lists no options"):
        prov.fetch_chain("ZZZ")
    fetch.files.clear()
    prov._status = None
    assert prov.feed_status() == ("red", "ASX unreachable")


@pytest.mark.skipif(not os.environ.get("VOLFIT_LIVE"), reason="live ASX API")
def test_live_asx_xjo():
    prov = ExchangeChainProvider(["XJO"], AsxAdapter())
    exp = prov.available_expiries("XJO")
    assert exp and prov.fetch_chain("XJO", exp[:1]).quotes


def test_mixed_styles_take_the_majority():
    """A class mixing styles (an American stock class listing a few European
    series) is tagged by the majority of its series, not alphabetically."""
    g = _groups("American")
    g["data"]["items"][0]["exerciseGroups"][0]["call"]["style"] = "European"  # one odd series
    assert parse_groups("BHP", g, datetime(2026, 8, 21, 12, 0))[1] == "american"

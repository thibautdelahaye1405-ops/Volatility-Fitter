"""Nasdaq delayed option chains (volfit.data.nasdaq) over the generic exchange
provider. Offline: canned payloads in the exact shape confirmed live 2026-08-21
(group-header rows + strike rows carrying both sides, "--" blanks, thousands
separators, drillDownURL expiry); the one live test is VOLFIT_LIVE-gated.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest

from volfit.data.exchange import ExchangeChainProvider
from volfit.data.nasdaq import (
    CHAIN_URL, INFO_URL, NasdaqAdapter, chain_ok, num, parse_chain, parse_drilldown,
    parse_group_date, parse_last_trade, parse_rows,
)

TODAY = date.today()
NEAR = TODAY + timedelta(days=30)
FAR = TODAY + timedelta(days=120)


def _url(root: str, d: date, cp: str, strike: float) -> str:
    return f"/market-activity/stocks/x/option-chain/call-put-options/{root.lower()}---{d:%y%m%d}{cp.lower()}{int(round(strike * 1000)):08d}"


def _header(d: date) -> dict:
    return {"expirygroup": d.strftime("%B %d, %Y").replace(" 0", " "), "expiryDate": None, "strike": None,
            "c_Bid": None, "c_Ask": None, "p_Bid": None, "p_Ask": None, "drillDownURL": None}


def _row(root: str, d: date, strike: float, c=("1.00", "1.20", "1.10", "10", "100"), p=("--", "0.05", "--", "--", "26,622")) -> dict:
    return {
        "expirygroup": "", "expiryDate": d.strftime("%b %d").replace(" 0", " "), "strike": f"{strike:,.2f}",
        "c_Last": c[2], "c_Bid": c[0], "c_Ask": c[1], "c_Volume": c[3], "c_Openinterest": c[4],
        "p_Last": p[2], "p_Bid": p[0], "p_Ask": p[1], "p_Volume": p[3], "p_Openinterest": p[4],
        "drillDownURL": _url(root, d, "c", strike),
    }


def _chain_payload(root="SPY", last_trade="LAST TRADE: $762.6 (AS OF AUG 21, 2026)"):
    rows = [
        _header(NEAR),
        _row(root, NEAR, 95.0, c=("6.10", "6.30", "6.20", "55", "1,200"), p=("--", "1.10", "--", "--", "40")),
        _row(root, NEAR, 105.0, c=("1.00", "1.20", "1.10", "--", "--"), p=("4.90", "5.10", "5.00", "3", "9")),
        _header(FAR),
        _row(root, FAR, 100.0, c=("--", "--", "--", "--", "--"), p=("3.00", "3.40", "3.20", "1", "7")),  # call side unlisted
    ]
    return {"data": {"totalRecord": len(rows), "lastTrade": last_trade, "table": {"rows": rows}}, "status": {"rCode": 200}}


WRONG = {"data": None, "message": None, "status": {"rCode": 400, "bCodeMessage": [{"code": 400}]}}


class FakeFetch:
    def __init__(self, files: dict[str, dict]):
        self.files = dict(files)
        self.calls: list[str] = []

    def __call__(self, url: str) -> dict:
        self.calls.append(url)
        if url not in self.files:
            raise ValueError(f"not found: {url}")
        return self.files[url]


def _provider(**kw):
    files = {
        CHAIN_URL.format(sym="SPY", ac="stocks"): WRONG,  # SPY is an ETF on Nasdaq's taxonomy
        CHAIN_URL.format(sym="SPY", ac="etf"): _chain_payload(),
        INFO_URL.format(sym="SPY", ac="stocks"): WRONG,
        INFO_URL.format(sym="SPY", ac="etf"): {"data": {"primaryData": {"lastSalePrice": "$766.01"}}},
        CHAIN_URL.format(sym="NDX", ac="stocks"): WRONG,
        CHAIN_URL.format(sym="NDX", ac="etf"): WRONG,
        CHAIN_URL.format(sym="NDX", ac="index"): _chain_payload("NDXP", "LATEST INDEX VALUE: 29,213.16 (AS OF AUG 20, 2026)"),
    }
    fetch = FakeFetch(files)
    return ExchangeChainProvider(["SPY", "NDX"], NasdaqAdapter(), fetch_json=fetch, **kw), fetch


# ------------------------------------------------------------------ pure
def test_number_and_text_parsers():
    assert num("10,860.40") == 10860.4 and num("$766.01") == 766.01 and num("--") is None and num("0.00") is None
    assert parse_last_trade("LAST TRADE: $762.6 (AS OF AUG 21, 2026)") == 762.6
    assert parse_last_trade("LATEST INDEX VALUE: 29,213.16 (AS OF AUG 20, 2026)") == 29213.16
    assert parse_last_trade(None) is None
    assert parse_group_date("August 21, 2026") == date(2026, 8, 21) and parse_group_date("nope") is None
    assert parse_drilldown("/x/spy---260821c00360000") == (date(2026, 8, 21), "C", 360.0)
    assert parse_drilldown("/x/ndxp--260911c18000000") == (date(2026, 9, 11), "C", 18000.0)
    assert parse_drilldown(None) is None and parse_drilldown("/x/garbage") is None
    assert chain_ok(WRONG) is False and chain_ok(_chain_payload()) is True


def test_parse_rows_splits_sides_and_handles_blanks():
    stamp = datetime(2026, 8, 21, 12, 0)
    quotes = parse_rows("spy", _chain_payload()["data"]["table"]["rows"], stamp)
    by = {(q.expiry, q.strike, q.call_put): q for q in quotes}
    c95 = by[(NEAR, 95.0, "C")]
    assert (c95.bid, c95.ask, c95.last, c95.volume, c95.open_interest, c95.ticker) == (6.1, 6.3, 6.2, 55, 1200, "SPY")
    p95 = by[(NEAR, 95.0, "P")]
    assert p95.bid is None and p95.ask == 1.1 and p95.last is None and p95.volume is None and p95.open_interest == 40
    assert (FAR, 100.0, "C") not in by  # fully blank side is not carried
    assert by[(FAR, 100.0, "P")].bid == 3.0 and all(q.timestamp == stamp for q in quotes)
    assert len(quotes) == 5


def test_parse_chain_stamps_the_documented_delay_and_styles():
    now = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)
    raw = parse_chain("SPY", _chain_payload(), "etf", None, now=now)
    assert raw.spot == 762.6 and raw.timestamp == datetime(2026, 8, 21, 13, 45) and raw.exercise_style == "american"
    raw2 = parse_chain("NDX", _chain_payload("NDXP"), "index", 29213.16, now=now)
    assert raw2.exercise_style == "european" and raw2.spot == 29213.16
    with pytest.raises(ValueError):
        parse_chain("SPY", WRONG, "stocks", None)


# -------------------------------------------------------------- provider
def test_asset_class_is_discovered_and_cached():
    prov, fetch = _provider()
    snap = prov.fetch_chain("SPY", [NEAR])
    assert snap.spot == 766.01 and snap.exercise_style == "american"  # live /info spot
    assert {(q.strike, q.call_put) for q in snap.quotes} == {(95.0, "C"), (95.0, "P"), (105.0, "C"), (105.0, "P")}
    assert fetch.calls[:2] == [CHAIN_URL.format(sym="SPY", ac="stocks"), CHAIN_URL.format(sym="SPY", ac="etf")]
    assert prov.adapter._class["SPY"] == "etf"
    prov.invalidate("SPY")
    prov.fetch_chain("SPY", [NEAR])
    assert fetch.calls[-2:] == [CHAIN_URL.format(sym="SPY", ac="etf"), INFO_URL.format(sym="SPY", ac="etf")]  # cached class first
    assert prov.available_expiries("NDX") == [NEAR, FAR]
    idx = prov.fetch_chain("NDX", [FAR])
    assert idx.exercise_style == "european" and idx.spot == 29213.16  # lastTrade fallback (no /info)


def test_spot_status_and_unknown_symbol():
    prov, fetch = _provider()
    assert prov.spot("SPY") == 766.01
    assert prov.feed_status() == ("amber", "Nasdaq ~15-min delayed")
    with pytest.raises(ValueError, match="lists no options"):
        prov.fetch_chain("ZZZZQ")
    fetch.files.clear()
    prov._status = None
    assert prov.feed_status()[0] == "red"


@pytest.mark.skipif(not os.environ.get("VOLFIT_LIVE"), reason="live Nasdaq API")
def test_live_nasdaq_spy():
    prov = ExchangeChainProvider(["SPY"], NasdaqAdapter())
    exp = prov.available_expiries("SPY")
    assert exp and prov.fetch_chain("SPY", exp[:1]).quotes

"""Cboe delayed option chains (volfit.data.cboe) over the generic exchange
provider (volfit.data.exchange). Offline: a canned CDN payload in the exact
shape confirmed live 2026-08-21 is served by a fake ``fetch_json``; the one live
test is skipped unless VOLFIT_LIVE is set.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import pytest

from volfit.data.cboe import CboeAdapter, OPTIONS_URL, QUOTE_URL, cdn_symbol, parse_chain, parse_timestamp
from volfit.data.exchange import ExchangeChainProvider

TODAY = date.today()


def _occ(root: str, d: date, cp: str, strike: float) -> str:
    return f"{root}{d:%y%m%d}{cp}{int(round(strike * 1000)):08d}"


NEAR = TODAY + timedelta(days=30)
FAR = TODAY + timedelta(days=120)
PAST = TODAY - timedelta(days=3)


def _payload(symbol="SPY", security_type="stock", spot=100.0, root="SPY", stamp="2026-08-21 11:45:27"):
    opts = [
        {"option": _occ(root, NEAR, "C", 95), "bid": 6.1, "ask": 6.3, "bid_size": 10, "ask_size": 12, "iv": 0.21,
         "open_interest": 1200.0, "volume": 55.0, "last_trade_price": 6.2, "last_trade_time": "2026-08-20T15:59:00"},
        {"option": _occ(root, NEAR, "P", 95), "bid": 0.0, "ask": 1.1, "open_interest": 40.0, "volume": float("nan"),
         "last_trade_price": 0.0},  # 0 bid -> None; NaN volume -> None; 0 last -> None
        {"option": _occ(root, NEAR, "C", 105), "bid": 1.0, "ask": 1.2, "open_interest": 0.0, "volume": 0.0,
         "last_trade_price": 1.1},
        {"option": _occ(root, FAR, "P", 100), "bid": 3.0, "ask": 3.4, "open_interest": 7.0, "volume": 1.0,
         "last_trade_price": 3.2},
        {"option": _occ(root, PAST, "C", 100), "bid": 1.0, "ask": 1.2},  # expired: listed but filtered
        {"option": "GARBAGE", "bid": 1, "ask": 2},  # not OCC: skipped
    ]
    return {
        "timestamp": stamp,
        "symbol": symbol,
        "data": {
            "symbol": symbol, "security_type": security_type, "current_price": spot,
            "bid": spot - 0.01, "ask": spot + 0.01, "last_trade_time": "2026-08-20T16:00:00",
            "options": opts,
        },
    }


class FakeFetch:
    """url -> payload, recording calls; unknown urls refuse like the CDN (ValueError)."""

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
        OPTIONS_URL.format(sym="SPY"): _payload(),
        QUOTE_URL.format(sym="SPY"): {"data": {"symbol": "SPY", "current_price": 101.5}},
        OPTIONS_URL.format(sym="_SPX"): _payload("_SPX", "index", 5000.0, "SPXW"),
        QUOTE_URL.format(sym="_SPX"): {"data": {"symbol": "^SPX", "current_price": 5001.0}},
    }
    fetch = FakeFetch(files)
    return ExchangeChainProvider(["SPY", "SPX"], CboeAdapter(), fetch_json=fetch, **kw), fetch


# ------------------------------------------------------------------ pure
def test_cdn_symbol_maps_indices_and_styles():
    assert cdn_symbol("SPY") == "SPY" and cdn_symbol("spy") == "SPY"
    assert cdn_symbol("SPX") == "_SPX" and cdn_symbol("^SPX") == "_SPX" and cdn_symbol("SPX Index") == "_SPX"
    assert cdn_symbol("SPXW") == "_SPX" and cdn_symbol("_VIX") == "_VIX" and cdn_symbol("^RUT") == "_RUT"
    assert cdn_symbol("XSP") == "_XSP" and cdn_symbol("NVDA") == "NVDA"


def test_parse_timestamp_is_utc():
    assert parse_timestamp("2026-08-21 11:45:27") == datetime(2026, 8, 21, 11, 45, 27)
    assert parse_timestamp("2026-08-21T11:45:27+02:00") == datetime(2026, 8, 21, 9, 45, 27)
    assert isinstance(parse_timestamp("garbage"), datetime) and isinstance(parse_timestamp(None), datetime)


def test_parse_chain_builds_quotes_in_app_conventions():
    raw = parse_chain("spy", _payload())
    assert raw.ticker == "SPY" and raw.spot == 100.0 and raw.exercise_style == "american"
    assert raw.timestamp == datetime(2026, 8, 21, 11, 45, 27)
    assert raw.spot_bid == 99.99 and raw.spot_ask == 100.01 and raw.security_type == "stock"
    assert len(raw.quotes) == 5  # GARBAGE skipped, expired kept here (the provider filters)
    c95 = next(q for q in raw.quotes if q.strike == 95.0 and q.call_put == "C")
    assert (c95.bid, c95.ask, c95.last, c95.volume, c95.open_interest) == (6.1, 6.3, 6.2, 55, 1200)
    assert c95.expiry == NEAR and c95.timestamp == raw.timestamp
    p95 = next(q for q in raw.quotes if q.strike == 95.0 and q.call_put == "P")
    assert p95.bid is None and p95.ask == 1.1 and p95.last is None and p95.volume is None
    idx = parse_chain("SPX", _payload("_SPX", "index", 5000.0, "SPXW"))
    assert idx.exercise_style == "european" and idx.quotes[0].ticker == "SPX"


def test_parse_chain_rejects_non_chain_payloads():
    with pytest.raises(ValueError):
        parse_chain("SPY", {"timestamp": "x"})
    with pytest.raises(ValueError):
        parse_chain("SPY", {"data": {"options": [], "current_price": 0}})


# -------------------------------------------------------------- provider
def test_expiries_chain_and_cache():
    prov, fetch = _provider()
    assert prov.available_expiries("SPY") == [NEAR, FAR]  # expired filtered, sorted
    snap = prov.fetch_chain("SPY", [NEAR])
    assert snap.ticker == "SPY" and snap.spot == 100.0 and snap.exercise_style == "american"
    assert snap.timestamp == datetime(2026, 8, 21, 11, 45, 27)  # the VENUE's publication time
    assert {(q.strike, q.call_put) for q in snap.quotes} == {(95.0, "C"), (95.0, "P"), (105.0, "C")}
    assert snap.tick_size == 0.01 and snap.settlement and NEAR in snap.settlement
    full = prov.fetch_chain("SPY")
    assert {q.expiry for q in full.quotes} == {NEAR, FAR}
    # ONE download served expiries + two chains (the 6-14 MB file is cached)
    assert fetch.calls.count(OPTIONS_URL.format(sym="SPY")) == 1
    prov.invalidate("SPY")
    prov.fetch_chain("SPY")
    assert fetch.calls.count(OPTIONS_URL.format(sym="SPY")) == 2


def test_index_ticker_is_european_and_uses_the_underscore_file():
    prov, fetch = _provider()
    snap = prov.fetch_chain("SPX", [NEAR])
    assert snap.exercise_style == "european" and snap.spot == 5000.0
    assert OPTIONS_URL.format(sym="_SPX") in fetch.calls
    assert all(q.ticker == "SPX" for q in snap.quotes)


def test_spot_uses_the_light_quote_endpoint_and_falls_back_to_the_chain():
    prov, fetch = _provider()
    assert prov.spot("SPY") == 101.5 and fetch.calls[-1] == QUOTE_URL.format(sym="SPY")
    del fetch.files[QUOTE_URL.format(sym="SPY")]
    assert prov.spot("SPY") == 100.0  # cached/downloaded chain spot


def test_unknown_symbol_is_a_clean_error_and_status_reports_it():
    prov, fetch = _provider()
    with pytest.raises(ValueError, match="lists no options"):
        prov.fetch_chain("ZZZZQ")
    assert prov.feed_status()[0] == "red"  # probe ok, but the last fetch was refused
    prov._status = None
    prov.fetch_chain("SPY")  # a success clears the refusal
    prov._status = None
    assert prov.feed_status() == ("amber", "Cboe ~15-min delayed")


def test_feed_status_red_when_unreachable():
    prov, fetch = _provider()
    fetch.files.clear()
    assert prov.feed_status() == ("red", "Cboe unreachable")


def test_selection_with_no_contracts_raises():
    prov, _ = _provider()
    with pytest.raises(ValueError):
        prov.fetch_chain("SPY", [TODAY + timedelta(days=999)])


@pytest.mark.skipif(not os.environ.get("VOLFIT_LIVE"), reason="live Cboe CDN")
def test_live_cboe_spy():
    prov = ExchangeChainProvider(["SPY"], CboeAdapter())
    exp = prov.available_expiries("SPY")
    assert exp and prov.fetch_chain("SPY", exp[:1]).quotes

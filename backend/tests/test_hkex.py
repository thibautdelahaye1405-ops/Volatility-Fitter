"""HKEX delayed option chains (volfit.data.hkex) over the generic exchange
provider. Offline: a fake text-capable fetcher serves the product page (token)
and JSONP widget answers in the exact shapes confirmed live 2026-08-21 (contract
list, near-window + full-window chains, futures, marquee, info); the one live
test is VOLFIT_LIVE-gated.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from volfit.data.exchange import ExchangeChainProvider
from volfit.data.hkex import (
    TOKEN_PAGE, WIDGET, HkexAdapter, class_code, contract_expiry, parse_lastupd, parse_optionlist,
    parse_token, unwrap_jsonp,
)

PAGE = """<script>
  if (typeof (LabCI) === "undefined") LabCI = {};
  LabCI.getToken = function () {
    // ----- THIS IS A SAMPLE IMPLEMENTATION -----
    //return "Base64-AES-Encrypted-Token";
    return "TOK%2fABC";
  };
</script>"""


def _jsonp(obj) -> str:
    import json
    return "cb(" + json.dumps({"data": obj, "qid": "1"}) + ");"


class FakeFetch:
    """Text-capable fetcher: dispatches widget endpoints by name + params."""

    def __init__(self, token_page=PAGE, refuse_first=False):
        self.token_page = token_page
        self.calls: list[str] = []
        self.refuse_first = refuse_first
        self.tokens_served = 0

    def __call__(self, url):  # JSON path unused by HKEX
        raise ValueError("json not served")

    def text(self, url):
        self.calls.append(url)
        if url.startswith(TOKEN_PAGE):
            self.tokens_served += 1
            return self.token_page
        assert url.startswith(WIDGET), url
        ep = url[len(WIDGET):].split("?", 1)[0]
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        assert q.get("callback") == "cb" and q.get("lang") == "eng" and q.get("token"), url
        if self.refuse_first and q.get("token") != "TOK/ABC-2":  # parse_qs decodes %2f
            # a stale token: the widget answers a non-000 code until re-scraped
            self.token_page = PAGE.replace("TOK%2fABC", "TOK%2fABC-2")
            return _jsonp({"responsecode": "001", "responsemsg": "invalid token"})
        ats = q.get("ats", "")
        if ep == "getderivativesinfo":
            return _jsonp({"responsecode": "000", "info": {"cd": ats, "opt": ats != "NOPE", "idx": ats in ("HSI", "HHI", "HTI")}})
        if ep == "getoptioncontractlist":
            return _jsonp({"responsecode": "000", "conlist": [{"id": "082026", "mon": "Aug-26"}, {"id": "122026", "mon": "Dec-26"}]})
        if ep == "getderivativesoption":
            con, fr, to = q["con"], q.get("fr"), q.get("to")
            base = [{"strike": "25,000", "c": {"bd": "1,020", "as": "1,040", "ls": "1,030", "vo": "12", "oi": "1,254", "iv": "20.1"},
                     "p": {"bd": "15", "as": "17", "ls": "16", "vo": "733", "oi": "1,258", "iv": "17.4"}}]
            if fr == "null":  # near-the-money window + the month's own bounds
                return _jsonp({"responsecode": "000", "lastupd": "21/08/2026 16:29", "min": "15,000", "max": "32,000" if con == "082026" else "40,000", "optionlist": base})
            assert (fr, to) == (("15000", "32000") if con == "082026" else ("15000", "40000")), url  # own window
            rows = base + [{"strike": "32,000", "c": {"bd": "", "as": "", "ls": "", "vo": "", "oi": "3", "iv": ""}, "p": {"bd": "6,900", "as": "", "ls": "", "vo": "", "oi": "", "iv": ""}}]
            return _jsonp({"responsecode": "000", "lastupd": "21/08/2026 16:29", "min": "15,000", "max": "32,000", "optionlist": rows})
        if ep == "getmarketmarquee":
            return _jsonp({"responsecode": "000", "indices": [{"ric": ".HSI", "ls": "26,009.46", "date": "21 Aug 2026", "tm": "16:08"}, {"ric": ".HSCE", "ls": "8,634.34"}]})
        if ep == "getderivativesfutures":
            return _jsonp({"responsecode": "000", "lastupd": "21/08/2026 15:59", "futureslist": [{"con": "Aug-26", "ls": "457.10", "bd": "457.20", "as": "458.00"}]})
        raise ValueError(f"not found: {url}")


def _provider(**kw):
    fetch = FakeFetch(**kw)
    ad = HkexAdapter(); ad.workers = 2
    return ExchangeChainProvider(["HSI", "TCH"], ad, fetch_json=fetch), fetch


# ------------------------------------------------------------------ pure
def test_class_codes_and_token_and_jsonp():
    assert class_code("^HSI") == "HSI" and class_code("hscei") == "HHI" and class_code("HSTECH") == "HTI"
    assert class_code("700") == "TCH" and class_code("0700.HK") == "TCH" and class_code("TCH") == "TCH" and class_code("9988") == "ALB"
    assert parse_token(PAGE) == "TOK%2fABC"  # the real return, not the commented sample
    assert parse_token("nothing here") is None
    assert unwrap_jsonp('cb({"data": {"a": 1}});')["data"]["a"] == 1
    with pytest.raises(ValueError):
        unwrap_jsonp("<html>403</html>")


def test_contract_expiry_is_the_second_last_business_day():
    assert contract_expiry("082026") == date(2026, 8, 28)  # Aug-2026: 31 Mon -> last biz 31, before it Fri 28
    assert contract_expiry("122026") == date(2026, 12, 30)  # Dec-2026: 31 Thu -> 30 Wed
    assert contract_expiry("052027") == date(2027, 5, 28)  # May-2027: 31 Mon -> Fri 28
    assert contract_expiry("xx") is None


def test_lastupd_hkt_to_utc_and_fallback():
    assert parse_lastupd("21/08/2026 16:29") == datetime(2026, 8, 21, 8, 29)
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    assert parse_lastupd("-", now) == datetime(2026, 8, 21, 11, 45)


def test_parse_optionlist_splits_sides_and_blanks():
    stamp = datetime(2026, 8, 21, 8, 29)
    rows = [{"strike": "25,000", "c": {"bd": "1,020", "as": "1,040", "ls": "1,030", "vo": "12", "oi": "1,254"}, "p": {"bd": "", "as": "", "ls": "", "vo": "", "oi": "9"}},
            {"strike": "", "c": {}, "p": {}}]
    q = parse_optionlist("hsi", date(2026, 8, 28), rows, stamp)
    assert len(q) == 1 and q[0].call_put == "C" and (q[0].bid, q[0].ask, q[0].last, q[0].volume, q[0].open_interest) == (1020.0, 1040.0, 1030.0, 12, 1254)
    assert q[0].ticker == "HSI" and q[0].expiry == date(2026, 8, 28) and q[0].timestamp == stamp


# -------------------------------------------------------------- provider
def test_index_chain_two_calls_per_month_own_window_and_spot():
    prov, fetch = _provider()
    exp = prov.available_expiries("HSI")
    assert exp == [date(2026, 8, 28), date(2026, 12, 30)]
    snap = prov.fetch_chain("HSI", [date(2026, 8, 28)])
    assert snap.exercise_style == "european" and snap.spot == 26009.46
    assert snap.timestamp == datetime(2026, 8, 21, 8, 29)  # lastupd HKT -> UTC
    assert {(q.strike, q.call_put) for q in snap.quotes} == {(25000.0, "C"), (25000.0, "P"), (32000.0, "P")}
    opt_calls = [u for u in fetch.calls if "getderivativesoption" in u]
    assert len(opt_calls) == 4  # 2 months x (near window + own full window)
    assert fetch.tokens_served == 1  # token scraped once, cached
    assert sum("getoptioncontractlist" in u for u in fetch.calls) == 1


def test_stock_class_is_american_with_future_spot_proxy():
    prov, fetch = _provider()
    snap = prov.fetch_chain("TCH", [date(2026, 12, 30)])
    assert snap.exercise_style == "american" and snap.spot == 457.1
    assert prov.spot("0700.HK") == 457.1


def test_stale_token_is_rescraped_once():
    prov, fetch = _provider(refuse_first=True)
    assert prov.spot("HSI") == 26009.46
    assert fetch.tokens_served == 2  # first token refused -> re-scraped -> served


def test_status_and_unknown_class():
    prov, fetch = _provider()
    assert prov.feed_status() == ("amber", "HKEX ~15-min delayed")
    with pytest.raises(ValueError, match="lists no options"):
        prov.fetch_chain("NOPE")


@pytest.mark.skipif(not os.environ.get("VOLFIT_LIVE"), reason="live HKEX widget")
def test_live_hkex_hsi():
    prov = ExchangeChainProvider(["HSI"], HkexAdapter())
    exp = prov.available_expiries("HSI")
    assert exp and prov.fetch_chain("HSI", exp[:1]).quotes

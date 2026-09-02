"""Market-data fetching (user report 2026-09-02): the progress gauge, the
non-blocking source probes / switch, the honest as-of picker, per-ticker
"not listed" verdicts, portable index tickers, and the marks-vs-quotes label
of a historical chain. All offline.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

import importlib.util
import pathlib

from volfit.api import asof as asof_svc

# The Cboe test rig (fixture payloads + the fake CDN fetcher), loaded by path:
# the tests directory is not a package.
_spec = importlib.util.spec_from_file_location("cboe_rig", pathlib.Path(__file__).with_name("test_cboe.py"))
cboe_rig = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(cboe_rig)
OPTIONS_URL, QUOTE_URL, FakeFetch, _payload, _occ = (
    cboe_rig.OPTIONS_URL, cboe_rig.QUOTE_URL, cboe_rig.FakeFetch, cboe_rig._payload, cboe_rig._occ
)
from volfit.api import datasource
from volfit.api.activity import ActivityReporter
from volfit.api.app import create_app
from volfit.api.state import AppState, AsOfSelection
from volfit.data import progress
from volfit.data.cboe import CboeAdapter
from volfit.data.exchange import DOWNLOAD_BUDGET_SECONDS, ExchangeChainProvider, RawChain
from volfit.data.expiries import third_friday
from volfit.data.expiry_time import session_close_utc
from volfit.data.massive import MassiveProvider
from volfit.data.provider import SyntheticProvider
from volfit.data.types import ChainSnapshot, OptionQuote
from volfit.data.yahoo import YahooProvider

REF = date(2026, 6, 10)


# ------------------------------------------------------------ progress gauge
def test_activity_frames_carry_elapsed_and_a_measured_progress_label():
    r = ActivityReporter()
    with r.activity("fetch", "Fetching SPY quotes from Cboe") as act:
        time.sleep(0.02)
        snap = r.snapshot()
        assert snap.active and snap.elapsedMs >= 10 and snap.total == 0 and snap.label == ""
        # The data layer reports bytes through the bound hook (no api import).
        progress.report(3_200_000, 13_000_000, progress.bytes_label(3_200_000, 13_000_000))
        snap = r.snapshot()
        assert (snap.done, snap.total, snap.label) == (3_200_000, 13_000_000, "3.2 / 13.0 MB")
        act.update(detail="chain 1 of 3")
        assert r.snapshot().detail == "chain 1 of 3"
    progress.report(1, 2, "ignored")  # unbound: a no-op, never an error
    assert r.snapshot().active is False


def test_status_payload_carries_the_gauge_fields():
    state = AppState(REF)
    from volfit.api import workflow

    with state.activity.activity("fetch", "Fetching ALPHA quotes from Synthetic", detail="chain 1 of 1"):
        progress.report(5, 10, "0.0 / 0.0 MB")
        act = workflow.status(state).activity
    assert act.active and act.label == "0.0 / 0.0 MB" and act.done == 5 and act.total == 10
    assert act.elapsedMs >= 0 and act.detail == "chain 1 of 1"


def test_exchange_download_streams_bytes_into_the_progress_hook():
    """A venue chain download reports bytes vs Content-Length as it streams
    (the status bar's determinate gauge) and is parsed from the streamed body."""
    body = b'{"data": {"symbol": "SPY", "current_price": 100.0, "options": []}, "timestamp": "2026-08-21 11:45:27"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-length": str(len(body))})

    prov = ExchangeChainProvider(["SPY"], CboeAdapter())
    prov._client = httpx.Client(transport=httpx.MockTransport(handler))
    seen: list[tuple[int, int, str]] = []
    with progress.bind(lambda d, t, l: seen.append((d, t, l))):
        doc = prov._default_fetch_json(OPTIONS_URL.format(sym="SPY"))
    assert doc["data"]["symbol"] == "SPY"
    assert seen and seen[-1][0] == len(body) and seen[-1][1] == len(body)
    assert seen[-1][2] == progress.bytes_label(len(body), len(body))


def test_exchange_download_has_a_wall_clock_budget(monkeypatch):
    """httpx's timeout is per socket read; a trickling transfer is capped by
    DOWNLOAD_BUDGET_SECONDS so a slow CDN cannot hold a fetch for minutes."""
    import volfit.data.exchange as ex

    monkeypatch.setattr(ex, "DOWNLOAD_BUDGET_SECONDS", -1.0)  # the deadline is already past

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 200_000)

    prov = ExchangeChainProvider(["SPY"], CboeAdapter())
    prov._client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(TimeoutError, match="exceeded"):
        prov._default_fetch_json(OPTIONS_URL.format(sym="SPY"))
    assert DOWNLOAD_BUDGET_SECONDS > 0  # the real budget


# ------------------------------------------------------ probes never block
class _Hung:
    """A provider whose status probe hangs (a wedged venue)."""

    def __init__(self, hang: float) -> None:
        self.hang = hang
        self.calls = 0

    def feed_status(self):
        self.calls += 1
        time.sleep(self.hang)
        return ("amber", "late")


def test_probe_statuses_returns_at_the_cap_and_never_joins_a_hung_probe(monkeypatch):
    monkeypatch.setattr(datasource, "_PROBE_TIMEOUT", 0.2)
    hung = _Hung(1.5)
    quick = SyntheticProvider(reference_date=REF)
    cache: dict = {}
    t0 = time.monotonic()
    out = datasource.probe_statuses({"hung": hung, "synthetic": quick}, cache)
    assert time.monotonic() - t0 < 1.0  # the cap, not the hang
    assert out["hung"][0] == "red" and "timed out" in out["hung"][1]
    assert out["synthetic"][0] == "green"
    # The still-running probe is not re-submitted on the next poll.
    cache.clear()
    datasource.probe_statuses({"hung": hung, "synthetic": quick}, cache)
    assert hung.calls == 1
    # Cache-only mode never probes: an unprobed source reads "pending".
    fresh: dict = {}
    assert datasource.probe_statuses({"hung": hung}, fresh, probe=False) == {"hung": datasource.PENDING_STATUS}


def test_switch_source_answers_from_the_cache_while_a_probe_hangs(monkeypatch):
    """The user must always be able to leave a hung feed: the switch never
    waits on a probe (it used to join the pool and hang with the venue)."""
    monkeypatch.setattr(datasource, "_PROBE_TIMEOUT", 0.2)

    class HungProvider(SyntheticProvider):
        def feed_status(self):
            time.sleep(2.0)
            return ("amber", "late")

    hung = HungProvider(reference_date=REF, tickers=("ALPHA",))
    good = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    with TestClient(create_app(reference_date=REF, providers={"hung": hung, "synthetic": good}, active_source="hung")) as c:
        t0 = time.monotonic()
        r = c.post("/datasource/synthetic")
        assert r.status_code == 200 and r.json()["active"] == "synthetic"
        assert time.monotonic() - t0 < 1.0
        assert {s["id"]: s["status"] for s in r.json()["sources"]}["hung"] in ("amber", "red")


# ------------------------------------------------------ per-ticker verdicts
def _cboe_provider() -> tuple[ExchangeChainProvider, FakeFetch]:
    files = {
        OPTIONS_URL.format(sym="SPY"): _payload(),
        QUOTE_URL.format(sym="SPY"): {"data": {"symbol": "SPY", "current_price": 101.5}},
    }
    fetch = FakeFetch(files)
    return ExchangeChainProvider(["SPY", "SX5E INDEX"], CboeAdapter(), fetch_json=fetch), fetch


def test_universe_names_the_ticker_a_venue_does_not_list():
    """A Eurex name in the universe on Cboe: the ladder stays empty, /universe
    says WHY, and the source keeps serving the other tickers (amber, naming
    the unlisted symbol) instead of going red."""
    prov, _fetch = _cboe_provider()
    with TestClient(create_app(reference_date=REF, providers={"cboe": prov}, active_source="cboe")) as c:
        u = c.get("/universe").json()
        assert u["expiries"]["SPY"] and u["expiries"]["SX5E INDEX"] == []
        assert "lists no options" in u["errors"]["SX5E INDEX"] and "SPY" not in u["errors"]
        src = {s["id"]: s for s in c.get("/datasources").json()["sources"]}["cboe"]
        assert src["status"] == "amber" and "not listed: SX5E INDEX" in src["detail"]


def test_exchange_lists_todays_expiry_only_while_its_session_is_open(monkeypatch):
    today = date(2026, 9, 2)  # a Wednesday session
    raw_quotes = [
        OptionQuote(ticker="SPY", expiry=today, strike=100.0, call_put="C", bid=1.0, ask=1.2),
        OptionQuote(ticker="SPY", expiry=today + timedelta(days=2), strike=100.0, call_put="C", bid=1.0, ask=1.2),
    ]
    raw = RawChain(ticker="SPY", spot=100.0, timestamp=datetime(2026, 9, 2, 14, 0), quotes=raw_quotes)
    prov = ExchangeChainProvider(["SPY"], CboeAdapter(), today=lambda: today)
    prov._cache["SPY"] = (time.monotonic(), raw)
    close = session_close_utc(today)
    monkeypatch.setattr(prov, "_now", lambda: close - timedelta(hours=1))
    assert prov.available_expiries("SPY") == [today, today + timedelta(days=2)]  # the 0DTE is live
    monkeypatch.setattr(prov, "_now", lambda: close + timedelta(minutes=1))
    assert prov.available_expiries("SPY") == [today + timedelta(days=2)]  # dead after the close


def test_cboe_index_file_settles_each_expiry_per_its_listing_root():
    """One _SPX file mixes SPX (AM-settled 3rd Fridays) and SPXW (PM weeklies):
    settlement is per DATE by the root that lists it — the whole file used to
    be stamped AM off the ticker."""
    monthly = third_friday(2026, 9)
    weekly = date(2026, 9, 9)
    payload = _payload("_SPX", "index", 5000.0, "SPX")
    payload["data"]["options"] = [
        {"option": _occ("SPX", monthly, "C", 5000), "bid": 10.0, "ask": 10.5},
        {"option": _occ("SPXW", monthly, "C", 5000), "bid": 10.0, "ask": 10.5},  # the sibling on the same date
        {"option": _occ("SPXW", weekly, "C", 5000), "bid": 5.0, "ask": 5.5},
    ]
    fetch = FakeFetch({OPTIONS_URL.format(sym="_SPX"): payload, QUOTE_URL.format(sym="_SPX"): {"data": {"current_price": 5000.0}}})
    prov = ExchangeChainProvider(["SPX"], CboeAdapter(), fetch_json=fetch, today=lambda: date(2026, 9, 1))
    snap = prov.fetch_chain("SPX", [monthly, weekly])
    assert snap.settlement[monthly].style == "am"  # the parent root lists it
    assert snap.settlement[weekly].style == "pm"  # SPXW only


# ------------------------------------------------------ portable tickers
def test_index_roots_carry_across_sources():
    assert YahooProvider._symbol("SPX") == "^SPX" and YahooProvider._symbol("^VIX") == "^VIX"
    assert YahooProvider._symbol("SPY") == "SPY"
    assert MassiveProvider._underlying("SPX") == "I:SPX" and MassiveProvider._underlying("NDX") == "I:NDX"
    assert MassiveProvider._underlying("spy") == "SPY" and MassiveProvider._underlying("I:SPX") == "I:SPX"


# ------------------------------------------------------ honest as-of picker
class _History(SyntheticProvider):
    """A provider with a flat-file-like EOD history that serves MARKS, can
    reconstruct past instants, and lists a holiday by mistake."""

    def historical_modes(self):
        return {"live", "prev_close", "eod"}

    def available_history(self, ticker):
        return [date(2026, 6, 8), date(2026, 6, 9)]  # Mon, Tue before REF (Wed)

    def intraday_capable(self):
        return True

    def historical_quote_kind(self):
        return "marks"


def test_asof_payload_offers_only_what_the_source_serves(tmp_path):
    prov = _History(reference_date=REF, tickers=("ALPHA",))
    app = create_app(reference_date=REF, providers={"h": prov}, active_source="h", store_path=str(tmp_path / "a.sqlite"))
    with TestClient(app) as c:
        days = {d["date"]: d for d in c.get("/asof").json()["days"]}
        today = days[REF.isoformat()]
        # Today is listed but is Live: no close yet, no intraday pick, a reason.
        assert today["isToday"] and not today["hasClose"] and not today["intraday"]
        assert "Live" in today["reason"]
        past = days["2026-06-09"]
        assert past["hasClose"] and past["intraday"] and past["spread"] == "marks" and past["reason"] is None
        # Today's "latest" is refused (it would silently be the live chain).
        r = c.post("/asof", json={"mode": "moment", "on": REF.isoformat(), "moment": "latest"})
        assert r.status_code == 422 and "Live" in r.json()["detail"]
        # A day the source does not list cannot be picked as a close.
        r = c.post("/asof", json={"mode": "eod", "on": "2026-06-05"})
        assert r.status_code == 404
        # A listed day can.
        r = c.post("/asof", json={"mode": "moment", "on": "2026-06-09", "moment": "close"})
        assert r.status_code == 200 and r.json()["mode"] == "eod"


def test_asof_payload_skips_holidays():
    """Independence Day (2026-07-03 observed) must not be offered as a session."""
    from volfit.data.expiry_time import is_trading_day

    assert not is_trading_day(date(2026, 7, 3))
    assert asof_svc._prev_business_day(date(2026, 7, 6)) == date(2026, 7, 2)


def test_massive_history_lists_trading_days_only_and_needs_the_flat_store():
    prov = MassiveProvider(["SPY"], api_key="k")
    assert prov.available_history("SPY") == []  # no flat store
    assert prov.intraday_capable() is False and prov.historical_quote_kind() == "marks"


# ------------------------------------------------------ marks on the smile
def test_smile_says_marks_when_the_chain_is_bid_equals_ask_closes():
    class Marks(SyntheticProvider):
        def fetch_chain(self, ticker, expiries=None, as_of=None):
            snap = super().fetch_chain(ticker, expiries, as_of)
            quotes = [
                OptionQuote(ticker=q.ticker, expiry=q.expiry, strike=q.strike, call_put=q.call_put,
                            bid=q.mid, ask=q.mid, last=q.mid)
                for q in snap.quotes
            ]
            return ChainSnapshot(ticker=snap.ticker, spot=snap.spot, timestamp=snap.timestamp, quotes=quotes,
                                 exercise_style=snap.exercise_style, quote_kind="marks")

    prov = Marks(reference_date=REF, tickers=("ALPHA",))
    with TestClient(create_app(reference_date=REF, providers={"m": prov}, active_source="m")) as c:
        iso = c.get("/universe").json()["expiries"]["ALPHA"][1]["expiry"]
        smile = c.get(f"/smiles/ALPHA/{iso}").json()
        assert smile["quoteKind"] == "marks"
        assert all(q["bid"] == q["ask"] for q in smile["quotes"])
    plain = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    with TestClient(create_app(reference_date=REF, providers={"s": plain}, active_source="s")) as c:
        iso = c.get("/universe").json()["expiries"]["ALPHA"][1]["expiry"]
        assert c.get(f"/smiles/ALPHA/{iso}").json()["quoteKind"] == "quotes"

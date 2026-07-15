"""Offline tests for the REST-based intraday 0DTE capture.

Everything runs against an ``httpx.MockTransport`` — no network. The mock
board is 4 expiries x 3 strikes x 2 sides around close=100 with parity-
consistent mids (C - P = S - K, discount 1), so the parity spot resolves to
exactly 100 and the fixture schema can be compared against the flat-file
capture's contract.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, time

import httpx
import pytest

import backtest.capture_intraday_rest as cir
from backtest.capture_intraday_rest import capture_day_rest, run
from backtest.capture_intraday import session_instants
from backtest.quotes_store import _to_ns
from volfit.data.store import VolStore

DAY = date(2026, 7, 10)  # a Friday NYSE session
CLOSE = 100.0
#: dailies (0 + 3 DTE) then two third-Friday monthlies — all inside the spans.
EXPIRIES = (date(2026, 7, 10), date(2026, 7, 13), date(2026, 8, 21), date(2026, 9, 18))
STRIKES = (90.0, 100.0, 110.0)
TIMES = (time(10, 0), time(12, 0))


def _occ(expiry: date, strike: float, cp: str) -> str:
    return f"O:SPY{expiry:%y%m%d}{cp}{int(strike * 1000):08d}"


class _Api:
    """Mock Massive REST API: reference (paginated), daily agg, quotes."""

    def __init__(self):
        self.quote_calls: list[tuple[str, int]] = []  # (occ, lte_ns)
        self.lock = threading.Lock()
        self.late_occ: str | None = None  # quoted only after late_after_ns
        self.late_after_ns = 0
        self.zero_bid_occ: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/v2/aggs/ticker/SPY/range/1/day/"):
            return httpx.Response(200, json={"results": [{"c": CLOSE}]})
        if path == "/v3/reference/options/contracts":
            return self._contracts(request)
        if path.startswith("/v3/quotes/"):
            return self._quote(request, path.removeprefix("/v3/quotes/"))
        raise AssertionError(f"unexpected path {path}")

    def _contracts(self, request: httpx.Request) -> httpx.Response:
        p = request.url.params
        # Only the expired=true daily span carries contracts (dedup makes the
        # other calls redundant); it is served in two pages to lock pagination.
        lo = date.fromisoformat(p["expiration_date.gte"])
        hi = date.fromisoformat(p["expiration_date.lte"])
        rows = [
            {"ticker": _occ(e, k, cp), "expiration_date": e.isoformat(),
             "strike_price": k, "contract_type": "call" if cp == "C" else "put"}
            for e in EXPIRIES if lo <= e <= hi
            for k in STRIKES
            if float(p["strike_price.gte"]) <= k <= float(p["strike_price.lte"])
            for cp in ("C", "P")
        ]
        if p["expired"] == "false":
            rows = []  # everything on this mock board is already expired
        if "cursor" in p:
            return httpx.Response(200, json={"results": rows[6:]})
        if len(rows) > 6:
            return httpx.Response(200, json={
                "results": rows[:6],
                "next_url": str(request.url.copy_add_param("cursor", "page2")),
            })
        return httpx.Response(200, json={"results": rows})

    def _quote(self, request: httpx.Request, occ: str) -> httpx.Response:
        lte = int(request.url.params["timestamp.lte"])
        with self.lock:
            self.quote_calls.append((occ, lte))
        if occ == self.late_occ and lte < self.late_after_ns:
            return httpx.Response(200, json={"results": []})
        strike = float(occ[-8:]) / 1000.0
        cp = occ[-9]
        # Parity-consistent mids: C = (CLOSE - K) + 15, P = 15  =>  spot = 100.
        mid = (CLOSE - strike) + 15.0 if cp == "C" else 15.0
        bid, ask = mid - 1.0, mid + 1.0
        if occ == self.zero_bid_occ:
            bid = 0.0
        return httpx.Response(200, json={"results": [{
            "bid_price": bid, "ask_price": ask, "bid_size": 1, "ask_size": 2,
            "sip_timestamp": lte - 1,
        }]})


@pytest.fixture()
def api(tmp_path, monkeypatch):
    api = _Api()
    monkeypatch.setattr(cir, "FIXTURE_DIR", str(tmp_path / "fx"))
    return api


def _client(api: _Api) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(api.handler),
                        base_url="http://test")


def test_run_writes_flatfile_compatible_fixture_and_db(api, tmp_path):
    db = tmp_path / "intraday.sqlite"
    written = run(DAY, DAY, tickers=("SPY",), times=TIMES,
                  db_path=str(db), client=_client(api))
    assert len(written) == 1
    doc = json.loads(open(written[0], encoding="utf-8").read())
    # The flat-file capture's contract, plus the provenance tag.
    assert set(doc) == {"asset", "day", "exercise_style", "source", "expiries", "snapshots"}
    assert doc["source"] == "rest"
    assert doc["expiries"] == [e.isoformat() for e in EXPIRIES]
    assert len(doc["snapshots"]) == 2
    snap = doc["snapshots"][0]
    assert snap["spot"] == pytest.approx(CLOSE, abs=1e-6)
    assert len(snap["quotes"]) == len(EXPIRIES) * len(STRIKES) * 2
    assert set(snap["quotes"][0]) == {"expiry", "strike", "cp", "bid", "ask", "size"}
    # VolStore replay path: snapshot found as-of, with the settlement map.
    with VolStore(str(db)) as vs:
        stored = vs.snapshot_at("SPY", datetime(2026, 7, 10, 23, 59))
    assert stored is not None and stored.settlement
    assert len(stored.quotes) == len(snap["quotes"])


def test_asof_semantics_late_contract(api):
    instants = session_instants(DAY, TIMES)
    api.late_occ = _occ(EXPIRIES[0], 100.0, "C")
    api.late_after_ns = _to_ns(instants[1])
    doc = capture_day_rest(_client(api), "SPY", DAY, times=TIMES)
    n0 = len(doc["snapshots"][0]["quotes"])
    n1 = len(doc["snapshots"][1]["quotes"])
    assert n1 == n0 + 1  # unquoted at 10:00, present at 12:00
    # every quote request was bounded by one of the two instants
    assert {lte for _, lte in api.quote_calls} == {_to_ns(t) for t in instants}


def test_zero_bid_becomes_none_ask_kept(api):
    api.zero_bid_occ = _occ(EXPIRIES[1], 90.0, "P")
    doc = capture_day_rest(_client(api), "SPY", DAY, times=TIMES[:1])
    rows = [q for q in doc["snapshots"][0]["quotes"]
            if q["expiry"] == EXPIRIES[1].isoformat() and q["strike"] == 90.0
            and q["cp"] == "P"]
    assert rows == [{"expiry": "2026-07-13", "strike": 90.0, "cp": "P",
                     "bid": None, "ask": 16.0, "size": 2}]


def test_checkpoint_resume_skips_done_instants(api, tmp_path):
    instants = session_instants(DAY, TIMES)
    fx = tmp_path / "fx"
    fx.mkdir(parents=True, exist_ok=True)
    sentinel = {"ts": instants[0].isoformat(), "spot": 42.0,
                "quotes": [{"expiry": "2026-07-10", "strike": 100.0, "cp": "C",
                            "bid": 1.0, "ask": 2.0, "size": 1}]}
    part = fx / "SPY_2026-07-10.part.json"
    part.write_text(json.dumps({instants[0].isoformat(): sentinel}), encoding="utf-8")
    doc = capture_day_rest(_client(api), "SPY", DAY, times=TIMES)
    assert doc["snapshots"][0] == sentinel  # instant 1 taken from the checkpoint
    assert {lte for _, lte in api.quote_calls} == {_to_ns(instants[1])}
    assert not part.exists()  # consumed on completion


def test_retry_on_429_then_success(api):
    hits = {"n": 0}
    inner = api.handler

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v2/aggs") and hits["n"] == 0:
            hits["n"] += 1
            return httpx.Response(429, headers={"Retry-After": "0"})
        return inner(request)

    client = httpx.Client(transport=httpx.MockTransport(flaky), base_url="http://test")
    doc = capture_day_rest(client, "SPY", DAY, times=TIMES[:1])
    assert doc is not None and hits["n"] == 1

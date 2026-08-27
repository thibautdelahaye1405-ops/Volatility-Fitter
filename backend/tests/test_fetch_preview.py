"""GET /fetch/preview — the Fetch-menu coverage preview (workbench follow-on,
2026-08-27; ROADMAP "As-of → Fetch ▾" proposal).

Locks (gated workflow, synthetic providers of tests/test_universe_asof.py):
  * the preview NEVER fetches: reading it leaves every chain cache empty;
  * live: every ticker's source honors the moment — all nodes exact, no
    fallback, "Live · n/n nodes";
  * previous close on a provider that IGNORES the as-of (serves today's
    chain): before any fetch the advertised capability reads as honoring;
    once the served chain proves inexact, providerHonors=False, fallback
    "live" and the summary counts the fallback nodes;
  * previous close on a provider that honors it: honors True before and
    after the fetch, "Previous close · provider serves it";
  * ``nodes`` counts the selected ladder rungs.
"""

from __future__ import annotations

from datetime import datetime, time

from fastapi.testclient import TestClient

from volfit.api import create_app

from tests.test_universe_asof import PREV, REF, _CloseProvider, _IgnoringProvider

TICKER = "ALPHA"


def _client(provider):
    return TestClient(
        create_app(
            reference_date=REF, gated=True, providers={"synthetic": provider},
            active_source="synthetic",
        )
    )


def _preview(c: TestClient) -> dict:
    res = c.get("/fetch/preview")
    assert res.status_code == 200
    return res.json()


def _ladder_len(c: TestClient, ticker: str) -> int:
    return len(c.get("/universe").json()["expiries"][ticker])


def test_live_all_exact_and_never_fetches():
    with TestClient(create_app(reference_date=REF, gated=True)) as c:
        state = c.app.state.volfit
        p = _preview(c)
        for t in state.active_tickers():
            assert state.loaded_snapshot(t) is None  # the preview fetched nothing
        assert p["mode"] == "live" and p["requestedDay"] is None
        assert p["dataSource"] == c.get("/datasources").json()["active"]
        assert p["tickers"] and len(p["tickers"]) == len(state.active_tickers())
        for row in p["tickers"]:
            assert row["nodes"] == _ladder_len(c, row["ticker"])
            assert row["requestedMode"] == "live" and row["requestedDay"] is None
            assert row["providerHonors"] is True and row["fallback"] is None
            assert row["currentlyExact"] is None and row["effectiveAsOf"] is None
        n = p["totals"]["nodes"]
        assert n > 0 and p["totals"] == {"nodes": n, "exact": n, "fallback": 0}
        assert p["summary"] == f"Live · {n}/{n} nodes"

        # After a live fetch the loaded chains are exact by construction.
        assert c.post("/fetch/options", json={}).status_code == 200
        p = _preview(c)
        for row in p["tickers"]:
            assert row["currentlyExact"] is True and row["providerHonors"] is True
            assert row["effectiveAsOf"] == datetime.combine(REF, time(16, 0)).isoformat()
        assert p["summary"] == f"Live · {n}/{n} nodes"


def test_prev_close_ignored_by_the_feed_falls_back_to_live():
    with _client(_IgnoringProvider(reference_date=REF, tickers=(TICKER,))) as c:
        state = c.app.state.volfit
        assert c.post("/asof", json={"mode": "prev_close"}).status_code == 200
        n = _ladder_len(c, TICKER)
        # Before any fetch: only the advertisement speaks (it claims prev_close).
        p = _preview(c)
        assert state.loaded_snapshot(TICKER) is None  # the preview fetched nothing
        assert p["mode"] == "prev_close" and p["requestedDay"] == PREV.isoformat()
        row = p["tickers"][0]
        assert row["ticker"] == TICKER and row["nodes"] == n
        assert row["requestedMode"] == "prev_close" and row["requestedDay"] == PREV.isoformat()
        assert row["currentlyExact"] is None and row["providerHonors"] is True
        assert p["summary"] == f"Previous close · provider serves it · {n} nodes"

        # The served chain (today's) is the evidence: not honored, falls back to live.
        assert c.post("/fetch/options", json={}).status_code == 200
        p = _preview(c)
        row = p["tickers"][0]
        assert row["currentlyExact"] is False
        assert row["providerHonors"] is False and row["fallback"] == "live"
        assert row["effectiveAsOf"] == datetime.combine(REF, time(16, 0)).isoformat()
        assert p["totals"] == {"nodes": n, "exact": 0, "fallback": n}
        assert p["summary"] == f"Previous close · 0/{n} nodes exact · {n} fall back to live"


def test_prev_close_honored_by_the_feed():
    with _client(_CloseProvider(reference_date=REF, tickers=(TICKER,))) as c:
        state = c.app.state.volfit
        assert c.post("/asof", json={"mode": "prev_close"}).status_code == 200
        n = _ladder_len(c, TICKER)
        p = _preview(c)
        assert state.loaded_snapshot(TICKER) is None  # the preview fetched nothing
        row = p["tickers"][0]
        assert row["providerHonors"] is True and row["fallback"] is None
        assert p["totals"] == {"nodes": n, "exact": n, "fallback": 0}
        assert p["summary"] == f"Previous close · provider serves it · {n} nodes"

        assert c.post("/fetch/options", json={}).status_code == 200
        p = _preview(c)
        row = p["tickers"][0]
        assert row["currentlyExact"] is True and row["providerHonors"] is True
        assert row["effectiveAsOf"] == datetime.combine(PREV, time(16, 0)).isoformat()
        assert p["summary"] == f"Previous close · provider serves it · {n} nodes"


def test_back_to_live_clears_the_fallback():
    with _client(_IgnoringProvider(reference_date=REF, tickers=(TICKER,))) as c:
        assert c.post("/asof", json={"mode": "prev_close"}).status_code == 200
        assert c.get("/universe").status_code == 200  # resolve the ladder first
        assert c.post("/fetch/options", json={}).status_code == 200
        assert _preview(c)["totals"]["fallback"] > 0
        assert c.post("/asof", json={"mode": "live"}).status_code == 200  # clears the chains
        p = _preview(c)
        assert p["mode"] == "live" and p["totals"]["fallback"] == 0
        assert p["tickers"][0]["currentlyExact"] is None

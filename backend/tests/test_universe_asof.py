"""Per-node EFFECTIVE as-of on the wire (workbench follow-on, 2026-08-27).

Locks (gated workflow, synthetic provider, offline):
  * before any fetch every rung carries effectiveAsOf / dataSource / asOfExact
    = None (the payload reads the chain CACHE only — nothing is fetched);
  * after Fetch a rung's effectiveAsOf is the loaded chain's stamp, dataSource
    the active source id and asOfExact True (live IS the moment);
  * under a Previous-close selection the triple reflects the SERVED chain: a
    provider honoring the close (stamped on the prior session) is exact; a
    provider that ignores ``as_of`` (serving today's chain) is flagged inexact;
  * every other key of the UniverseResponse is byte-identical to before;
  * GET /graph/nodes mirrors the same triple on GraphNodeInfo.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 10)  # a Wednesday
PREV = date(2026, 6, 9)  # its previous business day (the prev_close session)
NEW = ("effectiveAsOf", "dataSource", "asOfExact")
LEGACY = {"expiry", "t", "expiryType"}


class _CloseProvider(SyntheticProvider):
    """Synthetic chains advertising prev_close. ``honors`` re-stamps a close
    request on the prior session (what a real EOD feed serves); otherwise the
    as-of is ignored and today's chain comes back — the fallback the ROADMAP
    proposal wants flagged."""

    honors = True

    def historical_modes(self):
        return {"live", "prev_close"}

    def fetch_chain(self, ticker, expiries=None, as_of=None):
        snap = super().fetch_chain(ticker, expiries)
        if self.honors and as_of is not None and as_of.mode == "prev_close":
            return dataclasses.replace(snap, timestamp=datetime.combine(PREV, time(16, 0)))
        return snap


class _IgnoringProvider(_CloseProvider):
    honors = False


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF, gated=True)) as c:
        yield c


def _app(provider):
    return create_app(
        reference_date=REF, gated=True, providers={"synthetic": provider}, active_source="synthetic"
    )


def _rows(client) -> list[dict]:
    u = client.get("/universe").json()
    return [row for ladder in u["expiries"].values() for row in ladder]


def _without_new(u: dict) -> dict:
    """The payload with the three new keys stripped (the byte-identity view)."""
    return {
        **u,
        "expiries": {
            t: [{k: v for k, v in r.items() if k not in NEW} for r in ladder]
            for t, ladder in u["expiries"].items()
        },
    }


def test_before_fetch_the_triple_is_none(client):
    rows = _rows(client)
    assert rows
    for r in rows:
        assert set(r) == LEGACY | set(NEW)  # the wire contract: legacy keys + the three
        assert (r["effectiveAsOf"], r["dataSource"], r["asOfExact"]) == (None, None, None)


def test_after_fetch_stamp_source_and_exact(client):
    before = client.get("/universe").json()
    assert client.post("/fetch/options", json={}).status_code == 200
    after = client.get("/universe").json()
    state = client.app.state.volfit
    active = client.get("/datasources").json()["active"]
    for ticker, ladder in after["expiries"].items():
        stamp = state.loaded_snapshot(ticker).timestamp.isoformat()
        assert stamp == datetime.combine(REF, time(16, 0)).isoformat()  # the synthetic stamp
        for r in ladder:
            assert r["effectiveAsOf"] == stamp
            assert r["dataSource"] == active
            assert r["asOfExact"] is True  # live IS the moment
    assert _without_new(after) == _without_new(before)  # nothing else moved


def test_prev_close_honored_by_the_feed_is_exact():
    with TestClient(_app(_CloseProvider(reference_date=REF, tickers=("ALPHA",)))) as c:
        assert c.post("/asof", json={"mode": "prev_close"}).status_code == 200
        assert _rows(c)[0]["effectiveAsOf"] is None  # resolves the ladder, fetches nothing
        assert c.post("/fetch/options", json={}).status_code == 200
        row = _rows(c)[0]
        assert row["effectiveAsOf"] == datetime.combine(PREV, time(16, 0)).isoformat()
        assert row["dataSource"] == "synthetic"
        assert row["asOfExact"] is True


def test_prev_close_ignored_by_the_feed_is_flagged_inexact():
    with TestClient(_app(_IgnoringProvider(reference_date=REF, tickers=("ALPHA",)))) as c:
        # The dropdown form: the previous session's "close" moment.
        res = c.post("/asof", json={"mode": "moment", "on": PREV.isoformat(), "moment": "close"})
        assert res.status_code == 200 and res.json()["mode"] == "prev_close"
        assert _rows(c)[0]["effectiveAsOf"] is None  # resolves the ladder, fetches nothing
        assert c.post("/fetch/options", json={}).status_code == 200
        row = _rows(c)[0]
        assert row["effectiveAsOf"] == datetime.combine(REF, time(16, 0)).isoformat()  # today's chain served
        assert row["asOfExact"] is False
        # Back to live: the switch clears the chains (None), and the same chain
        # fetched live is exact again.
        assert c.post("/asof", json={"mode": "live"}).status_code == 200
        assert _rows(c)[0]["asOfExact"] is None
        assert c.post("/fetch/options", json={}).status_code == 200
        assert _rows(c)[0]["asOfExact"] is True


def test_graph_nodes_mirror_the_triple(client):
    assert client.get("/universe").status_code == 200  # resolve the ladder first
    assert client.post("/fetch/options", json={}).status_code == 200
    rows = {
        (t, r["expiry"]): r
        for t, ladder in client.get("/universe").json()["expiries"].items()
        for r in ladder
    }
    nodes = client.get("/graph/nodes").json()["nodes"]
    assert nodes
    for n in nodes:
        r = rows[(n["ticker"], n["expiry"])]
        assert (n["effectiveAsOf"], n["dataSource"], n["asOfExact"]) == (
            r["effectiveAsOf"], r["dataSource"], True,
        )

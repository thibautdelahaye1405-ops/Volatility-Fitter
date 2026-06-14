"""API tests: per-node lit/dark designation (ROADMAP Phase 10 follow-up).

Every selected node is lit by default; darkening one persists and is reflected
in both GET /universe/lit and the graph lattice (GET /graph/nodes). Lit = an
observed source for the graph solver, dark = an extrapolation target.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_all_lit_by_default(client):
    nodes = client.get("/universe/lit").json()["nodes"]
    assert len(nodes) >= 2
    assert all(n["lit"] for n in nodes)


def test_darken_and_relight_one_node(client):
    nodes = client.get("/universe/lit").json()["nodes"]
    node = nodes[0]
    t, e = node["ticker"], node["expiry"]

    # Darken it.
    resp = client.put(f"/universe/lit/{t}/{e}", json={"lit": False})
    assert resp.status_code == 200
    assert resp.json() == {"ticker": t, "expiry": e, "lit": False}
    # Reflected in the map.
    after = {(n["ticker"], n["expiry"]): n["lit"] for n in client.get("/universe/lit").json()["nodes"]}
    assert after[(t, e)] is False
    assert all(lit for (tk, ex), lit in after.items() if (tk, ex) != (t, e))

    # Relight it.
    assert client.put(f"/universe/lit/{t}/{e}", json={"lit": True}).json()["lit"] is True


def test_bulk_toggle_ticker(client):
    ticker = client.get("/universe").json()["tickers"][0]
    resp = client.put(f"/universe/lit/{ticker}", json={"lit": False})
    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    assert any(not n["lit"] for n in nodes if n["ticker"] == ticker)
    assert all(not n["lit"] for n in nodes if n["ticker"] == ticker)


def test_graph_nodes_report_lit(client):
    nodes = client.get("/graph/nodes").json()["nodes"]
    assert nodes and all(n["lit"] for n in nodes)
    t, e = nodes[0]["ticker"], nodes[0]["expiry"]
    client.put(f"/universe/lit/{t}/{e}", json={"lit": False})
    refreshed = {(n["ticker"], n["expiry"]): n["lit"] for n in client.get("/graph/nodes").json()["nodes"]}
    assert refreshed[(t, e)] is False


def test_unknown_node_is_404(client):
    ticker = client.get("/universe").json()["tickers"][0]
    assert client.put(f"/universe/lit/{ticker}/2099-01-01", json={"lit": False}).status_code == 404
    assert client.put("/universe/lit/NOPE", json={"lit": False}).status_code == 404

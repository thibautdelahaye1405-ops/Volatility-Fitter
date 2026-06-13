"""API tests: universe management — search, add/remove, named universes."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 10)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF)) as c:
        yield c


@pytest.fixture()
def store_client(tmp_path):
    db = tmp_path / "universe.sqlite"
    with TestClient(create_app(reference_date=REF, store_path=str(db))) as c:
        yield c


def test_universe_lists_active_tickers(client):
    data = client.get("/universe").json()
    assert set(data["tickers"]) == {"ALPHA", "BETA", "GAMMA"}
    assert len(data["expiries"]["ALPHA"]) == 4


def test_search_matches_and_echoes(client):
    matches = client.get("/universe/search", params={"q": "AL"}).json()["matches"]
    assert any(m["symbol"] == "ALPHA" for m in matches)
    # A plausible new symbol is echoed so it can be added (synthetic quotes any).
    echoed = client.get("/universe/search", params={"q": "DELTA"}).json()["matches"]
    assert any(m["symbol"] == "DELTA" for m in echoed)


def test_add_and_remove_ticker(client):
    added = client.post("/universe/tickers", json={"symbol": "delta"}).json()
    assert "DELTA" in added["tickers"]
    assert len(added["expiries"]["DELTA"]) == 4
    # Idempotent re-add.
    again = client.post("/universe/tickers", json={"symbol": "DELTA"}).json()
    assert again["tickers"].count("DELTA") == 1
    # Remove it.
    after = client.delete("/universe/tickers/DELTA").json()
    assert "DELTA" not in after["tickers"]


def test_cannot_remove_last_ticker(client):
    client.delete("/universe/tickers/ALPHA")
    client.delete("/universe/tickers/BETA")
    resp = client.delete("/universe/tickers/GAMMA")  # only one left
    assert resp.status_code == 422
    assert client.get("/universe").json()["tickers"] == ["GAMMA"]


def test_add_unknown_symbol_is_404():
    class Picky(SyntheticProvider):
        def fetch_chain(self, ticker):
            if ticker == "BAD":
                raise ValueError("no such symbol")
            return super().fetch_chain(ticker)

    with TestClient(create_app(reference_date=REF, provider=Picky(REF))) as c:
        assert c.post("/universe/tickers", json={"symbol": "BAD"}).status_code == 404


def test_named_universes_disabled_without_store(client):
    saved = client.get("/universes").json()
    assert saved["storeEnabled"] is False and saved["names"] == []
    assert client.post("/universes/tech").status_code == 422  # no store


def test_save_load_delete_named_universe(store_client):
    c = store_client
    c.post("/universe/tickers", json={"symbol": "DELTA"})  # ALPHA,BETA,GAMMA,DELTA
    saved = c.post("/universes/quad").json()
    assert "quad" in saved["names"] and saved["storeEnabled"] is True

    # Mutate the active universe, then load the saved one to restore it.
    c.delete("/universe/tickers/DELTA")
    c.delete("/universe/tickers/BETA")
    restored = c.post("/universe/load/quad").json()
    assert set(restored["tickers"]) == {"ALPHA", "BETA", "GAMMA", "DELTA"}

    assert c.post("/universe/load/missing").status_code == 404
    deleted = c.delete("/universes/quad").json()
    assert "quad" not in deleted["names"]

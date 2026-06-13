"""API tests: universe management — search, add/remove, expiries, named sets."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 10)


def _rich_ladder(ref: date) -> list[date]:
    """A 2-year M/W/F + 3rd-Friday ladder (so the default rule has work to do)."""
    out: set[date] = set()
    for w in range(0, 14):
        monday = ref + timedelta(days=(7 - ref.weekday()) % 7 + 7 * w)  # next Mondays
        for off in (0, 2, 4):
            out.add(monday + timedelta(days=off))
    for m in range(0, 24):
        y, mo = divmod(ref.month - 1 + m, 12)
        first = date(ref.year + y, mo + 1, 1)
        out.add(first + timedelta(days=(4 - first.weekday()) % 7 + 14))
    return sorted(e for e in out if (e - ref).days > 0)


class RichProvider(SyntheticProvider):
    """Synthetic chains but with a full live-like expiry ladder."""

    def available_expiries(self, ticker: str) -> list[date]:
        return _rich_ladder(self.reference_date)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF)) as c:
        yield c


@pytest.fixture()
def rich_client():
    with TestClient(create_app(reference_date=REF, provider=RichProvider(REF))) as c:
        yield c


@pytest.fixture()
def store_client(tmp_path):
    db = tmp_path / "universe.sqlite"
    with TestClient(create_app(reference_date=REF, store_path=str(db))) as c:
        yield c


@pytest.fixture()
def rich_store_client(tmp_path):
    db = tmp_path / "rich.sqlite"
    app = create_app(reference_date=REF, provider=RichProvider(REF), store_path=str(db))
    with TestClient(app) as c:
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
        def fetch_chain(self, ticker, expiries=None):
            if ticker == "BAD":
                raise ValueError("no such symbol")
            return super().fetch_chain(ticker, expiries)

    with TestClient(create_app(reference_date=REF, provider=Picky(REF))) as c:
        assert c.post("/universe/tickers", json={"symbol": "BAD"}).status_code == 404


def test_expiry_picker_applies_default_rule(rich_client):
    picker = rich_client.get("/universe/ALPHA/expiries").json()
    assert picker["mode"] == "auto"
    assert len(picker["expiries"]) > 20  # the full available ladder
    buckets = {e["bucket"] for e in picker["expiries"]}
    assert {"weekly", "monthly", "quarterly"} <= buckets
    selected = [e for e in picker["expiries"] if e["selected"]]
    # The default rule selects a curated subset, not everything.
    assert 0 < len(selected) < len(picker["expiries"])
    # Selected weeklies are >= 2 days; quarterlies <= ~18 months.
    sel_weeklies = [e for e in selected if e["bucket"] == "weekly"]
    assert len(sel_weeklies) == 2 and all(e["days"] >= 2 for e in sel_weeklies)
    assert all(e["days"] <= 548 for e in selected if e["bucket"] == "quarterly")
    # The /universe ladder reflects the selection (fewer than available).
    ladder = rich_client.get("/universe").json()["expiries"]["ALPHA"]
    assert len(ladder) == len(selected)


def test_set_and_reset_expiries(rich_client):
    avail = rich_client.get("/universe/ALPHA/expiries").json()["expiries"]
    pick = [e["expiry"] for e in avail[:3]]
    custom = rich_client.put("/universe/ALPHA/expiries", json={"expiries": pick}).json()
    assert custom["mode"] == "custom"
    assert {e["expiry"] for e in custom["expiries"] if e["selected"]} == set(pick)
    assert len(rich_client.get("/universe").json()["expiries"]["ALPHA"]) == 3
    # Empty selection is rejected.
    assert rich_client.put("/universe/ALPHA/expiries", json={"expiries": []}).status_code == 422
    # Reset returns to the default rule.
    reset = rich_client.post("/universe/ALPHA/expiries/reset").json()
    assert reset["mode"] == "auto"


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


def test_named_universe_persists_custom_selection(rich_store_client):
    c = rich_store_client
    avail = c.get("/universe/ALPHA/expiries").json()["expiries"]
    pick = [e["expiry"] for e in avail[:3]]
    c.put("/universe/ALPHA/expiries", json={"expiries": pick})
    c.post("/universes/mine")
    # Reset to auto, then reload the saved set -> custom picks restored.
    c.post("/universe/ALPHA/expiries/reset")
    assert c.get("/universe/ALPHA/expiries").json()["mode"] == "auto"
    c.post("/universe/load/mine")
    after = c.get("/universe/ALPHA/expiries").json()
    assert after["mode"] == "custom"
    assert {e["expiry"] for e in after["expiries"] if e["selected"]} == set(pick)

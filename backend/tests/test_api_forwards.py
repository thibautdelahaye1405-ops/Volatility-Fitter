"""API tests: forward modes (/forwards) and market settings (/settings/market).

[REQ 2026-06-12] forward fitting mode per expiry. Invariants:
1. The synthetic world has zero rates, so with default market settings the
   parity and theoretical forwards both sit at spot and parity is active.
2. A manual override changes the forward every subsequent fit uses (the
   forwards version is part of fit-cache keys) and parity mode restores it.
3. Validation: manual without a level is a 422; unknown nodes are 404s.
4. A dividend yield lowers every theoretical forward; a redundant PUT never
   bumps the forwards version (warm fit caches survive).
5. mode="theoretical" makes the smile fit on the theoretical forward.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    # Function-scoped: policies/settings are app-global, keep tests independent.
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _forwards(client, ticker: str = "ALPHA") -> dict:
    response = client.get(f"/forwards/{ticker}")
    assert response.status_code == 200
    return response.json()


def test_parity_defaults_cover_the_ladder(client):
    data = _forwards(client)
    ladder = client.get("/universe").json()["expiries"]["ALPHA"]
    assert data["ticker"] == "ALPHA"
    assert data["exerciseStyle"] == "european"  # SyntheticProvider default
    assert [e["expiry"] for e in data["entries"]] == [e["expiry"] for e in ladder]
    spot = data["spot"]
    for entry in data["entries"]:
        # Zero synthetic rates: parity ~ theo ~ spot (parity regression noise).
        assert entry["parityForward"] == pytest.approx(spot, rel=1e-3)
        assert entry["parityDiscount"] == pytest.approx(1.0, abs=1e-3)
        assert entry["theoForward"] == pytest.approx(spot, rel=1e-12)
        assert entry["theoDiscount"] == pytest.approx(1.0, abs=1e-12)
        assert entry["parityForward"] == pytest.approx(entry["theoForward"], rel=1e-3)
        assert entry["mode"] == "parity"
        assert entry["activeSource"] == "parity"
        assert entry["activeForward"] == entry["parityForward"]
        assert entry["activeDiscount"] == entry["parityDiscount"]


def test_manual_override_drives_fits_and_parity_restores(client):
    data = _forwards(client)
    spot = data["spot"]
    expiry = data["entries"][1]["expiry"]

    base = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert base["forward"] == pytest.approx(data["entries"][1]["activeForward"])

    override = 1.02 * spot
    response = client.put(
        f"/forwards/ALPHA/{expiry}", json={"mode": "manual", "manualForward": override}
    )
    assert response.status_code == 200
    entry = response.json()
    assert entry["activeSource"] == "manual"
    assert entry["manualForward"] == pytest.approx(override)
    assert entry["activeForward"] == pytest.approx(override)
    # Discount comes from parity when available (zero-rate world: ~1).
    assert entry["activeDiscount"] == pytest.approx(entry["parityDiscount"])

    # The fit cache must bust: the next smile payload fits on the override.
    smile = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert smile["forward"] == pytest.approx(override)

    # Back to parity: the original forward (and fit) returns.
    assert client.put(f"/forwards/ALPHA/{expiry}", json={"mode": "parity"}).status_code == 200
    restored = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert restored["forward"] == pytest.approx(base["forward"])


def test_validation_and_unknown_nodes(client):
    expiry = _forwards(client)["entries"][0]["expiry"]
    # manual without a level: schema-level 422.
    assert client.put(f"/forwards/ALPHA/{expiry}", json={"mode": "manual"}).status_code == 422
    # Unknown expiry / malformed expiry / unknown ticker: 404s.
    assert (
        client.put("/forwards/ALPHA/2031-01-01", json={"mode": "parity"}).status_code == 404
    )
    assert client.put("/forwards/ALPHA/not-a-date", json={"mode": "parity"}).status_code == 404
    assert client.put(f"/forwards/NOPE/{expiry}", json={"mode": "parity"}).status_code == 404
    assert client.get("/forwards/NOPE").status_code == 404
    assert client.get("/settings/market/NOPE").status_code == 404
    assert client.put("/settings/market/NOPE", json={"rate": 0.01}).status_code == 404


def test_dividend_yield_lowers_theoretical_forwards(client):
    spot = _forwards(client)["spot"]
    response = client.put("/settings/market/ALPHA", json={"dividendYield": 0.02})
    assert response.status_code == 200
    assert response.json()["dividendYield"] == pytest.approx(0.02)
    assert client.get("/settings/market/ALPHA").json()["dividendYield"] == pytest.approx(0.02)

    for entry in _forwards(client)["entries"]:
        assert entry["theoForward"] < spot
        # Parity (and the active default) is untouched by market settings.
        assert entry["activeSource"] == "parity"
        assert entry["parityForward"] == pytest.approx(spot, rel=1e-3)


def test_redundant_market_put_keeps_caches(client):
    state = client.app.state.volfit
    client.put("/settings/market/ALPHA", json={"dividendYield": 0.02})
    version = state.forwards_version("ALPHA")
    # Identical re-PUT: no version bump, warm fit caches stay valid.
    client.put("/settings/market/ALPHA", json={"dividendYield": 0.02})
    assert state.forwards_version("ALPHA") == version
    # A real change bumps it exactly once.
    client.put("/settings/market/ALPHA", json={"dividendYield": 0.03})
    assert state.forwards_version("ALPHA") == version + 1
    # Per-ticker: ALPHA's edit must NOT bump another ticker's forwards version.
    assert state.forwards_version("BETA") == 0


def test_theoretical_mode_drives_fits(client):
    data = _forwards(client)
    spot = data["spot"]
    assert client.put("/settings/market/ALPHA", json={"dividendYield": 0.01}).status_code == 200

    expiry = data["entries"][2]["expiry"]
    response = client.put(f"/forwards/ALPHA/{expiry}", json={"mode": "theoretical"})
    assert response.status_code == 200
    entry = response.json()
    assert entry["activeSource"] == "theoretical"
    assert entry["activeForward"] == pytest.approx(entry["theoForward"])
    assert entry["theoForward"] < spot  # the 1% yield shows up

    smile = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert smile["forward"] == pytest.approx(entry["theoForward"])
    # ... and is measurably away from the parity forward it replaced.
    assert abs(smile["forward"] - entry["parityForward"]) > 1e-4 * spot

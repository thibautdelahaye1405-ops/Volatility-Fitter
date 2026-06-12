"""Chart & UX additions API tests ([REQ 2026-06-12], ROADMAP Phase 6/3).

Covers the three backend pieces of the chart/UX block:
* expiry classification (volfit.data.expiries) — pure unit goldens plus the
  /universe payload's new expiryType tag on every rung;
* GET /surface/{ticker} — the shared-grid sigma(k, T) mesh for the 3D chart;
* GET /smiles/{t}/{e}/table and .../table.csv — the quote/price/IV export.

Runs in-process over fastapi.testclient like tests/test_api.py, on its own
app instance (module-scoped client) so nothing leaks between test files.
Surface tests use ALPHA, table tests use BETA (different expiries for the
edit test, so its session does not disturb the pristine-table assertions).
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.surface import N_SURFACE_POINTS
from volfit.api.table import CSV_COLUMNS
from volfit.data.expiries import classify_expiry, third_friday

REF_DATE = date(2026, 6, 10)

#: Reference date of the hand-picked classification cases below.
CLASSIFY_REF = date(2026, 6, 12)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def universe(client):
    response = client.get("/universe")
    assert response.status_code == 200
    return response.json()


# -- expiry classification ----------------------------------------------------


def test_third_friday_goldens():
    assert third_friday(2026, 6) == date(2026, 6, 19)
    assert third_friday(2026, 7) == date(2026, 7, 17)
    assert third_friday(2027, 1) == date(2027, 1, 15)
    assert third_friday(2028, 1) == date(2028, 1, 21)


def test_classify_expiry_hand_picked_cases():
    cases = {
        date(2026, 6, 19): "quarterly",  # 3rd Friday of June
        date(2026, 7, 17): "monthly",  # 3rd Friday of July
        date(2026, 6, 26): "weekly",  # 4th Friday — not a monthly
        date(2026, 6, 24): "daily",  # a Wednesday
        date(2027, 1, 15): "monthly",  # 3rd Fri Jan but ~217d out: NOT leaps
        date(2028, 1, 21): "leaps",  # 3rd Fri Jan, >= 270d out
        date(2027, 3, 19): "quarterly",  # far-dated but March: leaps is Jan-only
    }
    for expiry, expected in cases.items():
        assert classify_expiry(expiry, CLASSIFY_REF) == expected, expiry


def test_universe_carries_expiry_type(universe):
    # Synthetic ladder from 2026-06-10: +30d lands on a 2nd Friday (weekly),
    # +91/+182d on Wednesdays and +365d on a Thursday (daily).
    valid = {"daily", "weekly", "monthly", "quarterly", "leaps"}
    for ticker in universe["tickers"]:
        ladder = universe["expiries"][ticker]
        for rung in ladder:
            assert rung["expiryType"] in valid
            expected = classify_expiry(date.fromisoformat(rung["expiry"]), REF_DATE)
            assert rung["expiryType"] == expected
        assert [r["expiryType"] for r in ladder] == ["weekly", "daily", "daily", "daily"]


# -- 3D surface mesh ----------------------------------------------------------


def test_surface_mesh_shape_and_levels(client, universe):
    response = client.get("/surface/ALPHA")
    assert response.status_code == 200
    data = response.json()

    assert data["ticker"] == "ALPHA"
    assert data["expiries"] == [e["expiry"] for e in universe["expiries"]["ALPHA"]]

    ts = data["t"]
    assert len(ts) == len(data["expiries"])
    assert all(a < b for a, b in zip(ts, ts[1:]))  # strictly increasing
    assert len(data["atmVol"]) == len(ts) == len(data["forward"])
    assert all(f > 0 for f in data["forward"])

    k = np.array(data["k"])
    assert k.size == N_SURFACE_POINTS
    assert np.all(np.diff(k) > 0)

    vol = data["vol"]
    assert len(vol) == len(data["expiries"])  # one row per expiry
    for row in vol:
        assert len(row) == k.size  # full rectangular mesh
        v = np.array(row)
        assert np.all(np.isfinite(v)) and np.all((v > 0.05) & (v < 1.0))

    # The mesh column nearest k = 0 must sit on the exact ATM handle.
    j0 = int(np.argmin(np.abs(k)))
    for row, atm in zip(vol, data["atmVol"]):
        assert row[j0] == pytest.approx(atm, abs=0.01)


def test_surface_unknown_ticker_404(client):
    assert client.get("/surface/NOPE").status_code == 404


# -- table export -------------------------------------------------------------


def test_table_json_rows(client, universe):
    expiry = universe["expiries"]["BETA"][1]["expiry"]  # 3M, never edited here
    response = client.get(f"/smiles/BETA/{expiry}/table")
    assert response.status_code == 200
    data = response.json()

    assert data["ticker"] == "BETA" and data["expiry"] == expiry
    assert data["t"] == pytest.approx(91 / 365.0)
    # Zero-rate synthetic chain: parity regression can return a discount
    # a few ulp above 1.0 - allow float noise.
    assert data["forward"] > 0 and 0 < data["discount"] <= 1.0 + 1e-9

    rows = data["rows"]
    assert len(rows) >= 10
    ks = [r["k"] for r in rows]
    assert ks == sorted(ks)  # sorted by log-moneyness
    for r in rows:
        # OTM side convention and the strike <-> k round trip.
        assert r["type"] == ("C" if r["k"] >= 0 else "P")
        assert r["strike"] == pytest.approx(data["forward"] * np.exp(r["k"]), rel=1e-12)
        # IV band ordering survives into reconstructed prices (Black monotone).
        assert r["bidIv"] <= r["midIv"] <= r["askIv"]
        assert 0 < r["bidPrice"] <= r["midPrice"] <= r["askPrice"]
        # Fitted vol is a sane IV near the quoted band.
        assert 0.05 < r["modelIv"] < 1.0
        assert not r["excluded"] and not r["amended"]

    # The mid fit tracks the quoted mid IVs (same fit GET /smiles serves).
    err = np.median([abs(r["modelIv"] - r["midIv"]) for r in rows])
    assert float(err) < 1e-3


def test_table_csv_download(client, universe):
    expiry = universe["expiries"]["BETA"][1]["expiry"]
    rows = client.get(f"/smiles/BETA/{expiry}/table").json()["rows"]

    response = client.get(f"/smiles/BETA/{expiry}/table.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert f'filename="BETA_{expiry}_quotes.csv"' in disposition

    lines = response.text.strip().splitlines()
    assert lines[0] == CSV_COLUMNS  # exact frozen header
    assert len(lines) == len(rows) + 1  # header + one line per JSON row


def test_table_reflects_quote_exclusion(client, universe):
    expiry = universe["expiries"]["BETA"][0]["expiry"]  # 1M, its own session
    base = client.get(f"/smiles/BETA/{expiry}/table").json()
    wing = max(base["rows"], key=lambda r: abs(r["k"]))["index"]

    edited = client.post(
        f"/smiles/BETA/{expiry}/edits", json={"action": "exclude", "index": wing}
    )
    assert edited.status_code == 200

    after = client.get(f"/smiles/BETA/{expiry}/table").json()
    assert len(after["rows"]) == len(base["rows"])  # excluded rows stay listed
    assert after["rows"][wing]["excluded"] is True
    assert sum(r["excluded"] for r in after["rows"]) == 1


def test_table_unknown_nodes_404(client, universe):
    expiry = universe["expiries"]["BETA"][0]["expiry"]
    assert client.get(f"/smiles/NOPE/{expiry}/table").status_code == 404
    assert client.get("/smiles/BETA/2030-01-01/table").status_code == 404
    assert client.get(f"/smiles/NOPE/{expiry}/table.csv").status_code == 404

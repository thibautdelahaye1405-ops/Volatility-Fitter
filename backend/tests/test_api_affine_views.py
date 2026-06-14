"""API tests: Local-Vol-derived density / term / table views (Phase 10).

The Local Vol workspace mirrors the Parametric sub-tabs, deriving each view
from the calibrated affine surface (volfit.api.affine_views). The contract:
  * /term returns one point per fitted expiry + a dense curve, same shape as
    POST /term, with positive ATM and var-swap vols;
  * /density returns a normalized risk-neutral density (integrates ~1) for a
    requested expiry, no prior;
  * /table returns one row per quote with a reconstructed model IV that tracks
    the quotes and discounted prices;
  * unknown expiry / ticker are clean 4xx.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _ticker(client) -> str:
    return client.get("/universe").json()["tickers"][0]


def _expiries(client, ticker: str) -> list[str]:
    return [s["expiry"] for s in client.post(f"/fit/affine/{ticker}", json={}).json()["smiles"]]


def test_affine_term_shape(client):
    ticker = _ticker(client)
    resp = client.post(f"/fit/affine/{ticker}/term", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticker"] == ticker
    assert len(data["points"]) >= 2
    for p in data["points"]:
        assert p["atmVol"] > 0.0
        assert p["varSwapVol"] > 0.0
        assert p["w0"] == pytest.approx(p["atmVol"] ** 2 * p["t"], rel=1e-6)
    # Dense curve is well-formed and positive.
    assert len(data["curve"]["t"]) == len(data["curve"]["vol"]) > 0
    assert all(v > 0.0 for v in data["curve"]["vol"])


def test_affine_density_normalized(client):
    ticker = _ticker(client)
    expiries = _expiries(client, ticker)
    expiry = expiries[len(expiries) // 2]
    resp = client.post(f"/fit/affine/{ticker}/density", json={}, params={"expiry": expiry})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["prior"] is None  # the LV surface has no saved prior
    x = np.array(data["current"]["x"])
    pdf = np.array(data["current"]["density"])
    assert x.size > 10 and np.all(pdf >= 0.0)
    # Central-mass density integrates to a large fraction of 1 (trimmed tails).
    assert 0.8 < float(np.trapezoid(pdf, x)) <= 1.0 + 1e-6


def test_affine_table_tracks_quotes(client):
    ticker = _ticker(client)
    expiries = _expiries(client, ticker)
    expiry = expiries[len(expiries) // 2]
    resp = client.post(f"/fit/affine/{ticker}/table", json={}, params={"expiry": expiry})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["expiry"] == expiry and data["forward"] > 0.0
    assert len(data["rows"]) >= 2
    for r in data["rows"]:
        assert r["type"] == ("C" if r["k"] >= 0.0 else "P")
        assert r["bidPrice"] >= 0.0 and r["askPrice"] >= 0.0
        if not r["excluded"]:
            # Reconstructed model IV tracks the quote mid within a few vol pts.
            assert abs(r["modelIv"] - r["midIv"]) < 0.03


def test_affine_views_unknown(client):
    ticker = _ticker(client)
    # Unknown expiry -> 422; unknown ticker -> 404.
    assert (
        client.post(f"/fit/affine/{ticker}/density", json={}, params={"expiry": "2099-01-01"}).status_code
        == 422
    )
    assert client.post("/fit/affine/NOPE/term", json={}).status_code == 404

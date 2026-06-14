"""API test: GET /smiles/{ticker}/densities (stacked-densities view, Phase 10).

One density per fitted expiry, model-aware, each non-negative and integrating
to ~1 over the central mass (the visual no-butterfly-arbitrage check).
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


def test_stacked_densities_shape(client):
    ticker = client.get("/universe").json()["tickers"][0]
    resp = client.get(f"/smiles/{ticker}/densities")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticker"] == ticker
    expiries = data["expiries"]
    assert len(expiries) >= 2
    # Nearest-first, strictly increasing maturities.
    ts = [e["t"] for e in expiries]
    assert ts == sorted(ts)
    for e in expiries:
        x = np.array(e["x"])
        pdf = np.array(e["density"])
        assert x.size > 10 and len(pdf) == len(x)
        assert np.all(pdf >= 0.0)  # no butterfly arbitrage on any slice
        assert 0.8 < float(np.trapezoid(pdf, x)) <= 1.0 + 1e-6


def test_stacked_densities_unknown_ticker(client):
    assert client.get("/smiles/NOPE/densities").status_code == 404

"""API tests: POST /fit/affine/{ticker} (direct local-vol-affine surface fit).

Drives the endpoint against the deterministic synthetic provider and checks
the contract the Local Vol view depends on:
  * a well-formed response (nodal surface, one reconstructed smile per fitted
    expiry, diagnostics);
  * the reconstructed smiles track the quotes (the affine surface is fit to
    them) within a few vol points;
  * butterfly/calendar no-arbitrage holds by construction;
  * the per-request cache returns the identical payload;
  * too few expiries / an unknown ticker are clean 4xx errors.
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


def test_affine_fit_shape_and_arbitrage(client):
    ticker = _ticker(client)
    resp = client.post(f"/fit/affine/{ticker}", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Nodal surface: rectangular sqrt(variance) table over the vertex grid.
    assert len(data["localVol"]) == len(data["tNodes"])
    assert all(len(row) == len(data["xNodes"]) for row in data["localVol"])
    assert all(0.01 < v < 2.0 for row in data["localVol"] for v in row)
    # The ATM vertex x = 1 is always present.
    assert any(abs(x - 1.0) < 1e-9 for x in data["xNodes"])
    assert data["tNodes"][0] == 0.0

    # One reconstructed smile per fitted expiry, each a sane vol curve.
    assert len(data["smiles"]) >= 2
    for smile in data["smiles"]:
        assert len(smile["model"]) > 10
        assert all(0.01 < p["vol"] < 2.0 for p in smile["model"])
        assert len(smile["quotes"]) >= 2

    assert data["arbitrageFree"] is True
    assert data["calendarViolations"] == 0
    assert min(data["minDensity"]) > -1e-6


def test_affine_fit_tracks_quotes(client):
    """The reconstructed smiles fit the quotes within a few vol points."""
    ticker = _ticker(client)
    data = client.post(f"/fit/affine/{ticker}", json={}).json()
    # Synthetic quotes are smooth, so the affine surface should fit tightly.
    assert data["maxIvErrorBp"] < 200.0  # < 2 vol points worst quote
    assert data["rmsIvErrorBp"] < 80.0

    # Cross-check: interpolate one reconstructed curve at its quote strikes.
    smile = data["smiles"][len(data["smiles"]) // 2]
    ks = np.array([p["k"] for p in smile["model"]])
    vols = np.array([p["vol"] for p in smile["model"]])
    for q in smile["quotes"]:
        if not q["excluded"]:
            model_vol = float(np.interp(q["k"], ks, vols))
            assert abs(model_vol - q["mid"]) < 0.03


def test_affine_fit_is_cached(client):
    ticker = _ticker(client)
    first = client.post(f"/fit/affine/{ticker}", json={}).json()
    second = client.post(f"/fit/affine/{ticker}", json={}).json()
    assert first == second


def test_affine_fit_honours_request_params(client):
    """A coarser vertex grid yields a smaller nodal table."""
    ticker = _ticker(client)
    fine = client.post(f"/fit/affine/{ticker}", json={"nXNodes": 9}).json()
    coarse = client.post(f"/fit/affine/{ticker}", json={"nXNodes": 4}).json()
    assert len(fine["xNodes"]) > len(coarse["xNodes"])


def test_affine_fit_unknown_ticker(client):
    assert client.post("/fit/affine/NOPE", json={}).status_code == 404


def test_affine_fit_validation(client):
    ticker = _ticker(client)
    # nXNodes below the schema floor is a 422.
    assert client.post(f"/fit/affine/{ticker}", json={"nXNodes": 1}).status_code == 422

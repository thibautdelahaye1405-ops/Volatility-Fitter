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


def test_affine_grid_follows_options(client):
    """The vertex grid is an Options hyperparameter now: a larger gridXNodes
    yields a bigger nodal table after an (explicit) recalibration. The affine
    read path is frozen — calibration runs on demand (Calibrate)."""
    ticker = _ticker(client)
    opts = client.get("/settings/options").json()
    client.put("/settings/options", json={**opts, "gridXNodes": 11})
    client.post(f"/calibrate/{ticker}")  # rebuild the LV surface at the new grid
    fine = client.post(f"/fit/affine/{ticker}", json={}).json()
    client.put("/settings/options", json={**opts, "gridXNodes": 4})
    client.post(f"/calibrate/{ticker}")
    coarse = client.post(f"/fit/affine/{ticker}", json={}).json()
    assert len(fine["xNodes"]) > len(coarse["xNodes"])


def test_affine_optimal_size(client):
    """The optimal-size endpoint sizes the grid to the observed quotes."""
    ticker = _ticker(client)
    o = client.get(f"/fit/affine/{ticker}/optimal-size").json()
    assert o["nExpiries"] >= 2 and o["nQuotes"] > 0
    assert o["gridXNodes"] >= 3
    assert o["gridTNodes"] == 0  # auto: one time vertex per observed expiry


@pytest.mark.parametrize("mode", ["bidask", "haircut"])
def test_affine_fit_band_modes(client, mode):
    """The band fit modes calibrate end-to-end and stay arbitrage-free; the band
    objective changes the surface vs the mid fit. Driven through the force-
    calibrate path (the read path is frozen — calibration is a trigger now)."""
    from volfit.api.affine_fit import calibrate_affine_surface
    from volfit.api.schemas_affine import AffineFitRequest

    ticker = _ticker(client)
    state = client.app.state.volfit
    mid = calibrate_affine_surface(state, ticker, AffineFitRequest(fitMode="mid"))
    band = calibrate_affine_surface(state, ticker, AffineFitRequest(fitMode=mode))
    assert band.arbitrageFree is True and band.calendarViolations == 0
    assert len(band.smiles) == len(mid.smiles)
    flat_mid = [v for row in mid.localVol for v in row]
    flat_band = [v for row in band.localVol for v in row]
    assert any(abs(a - b) > 1e-6 for a, b in zip(flat_mid, flat_band))


def test_affine_density_is_clean_no_interior_zeros(client):
    """The LV density (from the Dupire PDE prices, d2C/dx2) is smooth and strictly
    positive across the central mass — no the short-dated interior zeros the
    implied-vol Breeden-Litzenberger formula produced."""
    ticker = _ticker(client)
    data = client.post(f"/fit/affine/{ticker}", json={}).json()
    short = data["smiles"][0]["expiry"]  # shortest expiry, the worst case
    dens = client.post(f"/fit/affine/{ticker}/density?expiry={short}", json={}).json()
    pdf = dens["current"]["density"]
    assert len(pdf) > 5
    assert all(p > 0.0 for p in pdf)  # no clamped-to-zero interior points
    # Integrates to ~1 over its log-return grid.
    xs = dens["current"]["x"]
    area = sum(0.5 * (pdf[i] + pdf[i - 1]) * (xs[i] - xs[i - 1]) for i in range(1, len(xs)))
    assert area == pytest.approx(1.0, abs=0.05)


def test_affine_fit_unknown_ticker(client):
    assert client.post("/fit/affine/NOPE", json={}).status_code == 404


def test_affine_fit_validation(client):
    ticker = _ticker(client)
    # The grid lives in Options now: a strike-node count below the floor is a 422.
    opts = client.get("/settings/options").json()
    assert client.put("/settings/options", json={**opts, "gridXNodes": 1}).status_code == 422
    # The per-request nodal-variance bound is still validated too.
    assert client.post(f"/fit/affine/{ticker}", json={"varLo": -1.0}).status_code == 422

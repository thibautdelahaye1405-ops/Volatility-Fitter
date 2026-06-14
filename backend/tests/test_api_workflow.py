"""API tests for the calibration / data-fetch workflow endpoints."""

import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _off_auto(client) -> None:
    opts = client.get("/settings/options").json()
    opts["autoCalibrate"] = False
    client.put("/settings/options", json=opts)


def _iso(client) -> str:
    return client.get("/universe").json()["expiries"][TICKER][1]["expiry"]


def test_status_reports_lit_nodes(client):
    client.get(f"/smiles/{TICKER}/{_iso(client)}")  # bootstrap one node
    st = client.get("/calibration/status").json()
    assert st["litNodes"] >= 1
    assert st["running"] is False


def test_global_calibrate_clears_stale(client):
    _off_auto(client)
    iso = _iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")  # bootstrap (current)
    # A settings change marks the node stale (auto off => no refit).
    fs = client.get("/settings/fit").json()
    fs["regLambda"] = fs["regLambda"] * 2 + 1e-9
    client.put("/settings/fit", json=fs)
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is True

    client.post("/calibrate")  # background job over all lit nodes
    for _ in range(100):  # wait for the job to drain
        if not client.get("/calibration/status").json()["running"]:
            break
        time.sleep(0.1)
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is False


def test_fetch_options_marks_stale_without_auto(client):
    _off_auto(client)
    iso = _iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")  # bootstrap
    res = client.post("/fetch/options", json={"tickers": [TICKER]}).json()
    assert TICKER in res["tickers"]
    assert res["calibrationStarted"] is False
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is True


def test_fetch_options_auto_calibrates(client):
    iso = _iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")  # bootstrap (auto on by default)
    res = client.post("/fetch/options", json={"tickers": [TICKER]}).json()
    assert res["calibrationStarted"] is True
    for _ in range(100):
        if not client.get("/calibration/status").json()["running"]:
            break
        time.sleep(0.1)
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is False


def test_lv_surface_stale_gating_and_background_calibrate(client):
    """The LV (affine) surface follows the same freeze/stale model and is
    rebuilt by the global background Calibrate (counted in the job total)."""
    _off_auto(client)
    base = client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()
    assert base["stale"] is False  # bootstrap surface is current

    # A fresh options fetch (auto off) marks the LV surface stale, no refit.
    client.post("/fetch/options", json={"tickers": [TICKER]})
    assert client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()["stale"] is True

    # Global Calibrate runs nodes AND LV surfaces in one background job.
    client.post("/calibrate")
    st = client.get("/calibration/status").json()
    assert st["total"] > st["litNodes"]  # LV surfaces are extra job items
    for _ in range(200):
        if not client.get("/calibration/status").json()["running"]:
            break
        time.sleep(0.1)
    assert client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()["stale"] is False


def test_fetch_spots_transports_without_recal(client):
    iso = _iso(client)
    base = client.get(f"/smiles/{TICKER}/{iso}").json()
    res = client.post("/fetch/spots", json={"tickers": [TICKER]}).json()
    # Synthetic spot is static => implied return ~0 => forward unchanged, no stale.
    assert res[TICKER]["spotReturn"] == pytest.approx(0.0, abs=1e-12)
    moved = client.get(f"/smiles/{TICKER}/{iso}").json()
    assert moved["forward"] == pytest.approx(base["forward"], rel=1e-12)
    assert moved["stale"] is False  # a spot fetch never recalibrates

"""Trigger-gated workflow (the live server): no fetch / no calibration until a
button is pressed.

create_app(gated=True) mirrors serve.py. The contract:
  * GET /universe lists the selected expiry ladder WITHOUT fetching any chain;
  * a smile READ never fetches quotes nor bootstraps a fit — it returns
    hasFit=False with an empty model (quotes only once fetched, the dotted prior
    if one exists);
  * POST /fetch/options loads the quotes (still no fit);
  * POST /calibrate produces the fit (auto-fetching the chain if needed).

Runs in-process over fastapi.testclient (synthetic provider, no network).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as c:
        yield c


def _expiry(client, ticker="ALPHA", index=2):
    u = client.get("/universe").json()
    return u["expiries"][ticker][index]["expiry"]


def test_universe_lists_ladder_without_fetching(client):
    """The expiry ladder is metadata only — no chain fetch on universe load."""
    u = client.get("/universe").json()
    assert u["tickers"] == ["ALPHA", "BETA", "GAMMA"]
    assert len(u["expiries"]["ALPHA"]) == 4  # the synthetic ladder, no quotes pulled


def test_smile_read_has_no_fit_and_no_quotes_before_fetch(client):
    """Opening a smile before Fetch must not calibrate or pull quotes."""
    data = client.get(f"/smiles/ALPHA/{_expiry(client)}").json()
    assert data["hasFit"] is False
    assert data["model"] == []
    assert data["quotes"] == []  # nothing fetched yet


def test_fetch_loads_quotes_but_does_not_fit(client):
    """Fetch loads quotes; the node still shows no model (calibrate is separate)."""
    expiry = _expiry(client)
    assert client.post("/fetch/options", json={}).status_code == 200
    data = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert data["hasFit"] is False
    assert data["model"] == []
    assert len(data["quotes"]) > 0  # quotes now present
    assert data["forward"] > 0


def test_calibrate_produces_the_fit(client):
    """Calibrate (here the synchronous per-node endpoint) yields the model curve."""
    expiry = _expiry(client)
    client.post("/fetch/options", json={})
    assert client.post(f"/calibrate/ALPHA/{expiry}").status_code == 200
    data = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert data["hasFit"] is True
    assert len(data["model"]) > 0
    assert data["diagnostics"]["atmVol"] > 0


def test_calibrate_auto_fetches_when_no_quotes(client):
    """Press Calibrate before Fetch: it auto-fetches the chain, then fits."""
    expiry = _expiry(client)
    assert client.post(f"/calibrate/ALPHA/{expiry}").status_code == 200  # no prior fetch
    data = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert data["hasFit"] is True
    assert len(data["model"]) > 0


def test_gated_app_defaults_autocalibrate_off(client):
    """The gated server defaults autoCalibrate OFF (fit only on the button)."""
    assert client.get("/settings/options").json()["autoCalibrate"] is False


def test_lit_map_available_before_any_fetch(client):
    """The lit/dark matrix lists every selected node from metadata, so nodes can
    be lit/darkened immediately after the universe changes (before Fetch)."""
    lit = client.get("/universe/lit").json()["nodes"]
    assert len(lit) == 4 * 3  # 4 expiries x 3 synthetic tickers, no chain fetched
    # And a node can be toggled at this stage (no fetch/calibrate needed).
    expiry = _expiry(client)
    toggled = client.put(f"/universe/lit/ALPHA/{expiry}", json={"lit": False}).json()
    assert toggled["lit"] is False


def test_fetch_priors_preserves_live_calibration(client):
    """Fetch priors switches the as-of to a past close and back; the live
    calibrated smile + quotes MUST survive (the gated workflow doesn't lazily
    re-bootstrap them, so a cache wipe would blank the chart)."""
    expiry = _expiry(client)
    client.post("/fetch/options", json={})
    client.post(f"/calibrate/ALPHA/{expiry}")
    before = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert before["hasFit"] is True and len(before["model"]) > 0

    assert client.post("/priors/fetch").status_code == 200

    after = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert after["hasFit"] is True  # live fit preserved (not wiped)
    assert len(after["model"]) > 0
    assert len(after["quotes"]) > 0  # live quotes preserved


def test_views_degrade_gracefully_before_calibration(client):
    """Term / surface / density / table never 500 with no calibrated node."""
    expiry = _expiry(client)
    assert client.post("/term/ALPHA", json={}).json()["points"] == []
    surface = client.get("/surface/ALPHA").json()
    assert surface["expiries"] == []
    assert client.get(f"/smiles/ALPHA/{expiry}/density").json()["current"]["x"] == []
    assert client.get(f"/smiles/ALPHA/{expiry}/table").json()["rows"] == []

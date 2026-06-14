"""API tests for the fast spot-move endpoints (/spot/{ticker}).

A spot shift transports the smile/term/LV-grid (GET /smiles reflects it) with no
recalibration; "Calibrate" re-anchors; the live probe reports the implied return.
"""

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


def _iso(client) -> str:
    # The universe lists each ticker's expiry ladder; pick the second rung (~3M).
    universe = client.get("/universe").json()
    return universe["expiries"][TICKER][1]["expiry"]


def test_spot_state_defaults(client):
    state = client.get(f"/spot/{TICKER}").json()
    assert state["ticker"] == TICKER
    assert state["spotReturn"] == 0.0
    assert state["anchorSpot"] > 0.0
    assert state["shiftedSpot"] == pytest.approx(state["anchorSpot"])
    assert state["regime"] == "sticky_strike"
    assert state["regimeSsr"] == 1.0


def test_put_shift_moves_forward_and_smile(client):
    iso = _iso(client)
    base = client.get(f"/smiles/{TICKER}/{iso}").json()
    f0 = base["forward"]

    st = client.put(f"/spot/{TICKER}", json={"spotReturn": 0.02}).json()
    assert st["spotReturn"] == pytest.approx(0.02)
    assert st["shiftedSpot"] == pytest.approx(st["anchorSpot"] * 1.02)

    moved = client.get(f"/smiles/{TICKER}/{iso}").json()
    assert moved["forward"] == pytest.approx(f0 * 1.02, rel=1e-9)
    # Sticky-strike, equity skew, spot up => ATM vol drops.
    assert moved["diagnostics"]["atmVol"] < base["diagnostics"]["atmVol"]


def test_calibrate_reanchors(client):
    iso = _iso(client)
    f0 = client.get(f"/smiles/{TICKER}/{iso}").json()["forward"]
    client.put(f"/spot/{TICKER}", json={"spotReturn": 0.05})
    st = client.post(f"/spot/{TICKER}/calibrate").json()
    assert st["spotReturn"] == 0.0
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["forward"] == pytest.approx(f0, rel=1e-9)


def test_live_spot_probe(client):
    live = client.get(f"/spot/{TICKER}/live").json()
    # Synthetic spot is static, so the live probe equals the anchor (return 0).
    assert live["liveSpot"] == pytest.approx(live["anchorSpot"])
    assert live["spotReturn"] == pytest.approx(0.0, abs=1e-12)


def test_unknown_ticker_404(client):
    assert client.get("/spot/NOPE").status_code == 404
    assert client.put("/spot/NOPE", json={"spotReturn": 0.01}).status_code == 404

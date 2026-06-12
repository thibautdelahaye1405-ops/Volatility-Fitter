"""API tests: GET /localvol/{ticker} and the sticky-local-vol-grid scenario.

In-process over fastapi.testclient against the synthetic provider (pinned
reference date). Invariants:

1. Grid shape & gates: one sigma row per listed expiry bucket, strictly
   positive vols, extraction repairs (nNan/nClipped) at zero on the clean
   synthetic surface, no-arbitrage diagnostics green.
2. Consistency: repricing each expiry through the Dupire PDE recovers the
   fitted ATM vol within a few vol bp (the grid is extracted from those very
   fits).
3. Sticky-local-vol-grid scenario: exact dynamics endpoint returns a
   finite realized SSR; for mid/long maturities it sits in the broad
   sticky-LV band (the shortest bucket is documented as ill-conditioned).
4. Unknown tickers are 404s, spotReturn = 0 is a no-op.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def universe(client):
    return client.get("/universe").json()


@pytest.fixture(scope="module")
def localvol(client):
    response = client.get("/localvol/ALPHA")
    assert response.status_code == 200
    return response.json()


def test_grid_shape_and_gates(localvol, universe):
    ladder = universe["expiries"]["ALPHA"]
    assert localvol["ticker"] == "ALPHA"
    assert localvol["expiries"] == [e["expiry"] for e in ladder]
    sigma = np.array(localvol["sigma"])
    assert sigma.shape == (len(ladder), len(localvol["k"]))
    assert np.all(sigma > 0.0)
    assert localvol["nNan"] == 0 and localvol["nClipped"] == 0
    assert localvol["arbitrageFree"] is True
    assert len(localvol["minDensity"]) == len(ladder)
    assert len(localvol["calendarViolation"]) == len(ladder) - 1
    assert min(localvol["minDensity"]) >= -1e-8
    assert max(localvol["calendarViolation"] or [0.0]) <= 1e-8


def test_reprice_matches_fitted_atm(client, universe):
    """LV-grid PDE reprice recovers each fitted slice's ATM vol (<= 10 bp)."""
    for entry in universe["expiries"]["ALPHA"]:
        smile = client.get(f"/smiles/ALPHA/{entry['expiry']}").json()
        scenario = client.post(
            "/scenario/ssr",
            json={
                "ticker": "ALPHA",
                "expiry": entry["expiry"],
                "spotReturn": 0.0,
                "regime": "sticky_local_vol_grid",
            },
        ).json()
        k = np.array(scenario["k"])
        atm_lv = float(np.interp(0.0, k, np.array(scenario["baseVol"])))
        assert abs(atm_lv - smile["diagnostics"]["atmVol"]) < 1e-3, entry["expiry"]
        # spotReturn = 0 must be an exact no-op
        assert scenario["baseVol"] == scenario["shiftedVol"]


def test_sticky_grid_scenario_realized_ssr(client, universe):
    """Mid/long expiries realize an SSR in the broad sticky-LV band."""
    for index in (2, 3):  # 6M, 1Y of the synthetic ladder
        expiry = universe["expiries"]["ALPHA"][index]["expiry"]
        scenario = client.post(
            "/scenario/ssr",
            json={
                "ticker": "ALPHA",
                "expiry": expiry,
                "spotReturn": -0.02,
                "regime": "sticky_local_vol_grid",
            },
        ).json()
        assert scenario["regime"] == "sticky_local_vol_grid"
        shifted = np.array(scenario["shiftedVol"])
        assert np.all(np.isfinite(shifted)) and np.all(shifted > 0.0)
        assert 1.0 < scenario["ssr"] < 3.5, (expiry, scenario["ssr"])


def test_unknown_ticker_404(client):
    assert client.get("/localvol/NOPE").status_code == 404

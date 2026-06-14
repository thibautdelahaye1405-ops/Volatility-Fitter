"""API tests: GET/PUT /settings/fit and its effect on slice fits.

Invariants:
1. Defaults match the long-standing API constants (N = 6, lambda = 1e-6).
2. A changed PUT bumps the settings version: the next GET /smiles refits
   under the new hyperparameters (a strong-damping lambda visibly degrades
   the in-sample fit; a redundant PUT changes nothing and keeps caches).
3. Validation bounds are 422s.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    # Function-scoped: settings are app-global state, keep tests independent.
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _expiry(client, index: int = 2) -> str:
    return client.get("/universe").json()["expiries"]["ALPHA"][index]["expiry"]


def _fit_rms_bp(client, expiry: str) -> float:
    """In-sample rms (model vol - quote mid) in vol bp for one smile."""
    data = client.get(f"/smiles/ALPHA/{expiry}").json()
    ks = np.array([p["k"] for p in data["model"]])
    vols = np.array([p["vol"] for p in data["model"]])
    errs = [
        np.interp(q["k"], ks, vols) - q["mid"]
        for q in data["quotes"]
        if not q["excluded"]
    ]
    return float(np.sqrt(np.mean(np.square(errs)))) * 1e4


def test_defaults(client):
    settings = client.get("/settings/fit").json()
    assert settings == {
        "model": "lqd",
        "nOrder": 6,
        "regLambda": 1e-6,
        "regPower": 1.0,
        "nCores": 2,
        "haircut": 0.005,
        "weightScheme": "equal",
    }


def test_put_changes_subsequent_fits(client):
    expiry = _expiry(client)
    rms_default = _fit_rms_bp(client, expiry)

    response = client.put(
        "/settings/fit",
        json={"model": "lqd", "nOrder": 6, "regLambda": 0.5, "regPower": 2.0},
    )
    assert response.status_code == 200
    assert response.json()["regLambda"] == 0.5

    rms_damped = _fit_rms_bp(client, expiry)
    # Strong high-order damping must visibly degrade the in-sample fit.
    assert rms_damped > rms_default + 1.0, (rms_default, rms_damped)

    # Back to defaults: the fit returns to the original quality.
    client.put(
        "/settings/fit",
        json={"model": "lqd", "nOrder": 6, "regLambda": 1e-6, "regPower": 1.0},
    )
    assert _fit_rms_bp(client, expiry) == pytest.approx(rms_default, abs=1e-9)


def test_n_order_changes_fit(client):
    expiry = _expiry(client, 3)
    rms_n6 = _fit_rms_bp(client, expiry)
    client.put(
        "/settings/fit",
        json={"model": "lqd", "nOrder": 4, "regLambda": 1e-6, "regPower": 1.0},
    )
    rms_n4 = _fit_rms_bp(client, expiry)
    # Fewer basis modes cannot fit better; on a smooth synthetic smile the
    # two still differ measurably.
    assert rms_n4 != pytest.approx(rms_n6, abs=1e-12)
    assert rms_n4 > rms_n6 - 1e-9


def test_validation_bounds(client):
    for bad in (
        {"nOrder": 2},
        {"nOrder": 99},
        {"regLambda": -1.0},
        {"regPower": 9.0},
        {"nCores": -1},  # Multi-Core SIV hat count is in [0, 6]
        {"nCores": 7},
        {"haircut": -0.001},  # haircut is in [0, 0.05] absolute vol
        {"haircut": 0.1},
        {"weightScheme": "inverse_spread"},  # not a known weighting scheme
        {"model": "localvol"},  # not a calibratable smile family via the API
    ):
        assert client.put("/settings/fit", json=bad).status_code == 422


def test_weight_scheme_changes_fit(client):
    """Switching to time-value density weighting refits the smile (the synthetic
    chains are non-uniform in log-strike, so the density correction bites)."""
    expiry = _expiry(client, 3)
    base = client.get(f"/smiles/ALPHA/{expiry}").json()
    assert client.put("/settings/fit", json={"weightScheme": "tv_density"}).status_code == 200
    weighted = client.get(f"/smiles/ALPHA/{expiry}").json()
    base_vols = [p["vol"] for p in base["model"]]
    new_vols = [p["vol"] for p in weighted["model"]]
    assert any(abs(a - b) > 1e-6 for a, b in zip(base_vols, new_vols))
    client.put("/settings/fit", json={"weightScheme": "equal"})


def test_n_cores_changes_sigmoid_fit(client):
    """The Multi-Core SIV cores slider changes the displayed sigmoid smile."""
    expiry = _expiry(client, 3)
    client.put("/settings/fit", json={"model": "sigmoid", "nCores": 0})
    rms_base = _fit_rms_bp(client, expiry)
    client.put("/settings/fit", json={"model": "sigmoid", "nCores": 3})
    rms_cored = _fit_rms_bp(client, expiry)
    # Adding hats cannot make the in-sample fit worse; on a curved smile it
    # changes the fitted curve measurably.
    assert rms_cored != pytest.approx(rms_base, abs=1e-9)
    assert rms_cored <= rms_base + 1e-6


def test_model_choice_refits_smile(client):
    """Selecting SVI/sigmoid refits the displayed smile through the overlay
    path (volfit.api.fit_models): the chart and diagnostics change but the
    request still succeeds and returns a well-formed payload."""
    universe = client.get("/universe").json()
    ticker = universe["tickers"][0]
    expiry = universe["expiries"][ticker][2]["expiry"]
    base = client.get(f"/smiles/{ticker}/{expiry}").json()

    for model in ("svi", "sigmoid"):
        assert client.put("/settings/fit", json={"model": model}).json()["model"] == model
        data = client.get(f"/smiles/{ticker}/{expiry}").json()
        assert len(data["model"]) == len(base["model"])
        assert data["diagnostics"]["atmVol"] > 0.0
        # Overlay families have no A_L/A_R endpoint-scale concept.
        assert data["diagnostics"]["aLeft"] == 0.0
        assert data["diagnostics"]["aRight"] == 0.0
        # The fitted curve differs from the LQD default somewhere on the grid.
        lqd_vols = [p["vol"] for p in base["model"]]
        new_vols = [p["vol"] for p in data["model"]]
        assert any(abs(a - b) > 1e-6 for a, b in zip(lqd_vols, new_vols))

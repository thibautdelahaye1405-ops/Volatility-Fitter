"""Event-weighted variance clock (volfit.calib.weighted_time + API wiring).

The model: each calendar day weighs 1, an event adds N extra equivalent days,
and the smile is calibrated/quoted in weighted years tau. Total variance is
fixed by the price, so the working IV = sqrt(w / tau) DROPS when an event is
added before the expiry. Normalization rescales all days so the 1Y weight
budget stays 365 (1Y vols unchanged).
"""

import math
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.calib.weighted_time import weighted_variance_years

REF_DATE = date(2026, 6, 10)


# ------------------------------------------------------------------ unit math
def test_no_events_is_identity():
    assert weighted_variance_years(0.5, []) == 0.5
    assert weighted_variance_years(0.5, [(0.9, 20.0)]) == 0.5  # event after expiry


def test_event_before_adds_day_weights():
    tau = weighted_variance_years(0.5, [(0.1, 20.0)])
    assert tau == pytest.approx((0.5 * 365.0 + 20.0) / 365.0)
    assert tau > 0.5


def test_normalization_pins_one_year():
    # At 1Y the normalized weighted budget is exactly the no-event year.
    tau_1y = weighted_variance_years(1.0, [(0.1, 20.0)], normalize=True)
    assert tau_1y == pytest.approx(1.0)
    # Uniform rescale: all days incl. the event shrink by 365 / (365 + extra).
    tau_half = weighted_variance_years(0.5, [(0.1, 20.0)], normalize=True)
    assert tau_half == pytest.approx((0.5 * 365.0 + 20.0) / 385.0)


# ------------------------------------------------------------------- API wiring
@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _node(client, idx=1):
    uni = client.get("/universe").json()
    tk = uni["tickers"][0]
    return tk, uni["expiries"][tk][idx]["expiry"]


def test_event_lowers_iv_by_sqrt_t_over_tau(client):
    tk, exp = _node(client)
    base = client.get(f"/smiles/{tk}/{exp}").json()
    t = base["T"]
    atm0 = base["diagnostics"]["atmVol"]
    vs0 = base["diagnostics"]["varSwapVol"]
    mid_i = len(base["quotes"]) // 2
    q0 = base["quotes"][mid_i]["mid"]

    client.put(f"/events/{tk}", json={"events": [{"time": 0.01, "weight": 20.0, "label": "e"}]})
    pen = client.get(f"/smiles/{tk}/{exp}").json()
    tau = t + 20.0 / 365.0
    factor = math.sqrt(t / tau)

    assert pen["diagnostics"]["atmVol"] == pytest.approx(atm0 * factor, rel=2e-3)
    assert pen["diagnostics"]["varSwapVol"] == pytest.approx(vs0 * factor, rel=2e-3)
    # The quote band itself is re-expressed in the weighted clock (drops too).
    assert pen["quotes"][mid_i]["mid"] == pytest.approx(q0 * factor, rel=2e-3)
    # T (the maturity axis) stays calendar.
    assert pen["T"] == pytest.approx(t)


def test_no_event_byte_identical(client):
    """An empty calendar leaves the fit identical to the calendar pipeline."""
    tk, exp = _node(client)
    a = client.get(f"/smiles/{tk}/{exp}").json()["diagnostics"]["atmVol"]
    client.put(f"/events/{tk}", json={"events": []})
    b = client.get(f"/smiles/{tk}/{exp}").json()["diagnostics"]["atmVol"]
    assert a == b


def test_normalization_keeps_one_year_vol(client):
    tk, exp1y = _node(client, idx=3)  # ~1Y rung
    o = client.get("/settings/options").json()
    o["normalizeEvents"] = True
    client.put("/settings/options", json=o)
    client.put(f"/events/{tk}", json={"events": [{"time": 0.01, "weight": 25.0, "label": "e"}]})
    with_event = client.get(f"/smiles/{tk}/{exp1y}").json()["diagnostics"]["atmVol"]
    client.put(f"/events/{tk}", json={"events": []})
    no_event = client.get(f"/smiles/{tk}/{exp1y}").json()["diagnostics"]["atmVol"]
    assert with_event == pytest.approx(no_event, rel=1e-3)


def test_localvol_iv_drops_with_event(client):
    """Consistency: the Local-Vol (affine) reconstructed smile drops too."""
    tk = client.get("/universe").json()["tickers"][0]
    body = {"nXNodes": 5, "nTNodes": 3}
    base = client.post(f"/fit/affine/{tk}", json=body).json()
    sm0 = base["smiles"][1]
    atm0 = next(p.get("vol") for p in sm0["model"] if abs(p["k"]) < 0.05)

    client.put(f"/events/{tk}", json={"events": [{"time": 0.005, "weight": 30.0, "label": "e"}]})
    pen = client.post(f"/fit/affine/{tk}", json=body).json()
    sm1 = next(s for s in pen["smiles"] if s["expiry"] == sm0["expiry"])
    atm1 = next(p.get("vol") for p in sm1["model"] if abs(p["k"]) < 0.05)
    assert atm1 < atm0

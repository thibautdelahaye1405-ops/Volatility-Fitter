"""HTTP API tests: universe, smiles, priors, surface fit, WebSocket stream.

Everything runs in-process over fastapi.testclient against
create_app(reference_date=2026-06-10) — no network, no server. The client
is module-scoped so AppState's fit cache keeps the suite fast.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
N_MODEL_POINTS = 161


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def universe(client):
    response = client.get("/universe")
    assert response.status_code == 200
    return response.json()


def expiry_of(universe, ticker: str, index: int) -> str:
    return universe["expiries"][ticker][index]["expiry"]


# -- universe ----------------------------------------------------------------


def test_universe_shape(universe):
    assert universe["asOf"] == "2026-06-10"
    assert universe["tickers"] == ["ALPHA", "BETA", "GAMMA"]
    for ticker in universe["tickers"]:
        ladder = universe["expiries"][ticker]
        assert len(ladder) == 4  # ~1M, 3M, 6M, 1Y
        ts = [e["t"] for e in ladder]
        assert ts == sorted(ts)
        # ACT/365 year fractions of the synthetic 30/91/182/365-day ladder.
        np.testing.assert_allclose(ts, np.array([30, 91, 182, 365]) / 365.0, atol=1e-12)
        assert [e["expiry"] for e in ladder] == sorted(e["expiry"] for e in ladder)


# -- smile payload -----------------------------------------------------------


def test_smile_payload_sanity(client, universe):
    expiry = expiry_of(universe, "ALPHA", 2)  # 6M
    data = client.get(f"/smiles/ALPHA/{expiry}").json()

    assert data["ticker"] == "ALPHA"
    assert data["expiry"] == expiry
    assert data["T"] == pytest.approx(182 / 365.0)
    assert data["forward"] > 0

    model = data["model"]
    assert len(model) == N_MODEL_POINTS
    vols = np.array([p["vol"] for p in model])
    ks = np.array([p["k"] for p in model])
    assert np.all(np.isfinite(vols)) and np.all((vols > 0.05) & (vols < 0.6))
    assert data["kMin"] == model[0]["k"] and data["kMax"] == model[-1]["k"]

    quotes = data["quotes"]
    assert len(quotes) >= 10
    for q in quotes:
        assert q["bid"] <= q["mid"] <= q["ask"]
        assert data["kMin"] < q["k"] < data["kMax"]

    # Model curve tracks the quoted mids (vega-weighted fit, so wings looser).
    quote_k = np.array([q["k"] for q in quotes])
    quote_iv = np.array([q["mid"] for q in quotes])
    model_at_quotes = np.interp(quote_k, ks, vols)
    assert float(np.median(np.abs(model_at_quotes - quote_iv))) < 1e-3

    # ATM vol diagnostic agrees with the quote-implied ATM level.
    atm_quote = float(np.interp(0.0, quote_k, quote_iv))
    diag = data["diagnostics"]
    assert diag["atmVol"] == pytest.approx(atm_quote, abs=1e-3)
    assert 0.19 < diag["atmVol"] < 0.24
    assert diag["skew"] < 0  # equity-like synthetic smile
    assert 0 < diag["aRight"] < 1  # integrability bound A_R < 1
    assert diag["varSwapVol"] > diag["atmVol"] > 0  # skew makes var-swap rich


def test_rms_error_reported_and_weighting_aware(client, universe):
    """Each fit reports its weighted RMS vol error; equal weighting equals the
    plain RMS of (model - mid) over the live quotes, and switching to the
    TV-density scheme changes it."""
    expiry = expiry_of(universe, "ALPHA", 2)
    data = client.get(f"/smiles/ALPHA/{expiry}").json()
    rms = data["diagnostics"]["rmsError"]
    assert 0.0 <= rms < 0.05  # a sane fit is well under 5 vol points

    # Under equal weighting it is the plain RMS vs mid of the live quotes.
    ks = np.array([p["k"] for p in data["model"]])
    vols = np.array([p["vol"] for p in data["model"]])
    res = [
        float(np.interp(q["k"], ks, vols)) - q["mid"]
        for q in data["quotes"]
        if not q["excluded"]
    ]
    assert rms == pytest.approx(float(np.sqrt(np.mean(np.square(res)))), abs=2e-4)

    try:
        client.put("/settings/fit", json={"weightScheme": "tv_density"})
        rms_tv = client.get(f"/smiles/ALPHA/{expiry}").json()["diagnostics"]["rmsError"]
        assert rms_tv != pytest.approx(rms, abs=1e-9)
    finally:
        client.put("/settings/fit", json={"weightScheme": "equal"})


def test_all_fit_modes_return_smiles(client, universe):
    expiry = expiry_of(universe, "ALPHA", 1)
    for mode in ("mid", "bidask", "haircut"):
        response = client.get(f"/smiles/ALPHA/{expiry}", params={"fit_mode": mode})
        assert response.status_code == 200
        assert len(response.json()["model"]) == N_MODEL_POINTS


def test_unknown_nodes_are_404(client, universe):
    expiry = expiry_of(universe, "ALPHA", 0)
    assert client.get(f"/smiles/NOPE/{expiry}").status_code == 404
    assert client.get("/smiles/ALPHA/2030-01-01").status_code == 404
    assert client.get("/smiles/ALPHA/not-a-date").status_code == 404
    assert client.post(f"/smiles/NOPE/{expiry}/prior").status_code == 404


# -- prior save --------------------------------------------------------------


def test_prior_save_round_trip(client, universe):
    expiry = expiry_of(universe, "GAMMA", 1)

    # Before any save the prior defaults to a copy of the current model.
    first = client.get(f"/smiles/GAMMA/{expiry}").json()
    assert first["prior"] == first["model"]

    assert client.post(f"/smiles/GAMMA/{expiry}/prior").json() == {"saved": True}

    # The saved prior (mid fit) is now served verbatim with *any* fit mode.
    later = client.get(f"/smiles/GAMMA/{expiry}", params={"fit_mode": "bidask"}).json()
    assert later["prior"] == first["model"]


# -- surface fit -------------------------------------------------------------


def test_surface_fit_is_calendar_clean(client, universe):
    response = client.post("/fit/surface", json={"ticker": "ALPHA"})
    assert response.status_code == 200
    data = response.json()

    assert data["ticker"] == "ALPHA"
    expected = [e["expiry"] for e in universe["expiries"]["ALPHA"]]
    assert data["expiries"] == expected

    residuals = data["calendarResiduals"]
    assert len(residuals) == 4 and residuals[0] == 0.0
    assert all(r <= 1e-6 + 5e-6 for r in residuals)  # soft-slack tolerance

    assert len(data["maxIvErrorBp"]) == 4
    assert all(0 <= bp < 100 for bp in data["maxIvErrorBp"])

    smiles = data["smiles"]
    assert [s["expiry"] for s in smiles] == expected
    assert all(len(s["model"]) == N_MODEL_POINTS for s in smiles)

    # The per-expiry results are cached: GET now serves the surface fit.
    cached = client.get(f"/smiles/ALPHA/{expected[2]}").json()
    assert cached == smiles[2]


def test_surface_fit_unknown_ticker_404(client):
    assert client.post("/fit/surface", json={"ticker": "NOPE"}).status_code == 404


# -- websocket streaming -----------------------------------------------------


def test_ws_surface_fit_streams_progress_then_done(client, universe):
    with client.websocket_connect("/ws/fit/surface") as ws:
        ws.send_json({"ticker": "BETA", "fitMode": "mid", "enforceCalendar": True})
        events = []
        while True:
            message = ws.receive_json()
            events.append(message)
            if message["type"] == "done":
                break

    progress = [e for e in events if e["type"] == "progress"]
    assert len(progress) == 4
    assert [p["index"] for p in progress] == [0, 1, 2, 3]
    assert all(p["total"] == 4 for p in progress)
    assert [p["expiry"] for p in progress] == [
        e["expiry"] for e in universe["expiries"]["BETA"]
    ]
    assert all(0 <= p["maxIvErrorBp"] < 100 for p in progress)

    result = events[-1]["result"]  # same shape as POST /fit/surface
    assert result["ticker"] == "BETA"
    assert len(result["smiles"]) == 4
    assert len(result["calendarResiduals"]) == 4
    assert all(r <= 1e-6 + 5e-6 for r in result["calendarResiduals"])

"""API tests: discrete-dividend ex-date markers on the term structure.

POST /term/{ticker} surfaces the ticker's discrete dividend ex-dates (within
the curve range) as markers once the dividend mode uses the discrete schedule,
so the Term view can draw them on either clock. Continuous mode emits none.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _ticker_and_last_expiry(client):
    u = client.get("/universe").json()
    ticker = u["tickers"][0]
    expiries = [e["expiry"] for e in u["expiries"][ticker]]
    return ticker, expiries[-1]


def _set_dividends(client, ticker, mode, dividends):
    body = {
        "rate": 0.04,
        "dividendMode": mode,
        "dividendYield": 0.0,
        "dividends": dividends,
        "switchYears": 1.0,
    }
    assert client.put(f"/settings/market/{ticker}", json=body).status_code == 200


def test_discrete_dividends_emit_markers(client):
    ticker, last = _ticker_and_last_expiry(client)
    ex = (REF_DATE + timedelta(days=30)).isoformat()  # ~0.08y, inside the range
    far = (date.fromisoformat(last) + timedelta(days=400)).isoformat()  # out of range
    _set_dividends(
        client,
        ticker,
        "discrete_absolute",
        [{"exDate": ex, "amount": 0.5}, {"exDate": far, "amount": 0.5}],
    )
    data = client.post(f"/term/{ticker}", json={"fitMode": "mid"}).json()
    markers = data["dividends"]
    assert len(markers) == 1  # the far ex-date is past the curve range
    m = markers[0]
    assert m["exDate"] == ex
    assert m["t"] == pytest.approx(30 / 365, abs=1e-6)
    assert m["tau"] == pytest.approx(m["t"], abs=1e-9)  # no events -> tau == t
    assert m["amount"] == 0.5


def test_continuous_mode_emits_no_markers(client):
    ticker, _ = _ticker_and_last_expiry(client)
    ex = (REF_DATE + timedelta(days=30)).isoformat()
    _set_dividends(client, ticker, "continuous", [{"exDate": ex, "amount": 0.5}])
    data = client.post(f"/term/{ticker}", json={"fitMode": "mid"}).json()
    assert data["dividends"] == []


def test_markers_follow_event_dilated_clock(client):
    """An event before the ex-date shifts its dilated tau past its real t."""
    ticker, _ = _ticker_and_last_expiry(client)
    ex = (REF_DATE + timedelta(days=60)).isoformat()  # ~0.164y
    _set_dividends(client, ticker, "discrete_absolute", [{"exDate": ex, "amount": 0.5}])
    body = {
        "fitMode": "mid",
        "events": [{"time": 0.05, "weight": 0.1, "label": "E"}],
        "eventsEnabled": True,
    }
    m = client.post(f"/term/{ticker}", json=body).json()["dividends"][0]
    assert m["tau"] == pytest.approx(m["t"] + 0.1, abs=1e-9)  # event weight added

"""API tests for GET /massive/iv/{ticker} (the read-only Massive IV overlay).

The app is built around a MassiveProvider with an injected ``http_get``, so no
network is touched. A second app on the default synthetic provider checks the
404 gate (the overlay is Massive-only).
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.data.massive import MassiveProvider

REF = date(2026, 6, 13)


def _exp(days: int) -> str:
    return date.fromordinal(REF.toordinal() + days).isoformat()


def _snap_result(strike, days, cp):
    return {
        "details": {
            "contract_type": cp,
            "exercise_style": "american",
            "expiration_date": _exp(days),
            "strike_price": strike,
        },
        "day": {"close": 12.5, "volume": 66},
        "greeks": {"delta": 0.5, "gamma": 0.01, "theta": -0.2, "vega": 0.1},
        "implied_volatility": 0.1834,
        "open_interest": 8,
    }


def _massive_app():
    pages = {
        "OK": {
            "results": [_snap_result(500, 30, "call"), _snap_result(520, 30, "put")],
            "status": "OK",
        }
    }

    def http_get(url, params):
        return pages["OK"]

    provider = MassiveProvider(["SPY"], api_key="k", http_get=http_get)
    return create_app(reference_date=REF, provider=provider)


def test_massive_iv_endpoint():
    client = TestClient(_massive_app())
    resp = client.get("/massive/iv/SPY", params={"expiry": _exp(30)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "SPY"
    assert len(body["points"]) == 2
    point = body["points"][0]
    assert point["iv"] == 0.1834
    assert point["callPut"] in ("C", "P") and point["delta"] == 0.5


def test_massive_iv_unknown_ticker_404():
    client = TestClient(_massive_app())
    assert client.get("/massive/iv/NOPE").status_code == 404


def test_massive_iv_requires_massive_provider():
    client = TestClient(create_app(reference_date=REF))  # synthetic default
    assert client.get("/massive/iv/ALPHA").status_code == 404

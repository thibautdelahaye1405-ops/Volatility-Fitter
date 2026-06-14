"""Per-ticker event-calendar endpoints (shared event-time dilation input).

Invariants:
1. GET returns an empty calendar for a ticker that never set one.
2. A PUT round-trips and is scoped per ticker.
3. Bad event specs (time <= 0, weight < 0) are 422s.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_events_default_empty(client):
    assert client.get("/events/ALPHA").json() == {"events": []}


def test_events_round_trip_per_ticker(client):
    body = {"events": [{"time": 0.25, "weight": 0.02, "label": "earnings"}]}
    assert client.put("/events/ALPHA", json=body).status_code == 200
    assert client.get("/events/ALPHA").json() == body
    # Scoped per ticker: a sibling is unaffected.
    assert client.get("/events/BETA").json() == {"events": []}


def test_events_validation(client):
    bad_time = {"events": [{"time": 0.0, "weight": 0.02, "label": "x"}]}
    bad_weight = {"events": [{"time": 0.25, "weight": -1.0, "label": "x"}]}
    assert client.put("/events/ALPHA", json=bad_time).status_code == 422
    assert client.put("/events/ALPHA", json=bad_weight).status_code == 422


def test_shared_events_dilate_both_term_views(client):
    """The same shared calendar dilates the Parametric term AND the Local-Vol
    (affine) term identically — event-time dilation is consistent across both."""
    client.put("/events/ALPHA", json={"events": [{"time": 0.04, "weight": 0.1, "label": "e"}]})

    # Parametric term: an expiry past the event has dilated tau > real t.
    pts = client.post("/term/ALPHA", json={}).json()["points"]
    assert any(p["tau"] > p["t"] + 1e-9 for p in pts)

    # Local-Vol term reads the same calendar (no events in the request body).
    lv = client.post("/fit/affine/ALPHA/term", json={"nXNodes": 5, "nTNodes": 3}).json()
    assert any(p["tau"] > p["t"] + 1e-9 for p in lv["points"])

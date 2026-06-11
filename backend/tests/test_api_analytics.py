"""Phase 6 analytics endpoints: term structure, density/quantile, priors.

Same in-process style as test_api.py: a module-scoped TestClient against
create_app(reference_date=2026-06-10), so the app-wide fit cache keeps the
suite fast. Term tests use ALPHA; density/prior tests use BETA (the quote
amend there must not disturb the term-structure fits) and the PriorRecord
round-trip guard uses GAMMA.
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
    response = client.get("/universe")
    assert response.status_code == 200
    return response.json()


def expiry_of(universe, ticker: str, index: int) -> str:
    return universe["expiries"][ticker][index]["expiry"]


# -- term structure ------------------------------------------------------------


def test_term_structure_no_events(client):
    response = client.post("/term/ALPHA", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "ALPHA"

    points = data["points"]
    assert len(points) == 4
    ts = [p["t"] for p in points]
    assert ts == sorted(ts)
    assert [p["tau"] for p in points] == ts  # no events: identity clock

    # Synthetic surface is calendar-clean: w0 strictly increasing in t.
    w0s = [p["w0"] for p in points]
    assert all(far > near for near, far in zip(w0s, w0s[1:]))
    assert data["calendarViolations"] == 0

    curve = data["curve"]
    assert all(len(curve[key]) == 80 for key in ("t", "tau", "w", "vol"))
    vol = np.array(curve["vol"])
    assert np.all(np.isfinite(vol)) and np.all((vol > 0.1) & (vol < 0.4))

    # Same fit cache as GET /smiles -> exactly equal ATM vols.
    for p in points:
        diag = client.get(f"/smiles/ALPHA/{p['expiry']}").json()["diagnostics"]
        assert p["atmVol"] == diag["atmVol"]


def test_term_structure_event_dilation(client):
    event = {"time": 0.3, "weight": 0.05, "label": "earnings"}
    data = client.post("/term/ALPHA", json={"events": [event]}).json()

    # tau jumps by the event weight at and after the event date only.
    for p in data["points"]:
        expected = p["t"] + (0.05 if p["t"] >= 0.3 else 0.0)
        assert p["tau"] == pytest.approx(expected, abs=1e-12)

    # The dense curve stays a nondecreasing total variance through the jump.
    w = np.array(data["curve"]["w"])
    assert np.all(np.diff(w) >= -1e-12)

    # Disabled clock: identity again even with events supplied.
    off = client.post("/term/ALPHA", json={"events": [event], "eventsEnabled": False}).json()
    assert all(p["tau"] == p["t"] for p in off["points"])


def test_term_structure_validation(client):
    bad = client.post("/term/ALPHA", json={"events": [{"time": 0.3, "weight": -0.1}]})
    assert bad.status_code == 422
    assert client.post("/term/NOPE", json={}).status_code == 404


# -- density / quantile --------------------------------------------------------


def test_density_before_any_prior(client, universe):
    expiry = expiry_of(universe, "BETA", 1)
    data = client.get(f"/smiles/BETA/{expiry}/density").json()
    assert data["prior"] is None

    cur = data["current"]
    x, density = np.array(cur["x"]), np.array(cur["density"])
    u, quantile = np.array(cur["u"]), np.array(cur["quantile"])
    assert len(x) == len(density) == len(u) == len(quantile) <= 241
    assert np.all(density >= 0)
    # Central-mass trimming (u in [1e-3, 1-1e-3]) loses ~0.2% of probability.
    assert abs(float(np.trapezoid(density, x)) - 1.0) < 0.02
    assert np.all(np.diff(quantile) > 0)
    assert np.all((u > 0) & (u < 1))


def test_density_prior_save_then_diverge(client, universe):
    expiry = expiry_of(universe, "BETA", 1)
    assert client.post(f"/smiles/BETA/{expiry}/prior").json() == {"saved": True}

    data = client.get(f"/smiles/BETA/{expiry}/density").json()
    prior, current = data["prior"], data["current"]
    assert prior is not None
    keys = ("x", "density", "u", "quantile")
    assert all(len(prior[key]) == len(current[key]) for key in keys)
    # Prior rebuilt from its saved LQDParams == the still-current fit.
    assert prior["density"] == current["density"]

    # Amend the nearest-ATM quote up 2 vol points: the refit's density must
    # now differ from the frozen prior by a meaningful margin.
    smile = client.get(f"/smiles/BETA/{expiry}").json()
    atm = min(smile["quotes"], key=lambda q: abs(q["k"]))
    edit = {"action": "amend", "index": atm["index"], "mid": atm["mid"] + 0.02}
    assert client.post(f"/smiles/BETA/{expiry}/edits", json=edit).status_code == 200

    after = client.get(f"/smiles/BETA/{expiry}/density").json()
    diff = np.abs(np.array(after["current"]["density"]) - np.array(after["prior"]["density"]))
    assert float(diff.max()) > 1e-3


# -- prior record refactor guard ------------------------------------------------


def test_prior_round_trip_in_smile_payload_unchanged(client, universe):
    expiry = expiry_of(universe, "GAMMA", 2)
    base = client.get(f"/smiles/GAMMA/{expiry}").json()
    assert base["prior"] == base["model"]  # unsaved: prior defaults to fit

    assert client.post(f"/smiles/GAMMA/{expiry}/prior").json() == {"saved": True}

    # The saved curve (mid fit) is served verbatim under any fit mode.
    later = client.get(f"/smiles/GAMMA/{expiry}", params={"fit_mode": "bidask"}).json()
    assert later["prior"] == base["model"]

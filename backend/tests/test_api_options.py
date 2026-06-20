"""API + state tests for the global Options settings (ROADMAP Phase 10).

Invariants:
1. GET /settings/options returns the documented defaults.
2. A PUT round-trips and validation bounds are 422s.
3. Only the calibration-affecting field (calendarWeight) bumps the options
   version (so warm fit caches survive pure-UI toggles), and it is folded into
   the fit-cache key so a changed weight refits.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.schemas import OptionsSettings
from volfit.api.service import fit_key
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    # Function-scoped: options are app-global state, keep tests independent.
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_defaults(client):
    settings = client.get("/settings/options").json()
    assert settings == {
        "fitMode": "mid",
        "enforceCalendar": True,
        "eventsEnabled": True,
        "normalizeEvents": False,
        "varSwapEnabled": True,
        "varSwapWeightPct": 10.0,
        "varSwapMethod": "static",
        "autoLoadPrior": False,
        "priorAnchorWeightPct": 50.0,
        "priorAnchorDeltas": [0.02, 0.05, 0.10, 0.25, 0.40],
        "gridStrikeMode": "delta",
        "gridXNodes": 12,
        "gridTNodes": 10,
        "gridRegLambda": 1e-2,
        "gridRegRho": 1.0,
        "convexWing": False,
        "convexWingWeight": 1e3,
        "frontTie": True,
        "frontTieWeight": 1e-2,
        "lvVolCapMult": 3.0,
        "timeScheme": "implicit",
        "leftWingSlopeMult": 1.5,
        "calendarWeight": 1e6,
        "graphKappaScale": 1.0,
        "graphEtaScale": 1.0,
        "graphLambdaScale": 0.0,
        "graphNu": 0.1,
        "dynamicsRegime": "sticky_strike",
        "ssr": 2.0,
        "autoCalibrate": True,
        "localVolEnabled": True,
        "spotMode": "static",
        "spotPollSeconds": 5.0,
        "optionsFetchMode": "on_demand",
        "optionsFetchMinutes": 5.0,
        "streamRefitSeconds": 5.0,
    }


def test_put_round_trip(client):
    body = {
        "fitMode": "haircut",
        "enforceCalendar": False,
        "eventsEnabled": False,
        "normalizeEvents": True,
        "varSwapEnabled": False,
        "varSwapWeightPct": 25.0,
        "varSwapMethod": "source_pde",
        "autoLoadPrior": True,
        "priorAnchorWeightPct": 25.0,
        "priorAnchorDeltas": [0.05, 0.1, 0.25],
        "gridStrikeMode": "linear",
        "gridXNodes": 9,
        "gridTNodes": 5,
        "gridRegLambda": 1.0,
        "gridRegRho": 2.0,
        "convexWing": True,
        "convexWingWeight": 5e2,
        "frontTie": False,
        "frontTieWeight": 5e-2,
        "lvVolCapMult": 4.0,
        "timeScheme": "rannacher",
        "leftWingSlopeMult": 2.0,
        "calendarWeight": 5e5,
        "graphKappaScale": 2.0,
        "graphEtaScale": 1.5,
        "graphLambdaScale": 0.5,
        "graphNu": 0.2,
        "dynamicsRegime": "custom",
        "ssr": 1.5,
        "autoCalibrate": False,
        "localVolEnabled": False,
        "spotMode": "realtime",
        "spotPollSeconds": 10.0,
        "optionsFetchMode": "auto",
        "optionsFetchMinutes": 15.0,
        "streamRefitSeconds": 3.0,
    }
    assert client.put("/settings/options", json=body).status_code == 200
    assert client.get("/settings/options").json() == body


def test_validation_bounds(client):
    for bad in (
        {"gridXNodes": 2},  # strike vertices are in [3, 200]
        {"gridXNodes": 999},
        {"gridTNodes": -1},  # in [0, 120] (0 = auto)
        {"gridRegLambda": -1.0},  # >= 0
        {"calendarWeight": -1.0},  # >= 0
        {"ssr": -0.1},  # >= 0
        {"dynamicsRegime": "sticky_gamma"},  # not a known regime
        {"spotMode": "delayed"},  # only realtime | static
    ):
        assert client.put("/settings/options", json=bad).status_code == 422


def test_only_calendar_weight_bumps_version():
    """Pure-UI toggles must not invalidate warm fit caches; only the calendar
    penalty strength (which changes calibration output) bumps the version."""
    state = AppState(reference_date=REF_DATE)
    v0 = state.options_version

    # A pure-UI change (spot mode + auto-calibrate) leaves the version untouched.
    state.set_options(OptionsSettings(spotMode="realtime", autoCalibrate=False))
    assert state.options_version == v0

    # Changing the calendar penalty weight bumps it (and changes the fit key).
    key_before = fit_key(state, "ALPHA", "2026-07-17", "mid")
    state.set_options(OptionsSettings(calendarWeight=1e5))
    assert state.options_version == v0 + 1
    key_after = fit_key(state, "ALPHA", "2026-07-17", "mid")
    assert key_before != key_after

    # A redundant PUT (same weight) does not bump again.
    state.set_options(OptionsSettings(calendarWeight=1e5))
    assert state.options_version == v0 + 1


def test_calendar_weight_threads_into_surface_fit(client):
    """A surface fit still succeeds under a softened calendar penalty (the
    weight is threaded into the calibration, ROADMAP Phase 10)."""
    assert client.put("/settings/options", json={"calendarWeight": 0.0}).status_code == 200
    resp = client.post("/fit/surface", json={"ticker": "ALPHA", "fitMode": "mid"})
    assert resp.status_code == 200
    assert len(resp.json()["smiles"]) > 0

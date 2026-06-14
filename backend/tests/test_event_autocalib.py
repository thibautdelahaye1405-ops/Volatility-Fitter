"""Auto-calibration of the event calendar from the term structure.

The optimizer places events (extra day-weights) before expiries up to a horizon
so the WEIGHTED forward variance is flatter / more monotone, with small & sparse
events. Real-time forward variance is event-invariant, so the smoothing acts on
the diffusive (event-time) forward variance.
"""

import numpy as np
import pytest
from datetime import date
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.calib.event_autocalib import autocalibrate_events

REF_DATE = date(2026, 6, 10)


def _fwd_var(t, w0):
    prev_t = np.concatenate([[0.0], t[:-1]])
    prev_w = np.concatenate([[0.0], w0[:-1]])
    return (w0 - prev_w) / (t - prev_t)


def _weighted_fwd_var(t, w0, events):
    """Forward variance after applying events (extra days) to the clock."""
    tau = t.copy()
    for i in range(t.size):
        extra = sum(n for te, n in events if te <= t[i])
        tau[i] = t[i] + extra / 365.0
    prev_tau = np.concatenate([[0.0], tau[:-1]])
    prev_w = np.concatenate([[0.0], w0[:-1]])
    return (w0 - prev_w) / (tau - prev_tau)


# ----------------------------------------------------------------- pure solver
def test_spike_is_flattened():
    # Interval 2 carries a 5x variance spike; events should pull it down.
    t = np.array([0.1, 0.2, 0.3, 0.4])
    fv0 = np.array([0.04, 0.20, 0.04, 0.04])  # calendar forward variance
    dw = fv0 * np.diff(np.concatenate([[0.0], t]))
    w0 = np.cumsum(dw)

    events = autocalibrate_events(t, w0, n_events=4)
    assert events, "expected at least one event for a clear spike"
    # An event lands in the spike interval (0.1, 0.2) (midpoint 0.15).
    assert any(0.1 < te <= 0.2 for te, _ in events)

    rough0 = float(np.sum(np.diff(_fwd_var(t, w0)) ** 2))
    rough1 = float(np.sum(np.diff(_weighted_fwd_var(t, w0, events)) ** 2))
    assert rough1 < 0.25 * rough0  # much flatter


def test_flat_input_stays_eventless():
    t = np.array([0.1, 0.2, 0.3, 0.4])
    w0 = 0.04 * t  # constant forward variance already
    assert autocalibrate_events(t, w0, n_events=4) == []


def test_horizon_limits_events():
    t = np.array([0.1, 0.2, 0.3, 0.4])
    fv0 = np.array([0.04, 0.20, 0.20, 0.20])
    w0 = np.cumsum(fv0 * np.diff(np.concatenate([[0.0], t])))
    events = autocalibrate_events(t, w0, n_events=2)  # only first 2 expiries
    assert all(te <= 0.2 + 1e-9 for te, _ in events)


# ------------------------------------------------------------------- API route
@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_autocalibrate_endpoint_sets_calendar(client):
    uni = client.get("/universe").json()
    tk = uni["tickers"][0]
    expiries = [e["expiry"] for e in uni["expiries"][tk]]
    horizon = expiries[-2]

    res = client.post(f"/events/{tk}/autocalibrate", json={"maxExpiry": horizon})
    assert res.status_code == 200
    events = res.json()["events"]
    # No event is placed beyond the horizon.
    t_h = next(e["t"] for e in uni["expiries"][tk] if e["expiry"] == horizon)
    assert all(ev["time"] <= t_h + 1e-9 for ev in events)
    # It is installed as the shared calendar (GET returns the same).
    assert client.get(f"/events/{tk}").json()["events"] == events

    assert client.post("/events/NOPE/autocalibrate", json={"maxExpiry": horizon}).status_code == 404

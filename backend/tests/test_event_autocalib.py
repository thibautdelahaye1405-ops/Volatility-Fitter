"""Auto-calibration of the event calendar from the term structure.

The solver is a DETECTOR: an interval whose forward variance per day-weight
runs hotter than both neighbours carries an event, sized exactly by its excess
over the higher neighbour. Shapes an event cannot produce — a contango ramp, a
smooth backwardation, an isolated dip — yield no events; a planted event is
recovered exactly at any vol level; the ladder's last interval is the tail
reference and never carries one; an intraday day base removes the weekend
artefact of calendar days.
"""

import numpy as np
import pytest
from datetime import date
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.calib.event_autocalib import autocalibrate_events
from volfit.calib.weighted_time import weighted_variance_years

REF_DATE = date(2026, 6, 10)
DPY = 365.0


def _w0_from_fwd(t, fv):
    """ATM total variances whose calendar forward variances are ``fv``."""
    return np.cumsum(np.asarray(fv) * np.diff(np.concatenate([[0.0], t])))


def _fwd_var(t, w0):
    prev_t = np.concatenate([[0.0], t[:-1]])
    prev_w = np.concatenate([[0.0], w0[:-1]])
    return (w0 - prev_w) / (t - prev_t)


def _weighted_fwd_var(t, w0, events):
    """Forward variance after applying events (extra days) to the clock."""
    tau = np.array([weighted_variance_years(float(x), events) for x in t])
    prev_tau = np.concatenate([[0.0], tau[:-1]])
    prev_w = np.concatenate([[0.0], w0[:-1]])
    return (w0 - prev_w) / (tau - prev_tau)


# ----------------------------------------------------------------- pure solver
def test_spike_is_flattened():
    # Interval 2 carries a 5x variance spike; one event pulls it down to its
    # higher neighbour and nothing else moves.
    t = np.array([0.1, 0.2, 0.3, 0.4])
    fv0 = np.array([0.04, 0.20, 0.04, 0.04])
    w0 = _w0_from_fwd(t, fv0)

    events = autocalibrate_events(t, w0, n_events=4)
    assert len(events) == 1
    te, days = events[0]
    assert te == pytest.approx(0.15)  # midpoint of the spike interval
    assert days == pytest.approx(0.1 * DPY * (0.20 / 0.04 - 1.0))  # exact excess

    rough0 = float(np.sum(np.diff(_fwd_var(t, w0)) ** 2))
    rough1 = float(np.sum(np.diff(_weighted_fwd_var(t, w0, events)) ** 2))
    assert rough1 < 1e-6 * rough0  # the ladder is flat once the peak is clipped


def test_flat_input_stays_eventless():
    t = np.array([0.1, 0.2, 0.3, 0.4])
    w0 = 0.04 * t  # constant forward variance already
    assert autocalibrate_events(t, w0, n_events=4) == []


def test_horizon_limits_events():
    # Two equal spikes; only the one at or before the horizon is a candidate.
    t = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    fv0 = np.array([0.04, 0.20, 0.04, 0.20, 0.04])
    w0 = _w0_from_fwd(t, fv0)
    events = autocalibrate_events(t, w0, n_events=2)  # first 2 expiries only
    assert [round(te, 6) for te, _ in events] == [0.15]
    assert len(autocalibrate_events(t, w0, n_events=5)) == 2


def test_contango_ramp_yields_no_events():
    # A monotone rising ladder (index contango) has no peak to attribute.
    t = np.array([2, 7, 14, 30, 60, 91, 182, 365]) / DPY
    vol = np.array([0.14, 0.145, 0.15, 0.155, 0.16, 0.165, 0.175, 0.185])
    assert autocalibrate_events(t, vol**2 * t, n_events=t.size) == []


def test_smooth_backwardation_yields_no_events():
    # A mean-reverting vol-spike front: forward variance decays smoothly from
    # the first interval on. Not a scheduled event — the front's reference is
    # the back ladder's log-slope continued one step.
    t = np.arange(1, 9) * 7.0 / DPY
    mids = t - 3.5 / DPY
    fv0 = 0.04 + 0.12 * np.exp(-12.0 * mids)
    w0 = _w0_from_fwd(t, fv0)
    assert autocalibrate_events(t, w0, n_events=t.size) == []


def test_front_event_is_detected():
    # Earnings before the FIRST listed expiry: the front interval runs 3x hot
    # against a gently backwardated back ladder.
    t = np.array([7, 14, 21, 28, 60]) / DPY
    fv0 = np.array([0.25, 0.080, 0.075, 0.072, 0.070])
    w0 = _w0_from_fwd(t, fv0)
    events = autocalibrate_events(t, w0, n_events=t.size)
    assert len(events) == 1 and events[0][0] == pytest.approx(3.5 / DPY)
    # Sized against the neighbour continued by the back's log-slope: well
    # above 10 extra days on a 7-day interval, and never the raw 0.25 / 0.08.
    assert 10.0 < events[0][1] < 7.0 * (0.25 / 0.080 - 1.0)


def test_dip_is_not_an_event():
    # An isolated LOW interval: its neighbours are not peaks (each has an
    # equal neighbour on the other side), so nothing is attributed.
    t = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    fv0 = np.array([0.08, 0.08, 0.06, 0.08, 0.08])
    assert autocalibrate_events(t, _w0_from_fwd(t, fv0), n_events=5) == []


def test_last_interval_is_the_tail_reference():
    # A rising tail (the last interval hotter than everything) is contango,
    # not an event — whatever the horizon.
    t = np.array([0.1, 0.2, 0.3, 0.4])
    fv0 = np.array([0.04, 0.04, 0.04, 0.10])
    assert autocalibrate_events(t, _w0_from_fwd(t, fv0), n_events=4) == []


@pytest.mark.parametrize("sigma", [0.20, 0.40])
@pytest.mark.parametrize("planted", [2.0, 3.0, 5.0, 8.0])
def test_planted_event_is_recovered_exactly(sigma, planted):
    # Flat clock vol with one planted event inside (0.10, 0.20]: the solver
    # returns the planted days to round-off, independent of the vol level.
    t_nodes = np.array([0.10, 0.20, 0.35, 0.60])
    tau = np.array([weighted_variance_years(float(x), [(0.15, planted)]) for x in t_nodes])
    events = autocalibrate_events(t_nodes, sigma**2 * tau, n_events=3)
    assert len(events) == 1
    assert events[0][0] == pytest.approx(0.15)
    assert events[0][1] == pytest.approx(planted, abs=1e-9)


def test_materiality_floor_drops_fit_noise():
    # A 1% wiggle on a 91-day interval is 0.9 days — over the half-day floor
    # but under the 3% relative floor: not an event.
    t = np.array([30, 121, 212, 303]) / DPY
    fv0 = np.array([0.04, 0.0404, 0.04, 0.04])
    assert autocalibrate_events(t, _w0_from_fwd(t, fv0), n_events=4) == []
    # The same excess on a ladder where it clears both floors is attributed.
    fv1 = np.array([0.04, 0.044, 0.04, 0.04])
    events = autocalibrate_events(t, _w0_from_fwd(t, fv1), n_events=4)
    assert len(events) == 1 and events[0][1] == pytest.approx(91.0 * 0.1)


def test_intraday_base_days_remove_the_weekend_artefact():
    # Flat variance per TRADING day over a Friday snapshot: the first interval
    # spans a weekend (3 calendar days, 1 trading day), the second two trading
    # days, the third a month. Per calendar day the second interval looks like
    # a peak; per trading day the ladder is flat.
    t = np.array([3.0, 5.0, 35.0]) / DPY
    trading = np.array([1.0, 3.0, 25.0])
    w0 = 1e-3 * trading  # flat variance per trading day
    calendar = autocalibrate_events(t, w0, n_events=3)
    assert len(calendar) == 1 and 3.0 / DPY < calendar[0][0] <= 5.0 / DPY
    assert autocalibrate_events(t, w0, n_events=3, base_days=trading) == []


def test_degenerate_ladders_are_safe():
    t = np.array([0.1, 0.2, 0.3])
    assert autocalibrate_events(t[:1], np.array([0.004]), n_events=1) == []
    assert autocalibrate_events(t, np.zeros(3), n_events=3) == []  # no variance
    # A calendar violation (falling total variance) is never clipped or used
    # as a reference below zero.
    w0 = np.array([0.004, 0.003, 0.005])
    assert autocalibrate_events(t, w0, n_events=3) == []


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
    assert all(ev["label"] == "auto" and ev["weight"] >= 0.5 for ev in events)
    # It is installed as the shared calendar (GET returns the same).
    assert client.get(f"/events/{tk}").json()["events"] == events

    assert client.post("/events/NOPE/autocalibrate", json={"maxExpiry": horizon}).status_code == 404

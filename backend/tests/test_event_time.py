"""Event-dilated clock: dilation mechanics and term-structure interpolation."""

import numpy as np
import pytest

from volfit.calib import Event, EventClock


def test_identity_without_events():
    clock = EventClock()
    assert clock.dilated_time(0.37) == 0.37
    disabled = EventClock(events=(Event(time=0.1, weight=0.05),), enabled=False)
    assert disabled.dilated_time(0.37) == 0.37


def test_dilation_jumps_at_event():
    clock = EventClock(events=(Event(time=0.25, weight=0.01, label="earnings"),))
    assert clock.dilated_time(0.20) == pytest.approx(0.20)
    assert clock.dilated_time(0.25) == pytest.approx(0.26)  # inclusive at the event
    assert clock.dilated_time(0.30) == pytest.approx(0.31)


def test_interpolation_lumps_event_variance():
    """ATM variance generated as flat-vol-in-dilated-time must be recovered
    exactly by dilated interpolation; calendar-time interpolation smears it."""
    clock = EventClock(events=(Event(time=0.25, weight=0.02),))
    rate = 0.04  # variance per dilated year (20% vol)
    expiries = np.array([0.2, 0.3])
    w_nodes = rate * np.asarray(clock.dilated_time(expiries))

    t_q = 0.26  # just after the event
    w_dilated = clock.interpolate_total_variance(t_q, expiries, w_nodes)
    assert w_dilated == pytest.approx(rate * (t_q + 0.02), abs=1e-14)

    w_calendar = EventClock().interpolate_total_variance(t_q, expiries, w_nodes)
    assert abs(w_calendar - w_dilated) > 1e-4  # the smearing the clock removes


def test_rate_preserving_extrapolation():
    clock = EventClock(events=(Event(time=0.25, weight=0.02),))
    rate = 0.04
    expiries = np.array([0.2, 0.3])
    w_nodes = rate * np.asarray(clock.dilated_time(expiries))
    # Short end: same variance rate in dilated time.
    assert clock.interpolate_total_variance(0.1, expiries, w_nodes) == pytest.approx(
        rate * 0.1, abs=1e-14
    )
    # Long end: forward rate of the last segment continues.
    assert clock.interpolate_total_variance(0.5, expiries, w_nodes) == pytest.approx(
        rate * (0.5 + 0.02), abs=1e-12
    )

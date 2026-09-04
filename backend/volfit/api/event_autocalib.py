"""Service for auto-calibrating a ticker's event calendar (Term workspace).

Gathers the ATM term structure from the cached slice fits (the calendar ATM
total variance w0_i = the LQD slice's implied_w(0), which is price-derived and
so event-invariant), counts the CALIBRATED expiries at or before the chosen
horizon, reads the peaks of the forward-variance ladder as events
(volfit.calib.event_autocalib), and installs them as the shared per-ticker
calendar (which bumps the events version, so every fit refits in the new
variance clock).

The ladder is measured per DAY-WEIGHT of the same clock the fits accrue tau
from (volfit.api.service.node_clock): plain calendar days by default, the
session-profile day base when the intraday clock is on — so a weekend does
not read as a hot Monday-to-Wednesday interval.
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import EventAutocalibrateRequest, EventCalendar, EventSpec
from volfit.api.service import fit_or_get, node_clock
from volfit.api.state import AppState
from volfit.calib.event_autocalib import autocalibrate_events


def autocalibrate(
    state: AppState, ticker: str, request: EventAutocalibrateRequest
) -> EventCalendar:
    """Solve and install the auto-calibrated event calendar for a ticker."""
    horizon = state.resolve_expiry(ticker, request.maxExpiry)  # 404 on a bad node
    forwards = state.forwards(ticker)

    t: list[float] = []
    w0: list[float] = []
    bases: list[float | None] = []
    n_events = 0
    for expiry in sorted(forwards):
        record = fit_or_get(state, ticker, expiry.isoformat(), request.fitMode)
        if record is None:
            continue  # uncalibrated node (gated, pre-Calibrate): no term point
        t.append(record.prepared.t)  # calendar maturity
        # Calendar ATM total variance from the LQD backbone (clock-invariant).
        w0.append(float(record.result.slice.implied_w(0.0)))
        bases.append(node_clock(state, ticker, expiry)[1])  # intraday base or None
        n_events += expiry <= horizon  # horizon counts calibrated expiries only

    # The session-profile day base replaces calendar days only when the intraday
    # clock supplied one for every node (it is all-or-nothing per Options).
    base_days = None if any(b is None for b in bases) else np.asarray(bases, dtype=float)
    solved = autocalibrate_events(t, w0, n_events, base_days=base_days)
    events = [
        EventSpec(time=time, weight=days, label="auto") for time, days in solved
    ]
    state.set_events(ticker, events)
    return EventCalendar(events=events)

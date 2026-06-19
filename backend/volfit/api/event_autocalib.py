"""Service for auto-calibrating a ticker's event calendar (Term workspace).

Gathers the ATM term structure from the cached slice fits (the calendar ATM
total variance w0_i = the LQD slice's implied_w(0), which is price-derived and
so event-invariant), counts the expiries at or before the chosen horizon, solves
for the events that smooth the weighted forward variance (volfit.calib.
event_autocalibrate), and installs them as the shared per-ticker calendar (which
bumps the events version, so every fit refits in the new variance clock).
"""

from __future__ import annotations

from volfit.api.schemas import EventAutocalibrateRequest, EventCalendar, EventSpec
from volfit.api.service import fit_or_get
from volfit.api.state import AppState
from volfit.calib.event_autocalib import autocalibrate_events


def autocalibrate(
    state: AppState, ticker: str, request: EventAutocalibrateRequest
) -> EventCalendar:
    """Solve and install the auto-calibrated event calendar for a ticker."""
    horizon = state.resolve_expiry(ticker, request.maxExpiry)  # 404 on a bad node
    forwards = state.forwards(ticker)
    expiries = sorted(forwards)

    t: list[float] = []
    w0: list[float] = []
    for expiry in expiries:
        record = fit_or_get(state, ticker, expiry.isoformat(), request.fitMode)
        if record is None:
            continue  # uncalibrated node (gated, pre-Calibrate): no term point
        t.append(record.prepared.t)  # calendar maturity
        # Calendar ATM total variance from the LQD backbone (clock-invariant).
        w0.append(float(record.result.slice.implied_w(0.0)))

    n_events = sum(1 for e in expiries if e <= horizon)
    solved = autocalibrate_events(t, w0, n_events)
    events = [
        EventSpec(time=time, weight=days, label="auto") for time, days in solved
    ]
    state.set_events(ticker, events)
    return EventCalendar(events=events)

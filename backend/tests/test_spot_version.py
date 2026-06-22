"""Per-ticker spot version (ROADMAP perf #3C).

A spot move on one ticker must bump ONLY that ticker's derived-grid cache key
(`spot_version_for`), never another ticker's — while still bumping the GLOBAL
`spot_version` (the client refresh signal in the status payload).
"""

from __future__ import annotations

from datetime import date

from volfit.api.state import AppState

REF = date(2026, 6, 20)


def test_spot_move_is_per_ticker_but_signals_globally():
    state = AppState(REF)
    tk = state.active_tickers()[0]
    g0 = state.spot_version
    assert state.spot_version_for(tk) == 0
    assert state.spot_version_for("OTHER") == 0

    state.set_spot_shift(tk, 0.01)
    assert state.spot_version_for(tk) == 1  # this name's derived grid re-transports
    assert state.spot_version_for("OTHER") == 0  # another name's cache is untouched
    assert state.spot_version == g0 + 1  # global client signal still fires

    # Redundant set: no bump anywhere.
    state.set_spot_shift(tk, 0.01)
    assert state.spot_version_for(tk) == 1
    assert state.spot_version == g0 + 1

    # A real change bumps the per-ticker counter again.
    state.set_spot_shift(tk, 0.02)
    assert state.spot_version_for(tk) == 2

    # Re-anchor (recalibrate) clears the shift and bumps the per-ticker counter.
    state.recalibrate(tk)
    assert state.spot_version_for(tk) == 3
    assert state.spot_version_for("OTHER") == 0

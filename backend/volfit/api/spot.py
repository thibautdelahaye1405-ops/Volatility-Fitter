"""Fast spot-move endpoints behind /spot/{ticker} (no-recalibration transport).

A spot move — the user sliding the spot level, or a real-time spot tick — should
refresh the calibrated smile / term-structure / local-vol grid *without* firing a
full recalibration (per Docs/spot_move_vol_surface_note_updated.tex). This module
exposes the per-ticker spot SHIFT that AppState holds and that
volfit.api.service.fit_or_get transports the cached anchor fit by:

  * ``spot_state``  — current shift, anchor spot and the active dynamics regime;
  * ``set_shift``   — apply a hypothetical/live shift (transports every view);
  * ``recalibrate`` — the explicit "Calibrate" action: clear the shift and drop
    the ticker's chain caches so the next fit refetches and recalibrates at the
    live spot (re-anchoring);
  * ``live_spot``   — re-probe the provider's spot for real-time polling
    (spotMode='realtime'); the frontend turns the implied return into a shift.

Everything is a thin pure function over AppState, like the rest of volfit.api.
"""

from __future__ import annotations

from volfit.api.schemas import LiveSpot, SpotShiftRequest, SpotState
from volfit.api.state import AppState
from volfit.dynamics.ssr import ssr_of_regime


def _regime_label(regime: str | float) -> str:
    """Human label for the active regime (named string or custom numeric SSR)."""
    if isinstance(regime, str):
        return regime
    return f"custom {regime:g}"


def spot_state(state: AppState, ticker: str) -> SpotState:
    """Current spot-move state of a ticker (validates the ticker -> 404)."""
    anchor = float(state.snapshot(ticker).spot)  # raises UnknownNodeError if bad
    shift = state.spot_shift(ticker)
    regime = state.dynamics_regime()
    return SpotState(
        ticker=ticker,
        anchorSpot=anchor,
        spotReturn=shift,
        shiftedSpot=anchor * (1.0 + shift),
        regime=_regime_label(regime),
        regimeSsr=float(ssr_of_regime(regime)),
    )


def set_shift(state: AppState, ticker: str, body: SpotShiftRequest) -> SpotState:
    """Apply a hypothetical/live spot shift; the surface transports on next read."""
    state.snapshot(ticker)  # validate the ticker before mutating
    state.set_spot_shift(ticker, body.spotReturn)
    return spot_state(state, ticker)


def recalibrate(state: AppState, ticker: str) -> SpotState:
    """Re-anchor: clear the shift and recalibrate at the live spot (Calibrate)."""
    state.snapshot(ticker)  # validate the ticker before mutating
    state.recalibrate(ticker)
    return spot_state(state, ticker)


def live_spot(state: AppState, ticker: str) -> LiveSpot:
    """Re-probe the provider's spot and report the implied return vs the anchor."""
    anchor = float(state.snapshot(ticker).spot)
    live = float(state.live_spot(ticker))
    ret = (live / anchor - 1.0) if anchor > 0.0 else 0.0
    return LiveSpot(ticker=ticker, anchorSpot=anchor, liveSpot=live, spotReturn=ret)

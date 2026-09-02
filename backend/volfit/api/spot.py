"""Fast spot-move endpoints behind /spot/{ticker} (no-recalibration transport).

A spot move — the user sliding the spot level, or a real-time spot tick — should
refresh the calibrated smile / term-structure / local-vol grid *without* firing a
full recalibration (per Docs/spot_move_vol_surface_note_updated.tex). This module
exposes the per-ticker spot SHIFT that AppState holds and that
volfit.api.service.fit_or_get transports the cached anchor fit by:

  * ``spot_state``  — current shift, the calibration anchor, the prevailing
    market spot (streamed / probed / chain), what the spot FOLLOWS (market vs
    scenario) and the active dynamics regime — the Spot panel's readouts;
  * ``set_shift``   — the dial: a hypothetical shift (switches the ticker to
    the scenario follow mode; transports every view, the tick stream too);
  * ``set_follow``  — the panel selector: follow the market (the shift syncs to
    the prevailing spot) or the scenario (the dial);
  * ``recalibrate`` — the top-bar Calibrate for ONE ticker (same scope, same
    snapshot rule; volfit.api.workflow_ticker) — the frozen fit stays on
    screen until the background job lands;
  * ``live_spot``   — re-probe the provider's spot for real-time polling
    (spotMode='realtime'); the frontend turns the implied return into a shift.

Everything is a thin pure function over AppState, like the rest of volfit.api.
"""

from __future__ import annotations

from volfit.api.schemas import LiveSpot, RecalibrateResult, SpotShiftRequest, SpotState
from volfit.api.state import AppState
from volfit.dynamics.ssr import ssr_of_regime


def _regime_label(regime: str | float) -> str:
    """Human label for the active regime (named string or custom numeric SSR)."""
    if isinstance(regime, str):
        return regime
    return f"custom {regime:g}"


def _source_label(state: AppState) -> str:
    from volfit.api.datasource import SOURCE_LABELS

    sid = state.active_source
    return SOURCE_LABELS.get(sid, sid.title())


def spot_state(state: AppState, ticker: str) -> SpotState:
    """Current spot-move state of a ticker (validates the ticker -> 404).

    ``anchorSpot`` is the CALIBRATION spot (what the shift and the transport are
    relative to), not the latest chain's — after a Fetch without a Calibrate the
    two differ, and the panel shows both. The market readout is the streaming
    book when live, else the newer of the last probe and the fetched chain's
    own spot (``AppState.market_spot``)."""
    from volfit.api.workflow_stages import lit_nodes

    state.snapshot(ticker)  # raises UnknownNodeError if bad
    anchor = float(state.anchor_spot(ticker))
    shift = state.spot_shift(ticker)
    regime = state.dynamics_regime()
    reading = state.market_spot(ticker)
    live = ret = at = src = None
    if reading is not None:
        live, stamp, src = reading
        ret = (live / anchor - 1.0) if anchor > 0.0 else None
        at = stamp.isoformat() if stamp is not None else None
    try:
        n_lit = len(lit_nodes(state, [ticker]))
    except Exception:  # noqa: BLE001 — a ladder mid-refetch never breaks the readout
        n_lit = 0
    return SpotState(
        ticker=ticker,
        anchorSpot=anchor,
        spotReturn=shift,
        shiftedSpot=anchor * (1.0 + shift),
        regime=_regime_label(regime),
        regimeSsr=float(ssr_of_regime(regime)),
        follow=state.spot_follow(ticker),
        followForced=state.options().spotMode == "realtime",
        liveSpot=live,
        liveReturn=ret,
        liveAt=at,
        liveSource=src,
        streaming=bool(state.is_streaming()),
        sourceLabel=_source_label(state),
        litNodes=n_lit,
        lvEnabled=bool(state.options().localVolEnabled),
    )


def set_shift(state: AppState, ticker: str, body: SpotShiftRequest) -> SpotState:
    """The dial: apply a hypothetical shift — the ticker now follows the
    SCENARIO (the whole app, tick stream included, lives at that spot); the
    surface transports on next read."""
    state.snapshot(ticker)  # validate the ticker before mutating
    state.set_spot_follow(ticker, "scenario")
    state.set_spot_shift(ticker, body.spotReturn)
    return spot_state(state, ticker)


def set_follow(state: AppState, ticker: str, follow: str) -> SpotState:
    """The panel selector. "market": the shift syncs to the prevailing market
    spot now (and keeps syncing: the scheduler while a book streams, every
    fetch). "scenario": the dial takes over from wherever the spot is — the
    current shift becomes the scenario's starting point."""
    state.snapshot(ticker)  # validate the ticker before mutating
    state.set_spot_follow(ticker, follow)
    if follow == "market":
        state.sync_market_shift(ticker)
    return spot_state(state, ticker)


def recalibrate(
    state: AppState, ticker: str, fit_mode: str = "mid", scope: str = "both"
) -> RecalibrateResult:
    """The top-bar Calibrate for ONE ticker (the panel's Recalibrate): the same
    snapshot rule and scope, as the background job (volfit.api.workflow_ticker)."""
    from volfit.api import workflow_ticker  # lazy: workflow imports this module

    state.snapshot(ticker)  # validate the ticker before mutating
    outcome = workflow_ticker.recalibrate_ticker(state, ticker, fit_mode, scope)
    base = spot_state(state, ticker)
    return RecalibrateResult(
        **base.model_dump(),
        calibrationStarted=outcome.started,
        busy=outcome.busy,
        snapshotted=outcome.snapshotted,
        scope=scope,
    )


def live_spot(state: AppState, ticker: str) -> LiveSpot:
    """Re-probe the provider's spot and report the implied return vs the anchor."""
    anchor = float(state.anchor_spot(ticker))
    live = float(state.live_spot(ticker))
    ret = (live / anchor - 1.0) if anchor > 0.0 else 0.0
    return LiveSpot(ticker=ticker, anchorSpot=anchor, liveSpot=live, spotReturn=ret)

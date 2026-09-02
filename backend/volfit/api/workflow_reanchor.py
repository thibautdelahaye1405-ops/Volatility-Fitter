"""The Spot panel's **Re-anchor** for ONE ticker (POST /spot/{ticker}/calibrate).

Composes the workflow blocks of volfit.api.workflow: clear the ticker's spot
move, refetch its chain (``AppState.refresh_chain`` — the live quotes AND the
live spot, off the streaming book when one is up; the calibrated pointers are
PRESERVED so every view keeps showing the previous fit, marked stale) and start
the ONE background calibration job over the ticker's lit nodes (the same
calendar-coupled parametric groups as the global Calibrate) followed by its LV
surface when Local-Vol is enabled.

Why a job and not the historical cache drop (``AppState.recalibrate``): in the
gated live server nothing recalibrates on a read, so dropping the calibrated
pointers left the ticker with no fit at all — a blank chart and nothing else.
Why the whole ticker and not the node on screen: a spot move is per ticker and
the calendar coupling needs the expiries fitted together.
"""

from __future__ import annotations

from dataclasses import dataclass

from volfit.api import workflow, workflow_stages
from volfit.api.jobs import Group
from volfit.api.state import AppState


@dataclass(frozen=True)
class ReanchorOutcome:
    """What ``reanchor_ticker`` did: whether the background job started, whether
    one was already running (``busy``), whether the chain refetch succeeded,
    and how many lit nodes the job covers."""

    started: bool
    busy: bool
    refetched: bool
    nodes: int


def reanchor_ticker(state: AppState, ticker: str, fit_mode: str = "mid") -> ReanchorOutcome:
    """The Spot panel's **Re-anchor** for ONE ticker: clear its spot move, refetch
    its chain (the live quotes AND the live spot — off the streaming book when
    one is up) and start a BACKGROUND calibration of ITS lit nodes, then its LV
    surface when Local-Vol is enabled, at that spot.

    The calibrated pointers are PRESERVED meanwhile (``refresh_chain`` marks the
    nodes stale but keeps the frozen fit), so every view keeps showing the
    previous calibration until the new one lands — never a blank chart, unlike
    the historical cache drop (``AppState.recalibrate``), which in the gated
    live server left the ticker with no fit at all. One ticker, every lit
    expiry: a spot move is per ticker, so re-anchoring it means all its lit
    nodes together (the calendar coupling needs them in one chain), not just
    the node on screen. ``busy`` = the one background job was already running:
    nothing started; the shift is still cleared and the chain refetched, so a
    second press once idle completes the re-anchor."""
    state.set_spot_shift(ticker, 0.0)  # the dial back to the anchor
    source = workflow._source_label(state)
    refetched = True
    try:
        with state.activity.activity("fetch", f"Fetching {ticker} quotes from {source}"):
            state.refresh_chain(ticker)  # new spot + quotes; pointers preserved
    except Exception:
        refetched = False  # feed miss: calibrate on the cached chain (best effort)
    nodes = workflow_stages.lit_nodes(state, [ticker])
    if not nodes:
        return ReanchorOutcome(started=False, busy=False, refetched=refetched, nodes=0)
    stages: list[list[Group]] = [workflow_stages._parametric_groups(state, nodes, fit_mode)]
    if state.options().localVolEnabled:
        lv_item = (f"{ticker} · LV surface", "LV", workflow_stages._affine_thunk(state, ticker, fit_mode))
        stages.append([(ticker, [lv_item])])
    started = workflow._start_stages(state, stages)
    return ReanchorOutcome(started=started, busy=not started, refetched=refetched, nodes=len(nodes))

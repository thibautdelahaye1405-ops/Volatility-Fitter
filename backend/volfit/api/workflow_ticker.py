"""The Spot panel's **Recalibrate** for ONE ticker (POST /spot/{ticker}/calibrate).

The top-bar Calibrate verb narrowed to a single ticker — nothing else differs:
the same calibration snapshot rule (``workflow.calibration_chains``: a fresh
synchronous quotes + spot snapshot off the streaming book, else the last
fetched chain — no request), the same scope names as the top bar ("both" =
parametric then the LV surface when Local-Vol is enabled, "parametric",
"lv" = the LV surface regardless of the toggle), the same calendar-coupled
parametric groups and LV item, the same ONE background job. The calibrated
pointers are preserved meanwhile, so every view keeps showing the previous
fit (marked stale) until the new one lands.

Why the whole ticker and not the node on screen: a spot move is per ticker and
the calendar coupling needs the expiries fitted together.
"""

from __future__ import annotations

from dataclasses import dataclass

from volfit.api import workflow, workflow_stages
from volfit.api.jobs import Group
from volfit.api.state import AppState


@dataclass(frozen=True)
class RecalibrateOutcome:
    """What ``recalibrate_ticker`` did: whether the background job started,
    whether one was already running (``busy``), whether a streaming snapshot
    was taken (else the last fetched chain), and the lit-node count."""

    started: bool
    busy: bool
    snapshotted: bool
    nodes: int


def recalibrate_ticker(
    state: AppState, ticker: str, fit_mode: str = "mid", scope: str = "both"
) -> RecalibrateOutcome:
    """Recalibrate one ticker's lit nodes (``scope`` as the top bar: "both" |
    "parametric" | "lv") on the calibration snapshot, as the background job.
    The dial is cleared up front (the fits re-anchor at the snapshot's spot);
    ``busy`` = the one job was already running — nothing started, press again
    when idle."""
    snapshotted = workflow.calibration_chains(state, [ticker])
    state.set_spot_shift(ticker, 0.0)  # the dial back to the (new) anchor
    nodes = workflow_stages.lit_nodes(state, [ticker])
    stages: list[list[Group]] = []
    if nodes and scope in ("both", "parametric"):
        stages.append(workflow_stages._parametric_groups(state, nodes, fit_mode))
    if nodes and (scope == "lv" or (scope == "both" and state.options().localVolEnabled)):
        lv_item = (f"{ticker} · LV surface", "LV", workflow_stages._affine_thunk(state, ticker, fit_mode))
        stages.append([(ticker, [lv_item])])
    if not stages:
        return RecalibrateOutcome(started=False, busy=False, snapshotted=snapshotted, nodes=len(nodes))
    started = workflow._start_stages(state, stages)
    return RecalibrateOutcome(started=started, busy=not started, snapshotted=snapshotted, nodes=len(nodes))

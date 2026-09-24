"""The wire shapes of the live quote-table tick stream (split out of
volfit.api.table_stream on 2026-09-24 to keep that module under the 400-line
policy; the contract is documented there): one live OTM row
(``LiveTickRow``), one SSE event (``LiveTableFrame``, with the node's tier —
live / rest / none — since the tiered-cadence layer), the strike key that
joins a live row to the table's row, and the prepared ``LiveSlice`` the
tracker diffs. ``table_stream`` re-exports them, so readers of the old
module see no change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from volfit.api.schemas import SmilePoint

#: How a node is served (AppState.stream_tier): its whole planned rung on the
#: socket, the belly live with REST wings, or not streaming.
LiveTier = Literal["live", "rest", "none"]


class LiveTickRow(BaseModel):
    """One live OTM quote of the node's slice, in the table's conventions."""

    key: str  # "<strike .4f>" — joins the table row / chart quote by strike
    strike: float
    type: str
    k: float
    bidIv: float
    midIv: float
    askIv: float
    bidPrice: float
    midPrice: float
    askPrice: float
    #: Fit-target band of the requested fit mode (None in "mid"), the market as
    #: quoted (no edits) — the chart's live target ribbon.
    targetLo: float | None = None
    targetHi: float | None = None
    #: The calibration quote at the same strike (click-through), -1 when none.
    index: int = -1
    #: The fit ROLLED to the live spot, at this row's live moneyness (the table's
    #: "Model IV" of the market frame); None when the node has no fit.
    modelIv: float | None = None


class LiveTableFrame(BaseModel):
    """One SSE event of the table tick stream."""

    type: Literal["ticks", "status"]
    streaming: bool  # the active source has a live book
    ready: bool  # the book served this node's chain (painted + covered)
    tier: LiveTier = "none"
    #: The REST cadence (s) behind a "rest" node — the badge's "1-min REST".
    restSeconds: float | None = None
    full: bool = False  # rows are the whole live slice (first frame / reset)
    ts: str | None = None  # newest provider stamp of the live chain (ISO, UTC)
    spot: float | None = None  # the FRAME's spot (the manual dial's when one is set)
    forward: float | None = None
    #: The book's actual underlying spot (independent of the dial) — the Spot
    #: panel's streamed readout.
    liveSpot: float | None = None
    rows: list[LiveTickRow] = Field(default_factory=list)
    gone: list[str] = Field(default_factory=list)  # keys no longer two-sided
    nLive: int = 0  # live two-sided rows in the slice after this frame
    #: The graph-INFERRED smile of the last Run (api/graph_inferred) ROLLED to
    #: the live spot, sent on the same occasions as ``model`` (and after a new
    #: Run); None = unchanged (or no inferred smile).
    inferred: list[SmilePoint] | None = None
    #: The displayed fit ROLLED to the live spot (k relative to ``forward``),
    #: sent whenever the live forward moved / the calibration changed; None =
    #: unchanged (or no fit).
    model: list[SmilePoint] | None = None


def row_key(strike: float) -> str:
    """The overlay join key: the strike at 4 dp (the table's precision)."""
    return f"{strike:.4f}"


@dataclass(frozen=True)
class LiveSlice:
    """The node's prepared live slice (table_stream.live_slice)."""

    rows: list[LiveTickRow]
    ts: datetime | None
    spot: float
    forward: float
    fingerprint: str
    shift: float = 0.0  # the FRAME's return vs the calibration anchor (rolls the fit)
    live_spot: float = 0.0  # the book's actual spot (the frame's unless a manual dial is set)


__all__ = ["LiveSlice", "LiveTableFrame", "LiveTickRow", "LiveTier", "row_key"]

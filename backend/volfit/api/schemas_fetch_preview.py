"""Response models of GET /fetch/preview — the Fetch-menu coverage preview
(ROADMAP "As-of → Fetch ▾" proposal: "14:30 · 9/12 nodes exact · 3 fall
back to close", shown BEFORE the user pulls).

Built by ``volfit.api.fetch_preview`` from cached state only: the global
as-of selection, the active provider's ADVERTISED capabilities
(``historical_modes`` / ``intraday_capable``) and, once a chain is loaded,
the per-node effective as-of (``volfit.api.node_asof``). Never fetches.
Mirrors the schemas.py / schemas_quality.py split.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FetchPreviewTicker(BaseModel):
    """One active ticker's coverage under the current as-of selection."""

    ticker: str
    #: Ladder rungs (selected expiries) — every node of a ticker shares one
    #: ChainSnapshot, so the whole ladder is exact or falls back together.
    nodes: int
    #: The global as-of mode ("live" | "prev_close" | "eod" | "captured" |
    #: "intraday") and the trading day it asks for (None for live).
    requestedMode: str
    requestedDay: str | None
    #: Whether the active source serves the requested moment: its advertised
    #: capability, overridden by the EVIDENCE once a chain is loaded (a
    #: served chain stamped off the requested session proves it does not).
    providerHonors: bool
    #: What the source serves instead when it does not honor the request:
    #: "live" (its latest chain) or "close" (another session's close).
    fallback: Literal["live", "close"] | None
    #: Exactness of the chain CURRENTLY loaded (node_asof); None before any fetch.
    currentlyExact: bool | None
    effectiveAsOf: str | None


class FetchPreviewTotals(BaseModel):
    """Node counts across the active tickers."""

    nodes: int
    exact: int  # nodes whose source honors the requested moment
    fallback: int  # nodes that would be served from another moment


class FetchPreview(BaseModel):
    """GET /fetch/preview response."""

    mode: str
    requestedDay: str | None
    dataSource: str  # the active source id
    #: One line for the Fetch menu: "Live · 12/12 nodes" /
    #: "Previous close · provider serves it" /
    #: "14:30 · 9/12 nodes exact · 3 fall back to close".
    summary: str
    totals: FetchPreviewTotals
    tickers: list[FetchPreviewTicker]

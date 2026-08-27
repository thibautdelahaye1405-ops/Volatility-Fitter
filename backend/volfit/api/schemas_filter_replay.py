"""DTOs for the served offline filter-replay artifacts (V3.9 rider).

``backtest.filter_replay`` writes, per (ticker, day), a JSON part
``<TICKER>_<YYYY-MM-DD>.json`` of shape ``{"meta": {...}, "nodes": {iso:
[FilterStepOut dict, ...]}}`` plus one ``filter_replay.html`` evidence page.
The routes in ``routers/filter_replay.py`` only SERVE those files — nothing
is computed at request time — and these models describe the listing.
The part document itself is returned verbatim (no model: its ``nodes`` steps
are already the ``/filter/history`` wire dicts, byte-for-byte).
"""

from __future__ import annotations

from pydantic import BaseModel


class FilterReplayPartMeta(BaseModel):
    """One replay part's metadata, parsed from its ``meta`` block (the file
    name is the fallback when the block is incomplete)."""

    ticker: str
    day: str  # ISO date the session was replayed over
    nInstants: int  # stored intraday instants driven through the commit path
    fitMode: str  # "mid" | "bid_ask" | "haircut"
    filterMode: str  # "overlay" — the replay's observationFilterMode
    expiries: list[str] = []  # node ISOs carried in ``nodes`` (sorted)
    mtime: float  # file modification epoch seconds (the tie-breaker)


class FilterReplayPartsResponse(BaseModel):
    """GET /filter/replay/parts: parts NEWEST FIRST (by replayed day, then
    file mtime); empty — never an error — when no replay ran yet."""

    parts: list[FilterReplayPartMeta] = []

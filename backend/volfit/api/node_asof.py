"""Per-node EFFECTIVE as-of (workbench follow-on, 2026-08-27 — the wire only).

The as-of selection is GLOBAL (``AppState.as_of``), but the chain that actually
SERVES a node is whatever the active provider returned for its ticker — a
provider that cannot honor the requested moment falls back (a live-only source
ignores a close request; Massive stamps a prev-close chain at fetch time). The
ROADMAP proposal (UI shell v2 wave 3, item 4) has every node carry its
EFFECTIVE as-of so the nodes pane / status bar can flag ``≠ as-of`` instead of
silently mixing moments. This module is the single resolution shared by the
universe payload (``ExpiryInfo``) and the graph lattice (``GraphNodeInfo``):

* ``effectiveAsOf`` — the loaded chain's stamp (UTC-naive ISO), None before
  any fetch;
* ``dataSource``    — the active source id serving it (cached chains ALWAYS
  come from the active provider: a source switch clears every chain cache);
  the snapshot-file source reports ``"file"``;
* ``asOfExact``     — True when the stamp lies in the requested session:
  live IS the moment (always exact once a chain exists); a close / captured /
  intraday selection is exact when the stamp's date is the requested day.
  None when no chain is loaded.

Reads CACHED state only (``state.loaded_snapshot``) — never fetches, so the
universe payload stays as network-light as before. The publish gate and the
Fetch coverage preview of the proposal are NOT here (recorded follow-ons).
"""

from __future__ import annotations

from datetime import date

from volfit.api.asof import _prev_business_day
from volfit.api.state import AppState, AsOfSelection

#: The (effectiveAsOf, dataSource, asOfExact) triple of one node.
NodeAsOf = tuple[str | None, str | None, bool | None]

NO_CHAIN: NodeAsOf = (None, None, None)


def requested_day(selection: AsOfSelection, reference_date: date) -> date | None:
    """The trading day the global as-of asks for; None for live (no target).

    ``eod`` → its date; ``captured`` / ``intraday`` → the instant's date;
    ``prev_close`` → the dropdown day it resolved from, else the previous
    business day of the reference date (no provider call — the payload must
    stay feed-free).
    """
    mode = selection.mode
    if mode == "live":
        return None
    if mode == "eod":
        return selection.on
    if mode in ("captured", "intraday"):
        return selection.ts.date() if selection.ts is not None else selection.day
    if mode == "prev_close":
        return selection.day or _prev_business_day(reference_date)
    return selection.day


def node_effective_asof(state: AppState, ticker: str) -> NodeAsOf:
    """(effectiveAsOf, dataSource, asOfExact) of every node of ``ticker`` — a
    ChainSnapshot is one atomic observation, so all its expiries share it.
    ``NO_CHAIN`` (three Nones) when nothing is loaded."""
    snap = state.loaded_snapshot(ticker)
    if snap is None or not snap.quotes:
        return NO_CHAIN
    day = requested_day(state.as_of, state.reference_date)
    exact = True if day is None else snap.timestamp.date() == day
    return snap.timestamp.isoformat(), state.source_of(ticker), exact


def ticker_asof_map(state: AppState, tickers) -> dict[str, NodeAsOf]:
    """``node_effective_asof`` for a set of tickers (one lock read each)."""
    return {t: node_effective_asof(state, t) for t in dict.fromkeys(tickers)}

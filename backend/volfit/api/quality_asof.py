"""Quality-row reading of the per-node EFFECTIVE as-of (workbench follow-on,
2026-08-27 — the "as-of mismatch" issue + publish gate of the ROADMAP
"As-of → Fetch ▾" proposal).

``volfit.api.node_asof`` resolves, per ticker, the stamp of the chain that
SERVES a node and whether that stamp lies in the requested as-of session
(``asOfExact``). This module turns that triple into the quality row's
fields and — under ``OptionsSettings.asOfMismatchGate`` — into a readiness
issue that the publish export (``export_blockers._node_blockers``) blocks
on. Gate OFF (the default) keeps the reading ADVISORY: the row still carries
``asOfExact`` / ``effectiveAsOf`` so the Nodes pane and the Quality card can
flag ``≠ as-of``, but readiness and publish ignore it.

The mismatch is a DATA issue, not an arbitrage one: it fails ``ready`` but
must never count in the ticker-level ``arbFlags``. Reads cached state only
(never fetches), like every other quality read.
"""

from __future__ import annotations

from dataclasses import dataclass

from volfit.api.node_asof import node_effective_asof, requested_day
from volfit.api.state import AppState


@dataclass(frozen=True)
class AsOfFields:
    """The quality row's as-of fields (api.quality._node_row unpacks these):
    the serving chain's stamp, its exactness vs the requested session, whether
    the gate applied to this row, and the issue line (None when exact, when
    nothing is loaded, or when the gate is off)."""

    effective: str | None
    exact: bool | None
    gated: bool
    issue: str | None


def asof_issue(state: AppState, ticker: str, gate: bool) -> str | None:
    """The gated "as-of mismatch" issue line of one ticker's nodes, or None.

    None whenever the gate is off, no chain is loaded, or the served chain's
    stamp sits in the requested session (``node_effective_asof``); otherwise
    "as-of mismatch: chain stamped <ISO> vs the requested <day>" — the day
    being what the global selection asked for (``requested_day``)."""
    if not gate:
        return None
    stamp, _source, exact = node_effective_asof(state, ticker)
    if exact is not False:
        return None
    day = requested_day(state.as_of, state.reference_date)
    asked = day.isoformat() if day is not None else state.as_of.mode
    return f"as-of mismatch: chain stamped {stamp} vs the requested {asked}"


def asof_fields(state: AppState, ticker: str) -> AsOfFields:
    """``AsOfFields`` of one ticker's nodes under the current options (all
    expiries of a ticker share one ChainSnapshot, hence one reading)."""
    gate = bool(state.options().asOfMismatchGate)
    stamp, _source, exact = node_effective_asof(state, ticker)
    return AsOfFields(
        effective=stamp,
        exact=exact,
        gated=gate,
        issue=asof_issue(state, ticker, gate),
    )

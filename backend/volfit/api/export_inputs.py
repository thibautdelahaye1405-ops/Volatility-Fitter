"""Input embedding for the surfaces export (self-contained artifacts).

The slim surfaces artifact carries the *outputs* (fitted curves, params, LV
grid) and the *recipe* (settings, versions, lineage) but not the *inputs* —
the fetched chains and the prepared quotes the fits consumed. This module
serializes those inputs into the same JSON artifact so a single file supports
offline recalibration, live-vs-offline comparisons and Notes fixtures with no
store round-trip:

* per ticker: the full normalized ``ChainSnapshot`` (every fetched expiry and
  contract, with the schema-v7 metadata — exercise style, zero-carry flag,
  tick size, per-expiry settlement) plus the active ``MarketSettings`` (rate,
  dividend model);
* per fitted node: the ``PreparedQuotes`` the calibration actually consumed
  (post-screen, de-Americanized iv bid/mid/ask band, EEP), the quarantined
  quotes with their reasons, and the forward's source + parity diagnostics.

Quote tables are serialized as ``columns`` + row arrays — compact, order-
stable, and trivially loadable into numpy/pandas. Embedding is the JSON
default (``inputs=false`` opts out); the CSV format never embeds.
"""

from __future__ import annotations

from datetime import date

import numpy as np
from pydantic import BaseModel

#: Column order of the raw-chain quote table (schema v7 + the fetch-time
#: per-quote timestamp, which the SQLite store does not persist).
CHAIN_COLUMNS = (
    "expiry", "strike", "callPut", "bid", "ask", "last",
    "volume", "openInterest", "timestamp",
)

#: Column order of the per-node prepared-quote table. ``eep`` is the dollar
#: early-exercise premium stripped before inversion (null on European chains).
PREPARED_COLUMNS = ("k", "strike", "ivBid", "ivMid", "ivAsk", "wMid", "eep")


class ExportChain(BaseModel):
    """The normalized snapshot exactly as fetched (all expiries, schema v7)."""

    exerciseStyle: str
    zeroCarry: bool
    tickSize: float | None = None
    #: {expiry ISO: {style, lastTrade, settle}} — AM/PM settlement semantics.
    settlement: dict[str, dict] | None = None
    quoteColumns: list[str]
    quotes: list[list]


class ExportNodeInputs(BaseModel):
    """What one node's calibration consumed, plus how its forward was made."""

    forwardSource: str  # "parity" | "theoretical" | "manual"
    #: Parity-regression diagnostics (None for theoretical/manual forwards):
    #: {residualRms, nStrikes, nOutliers} of volfit.data.forwards.
    forwardDiagnostics: dict | None = None
    nDeamericanized: int
    nDeamInput: int
    vegaFloored: int
    preparedColumns: list[str]
    prepared: list[list]
    #: Quarantined quotes with their reasons (R1 item 6 observability).
    screened: list[dict]


def export_chain(snapshot) -> ExportChain:
    """Serialize a ChainSnapshot's full quote table + schema-v7 metadata."""
    settlement = None
    if snapshot.settlement is not None:
        settlement = {
            e.isoformat(): {
                "style": s.style,
                "lastTrade": s.last_trade.isoformat(),
                "settle": s.settle.isoformat(),
            }
            for e, s in snapshot.settlement.items()
        }
    rows = [
        [
            q.expiry.isoformat(), q.strike, q.call_put, q.bid, q.ask, q.last,
            q.volume, q.open_interest,
            q.timestamp.isoformat() if q.timestamp is not None else None,
        ]
        for q in snapshot.quotes
    ]
    return ExportChain(
        exerciseStyle=snapshot.exercise_style,
        zeroCarry=bool(snapshot.zero_carry),
        tickSize=snapshot.tick_size,
        settlement=settlement,
        quoteColumns=list(CHAIN_COLUMNS),
        quotes=rows,
    )


def export_node_inputs(state, ticker: str, expiry_iso: str, prepared) -> ExportNodeInputs:
    """Serialize one node's PreparedQuotes + forward provenance."""
    expiry = date.fromisoformat(expiry_iso)
    source = "parity"
    diagnostics: dict | None = None
    try:
        source = state.resolved_forward(ticker, expiry).source
        implied = state.forwards(ticker).get(expiry)
        if source == "parity" and implied is not None:
            diagnostics = {
                "residualRms": float(implied.residual_rms),
                "nStrikes": int(implied.n_strikes),
                "nOutliers": int(implied.n_outliers),
            }
    except Exception:  # noqa: BLE001 — provenance must never break an export
        pass
    strikes = prepared.forward * np.exp(prepared.k)
    eep = prepared.eep
    rows = [
        [
            float(prepared.k[i]), float(strikes[i]),
            float(prepared.iv_bid[i]), float(prepared.iv_mid[i]),
            float(prepared.iv_ask[i]), float(prepared.w_mid[i]),
            float(eep[i]) if eep is not None else None,
        ]
        for i in range(prepared.k.size)
    ]
    return ExportNodeInputs(
        forwardSource=source,
        forwardDiagnostics=diagnostics,
        nDeamericanized=int(prepared.n_deamericanized),
        nDeamInput=int(prepared.n_deam_input),
        vegaFloored=int(prepared.vega_floored),
        preparedColumns=list(PREPARED_COLUMNS),
        prepared=rows,
        screened=[
            {"strike": s.strike, "callPut": s.call_put, "k": s.k,
             "reason": s.reason}
            for s in prepared.screened
        ],
    )

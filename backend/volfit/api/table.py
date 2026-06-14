"""Quote/price/IV table of one fitted smile node (Phase 6 [REQ 2026-06-12]).

Backs the table-export endpoints — GET /smiles/{ticker}/{expiry}/table
(JSON grid) and .../table.csv (download) — from the SAME cached FitRecord
that the Smile Viewer charts (volfit.api.service.fit_or_get), so the rows
always match the displayed fit.

Each prepared quote becomes one row: the displayed IV band (an amended
quote shows its overridden mid, mirroring service.smile_payload), the
fitted model vol at its k, and discounted OTM option prices reconstructed
through the normalized Black call (volfit.core.black) at the band IVs —
calls priced as D F B(k, w), puts by parity D F (B(k, w) - 1 + e^k), the
exact inverse of the price -> IV map in volfit.api.quotes. The OTM side
convention tags type "C" iff k >= 0.

Lives outside service.py purely for the file-size policy; same conventions
(pure functions over AppState returning pydantic response models).
"""

from __future__ import annotations

import csv
import io
import math

import numpy as np

from volfit.api.displayed import displayed_slice
from volfit.api.schemas import TableResponse, TableRow
from volfit.api.service import fit_or_get
from volfit.api.state import AppState
from volfit.core.black import black_call

#: CSV column order — frozen against the frontend download contract.
CSV_COLUMNS = (
    "strike,type,k,bid_iv,mid_iv,ask_iv,model_iv,"
    "bid_price,mid_price,ask_price,excluded,amended"
)


def _price(k: float, iv: float, t: float, forward: float, discount: float) -> float:
    """Discounted OTM option price at one band IV (Black call + put parity)."""
    c_norm = float(black_call(k, iv * iv * t))
    if k < 0.0:  # OTM put: parity in normalized undiscounted forward units
        c_norm += math.exp(k) - 1.0
    return discount * forward * c_norm


def table_payload(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> TableResponse:
    """Assemble the full quote table for one (ticker, expiry) node."""
    record = fit_or_get(state, ticker, expiry_iso, fit_mode)
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()  # session key
    session = state.session_if_exists((ticker, iso))
    prepared = record.prepared
    t, forward, discount = prepared.t, prepared.forward, prepared.discount
    # IVs are in the event-weighted clock (prepared.tau): total variance is
    # iv^2 * tau, so prices reconstructed at tau equal the real market prices,
    # and the model IV is the weighted vol. ``t`` (calendar) stays the maturity.
    tv = prepared.tau
    model_iv = np.sqrt(displayed_slice(record).implied_w(prepared.k) / tv)

    rows: list[TableRow] = []
    for i, (k, bid, mid, ask) in enumerate(
        zip(prepared.k, prepared.iv_bid, prepared.iv_mid, prepared.iv_ask)
    ):
        edit = session.edits.get(i) if session is not None else None
        amended = edit is not None and edit.amended_iv is not None
        mid_iv = edit.amended_iv if amended else float(mid)
        k = float(k)
        rows.append(
            TableRow(
                index=i,
                strike=forward * math.exp(k),
                type="C" if k >= 0.0 else "P",
                k=k,
                bidIv=float(bid),
                midIv=mid_iv,
                askIv=float(ask),
                modelIv=float(model_iv[i]),
                bidPrice=_price(k, float(bid), tv, forward, discount),
                midPrice=_price(k, mid_iv, tv, forward, discount),
                askPrice=_price(k, float(ask), tv, forward, discount),
                excluded=edit is not None and edit.excluded,
                amended=amended,
            )
        )
    return TableResponse(
        ticker=ticker, expiry=expiry_iso, t=t, forward=forward, discount=discount, rows=rows
    )


def table_csv(payload: TableResponse) -> str:
    """Render one TableResponse as CSV text (header + one line per row)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS.split(","))
    for r in payload.rows:
        writer.writerow(
            [
                r.strike,
                r.type,
                r.k,
                r.bidIv,
                r.midIv,
                r.askIv,
                r.modelIv,
                r.bidPrice,
                r.midPrice,
                r.askPrice,
                r.excluded,
                r.amended,
            ]
        )
    return buffer.getvalue()

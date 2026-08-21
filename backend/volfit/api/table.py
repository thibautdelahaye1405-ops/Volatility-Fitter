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

from volfit.api import smile_layers
from volfit.api.displayed import displayed_slice
from volfit.api.schemas import TableResponse, TableRow
from volfit.api.service import displayed_base, edited_band_full, fit_or_get, prepare_slice
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
    """Assemble the full quote table for one (ticker, expiry) node: the
    calibration rows (``rows``) + the prevailing market rows (``marketRows``)."""
    record = fit_or_get(state, ticker, expiry_iso, fit_mode)
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()  # session key
    session = state.session_if_exists((ticker, iso))
    if record is None:  # gated, never calibrated: quotes only (no model column)
        prepared = prepare_slice(state, ticker, iso)
        if prepared is None:
            return TableResponse(
                ticker=ticker, expiry=expiry_iso, t=0.0, forward=0.0, discount=1.0, rows=[]
            )
        model_iv = prepared.iv_mid  # no fit yet -> the mid stands in for the model col
    else:
        prepared = record.prepared
        # IVs are in the event-weighted clock (prepared.tau): total variance is
        # iv^2 * tau, so prices reconstructed at tau equal the real market prices,
        # and the model IV is the weighted vol. ``t`` (calendar) stays the maturity.
        model_iv = np.sqrt(displayed_slice(record).implied_w(prepared.k) / prepared.tau)
    t, forward, discount = prepared.t, prepared.forward, prepared.discount
    tv = prepared.tau
    band = edited_band_full(state, ticker, iso, prepared, fit_mode)  # the fit's own target

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
                targetLo=float(band.iv_lo[i]) if band is not None else None,
                targetHi=float(band.iv_hi[i]) if band is not None else None,
            )
        )
    market = _market_rows(state, ticker, iso, fit_mode, rows)
    return TableResponse(
        ticker=ticker, expiry=expiry_iso, t=t, forward=forward, discount=discount, rows=rows,
        **market,
    )


def _market_rows(
    state: AppState, ticker: str, iso: str, fit_mode: str, calib_rows: list[TableRow]
) -> dict:
    """The PREVAILING frame of the table (api/smile_layers semantics): the latest
    fetched chain as quoted (no edits, target of ``fit_mode``), Model IV = the fit
    ROLLED to the prevailing spot evaluated at each strike's market moneyness,
    prices reconstructed at the market forward. Empty when no chain."""
    base = displayed_base(state, ticker, iso, fit_mode)
    prepared = prepare_slice(state, ticker, iso)
    if prepared is None:
        return {}
    calib_index = {smile_layers.strike_key(r.strike): r.index for r in calib_rows}
    shift, spot = smile_layers.prevailing_shift(state, ticker)
    if base is not None:  # ONE transport: its forward is the market forward
        rolled = smile_layers.rolled_record(state, ticker, iso, base, shift)
        f = float(rolled.prepared.forward)
        discount, tv = float(rolled.prepared.discount), float(rolled.prepared.tau)
    else:
        rolled, f = None, float(prepared.forward)
        discount, tv = float(prepared.discount), float(prepared.tau)
    quotes = smile_layers.market_quote_bands(
        prepared, f, fit_mode, state.fit_settings().haircut, calib_index
    )
    ks = np.array([q.k for q in quotes])
    if rolled is not None:
        model_iv = smile_layers.model_iv_at(rolled, ks) if ks.size else ks
    else:
        model_iv = np.array([q.mid for q in quotes])  # no fit: the mid stands in
    try:
        stamp = state.snapshot(ticker).timestamp
        timestamp = stamp.isoformat() if stamp is not None else None
    except Exception:  # noqa: BLE001
        timestamp = None
    rows = [
        TableRow(
            index=q.index,
            strike=float(q.strike),
            type="C" if q.k >= 0.0 else "P",
            k=q.k,
            bidIv=q.bid,
            midIv=q.mid,
            askIv=q.ask,
            modelIv=float(model_iv[i]),
            bidPrice=_price(q.k, q.bid, tv, f, discount),
            midPrice=_price(q.k, q.mid, tv, f, discount),
            askPrice=_price(q.k, q.ask, tv, f, discount),
            excluded=False,
            amended=False,
            targetLo=q.targetLo,
            targetHi=q.targetHi,
        )
        for i, q in enumerate(quotes)
    ]
    return {
        "marketForward": f,
        "marketSpot": spot,
        "marketTimestamp": timestamp,
        "marketLive": bool(state.is_streaming()),
        "marketRows": rows,
    }


def table_csv(payload: TableResponse, frame: str = "calib") -> str:
    """Render one TableResponse as CSV text (header + one line per row):
    ``frame="calib"`` (default, the frozen contract) = the calibration rows,
    ``"market"`` = the prevailing market rows (same columns)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS.split(","))
    for r in payload.marketRows if frame == "market" else payload.rows:
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

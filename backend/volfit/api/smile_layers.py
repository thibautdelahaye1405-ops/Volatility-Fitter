"""The Smile Viewer's two comparable frames (SmileData.market / SmileData.calib).

The chart shows two worlds that must each be internally comparable:

* **Market** (layers 1 + 3): the PREVAILING bid/ask quotes with the fit-target
  band of the viewed fit mode, and the fitted smile ROLLED to the prevailing
  spot under the dynamics regime (the same no-recal transport the app applies
  under a spot move — service.transport_record — just driven by the prevailing
  spot instead of the active shift). Quotes are the market as quoted: NO user
  edits (those belong to the calibration frame). Prevailing = the live book
  when streaming (the SSE tick stream refines this layer at 1 Hz,
  volfit.api.table_stream), else the latest fetched chain.
* **Calibration** (layers 2 + 4): the quotes + target the last calibration used
  (SmileData.quotes, with edits) and the fitted smile on its CALIBRATION spot
  (k relative to F0).

Every quote carries its strike, the layer-independent identity the chart
joins on (click-through from a market quote to the calibration quote at the
same strike) and places with log(strike / layer forward).

Prevailing spot rule: the app's active spot shift when one is set (the
real-time spot poll / a hypothetical move — the whole app already lives at
that spot), else the latest fetched chain's spot. The forward at that spot
follows the app's own forward-transport rule (proportional, or additive under
discrete cash dividends — service.spot_forward_shift).
"""

from __future__ import annotations

import math
from datetime import date

from volfit.api.quotes import PreparedQuotes
from volfit.api.schemas import CalibLayer, MarketLayer, QuoteBand, SmilePoint
from volfit.api.state import AppState, FitRecord
from volfit.calib.band import resolve_band


def strike_key(strike: float) -> str:
    """Strike at 4 dp — the cross-layer join key (== table_stream.row_key)."""
    return f"{strike:.4f}"


def prevailing_shift(state: AppState, ticker: str) -> tuple[float, float | None]:
    """``(shift vs the calibration anchor, prevailing spot)``: the active spot
    shift when one is set, else the latest fetched chain's spot return vs the
    anchor (0 when it cannot be read)."""
    active = state.spot_shift(ticker)
    try:
        anchor = float(state.anchor_spot(ticker))
    except Exception:  # noqa: BLE001 — no chain yet
        return 0.0, None
    if active != 0.0:
        return active, anchor * (1.0 + active)
    try:
        spot = float(state.snapshot(ticker).spot)
    except Exception:  # noqa: BLE001
        return 0.0, None
    if anchor <= 0.0 or spot <= 0.0:
        return 0.0, spot
    return spot / anchor - 1.0, spot


def rolled_model(state: AppState, ticker: str, iso: str, base: FitRecord | None, shift: float) -> list[SmilePoint]:
    """The calibrated fit ``base`` rolled by ``shift`` (k relative to the rolled
    forward) under the dynamics regime; [] when there is no fit."""
    from volfit.api.service import model_curve, transport_record

    if base is None:
        return []
    return model_curve(transport_record(state, ticker, iso, base, shift=shift))


def rolled_forward(state: AppState, ticker: str, iso: str, base: FitRecord, shift: float) -> float:
    """The calibration forward moved by ``shift`` (the app's transport rule)."""
    from volfit.api.service import spot_forward_shift

    p = base.prepared
    f1, _h = spot_forward_shift(
        state, ticker, date.fromisoformat(iso), float(p.forward), float(p.discount), float(p.t), shift=shift
    )
    return float(f1)


def market_quote_bands(
    prepared: PreparedQuotes,
    forward: float,
    fit_mode: str,
    haircut: float,
    calib_index: dict[str, int] | None = None,
) -> list[QuoteBand]:
    """Pure-market quote bands of a prepared slice: bid/mid/ask as quoted (no
    edits), the fit-target band of ``fit_mode`` (None in "mid"), k re-expressed
    against the LAYER ``forward`` (fixed strikes), ``index`` = the calibration
    quote at the same strike (click-through) or -1."""
    band = resolve_band(prepared.iv_bid, prepared.iv_mid, prepared.iv_ask, fit_mode, haircut)
    out: list[QuoteBand] = []
    f_src = float(prepared.forward)
    for i, (k, b, m, a) in enumerate(zip(prepared.k, prepared.iv_bid, prepared.iv_mid, prepared.iv_ask)):
        strike = f_src * math.exp(float(k))
        out.append(
            QuoteBand(
                k=math.log(strike / forward) if forward > 0.0 else float(k),
                bid=float(b),
                ask=float(a),
                mid=float(m),
                index=(calib_index or {}).get(strike_key(strike), -1),
                excluded=False,
                amended=False,
                strike=strike,
                targetLo=float(band.iv_lo[i]) if band is not None else None,
                targetHi=float(band.iv_hi[i]) if band is not None else None,
            )
        )
    return out


def calib_index_by_strike(quotes: list[QuoteBand]) -> dict[str, int]:
    """``{strike key -> index}`` of the calibration quotes (those with a strike)."""
    return {strike_key(q.strike): q.index for q in quotes if q.strike is not None}


def calib_layer(base: FitRecord | None) -> CalibLayer | None:
    """The calibration frame: the fit on its own spot (None when no fit)."""
    from volfit.api.service import model_curve

    if base is None:
        return None
    p = base.prepared
    return CalibLayer(forward=float(p.forward), spot=None, model=model_curve(base))


def market_layer(
    state: AppState,
    ticker: str,
    iso: str,
    fit_mode: str,
    base: FitRecord | None,
    calib_quotes: list[QuoteBand],
    prepared_market: PreparedQuotes | None,
    active_model: list[SmilePoint] | None = None,
) -> MarketLayer | None:
    """The market frame for a node, or None when no chain is loaded.

    ``prepared_market`` is the latest fetched chain's prepared slice (the
    caller resolves it — it is memoized). ``active_model`` is the payload's
    displayed (active-shift) curve: reused as the rolled model when the
    prevailing shift IS the active one, so the common case costs no second
    transport."""
    if prepared_market is None:
        return None
    shift, spot = prevailing_shift(state, ticker)
    if base is not None:
        forward = rolled_forward(state, ticker, iso, base, shift)
        if active_model is not None and shift == state.spot_shift(ticker):
            model = list(active_model)
        else:
            model = rolled_model(state, ticker, iso, base, shift)
    else:
        forward, model = float(prepared_market.forward), []
    try:
        stamp = state.snapshot(ticker).timestamp
        timestamp = stamp.isoformat() if stamp is not None else None
    except Exception:  # noqa: BLE001
        timestamp = None
    quotes = market_quote_bands(
        prepared_market, forward, fit_mode, state.fit_settings().haircut,
        calib_index_by_strike(calib_quotes),
    )
    return MarketLayer(
        forward=forward,
        spot=spot,
        timestamp=timestamp,
        live=bool(state.is_streaming()),
        quotes=quotes,
        model=model,
    )

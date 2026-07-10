"""Quote quarantine with reasons (R1 item 6, volfit.api.quotes).

Contracts: (1) the KEPT set is byte-identical to the silent-drop pipeline —
the quarantine only NAMES the drops (tick_floor / missing_or_crossed /
below_intrinsic / price_bound / wing / nonpositive_bid); (2) each reason
fires on its constructed case; (3) per-quote EEP is retained on American
chains (None on European); (4) the vega-floor diagnostic counts kept quotes
whose Black vega is below the floor; (5) the quality report surfaces the
counts, advisory only.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np

from volfit.api.quotes import VEGA_FLOOR_DIAG, prepare_quotes
from volfit.core.black import black_call, black_vega_sigma
from volfit.data.forwards import ImpliedForward
from volfit.data.types import ChainSnapshot, OptionQuote

EXPIRY = date(2026, 7, 17)
TS = datetime(2026, 6, 10, 20, 0)
F = 100.0


def _fwd(discount: float = 1.0) -> ImpliedForward:
    return ImpliedForward(expiry=EXPIRY, forward=F, discount=discount,
                          n_strikes=9, residual_rms=0.0)


def _quote(strike: float, cp: str, bid: float, ask: float) -> OptionQuote:
    return OptionQuote(ticker="X", expiry=EXPIRY, strike=strike, call_put=cp,
                       bid=bid, ask=ask)


def _price(strike: float, cp: str, sigma: float, t: float) -> float:
    k = np.log(strike / F)
    c = float(black_call(np.array([k]), np.array([sigma * sigma * t]))[0])
    return c * F if cp == "C" else (c - 1.0 + strike / F) * F


def _chain(quotes, style: str = "european", tick: float | None = None) -> ChainSnapshot:
    return ChainSnapshot(ticker="X", spot=F, timestamp=TS, quotes=quotes,
                         exercise_style=style, tick_size=tick)


def _base_quotes(sigma: float = 0.2, t: float = 0.1, spread: float = 0.10):
    out = []
    for strike in (80, 85, 90, 95, 100, 105, 110, 115, 120):
        cp = "C" if strike >= F else "P"
        mid = _price(strike, cp, sigma, t)
        out.append(_quote(strike, cp, max(mid - spread / 2, 0.01), mid + spread / 2))
    return out


def test_clean_chain_screens_nothing():
    prepared = prepare_quotes(_chain(_base_quotes()), EXPIRY, _fwd(), 0.1)
    assert prepared.screened == ()
    assert prepared.eep is None  # European: no EEP array
    assert prepared.vega_floored == 0


def test_tick_floor_and_crossed_reasons():
    quotes = _base_quotes()
    quotes.append(_quote(125, "C", 0.01, 0.02))  # ~1.5 ticks: quantum noise
    quotes.append(OptionQuote(ticker="X", expiry=EXPIRY, strike=87.5, call_put="P",
                              bid=None, ask=1.0))  # one-sided market
    prepared = prepare_quotes(_chain(quotes, tick=0.01), EXPIRY, _fwd(), 0.1)
    reasons = {(s.strike, s.reason) for s in prepared.screened}
    assert (125.0, "tick_floor") in reasons
    assert (87.5, "missing_or_crossed") in reasons
    assert 125.0 not in prepared.forward * np.exp(prepared.k)  # dropped, not kept


def test_below_intrinsic_and_price_bound_reasons():
    quotes = _base_quotes()
    # An OTM put whose bid is zero inverts to c_bid == intrinsic exactly —
    # near-zero time value on that side, no stable IV: quarantined by name.
    quotes.append(_quote(70, "P", 0.0, 0.05))
    # An OTM put priced ABOVE the upper static bound (c >= 1).
    quotes.append(_quote(75, "P", 90.0, 91.0))
    prepared = prepare_quotes(_chain(quotes), EXPIRY, _fwd(), 0.1)
    by_strike = {s.strike: s.reason for s in prepared.screened}
    assert by_strike[70.0] == "below_intrinsic"
    assert by_strike[75.0] == "price_bound"


def test_wing_reason_beyond_z_max():
    quotes = _base_quotes(sigma=0.2, t=0.01)  # ATM sd ~ 2%: k=+-0.18 is ~9 sd
    quotes.append(_quote(140, "C", 0.02, 0.06))
    prepared = prepare_quotes(_chain(quotes), EXPIRY, _fwd(), 0.01)
    assert any(s.strike == 140.0 and s.reason == "wing" for s in prepared.screened)


def test_vega_floor_diagnostic_counts_kept_quotes():
    t = 0.01  # ATM sd = 0.02: strikes 93/107 sit ~3.6 sd out — inside the
    # Z_MAX=4 wing cut but with Black vega ~6e-5, far below the 1e-3 floor.
    quotes = _base_quotes(sigma=0.2, t=t, spread=0.02)
    for strike in (93.0, 107.0):
        cp = "C" if strike >= F else "P"
        mid = _price(strike, cp, 0.2, t)  # true tiny Black price (~fractions
        quotes.append(_quote(strike, cp, mid * 0.8, mid * 1.2))  # of a cent)
    prepared = prepare_quotes(_chain(quotes), EXPIRY, _fwd(), t)
    vega = black_vega_sigma(prepared.k, prepared.iv_mid, prepared.tau)
    assert prepared.vega_floored == int(np.count_nonzero(vega < VEGA_FLOOR_DIAG))
    assert prepared.vega_floored > 0  # short-dated wings sit below the floor


def test_american_chain_retains_per_quote_eep():
    prepared = prepare_quotes(
        _chain(_base_quotes(t=0.25), style="american"), EXPIRY,
        _fwd(0.99), 0.25,
    )
    assert prepared.eep is not None
    assert prepared.eep.shape == prepared.k.shape
    assert np.all(prepared.eep >= 0.0)


def test_quality_surfaces_screen_counts_advisory():
    from volfit.api import quality, service
    from volfit.api.state import AppState

    state = AppState(date(2026, 6, 10))
    tk = state.active_tickers()[0]
    iso = sorted(state.forwards(tk))[0].isoformat()
    service.calibrate_node(state, tk, iso, "mid")
    report = quality.build_quality_report(state)
    row = next(n for n in report.nodes if n.ticker == tk and n.expiry == iso)
    assert isinstance(row.screened, dict) and isinstance(row.vegaFloored, int)
    # Advisory: naming the drops must never create readiness issues.
    assert not any("screen" in i or "quarantine" in i for i in row.issues)

"""CarryCurve v0 (volfit.api.carry, R1 item 7).

Contracts: (1) an identified expiry's borrow read recovers a synthetic
borrow planted in the parity forward (ln(F_theo/F_parity)/t); (2)
identifiability is explicit and CALM — zero-carry chains, thin parity and
noisy regressions report borrowBp=None with borrowSource="unidentified",
NEVER a silent zero; (3) every component carries a source tag; (4) the
quality rollup surfaces identified/unidentified counts advisory-only;
(5) the ForwardEntry payload carries impliedBorrowBp under the same rule.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest

from volfit.api import carry as carry_mod
from volfit.api.carry import borrow_identified, carry_curve, implied_borrow_bp
from volfit.api.state import AppState
from volfit.data.types import ChainSnapshot, OptionQuote

REF_DATE = date(2026, 6, 10)


def test_implied_borrow_formula():
    # F_parity below theoretical = positive borrow (hard-to-borrow).
    t = 0.5
    bp = implied_borrow_bp(98.0, 100.0, t)
    assert bp == pytest.approx(np.log(100.0 / 98.0) / t * 1e4)
    assert bp > 0.0
    assert implied_borrow_bp(98.0, 100.0, 0.0) is None


class _Parity:
    def __init__(self, n_strikes=10, residual_rms=0.001, forward=100.0):
        self.n_strikes = n_strikes
        self.residual_rms = residual_rms
        self.forward = forward


def test_borrow_identifiability_rules():
    spot = 100.0
    assert borrow_identified(_Parity(), False, spot)
    assert not borrow_identified(None, False, spot)  # no parity regression
    assert not borrow_identified(_Parity(), True, spot)  # zero-carry chain
    assert not borrow_identified(_Parity(n_strikes=3), False, spot)  # thin
    assert not borrow_identified(_Parity(residual_rms=1.0), False, spot)  # noisy


def _borrow_chain(ticker: str, spot: float, borrow: float) -> ChainSnapshot:
    """A clean European chain whose parity forward embeds a borrow rate."""
    from volfit.core.black import black_call

    expiry = date(2026, 12, 18)
    t = (expiry - REF_DATE).days / 365.0
    f = spot * float(np.exp(-borrow * t))  # rate 0, divs 0: only borrow moves F
    quotes = []
    for strike in np.linspace(0.8 * spot, 1.2 * spot, 15):
        k = float(np.log(strike / f))
        c = float(black_call(np.array([k]), np.array([0.04 * t]))[0]) * f
        p = c - (f - strike)  # parity at D = 1
        for cp, px in (("C", c), ("P", p)):
            quotes.append(
                OptionQuote(ticker=ticker, expiry=expiry, strike=float(strike),
                            call_put=cp, bid=px - 0.02, ask=px + 0.02)
            )
    return ChainSnapshot(ticker=ticker, spot=spot,
                         timestamp=datetime(2026, 6, 10, 20, 0), quotes=quotes)


def test_carry_curve_recovers_planted_borrow(monkeypatch):

    borrow = 0.03  # 300 bp hard-to-borrow
    chain = _borrow_chain("ALPHA", 100.0, borrow)
    state = AppState(REF_DATE)
    monkeypatch.setattr(
        type(state.provider), "fetch_chain",
        lambda self, ticker, expiries=None, as_of=None: chain,
        raising=False,
    )
    state.ensure_chain("ALPHA")
    curve = carry_curve(state, "ALPHA")
    assert curve.identified >= 1 and curve.unidentified == len(curve.points) - curve.identified
    pt = next(p for p in curve.points if p.borrowBp is not None)
    # rate 0 + no dividends: theoretical F = spot, so the read is the borrow.
    assert pt.borrowBp == pytest.approx(borrow * 1e4, rel=0.02)
    assert pt.borrowSource == "parity_implied"
    assert pt.forwardSource == "parity_implied"
    assert pt.discountSource == "parity_implied"
    assert curve.rateSource == "desk" and curve.dividendSource == "none"


def test_zero_carry_chain_is_calmly_unidentified():
    state = AppState(REF_DATE)
    tk = state.active_tickers()[0]
    state.ensure_chain(tk)
    snap = state.snapshot(tk)
    state._snapshots[tk] = ChainSnapshot(
        ticker=snap.ticker, spot=snap.spot, timestamp=snap.timestamp,
        quotes=snap.quotes, exercise_style=snap.exercise_style, zero_carry=True,
    )
    state._forwards.pop(tk, None)  # re-derive under the zero-carry pin
    curve = carry_curve(state, tk)
    assert curve.zeroCarry is True
    assert curve.identified == 0
    assert all(p.borrowBp is None and p.borrowSource == "unidentified"
               for p in curve.points)


def test_quality_rollup_and_forward_entry_are_advisory():
    from volfit.api import market, quality, service

    state = AppState(REF_DATE)
    tk = state.active_tickers()[0]
    iso = sorted(state.forwards(tk))[0].isoformat()
    service.calibrate_node(state, tk, iso, "mid")

    report = quality.build_quality_report(state)
    row = next(t for t in report.tickers if t.ticker == tk)
    assert row.carryIdentified + row.carryUnidentified == len(state.forwards(tk))
    node = next(n for n in report.nodes if n.hasFit)
    assert not any("carry" in i or "borrow" in i for i in node.issues)  # advisory

    payload = market.forwards_payload(state, tk)
    for e in payload.entries:  # the same identifiability rule, per entry
        assert (e.impliedBorrowBp is not None) == (
            e.parityNStrikes is not None
            and e.parityNStrikes >= carry_mod.CARRY_MIN_STRIKES
            and e.parityResidualRms <= carry_mod.CARRY_RMS_FRAC * payload.spot
        )

"""Joint borrow / de-Am fixed point (R2 item 11 increment 1, volfit.data.carry_solve).

The decisive contract: an American chain PRICED with a known borrow (the
tree is the market) must give the borrow back through the full loop —
de-Am at the trial carry, European reprice, parity regression, theoretical
forward — while the v0 naive read (parity on the raw AMERICAN mids) is
EEP-biased on the same chain. Plus: discrete dividends ride BOTH legs, the
European short-circuit is exact, ordinary names read ~0, and failure
accounting is explicit (the exit gate's "failure rates explicit").
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest

from volfit.core.american import binomial_price_batch
from volfit.data.carry_solve import MIN_PAIRS, JointBorrowResult, joint_borrow
from volfit.data.types import ChainSnapshot, OptionQuote

REF = date(2026, 6, 10)
EXPIRY = date(2026, 12, 18)
T = (EXPIRY - REF).days / 365.0
SPOT, RATE, VOL = 100.0, 0.04, 0.35


def _chain(borrow: float, *, american: bool = True,
           div_times=None, div_amounts=None) -> ChainSnapshot:
    """Bid = ask = the tree price at the PLANTED carry: the tree is the market."""
    strikes = np.arange(60.0, 141.0, 5.0)
    quotes = []
    for cp in ("C", "P"):
        is_call = np.full(strikes.size, cp == "C")
        px = binomial_price_batch(
            is_call, SPOT, strikes, T, np.full(strikes.size, VOL),
            r=RATE, q=borrow, american=american,
            div_times=div_times, div_amounts=div_amounts,
        )
        for k, p in zip(strikes, px):
            quotes.append(OptionQuote("HTB", EXPIRY, float(k), cp,
                                      bid=float(p), ask=float(p),
                                      timestamp=datetime(2026, 6, 10, 16, 0)))
    return ChainSnapshot(
        "HTB", SPOT, datetime(2026, 6, 10, 16, 0), quotes,
        "american" if american else "european",
    )


def _naive_borrow_bp(snap: ChainSnapshot) -> float:
    """The v0-style read: parity regressed on RAW American mids vs theo."""
    from volfit.data.carry_solve import _paired_mids, _parity_fit

    strikes, c, p = _paired_mids(snap, EXPIRY)
    f_parity, _ = _parity_fit(strikes, c - p)
    return float(np.log(SPOT * np.exp(RATE * T) / f_parity) / T * 1e4)


def test_planted_borrow_recovered_where_naive_read_is_biased():
    planted = 0.03  # 300 bp hard-to-borrow
    snap = _chain(planted)
    res = joint_borrow(snap, EXPIRY, REF, RATE)
    assert res is not None and res.converged
    assert res.n_pairs == 17 and res.deam_failures == 0
    assert abs(res.borrow_bp - 3.0e2) < 20.0  # within 20 bp of the plant
    naive = _naive_borrow_bp(snap)
    # The naive read on raw American mids must be meaningfully worse — the
    # EEP contamination the fixed point exists to remove.
    assert abs(naive - 300.0) > 2.0 * abs(res.borrow_bp - 300.0)


def test_discrete_dividends_ride_both_legs():
    planted = 0.02
    div_times = np.array([T / 2.0])
    div_amounts = np.array([1.5])
    snap = _chain(planted, div_times=div_times, div_amounts=div_amounts)
    res = joint_borrow(snap, EXPIRY, REF, RATE,
                       div_times=div_times, div_amounts=div_amounts)
    assert res is not None and res.converged
    assert abs(res.borrow_bp - 200.0) < 20.0
    # Dropping the schedule from the SOLVE while the market priced it in must
    # visibly bias the read (the "consistent in both legs" clause).
    res_wrong = joint_borrow(snap, EXPIRY, REF, RATE)
    assert res_wrong is not None
    assert abs(res_wrong.borrow_bp - 200.0) > 3.0 * abs(res.borrow_bp - 200.0)


def test_european_short_circuit_is_exact_one_step():
    planted = 0.025
    snap = _chain(planted, american=False)
    res = joint_borrow(snap, EXPIRY, REF, RATE)
    assert res is not None and res.converged and res.iterations == 1
    assert abs(res.borrow_bp - 250.0) < 10.0


def test_ordinary_name_reads_near_zero():
    snap = _chain(0.0)
    res = joint_borrow(snap, EXPIRY, REF, RATE)
    assert res is not None and res.converged
    assert abs(res.borrow_bp) < 10.0


def test_unsupportable_data_returns_none():
    snap = _chain(0.01)
    thin = ChainSnapshot("HTB", SPOT, snap.timestamp,
                         snap.quotes[: 2 * (MIN_PAIRS - 1) : 2], "american")
    assert joint_borrow(thin, EXPIRY, REF, RATE) is None  # too few pairs
    zero_carry = ChainSnapshot("HTB", SPOT, snap.timestamp, snap.quotes,
                               "american", zero_carry=True)
    assert joint_borrow(zero_carry, EXPIRY, REF, RATE) is None  # synthesized
    assert joint_borrow(snap, EXPIRY, EXPIRY, RATE) is None  # t <= 0


def test_continuous_dividend_yield_rides_both_legs():
    planted, dy = 0.02, 0.015
    strikes = np.arange(60.0, 141.0, 5.0)
    quotes = []
    for cp in ("C", "P"):
        is_call = np.full(strikes.size, cp == "C")
        px = binomial_price_batch(is_call, SPOT, strikes, T,
                                  np.full(strikes.size, VOL),
                                  r=RATE, q=dy + planted, american=True)
        for k, p in zip(strikes, px):
            quotes.append(OptionQuote("HTB", EXPIRY, float(k), cp,
                                      bid=float(p), ask=float(p),
                                      timestamp=datetime(2026, 6, 10, 16, 0)))
    snap = ChainSnapshot("HTB", SPOT, datetime(2026, 6, 10, 16, 0), quotes, "american")
    res = joint_borrow(snap, EXPIRY, REF, RATE, dividend_yield=dy)
    assert res is not None and res.converged
    assert abs(res.borrow_bp - 200.0) < 20.0  # the yield leg is not read as borrow


def test_carry_view_joint_read_end_to_end():
    """GET /carry wiring: joint=True fills the joint fields off the fixed
    point; joint=False leaves them None (the v0 payload, byte-identical)."""
    from volfit.api.carry import carry_curve
    from volfit.api.schemas import MarketSettings
    from volfit.api.state import AppState
    from volfit.replay_report import _StoredChains

    snap = _chain(0.03)
    state = AppState(REF, provider=_StoredChains({"HTB": snap}))
    state.set_expiries("HTB", [EXPIRY])
    state.set_market_settings("HTB", MarketSettings(rate=RATE))

    plain = carry_curve(state, "HTB")
    assert plain.points[0].jointBorrowBp is None  # v0 untouched by default
    joint = carry_curve(state, "HTB", joint=True)
    pt = joint.points[0]
    assert pt.jointConverged is True and pt.jointDeamFailures == 0
    assert abs(pt.jointBorrowBp - 300.0) < 20.0
    # The v0 column stays alongside for the trader comparison. On this clean
    # flat-vol no-dividend chain the two AGREE (v0 rides _refine_american's
    # lumped-carry de-Am, which handles flat carry well) — the joint solve's
    # edge is the discrete-dividend case, locked above where dropping the
    # schedule biases the read 3x.
    assert pt.borrowBp is not None and abs(pt.borrowBp - pt.jointBorrowBp) < 20.0

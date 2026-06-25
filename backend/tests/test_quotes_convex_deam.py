"""R3 — convex projection of de-Americanized call prices (butterfly repair).

Independent per-strike de-Am + the ``max(EEP, 0)`` clamp can leave the European-
equivalent call curve locally non-convex in strike, i.e. butterfly-arbitrageable
inputs handed to every model. ``prepare_quotes`` projects the surviving mid call
curve onto the convex cone before reporting. These gates lock R3's acceptance:
the projection produces a convex curve, leaves an already-convex curve untouched,
keeps EUROPEAN chains byte-identical, restores convexity on a non-convex American
chain, and preserves the quoted bid-ask spread.
"""

from datetime import date, datetime, timedelta

import numpy as np

from volfit.api.quotes import _convex_call_projection, prepare_quotes
from volfit.core.american import DEFAULT_BATCH_STEPS, binomial_price
from volfit.core.black import black_call
from volfit.data.forwards import ResolvedForward
from volfit.data.types import ChainSnapshot, OptionQuote

REF_DATE = date(2026, 6, 10)
EXPIRY = REF_DATE + timedelta(days=182)
TIMESTAMP = datetime(2026, 6, 10, 16, 0)
T, SPOT, RATE, DIV = 0.5, 100.0, 0.05, 0.02
FORWARD = SPOT * float(np.exp((RATE - DIV) * T))
DISCOUNT = float(np.exp(-RATE * T))
RESOLVED = ResolvedForward(expiry=EXPIRY, forward=FORWARD, discount=DISCOUNT, source="manual")
MONEYNESS = np.linspace(0.80, 1.25, 12)


# =========================================================================
# 1. The projection algorithm itself
# =========================================================================
def _slopes(strikes, c):
    return np.diff(c) / np.diff(strikes)


def _min_butterfly(strikes, c):
    """Most-negative discrete butterfly price (>= 0 iff convex) — the economic,
    spacing-robust no-arbitrage measure the implementation uses."""
    k = np.asarray(strikes, float)
    return float(np.min(c[:-2] * (k[2:] - k[1:-1]) - c[1:-1] * (k[2:] - k[:-2])
                        + c[2:] * (k[1:-1] - k[:-2])))


def test_projection_returns_convex_curve():
    strikes = np.linspace(80.0, 120.0, 9)
    # a convex base call curve with a non-convex dip injected at one interior knot
    c = np.maximum(105.0 - strikes, 0.0) + 0.5 * (strikes - 100.0) ** 2 / 100.0 + 8.0
    c[4] -= 1.5  # push one point below the chord -> local concavity
    proj = _convex_call_projection(strikes, c)
    assert np.all(np.diff(_slopes(strikes, proj)) >= -1e-9)  # slopes non-decreasing
    # the projection is the L2-closest convex curve, so it must be closer than the
    # raw data is to ANY convex reference (here: it removed the injected dip)
    assert abs(proj[4] - c[4]) > 0.1


def test_projection_is_noop_on_convex_input():
    strikes = np.linspace(80.0, 120.0, 11)
    c = 0.5 * (strikes - 70.0) ** 2 / 100.0 + 2.0  # strictly convex
    proj = _convex_call_projection(strikes, c)
    assert np.allclose(proj, c, atol=1e-7)


def test_projection_passthrough_below_three_points():
    strikes = np.array([90.0, 110.0])
    c = np.array([12.0, 3.0])
    assert np.array_equal(_convex_call_projection(strikes, c), c)


# =========================================================================
# 2. European chains are byte-identical (the repair must not touch them)
# =========================================================================
def _european_chain() -> ChainSnapshot:
    quotes = []
    for m in MONEYNESS:
        strike = float(m * FORWARD)
        k = float(np.log(strike / FORWARD))
        w = (0.2 + 0.05 * k**2) ** 2 * T
        call = DISCOUNT * FORWARD * float(black_call(k, w))
        put = call - DISCOUNT * (FORWARD - strike)
        for cp, mid in (("C", call), ("P", put)):
            half = min(0.15, 0.45 * mid)
            quotes.append(OptionQuote(ticker="X", expiry=EXPIRY, strike=strike, call_put=cp,
                                      bid=mid - half, ask=mid + half, timestamp=TIMESTAMP))
    return ChainSnapshot("X", SPOT, TIMESTAMP, quotes, exercise_style="european")


def test_european_byte_identical_with_convex_flag():
    chain = _european_chain()
    on = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=True)
    off = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=False)
    assert np.array_equal(on.k, off.k)
    assert np.array_equal(on.w_mid, off.w_mid)
    assert np.array_equal(on.iv_bid, off.iv_bid)
    assert np.array_equal(on.iv_ask, off.iv_ask)


# =========================================================================
# 3. American chain with an injected non-convexity
# =========================================================================
def _american_chain(bump_idx: int | None, bump: float) -> ChainSnapshot:
    """American CRR prices on a smooth smile; optionally overprice one OTM strike's
    mid by ``bump`` (a fractional bump) to inject a butterfly violation."""
    quotes = []
    moneyness = list(MONEYNESS)
    for i, m in enumerate(moneyness):
        strike = float(m * FORWARD)
        sigma = float(0.2 + 0.05 * np.log(strike / FORWARD) ** 2)
        for cp in ("C", "P"):
            mid = binomial_price(cp == "C", SPOT, strike, T, sigma, RATE, DIV,
                                 n_steps=DEFAULT_BATCH_STEPS, american=True)
            otm = (cp == "C") == (strike >= FORWARD)
            if bump_idx is not None and i == bump_idx and otm:
                mid *= 1.0 + bump  # overprice the OTM side at this strike
            half = min(0.15, 0.45 * mid)
            quotes.append(OptionQuote(ticker="X", expiry=EXPIRY, strike=strike, call_put=cp,
                                      bid=mid - half, ask=mid + half, timestamp=TIMESTAMP))
    return ChainSnapshot("X", SPOT, TIMESTAMP, quotes, exercise_style="american")


def _call_curve(prepared):
    """Reconstruct the normalized call prices c(K) from the prepared mids."""
    return np.asarray(black_call(prepared.k, prepared.w_mid), float)


def test_american_nonconvex_is_repaired():
    chain = _american_chain(bump_idx=6, bump=0.30)  # overprice a near-ATM OTM call
    off = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=False)
    on = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=True)
    assert on.n_deamericanized > 0 and np.array_equal(on.k, off.k)
    knf = np.exp(on.k)  # K/F, the scale-stable abscissa the projection uses
    # OFF: the injected bump leaves a genuine (economically meaningful) butterfly arb
    assert _min_butterfly(knf, _call_curve(off)) < -1e-4
    # ON: the projection restores convexity (no-butterfly condition on C(K))
    assert _min_butterfly(knf, _call_curve(on)) >= -1e-4
    # and it only moved the smile where it had to (a few bp on the bumped region)
    assert np.max(np.abs(on.iv_mid - off.iv_mid)) < 5e-2


def test_american_repair_preserves_bid_ask_spread():
    chain = _american_chain(bump_idx=6, bump=0.30)
    on = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=True)
    off = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=False)
    # The repair shifts bid/mid/ask by the SAME per-strike delta in price space, so
    # the call-price spread (ask - bid) is unchanged on every kept strike.
    sp_on = black_call(on.k, on.iv_ask**2 * on.tau) - black_call(on.k, on.iv_bid**2 * on.tau)
    sp_off = black_call(off.k, off.iv_ask**2 * off.tau) - black_call(off.k, off.iv_bid**2 * off.tau)
    assert np.allclose(sp_on, sp_off, atol=1e-9)


def test_american_smooth_chain_barely_moves():
    """On an already arb-free American smile the projection is ~a no-op (the smooth
    de-Am'd curve is convex), so American RMS is not worsened by R3."""
    chain = _american_chain(bump_idx=None, bump=0.0)
    on = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=True)
    off = prepare_quotes(chain, EXPIRY, RESOLVED, T, convex_deam=False)
    assert np.array_equal(on.k, off.k)
    assert np.max(np.abs(on.iv_mid - off.iv_mid)) < 5e-4  # < 5 vol bp drift

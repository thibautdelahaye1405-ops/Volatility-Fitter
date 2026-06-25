"""Robust parity forward on noisy/stale live data ([REQ 2026-06-25]).

The parity SLOPE is the discount — the worst-identified parameter — and on a noisy
delayed feed (wide/stale deep-ITM quotes) the equal-weight regression drifts to an
implied discount > 1 (a negative rate), tilting the forward and gapping the smile at
the money. When a reference date is supplied (the fitting path), ``implied_forward``
clamps the discount to a physical rate band and re-derives the forward from the
well-identified level. These tests pin: (1) a clean chain is unchanged/recovered to
truth; (2) stale wings that break the unclamped fit stay sane once clamped;
(3) zero-spread close-like data still resolves; (4) no reference date = legacy.
"""

from datetime import date, datetime

import numpy as np

from volfit.core.black import black_call
from volfit.data.forwards import RATE_MAX, RATE_MIN, implied_forward
from volfit.data.types import ChainSnapshot, OptionQuote

SPOT, RATE, DIV, VOL = 100.0, 0.045, 0.01, 0.20
REF, EXPIRY = date(2026, 6, 10), date(2026, 7, 10)  # ~30d, the short-dated case that broke
T = (EXPIRY - REF).days / 365.0
F_TRUE = SPOT * np.exp((RATE - DIV) * T)
D_TRUE = np.exp(-RATE * T)


def _chain(corrupt: bool = False, zero_spread: bool = False) -> ChainSnapshot:
    """Exact European parity prices at a flat vol; optionally make the ITM calls
    stale (mid biased ABOVE true and wide-spread, growing with depth — the real
    `mid > last` pattern that tilts the parity slope), or quote everything
    zero-spread (close-like)."""
    quotes: list[OptionQuote] = []
    for strike in np.arange(60.0, 141.0, 5.0):
        k = float(np.log(strike / F_TRUE))
        call = float(D_TRUE * F_TRUE * black_call(k, VOL**2 * T))
        put = call - float(D_TRUE * (F_TRUE - strike))
        cmid, ch, ph = call, 0.01 * call, 0.01 * put  # 1% half-spread
        if corrupt and strike < SPOT:  # ITM calls: stale (over-priced) + wide, deeper = worse
            depth = (SPOT - strike) / SPOT
            cmid, ch = call * (1.0 + 0.12 * depth), 0.10 * call
        if zero_spread:
            ch = ph = 0.0
        quotes.append(OptionQuote("X", EXPIRY, float(strike), "C", bid=cmid - ch, ask=cmid + ch))
        quotes.append(OptionQuote("X", EXPIRY, float(strike), "P", bid=put - ph, ask=put + ph))
    return ChainSnapshot("X", SPOT, datetime(2026, 6, 10), quotes, "european")


def test_clean_chain_recovered_to_truth_and_unclamped():
    """On a clean chain the discount sits inside the rate band, so the clamp never
    bites and forward + discount land on truth."""
    f = implied_forward(_chain(), EXPIRY, REF)
    assert f is not None
    assert abs(f.forward / F_TRUE - 1.0) < 1e-3
    assert abs(f.discount / D_TRUE - 1.0) < 1e-3
    assert RATE_MIN <= -np.log(f.discount) / T <= RATE_MAX  # in band -> untouched


def test_stale_wings_break_unclamped_but_clamp_stays_sane():
    """Stale ITM calls tilt the slope: the unclamped fit (no reference date) returns a
    nonsensical discount (> 1, a negative rate); supplying the reference date clamps it
    to a physical rate and re-derives the forward near truth."""
    chain = _chain(corrupt=True)
    unclamped = implied_forward(chain, EXPIRY)  # no reference date -> no clamp
    clamped = implied_forward(chain, EXPIRY, REF)
    assert unclamped is not None and clamped is not None
    # the unclamped fit is broken by the stale wings (discount implies a wild rate)...
    assert unclamped.discount > 1.0 or not (RATE_MIN <= -np.log(unclamped.discount) / T <= RATE_MAX)
    # ...while the clamped discount is physically sane and the forward is near truth.
    assert RATE_MIN <= -np.log(clamped.discount) / T <= RATE_MAX
    assert abs(clamped.forward / F_TRUE - 1.0) < 0.01
    assert abs(clamped.forward / F_TRUE - 1.0) < abs(unclamped.forward / F_TRUE - 1.0)


def test_zero_spread_close_like_data_still_resolves_sane():
    """Close-like data (bid == ask, no spread signal): the clamp + ATM-kernel forward
    re-derivation still yields a sane discount + forward, not the > 1 garbage."""
    f = implied_forward(_chain(corrupt=True, zero_spread=True), EXPIRY, REF)
    assert f is not None
    assert RATE_MIN <= -np.log(f.discount) / T <= RATE_MAX
    assert abs(f.forward / F_TRUE - 1.0) < 0.01


def test_no_reference_date_skips_clamp():
    """Without a reference date the legacy regression is used unchanged (clean chain
    recovers truth; the clamp simply never runs)."""
    legacy = implied_forward(_chain(), EXPIRY)
    assert legacy is not None
    assert abs(legacy.forward / F_TRUE - 1.0) < 1e-3

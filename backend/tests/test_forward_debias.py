"""Regression: American parity bias in the implied forward and the ATM kink.

Put-call parity is an EQUALITY only for European options; regressing raw
American C - P returns a biased (F, D), and quote prep then de-Americanizes
OTM puts (left of the forward) and OTM calls (right of it) under that biased
carry in opposite directions — a visible implied-vol jump at the money.
volfit.data.forwards re-implies the forward from de-Americanized mids when a
reference date is supplied; these tests pin both the bias and the cure on a
controlled flat-vol American chain (the true European smile is exactly flat,
so any ATM jump is the bug).
"""

from datetime import date, datetime

import numpy as np

from volfit.api.quotes import prepare_quotes
from volfit.core.american import binomial_price
from volfit.data import forwards as forwards_mod
from volfit.data.forwards import implied_forward
from volfit.data.types import ChainSnapshot, OptionQuote

# Flat 20% vol, dividend-paying-stock carry; the European smile is flat.
SPOT, RATE, DIV, VOL = 100.0, 0.05, 0.015, 0.20
REF, EXPIRY = date(2026, 6, 10), date(2026, 12, 9)
T = (EXPIRY - REF).days / 365.0
F_TRUE = SPOT * np.exp((RATE - DIV) * T)
D_TRUE = np.exp(-RATE * T)


def _american_chain(style: str = "american") -> ChainSnapshot:
    quotes: list[OptionQuote] = []
    for strike in np.arange(80.0, 121.0, 2.0):
        c = binomial_price(True, SPOT, strike, T, VOL, RATE, DIV, n_steps=501)
        p = binomial_price(False, SPOT, strike, T, VOL, RATE, DIV, n_steps=501)
        quotes.append(OptionQuote("X", EXPIRY, strike, "C", bid=c * 0.99, ask=c * 1.01))
        quotes.append(OptionQuote("X", EXPIRY, strike, "P", bid=p * 0.99, ask=p * 1.01))
    return ChainSnapshot("X", SPOT, datetime(2026, 6, 10), quotes, style)


def _atm_jump(prepared) -> float:
    """Vol-bp gap between the OTM put and OTM call nearest the forward."""
    order = np.argsort(prepared.k)
    k, iv = prepared.k[order], prepared.iv_mid[order]
    left, right = k < 0.0, k >= 0.0
    il, ir = np.nonzero(left)[0][-1], np.nonzero(right)[0][0]
    return 1e4 * abs(iv[ir] - iv[il])


def test_raw_american_forward_is_biased_and_kinks():
    """Without a reference date the raw-mid regression keeps the bias/kink."""
    chain = _american_chain()
    raw = implied_forward(chain, EXPIRY)  # no reference date -> raw behavior
    assert abs(raw.forward / F_TRUE - 1.0) > 1e-3  # > 10 bp forward bias
    jump = _atm_jump(prepare_quotes(chain, EXPIRY, raw, T))
    assert jump > 40.0  # tens of vol bp jump at the money (the bug)


def test_debias_recovers_discount_and_forward_and_smooths():
    """With a reference date the joint refinement recovers BOTH the forward and
    the discount ([REQ 2026-07-11], the SPY 17-Jun-27 kink): the raw parity
    slope is EEP-contaminated (here D = 1.0047, an impossible negative rate on
    a 5% chain), and under that rate the binomial model prices no early
    exercise at all, so the historical forward-only de-bias had nothing to act
    on. The de-Americanized put/call IV gap at the switch identifies the rate;
    on this controlled chain it recovers r to a few tens of bp."""
    chain = _american_chain()
    raw = implied_forward(chain, EXPIRY)
    fixed = implied_forward(chain, EXPIRY, REF)
    # The raw slope is contaminated (D > 1); the refinement lands near truth.
    assert raw.discount > 1.0
    r_fixed = -np.log(fixed.discount) / T
    assert abs(r_fixed - RATE) < 5e-3  # rate recovered within 50 bp
    assert abs(fixed.forward / F_TRUE - 1.0) < 2e-3  # within ~20 bp of truth
    assert abs(fixed.forward / F_TRUE - 1.0) < abs(raw.forward / F_TRUE - 1.0)
    # The de-Am'd parity residual collapses and the kink is gone.
    assert fixed.residual_rms < 0.1 * raw.residual_rms
    assert _atm_jump(prepare_quotes(chain, EXPIRY, fixed, T)) < 15.0


def test_short_dated_chain_keeps_raw_discount():
    """Short-dated: EEP ~ 0 makes the rate unidentifiable AND the kink
    invisible — the gate keeps the raw regressed discount bit-for-bit (the
    historical behavior for every chain whose sides already join)."""
    expiry = date(2026, 6, 24)  # two weeks
    t = (expiry - REF).days / 365.0
    quotes: list[OptionQuote] = []
    for strike in np.arange(90.0, 111.0, 2.0):
        c = binomial_price(True, SPOT, strike, t, VOL, RATE, DIV, n_steps=501)
        p = binomial_price(False, SPOT, strike, t, VOL, RATE, DIV, n_steps=501)
        quotes.append(OptionQuote("X", expiry, strike, "C", bid=c * 0.99, ask=c * 1.01))
        quotes.append(OptionQuote("X", expiry, strike, "P", bid=p * 0.99, ask=p * 1.01))
    chain = ChainSnapshot("X", SPOT, datetime(2026, 6, 10), quotes, "american")
    raw = implied_forward(chain, expiry)
    fixed = implied_forward(chain, expiry, REF)
    # The pre-existing physical-band clamp may bound the raw slope (it does
    # here: 2-week slope noise reads as an absurd rate); the REFINEMENT must
    # pass that pre-refine discount through untouched.
    d_clamped = min(
        max(raw.discount, np.exp(-forwards_mod.RATE_MAX * t)),
        np.exp(-forwards_mod.RATE_MIN * t),
    )
    assert fixed.discount == d_clamped


def test_debiased_smile_has_no_localized_atm_spike():
    """The de-biased smile is smooth: the ATM put->call transition is no
    bigger than a few typical adjacent steps (the raw smile spikes there)."""
    chain = _american_chain()
    prepared = prepare_quotes(chain, EXPIRY, implied_forward(chain, EXPIRY, REF), T)
    order = np.argsort(prepared.k)
    steps = np.abs(np.diff(prepared.iv_mid[order]))  # adjacent IV steps
    atm_jump_bp = _atm_jump(prepared)
    typical_bp = 1e4 * float(np.median(steps))
    assert atm_jump_bp < 3.0 * typical_bp + 5.0  # no spike localized at ATM


def test_european_chain_unaffected_by_reference_date():
    """European snapshots never de-Americanize: ref date changes nothing."""
    chain = _american_chain(style="european")
    without = implied_forward(chain, EXPIRY)
    with_ref = implied_forward(chain, EXPIRY, REF)
    assert without.forward == with_ref.forward
    assert without.discount == with_ref.discount

"""Discrete cash-dividend de-Americanization removes the ex-date ATM kink.

A flat-vol American chain priced WITH a mid-period cash dividend has a flat
European smile. The continuous-yield de-Americanization smears the dividend
into an average yield and mis-models the call/put early-exercise asymmetry
near the ex-date -> an implied-vol jump at the money. Routing de-Am through
the discrete escrowed cash schedule (forward-consistent amounts) recovers the
flat smile. Also checks the escrowed pricer's European leg equals Black at the
escrowed forward, and the schedule scaling matches the forward.
"""

from datetime import date, datetime

import numpy as np

from volfit.api.quotes import prepare_quotes
from volfit.core.american import binomial_price
from volfit.core.black import black_call
from volfit.data.dividends import (
    Dividend,
    DividendModel,
    forward_consistent_cash_schedule,
)
from volfit.data.forwards import ResolvedForward
from volfit.data.types import ChainSnapshot, OptionQuote

SPOT, RATE, VOL = 100.0, 0.05, 0.20
REF, EXPIRY = date(2026, 6, 10), date(2026, 12, 9)
T = (EXPIRY - REF).days / 365.0
DIV_AMT, DIV_TAU = 2.0, 0.25  # $2 cash, ~3M out
EX_DATE = date.fromordinal(REF.toordinal() + round(DIV_TAU * 365))
TAU = (EX_DATE - REF).days / 365.0
PV0 = DIV_AMT * np.exp(-RATE * TAU)
F_TRUE = (SPOT - PV0) * np.exp(RATE * T)
D_TRUE = np.exp(-RATE * T)

_DIVT = np.array([TAU])
_DIVA = np.array([DIV_AMT])


def _chain() -> ChainSnapshot:
    quotes: list[OptionQuote] = []
    for strike in np.arange(82.0, 119.0, 2.0):
        c = binomial_price(True, SPOT, strike, T, VOL, RATE, 0.0, 801, True, _DIVT, _DIVA)
        p = binomial_price(False, SPOT, strike, T, VOL, RATE, 0.0, 801, True, _DIVT, _DIVA)
        quotes.append(OptionQuote("X", EXPIRY, strike, "C", bid=c * 0.99, ask=c * 1.01))
        quotes.append(OptionQuote("X", EXPIRY, strike, "P", bid=p * 0.99, ask=p * 1.01))
    return ChainSnapshot("X", SPOT, datetime(2026, 6, 10), quotes, "american")


def _forward() -> ResolvedForward:
    return ResolvedForward(EXPIRY, F_TRUE, D_TRUE, "parity")


def _atm_jump(prepared) -> float:
    order = np.argsort(prepared.k)
    k, iv = prepared.k[order], prepared.iv_mid[order]
    il, ir = np.nonzero(k < 0)[0][-1], np.nonzero(k >= 0)[0][0]
    return 1e4 * abs(iv[ir] - iv[il])


def test_escrowed_european_leg_matches_black():
    """The escrowed-tree European price equals Black at the escrowed forward."""
    for strike in (90.0, 100.0, 110.0):
        k = np.log(strike / F_TRUE)
        euro = binomial_price(True, SPOT, strike, T, VOL, RATE, 0.0, 801, False, _DIVT, _DIVA)
        black = D_TRUE * F_TRUE * float(black_call(k, VOL**2 * T))
        assert abs(euro - black) < 5e-3  # tree discretization, < 0.5 cent


def test_schedule_is_forward_consistent():
    """The forward-consistent schedule reproduces the true dividend (alpha~1)."""
    model = DividendModel(mode="discrete_absolute", dividends=(Dividend(EX_DATE, DIV_AMT),))
    sched = forward_consistent_cash_schedule(SPOT, F_TRUE, RATE, T, model, REF)
    assert sched is not None
    times, amounts = sched
    assert times[0] == TAU
    np.testing.assert_allclose(amounts[0], DIV_AMT, rtol=1e-6)  # alpha == 1


def test_continuous_q_kinks_discrete_smooths():
    """Continuous-yield de-Am kinks at ATM; discrete de-Am removes it."""
    chain = _chain()
    fwd = _forward()
    cont = prepare_quotes(chain, EXPIRY, fwd, T)  # continuous-q de-Am
    model = DividendModel(mode="discrete_absolute", dividends=(Dividend(EX_DATE, DIV_AMT),))
    times, amounts = forward_consistent_cash_schedule(SPOT, F_TRUE, RATE, T, model, REF)
    disc = prepare_quotes(chain, EXPIRY, fwd, T, (times, amounts, RATE))

    assert _atm_jump(cont) > 25.0  # continuous-q leaves a visible ATM kink
    assert _atm_jump(disc) < 12.0  # discrete schedule joins the two sides
    # The discrete-de-Am smile is the flat 20% European surface it was built on.
    assert np.max(np.abs(disc.iv_mid - VOL)) < 4e-3


def test_non_physical_rate_falls_back():
    """When the rate is too low to admit positive dividends, None (fall back)."""
    model = DividendModel(mode="discrete_absolute", dividends=(Dividend(EX_DATE, DIV_AMT),))
    # rate 0 with a forward above spot implies negative dividends -> None.
    assert forward_consistent_cash_schedule(SPOT, F_TRUE, 0.0, T, model, REF) is None

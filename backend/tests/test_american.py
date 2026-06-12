"""American pricing & de-Americanization: convergence, bounds, round trips.

Invariants:
1. The European leg of the CRR tree converges to Black-Scholes (golden
   anchor for the discretization).
2. No-early-exercise theorems hold on the tree: an American call on a
   non-dividend-paying stock equals the European; American >= European
   always; deep-ITM American puts sit at (or above) intrinsic under
   positive rates.
3. De-Americanization round-trips: price a put with known sigma, invert,
   recover sigma to root-finder precision; on a dividend-free call it
   reduces to the plain Black implied vol.
4. Unusable prices (below intrinsic, above static bounds) come back nan,
   matching core.black's convention.
"""

import numpy as np
import pytest

from volfit.core.american import binomial_price, deamericanize
from volfit.core.black import black_call, implied_total_variance

S, T, SIGMA, R, Q = 100.0, 0.75, 0.25, 0.04, 0.02


def black_dollar_call(s, k, t, sigma, r=0.0, q=0.0) -> float:
    """Dollar Black-Scholes call from the normalized-forward black_call."""
    forward = s * np.exp((r - q) * t)
    return float(np.exp(-r * t) * forward * black_call(np.log(k / forward), sigma**2 * t))


def test_european_leg_converges_to_black():
    for k in (80.0, 100.0, 125.0):
        tree = binomial_price(True, S, k, T, SIGMA, R, Q, n_steps=801, american=False)
        bs = black_dollar_call(S, k, T, SIGMA, R, Q)
        assert tree == pytest.approx(bs, abs=3e-3), k  # < 0.3 cents on spot 100


def test_american_call_no_dividends_equals_european():
    for k in (90.0, 100.0, 110.0):
        eu = binomial_price(True, S, k, T, SIGMA, R, 0.0, american=False)
        am = binomial_price(True, S, k, T, SIGMA, R, 0.0, american=True)
        assert am == pytest.approx(eu, abs=1e-10), k


def test_american_dominates_european_and_intrinsic():
    for is_call in (True, False):
        for k in (70.0, 100.0, 140.0):
            eu = binomial_price(is_call, S, k, T, SIGMA, R, Q, american=False)
            am = binomial_price(is_call, S, k, T, SIGMA, R, Q, american=True)
            intrinsic = max(S - k, 0.0) if is_call else max(k - S, 0.0)
            assert am >= eu - 1e-12 and am >= intrinsic - 1e-12, (is_call, k)
    # Early exercise is strictly valuable for an ITM put under positive rates.
    eu_put = binomial_price(False, S, 140.0, T, SIGMA, R, 0.0, american=False)
    am_put = binomial_price(False, S, 140.0, T, SIGMA, R, 0.0, american=True)
    assert am_put > eu_put + 1e-3


def test_early_exercise_premium_increases_with_rate():
    premiums = [
        binomial_price(False, S, 120.0, T, SIGMA, r, 0.0)
        - binomial_price(False, S, 120.0, T, SIGMA, r, 0.0, american=False)
        for r in (0.0, 0.03, 0.08)
    ]
    assert premiums[0] == pytest.approx(0.0, abs=1e-10)  # r=0: never exercise
    assert premiums[0] < premiums[1] < premiums[2]


def test_deamericanize_round_trip():
    for is_call, k in ((False, 95.0), (False, 120.0), (True, 105.0)):
        price = binomial_price(is_call, S, k, T, SIGMA, R, Q)
        sigma = deamericanize(is_call, price, S, k, T, R, Q)
        assert sigma == pytest.approx(SIGMA, abs=1e-7), (is_call, k)


def test_deamericanize_reduces_to_black_without_dividends():
    # Dividend-free call: American == European, so the de-Americanized vol
    # must equal the plain Black implied vol up to tree discretization.
    k = 110.0
    price = black_dollar_call(S, k, T, SIGMA, R, 0.0)
    sigma = deamericanize(True, price, S, k, T, R, 0.0)
    forward = S * np.exp(R * T)
    w = float(implied_total_variance(np.log(k / forward), price * np.exp(R * T) / forward))
    assert sigma == pytest.approx(np.sqrt(w / T), abs=5e-4)


def test_unusable_prices_are_nan():
    assert np.isnan(deamericanize(False, 19.9, S, 120.0, T, R))  # below intrinsic
    assert np.isnan(deamericanize(True, 100.1, S, 90.0, T, R))  # above spot
    assert np.isnan(deamericanize(False, 120.1, S, 120.0, T, R))  # above strike

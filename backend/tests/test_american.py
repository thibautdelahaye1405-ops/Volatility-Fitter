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
5. The batch path is the scalar path: binomial_price_batch matches
   binomial_price to machine precision at equal depth, deamericanize_batch
   matches the scalar root-finder, and unusable quotes go nan without
   poisoning the rest of the batch.
"""

import numpy as np
import pytest

from volfit.core.american import (
    DEFAULT_BATCH_STEPS,
    binomial_price,
    binomial_price_batch,
    deamericanize,
    deamericanize_batch,
)
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


# ------------------------------------------------------------- batch path

# Mixed chain: deep/near wings, alternating call/put, vol from 18% to 55%.
KS = np.array([70.0, 85.0, 95.0, 100.0, 105.0, 115.0, 130.0, 150.0])
IS_CALL = np.array([True, False, True, False, True, False, True, False])
SIGMAS = np.array([0.18, 0.22, 0.25, 0.28, 0.32, 0.38, 0.45, 0.55])
RB, QB = 0.04, 0.01


def scalar_prices(american: bool) -> np.ndarray:
    return np.array(
        [
            binomial_price(
                bool(IS_CALL[i]), S, float(KS[i]), T, float(SIGMAS[i]),
                RB, QB, n_steps=DEFAULT_BATCH_STEPS, american=american,
            )
            for i in range(KS.size)
        ]
    )


def test_batch_pricer_matches_scalar_european():
    batch = binomial_price_batch(IS_CALL, S, KS, T, SIGMAS, RB, QB, american=False)
    np.testing.assert_allclose(batch, scalar_prices(american=False), rtol=0.0, atol=1e-12)


def test_batch_pricer_matches_scalar_american():
    batch = binomial_price_batch(IS_CALL, S, KS, T, SIGMAS, RB, QB, american=True)
    np.testing.assert_allclose(batch, scalar_prices(american=True), rtol=0.0, atol=1e-12)


def test_batch_pricer_intrinsic_at_expiry_and_nan_on_bad_probability():
    expired = binomial_price_batch(IS_CALL[:2], S, KS[:2], 0.0, SIGMAS[:2], RB, QB)
    np.testing.assert_allclose(expired, [30.0, 0.0])  # call k=70, put k=85
    # Near-zero sigma against the drift pushes the CRR probability out of
    # (0,1): that quote goes nan, the healthy one in the same batch survives.
    out = binomial_price_batch(
        np.array([True, True]), S, np.array([100.0, 100.0]), T,
        np.array([1e-5, 0.25]), RB, QB,
    )
    assert np.isnan(out[0]) and np.isfinite(out[1])


def test_deamericanize_batch_matches_scalar():
    prices = scalar_prices(american=True)
    batch = deamericanize_batch(IS_CALL, prices, S, KS, T, RB, QB)
    for i in range(KS.size):
        scalar = deamericanize(
            bool(IS_CALL[i]), float(prices[i]), S, float(KS[i]), T,
            RB, QB, n_steps=DEFAULT_BATCH_STEPS,
        )
        assert batch[i] == pytest.approx(scalar, abs=2e-4), (IS_CALL[i], KS[i])


def test_deamericanize_batch_round_trip():
    prices = binomial_price_batch(IS_CALL, S, KS, T, SIGMAS, RB, QB)
    recovered = deamericanize_batch(IS_CALL, prices, S, KS, T, RB, QB)
    np.testing.assert_allclose(recovered, SIGMAS, rtol=0.0, atol=1e-6)


def test_deamericanize_batch_nan_cases_do_not_poison_batch():
    # With r=0, q=4% the near-zero-vol American put price is K - S e^{-qT}
    # (its early-exercise floor): a quote below that floor has no vol.
    r0, q0 = 0.0, 0.04
    is_call = np.array([False, True, False, False, False])
    strikes = np.array([120.0, 90.0, 150.0, 150.0, 100.0])
    good = binomial_price(False, S, 100.0, T, 0.3, r0, q0, n_steps=DEFAULT_BATCH_STEPS)
    prices = np.array(
        [
            19.9,  # put below intrinsic 20
            100.1,  # call above spot
            50.0,  # put exactly at intrinsic (strict bound)
            51.0,  # put below its zero-vol floor 150 - 100 e^{-0.03} ~ 52.95
            good,  # healthy quote sharing the batch
        ]
    )
    out = deamericanize_batch(is_call, prices, S, strikes, T, r0, q0)
    assert np.isnan(out[:4]).all()
    assert out[4] == pytest.approx(0.3, abs=1e-6)
    # The scalar agrees that each bad quote is unusable.
    for i in range(4):
        assert np.isnan(
            deamericanize(
                bool(is_call[i]), float(prices[i]), S, float(strikes[i]), T,
                r0, q0, n_steps=DEFAULT_BATCH_STEPS,
            )
        ), i

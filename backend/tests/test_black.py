"""Black formula and implied-variance inversion round trips."""

import numpy as np
import pytest

from volfit.core.black import (
    atm_total_variance,
    black_call,
    black_vega_w,
    implied_total_variance,
)


def test_atm_closed_form_inversion():
    w = 0.04
    price = float(black_call(0.0, w))
    assert atm_total_variance(price) == pytest.approx(w, abs=1e-14)


def test_implied_w_round_trip_grid():
    k = np.linspace(-0.6, 0.5, 23)
    w = 0.02 + 0.08 * np.abs(k) + 0.01  # a crude smile, all strictly positive
    price = black_call(k, w)
    w_back = implied_total_variance(k, price)
    np.testing.assert_allclose(w_back, w, rtol=0, atol=1e-12)


def test_price_monotone_in_variance():
    k = 0.1
    w_grid = np.linspace(1e-4, 1.0, 200)
    prices = black_call(k, w_grid)
    assert np.all(np.diff(prices) > 0)


def test_vega_w_positive_and_consistent():
    k = np.linspace(-0.4, 0.4, 9)
    w = np.full_like(k, 0.05)
    vega = black_vega_w(k, w)
    assert np.all(vega > 0)
    # Finite-difference check of dB/dw.
    h = 1e-7
    fd = (black_call(k, w + h) - black_call(k, w - h)) / (2 * h)
    np.testing.assert_allclose(vega, fd, rtol=1e-6)


def test_arbitrage_violating_price_returns_nan():
    assert np.isnan(implied_total_variance(0.1, 1.5))
    assert np.isnan(implied_total_variance(-0.5, 0.1))  # below intrinsic 1 - e^k

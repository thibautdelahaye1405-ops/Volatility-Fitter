"""Short-dated wing inversion: the OTM price -> IV pipeline (2026-08-31 fix).

Regression locks for the 2-4 day smile display bug: the far-UPSIDE IV curve
was ragged (black_call's erf-based CDF is quantized in ~1e-16 ABSOLUTE steps
and rounds to 0 beyond d ~ -8.3, so inverting prices of 1e-20..1e-60 landed
on saturation noise) and the far DOWNSIDE was drawn flat (implied_w inverted
CALL prices everywhere; on the left the time value drowned in the intrinsic
leg's round-off, the inversion went nan, and fill_nonfinite edge-extended the
last invertible vol). Neither the LQD prices nor the density were wrong —
only the price -> IV inversion.

The fix inverts the OTM instrument per side through a tail-accurate map
(core.black.black_otm / implied_total_variance_otm, Newton on LOG price so
deep-OTM quotes converge instead of crawling one e-fold per step), with puts
priced on their OWN quadrature side (volfit.models.lqd.putside, the mirror
of eq. call_logit of Docs/lqd_model_note.tex).
"""

import numpy as np
import pytest

from volfit.core.black import (
    black_call,
    black_otm,
    implied_total_variance,
    implied_total_variance_otm,
)
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import build_slice

#: ~2-day SPY-like slice: T = 2/365, ATM vol ~23%, left tail heavier.
T_2D = 2.0 / 365.0


@pytest.fixture(scope="module")
def slice_2d():
    return build_slice(LQDParams(L=np.log(0.012), R=np.log(0.008), a=np.zeros(5)))


# --------------------------------------------------------- the reported bug
def test_far_upside_smooth_and_monotone(slice_2d):
    """k in [0.2, 1.0] at 2 days (the report's ragged range): finite,
    strictly increasing vol, and curvature at the smooth-model scale — the
    pre-fix curve had erf-saturation steps orders of magnitude larger."""
    k = np.linspace(0.2, 1.0, 81)
    vol = slice_2d.implied_vol(k, T_2D)
    assert np.all(np.isfinite(vol))
    assert np.all(np.diff(vol) > 0.0)
    assert float(np.max(np.abs(np.diff(vol, 2)))) < 5e-4


def test_far_downside_not_flat_and_monotone(slice_2d):
    """k in [-1.0, -0.45] at 2 days (the report's flat range): finite and
    STRICTLY decreasing toward ATM — a flat fill would zero the differences."""
    k = np.linspace(-1.0, -0.45, 56)
    vol = slice_2d.implied_vol(k, T_2D)
    assert np.all(np.isfinite(vol))
    assert np.all(np.diff(vol) < 0.0)
    assert float(vol[0] - vol[-1]) > 0.05  # a real skew, not a plateau


# ------------------------------------------------------------ put-side path
def test_put_price_left_side_keeps_relative_accuracy(slice_2d):
    """Deep-left puts price at 1e-40..1e-20 — far below one ulp of the
    intrinsic leg, so the parity route C - (1 - e^k) cannot represent them.
    The direct path must stay positive, strictly increasing in k, and match
    parity where parity is still representable."""
    k = np.linspace(-1.0, -0.2, 33)
    p = np.asarray(slice_2d.put_price(k), dtype=float)
    assert np.all(p > 0.0)
    assert np.all(np.diff(p) > 0.0)
    # Parity in the body, where both routes are exact.
    k_body = np.linspace(-0.35, 0.3, 27)
    par = (
        np.asarray(slice_2d.call_price(k_body))
        - np.asarray(slice_2d.put_price(k_body))
        - (1.0 - np.exp(k_body))
    )
    np.testing.assert_allclose(par, 0.0, atol=1e-12)


def test_put_price_continuous_at_left_seam(slice_2d):
    """The direct put and the beyond-grid tail continuation share the seam at
    Q(-Z) (same continuation the martingale ledger uses)."""
    q_lo = float(slice_2d.q_z[0])
    eps = 1e-9
    p_in = float(slice_2d.put_price(q_lo + eps))
    p_out = float(slice_2d.put_price(q_lo - eps))
    assert p_in > 0.0 and p_out > 0.0
    assert abs(p_in - p_out) < 1e-4 * p_in + 1e-15


# ------------------------------------------------------- black.py inversion
def test_otm_inversion_round_trip_extreme_quotes():
    """w -> price -> w round trip at |d| up to ~30 (price ~1e-200): the
    erf-based path died at |d| ~ 8.3; the log-Newton must converge to ~1e-9
    relative everywhere the price is representable."""
    w = 4e-4  # vol ~27% over 2 days
    k = np.concatenate([-np.linspace(0.05, 0.55, 21), np.linspace(0.05, 0.55, 21)])
    price = black_otm(k, np.full_like(k, w))
    assert np.all(price > 0.0)
    w_back = implied_total_variance_otm(k, price)
    np.testing.assert_allclose(w_back, w, rtol=1e-9)


def test_otm_inversion_matches_call_inversion_in_body():
    """Body quotes: the OTM path and the historical call-price path agree to
    the solver tolerance (the calibration pipeline stays on black_call)."""
    k = np.linspace(-0.6, 0.5, 23)
    w = 0.02 + 0.08 * np.abs(k) + 0.01
    call = black_call(k, w)
    w_call = implied_total_variance(k, call)
    otm = np.where(k < 0.0, call - 1.0 + np.exp(k), call)
    w_otm = implied_total_variance_otm(k, otm)
    np.testing.assert_allclose(w_call, w, rtol=0, atol=1e-12)
    np.testing.assert_allclose(w_otm, w, rtol=0, atol=1e-12)


def test_otm_inversion_bounds():
    """Static bounds: nan outside 0 < P < min(1, e^k); zero prices (true
    underflow) are refused, never inverted to a fabricated vol."""
    assert np.isnan(implied_total_variance_otm(-0.5, 0.0))
    assert np.isnan(implied_total_variance_otm(-0.5, float(np.exp(-0.5))))
    assert np.isnan(implied_total_variance_otm(0.3, 1.0))
    assert np.isnan(implied_total_variance_otm(0.3, -1e-30))


def test_implied_w_atm_closed_form_unchanged(slice_2d):
    """k = 0 keeps the closed-form ATM inversion on the call price —
    bit-for-bit what the calibration's w0 handle reads."""
    from volfit.core.black import atm_total_variance

    w0 = float(slice_2d.implied_w(0.0))
    assert w0 == pytest.approx(atm_total_variance(float(slice_2d.call_price(0.0))), abs=0.0)

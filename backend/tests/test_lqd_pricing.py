"""Golden pricing tests: the two published LQD fits of the note.

Using the note's fitted coefficient tables directly exercises the entire
quadrature + pricing pipeline without depending on optimizer behavior.
"""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.core.black import implied_total_variance
from volfit.models.lqd.quadrature import build_slice
from volfit.models.svi_jw import jw_to_raw


@pytest.fixture(scope="module")
def svi_slice():
    return build_slice(bm.SVI_LQD_PARAMS)


@pytest.fixture(scope="module")
def dh_slice():
    return build_slice(bm.DH_LQD_PARAMS)


def test_jw_conversion_matches_note(svi_slice):
    raw = jw_to_raw(bm.SVI_JW_PARAMS)
    assert raw.a == pytest.approx(bm.SVI_RAW.a, abs=1e-9)
    assert raw.b == pytest.approx(bm.SVI_RAW.b, abs=1e-9)
    assert raw.rho == pytest.approx(bm.SVI_RAW.rho, abs=1e-9)
    assert raw.m == pytest.approx(bm.SVI_RAW.m, abs=1e-9)
    assert raw.sigma == pytest.approx(bm.SVI_RAW.sigma, abs=1e-9)


def test_svi_fit_martingale_shift_matches_note(svi_slice):
    assert svi_slice.mu == pytest.approx(bm.SVI_LQD_MU, abs=2e-6)


def test_svi_fit_martingale_integral_is_one(svi_slice):
    assert svi_slice.martingale_check() == pytest.approx(1.0, abs=1e-9)


def test_svi_fit_reproduces_target_smile(svi_slice):
    """Max implied-vol gap vs the SVI target must stay near the note's 1.2 bp."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 66)
    w_target = bm.SVI_RAW.total_variance(k)
    iv_target = np.sqrt(w_target / bm.SVI_T)
    iv_model = svi_slice.implied_vol(k, bm.SVI_T)
    max_err = np.max(np.abs(iv_model - iv_target))
    assert max_err < 2.0e-4  # 2 vol bp


def test_put_call_parity(svi_slice):
    k = np.linspace(-0.4, 0.4, 17)
    parity = svi_slice.call_price(k) - svi_slice.put_price(k)
    np.testing.assert_allclose(parity, 1.0 - np.exp(k), atol=1e-12)


def test_call_curve_monotone_and_convex_in_strike(svi_slice):
    """No-butterfly invariants on the normalized strike grid y = e^k."""
    k = np.linspace(-1.0, 0.8, 400)
    y = np.exp(k)
    c = svi_slice.call_price(k)
    slopes = np.diff(c) / np.diff(y)
    assert np.all(slopes < 1e-12)  # decreasing in strike
    assert np.all(np.diff(slopes) > -1e-9)  # convex in strike


def test_density_positive(svi_slice):
    _, pdf = svi_slice.density()
    assert np.all(pdf > 0)


def test_double_hat_martingale_shift_matches_note(dh_slice):
    assert dh_slice.mu == pytest.approx(bm.DH_LQD_MU, abs=2e-6)


def test_double_hat_reproduces_mixture_smile(dh_slice):
    """Note reports ~11 bp max IV error vs the closed-form mixture target."""
    k = np.linspace(*bm.DH_FIT_RANGE, 101)
    w_target = implied_total_variance(k, bm.double_hat_call(k))
    iv_target = np.sqrt(w_target / bm.DH_T)
    iv_model = dh_slice.implied_vol(k, bm.DH_T)
    max_err = np.max(np.abs(iv_model - iv_target))
    assert max_err < 1.5e-3  # 15 vol bp

    # The target ATM vol is about 41.9% (note section 9.2).
    atm_iv = float(dh_slice.implied_vol(0.0, bm.DH_T))
    assert atm_iv == pytest.approx(0.419, abs=5e-3)


def test_double_hat_density_is_bimodal(dh_slice):
    x, pdf = dh_slice.density()
    body = (x > -0.2) & (x < 0.2)
    pdf_body = pdf[body]
    # Count strict local maxima of the density on the body grid.
    interior = pdf_body[1:-1]
    n_modes = int(np.sum((interior > pdf_body[:-2]) & (interior > pdf_body[2:])))
    assert n_modes == 2


def test_var_swap_strike_is_sane(svi_slice):
    """Var-swap total variance should sit near ATM total variance for this smile
    (slightly above, given the skew)."""
    w_atm = float(svi_slice.implied_w(0.0))
    var_swap = svi_slice.var_swap_strike()
    assert 0.8 * w_atm < var_swap < 1.6 * w_atm

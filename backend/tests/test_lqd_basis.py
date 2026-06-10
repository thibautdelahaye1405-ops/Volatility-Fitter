"""LQD basis: Legendre recursion, endpoint scales, Lee slopes vs the note."""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.models.lqd.basis import endpoint_scales, lee_slopes, legendre_matrix


def test_legendre_recursion_matches_explicit_polynomials():
    """Recursion output vs the explicit P_2..P_6 formulas (eqs. P2-P6)."""
    u = np.linspace(0.001, 0.999, 101)
    x = 1.0 - 2.0 * u
    legendre = legendre_matrix(6, x)
    explicit = {
        2: 6 * u**2 - 6 * u + 1,
        3: -20 * u**3 + 30 * u**2 - 12 * u + 1,
        4: 70 * u**4 - 140 * u**3 + 90 * u**2 - 20 * u + 1,
        5: -252 * u**5 + 630 * u**4 - 560 * u**3 + 210 * u**2 - 30 * u + 1,
        6: 924 * u**6 - 2772 * u**5 + 3150 * u**4 - 1680 * u**3 + 420 * u**2 - 42 * u + 1,
    }
    for n, values in explicit.items():
        np.testing.assert_allclose(legendre[n], values, rtol=0, atol=1e-12)


def test_legendre_orthogonality_on_unit_interval():
    """int_0^1 P_m P_n du = delta_mn / (2n + 1)  (eq. leg_orth)."""
    u = np.linspace(0.0, 1.0, 200001)
    legendre = legendre_matrix(6, 1.0 - 2.0 * u)
    gram = np.trapezoid(legendre[:, None, :] * legendre[None, :, :], u, axis=2)
    expected = np.diag(1.0 / (2.0 * np.arange(7) + 1.0))
    np.testing.assert_allclose(gram, expected, atol=5e-9)


def test_svi_fit_endpoint_scales_match_note():
    a_l, a_r = endpoint_scales(bm.SVI_LQD_PARAMS)
    assert a_l == pytest.approx(bm.SVI_LQD_A_LEFT, abs=5e-8)
    assert a_r == pytest.approx(bm.SVI_LQD_A_RIGHT, abs=5e-8)


def test_double_hat_endpoint_scales_match_note():
    a_l, a_r = endpoint_scales(bm.DH_LQD_PARAMS)
    assert a_l == pytest.approx(bm.DH_LQD_A_LEFT, abs=5e-8)
    assert a_r == pytest.approx(bm.DH_LQD_A_RIGHT, abs=5e-8)


def test_svi_fit_lee_slopes_match_note():
    beta_l, beta_r = lee_slopes(bm.SVI_LQD_PARAMS)
    assert beta_l == pytest.approx(bm.SVI_LQD_BETA_LEFT, abs=2e-7)
    assert beta_r == pytest.approx(bm.SVI_LQD_BETA_RIGHT, abs=2e-7)

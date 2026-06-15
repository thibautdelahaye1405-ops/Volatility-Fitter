"""Model-agnostic diagnostics match the LQD exact handles / var-swap.

The numeric helpers (volfit.models.diagnostics) back non-LQD display fits, so
they must reproduce the dedicated LQD closed forms (volfit.models.lqd.atm and
LQDSlice.var_swap_strike) on an LQD slice to a sensible numeric tolerance.
"""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.models.diagnostics import (
    numeric_density,
    numeric_handles,
    numeric_lee_slopes,
    numeric_var_swap_w,
    weighted_rms_vol,
)
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.quadrature import build_slice
from volfit.models.svi_jw import RawSVI


def test_numeric_handles_match_lqd_exact():
    slice_ = build_slice(bm.SVI_LQD_PARAMS)
    exact = atm_handles(slice_, bm.SVI_T)
    got = numeric_handles(slice_, bm.SVI_T)
    assert abs(got.atm_vol - exact.sigma0) < 1e-6
    assert abs(got.skew - exact.skew) < 1e-3
    assert abs(got.curvature - exact.curvature) < 1e-2


def test_numeric_var_swap_matches_lqd_exact():
    slice_ = build_slice(bm.SVI_LQD_PARAMS)
    exact = slice_.var_swap_strike()
    got = numeric_var_swap_w(slice_)
    np.testing.assert_allclose(got, exact, rtol=2e-4)


def test_numeric_var_swap_on_flat_smile():
    """A flat slice (b = 0, constant w = a) has var-swap variance a exactly."""
    flat = RawSVI(a=0.04 * 0.5, b=0.0, rho=0.0, m=0.0, sigma=1.0)
    w_vs = numeric_var_swap_w(flat)
    np.testing.assert_allclose(w_vs, flat.a, rtol=1e-4)


def test_lee_slopes_match_svi_wings():
    """SVI total-variance wing slopes are b(1 -+ rho) in closed form."""
    raw = bm.SVI_RAW
    left, right = numeric_lee_slopes(raw)
    np.testing.assert_allclose(right, raw.b * (1.0 + raw.rho), rtol=1e-2)
    np.testing.assert_allclose(left, raw.b * (1.0 - raw.rho), rtol=1e-2)


def test_numeric_density_matches_lqd_exact():
    """The Breeden-Litzenberger density reproduces LQDSlice's exact density."""
    slice_ = build_slice(bm.SVI_LQD_PARAMS)
    xq, pdf_exact = slice_.density()
    k, pdf, cdf = numeric_density(slice_)
    # Valid distribution: integrates to 1, CDF monotone in [0, 1].
    np.testing.assert_allclose(float(np.trapezoid(pdf, k)), 1.0, atol=1e-3)
    assert cdf[0] >= 0.0 and abs(cdf[-1] - 1.0) < 1e-6
    assert np.all(np.diff(cdf) >= -1e-12)
    # Matches the exact LQD pdf over the central mass (interp onto the k grid).
    pe = np.interp(k, xq, pdf_exact)
    central = (cdf > 0.05) & (cdf < 0.95)
    assert float(np.max(np.abs(pdf[central] - pe[central]))) < 0.02


def test_weighted_rms_vol():
    """RMS vol error: zero on an exact fit, and weights bias toward weighted quotes."""
    slice_ = build_slice(bm.SVI_LQD_PARAMS)
    t = bm.SVI_T
    k = np.linspace(-0.3, 0.3, 9)
    w_exact = slice_.implied_w(k)
    assert weighted_rms_vol(slice_, k, w_exact, t) == pytest.approx(0.0, abs=1e-9)

    # Perturb the quotes by a known vol bump on one wing; equal-weight RMS is the
    # plain root-mean-square; up-weighting that quote raises the weighted RMS.
    quote_vol = np.sqrt(w_exact / t).copy()
    quote_vol[0] += 0.02  # 2 vol-pt error on the left wing
    w_pert = quote_vol**2 * t
    equal = weighted_rms_vol(slice_, k, w_pert, t)
    plain = float(np.sqrt(np.mean((np.sqrt(slice_.implied_w(k) / t) - quote_vol) ** 2)))
    assert equal == pytest.approx(plain, rel=1e-9)
    up = np.ones(k.size)
    up[0] = 50.0  # heavily weight the erroneous quote
    assert weighted_rms_vol(slice_, k, w_pert, t, up) > equal
    assert weighted_rms_vol(slice_, k, w_exact, t, up) == pytest.approx(0.0, abs=1e-9)


def test_numeric_density_flat_smile_is_lognormal():
    """A flat slice w = a gives the Gaussian log-return density N(-a/2, a)."""
    a = 0.04
    flat = RawSVI(a=a, b=0.0, rho=0.0, m=0.0, sigma=1.0)
    k, pdf, _ = numeric_density(flat)
    expected = np.exp(-0.5 * (k + a / 2.0) ** 2 / a) / np.sqrt(2.0 * np.pi * a)
    np.testing.assert_allclose(pdf, expected, atol=1e-3)


class _WingNaNSlice:
    """A slice that is finite near ATM but non-finite at the far wings — what a
    transported/degenerate fit can produce, which used to emit NaN diagnostics
    that JSON-serialize to null and crashed the aside."""

    def implied_w(self, k):
        k = np.asarray(k, dtype=float)
        return np.where(np.abs(k) > 5.0, np.nan, 0.04 + 0.0 * k)


def test_numeric_diagnostics_are_finite_on_nan_wings():
    from volfit.models.diagnostics import numeric_var_swap_w

    slice_ = _WingNaNSlice()
    left, right = numeric_lee_slopes(slice_)
    assert np.isfinite(left) and np.isfinite(right)  # wings at +-6 are NaN -> 0.0
    h = numeric_handles(slice_, t=0.5)
    assert np.isfinite(h.atm_vol) and np.isfinite(h.skew) and np.isfinite(h.curvature)
    assert np.isfinite(numeric_var_swap_w(slice_))  # integral spans the NaN wings

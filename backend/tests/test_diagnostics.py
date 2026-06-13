"""Model-agnostic diagnostics match the LQD exact handles / var-swap.

The numeric helpers (volfit.models.diagnostics) back non-LQD display fits, so
they must reproduce the dedicated LQD closed forms (volfit.models.lqd.atm and
LQDSlice.var_swap_strike) on an LQD slice to a sensible numeric tolerance.
"""

import numpy as np

from tests import benchmarks as bm
from volfit.models.diagnostics import (
    numeric_handles,
    numeric_lee_slopes,
    numeric_var_swap_w,
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

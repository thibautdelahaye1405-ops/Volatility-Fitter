"""Exact ATM handles vs finite differences of the model implied-vol curve."""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.quadrature import build_slice


@pytest.fixture(scope="module")
def svi_slice():
    return build_slice(bm.SVI_LQD_PARAMS)


def test_atm_level_matches_implied_vol(svi_slice):
    handles = atm_handles(svi_slice, bm.SVI_T)
    iv0 = float(svi_slice.implied_vol(0.0, bm.SVI_T))
    assert handles.sigma0 == pytest.approx(iv0, abs=1e-10)
    # Benchmark sanity: the SPX-like target has ATM vol close to 20.6%.
    assert handles.sigma0 == pytest.approx(0.206, abs=3e-3)


def test_atm_skew_matches_finite_difference(svi_slice):
    handles = atm_handles(svi_slice, bm.SVI_T)
    dk = 5e-4
    iv = svi_slice.implied_vol(np.array([-dk, dk]), bm.SVI_T)
    skew_fd = float((iv[1] - iv[0]) / (2 * dk))
    assert handles.skew == pytest.approx(skew_fd, abs=5e-6)


def test_atm_curvature_matches_finite_difference(svi_slice):
    handles = atm_handles(svi_slice, bm.SVI_T)
    dk = 2e-3
    iv = svi_slice.implied_vol(np.array([-dk, 0.0, dk]), bm.SVI_T)
    curv_fd = float((iv[2] - 2 * iv[1] + iv[0]) / dk**2)
    assert handles.curvature == pytest.approx(curv_fd, rel=2e-3, abs=2e-3)

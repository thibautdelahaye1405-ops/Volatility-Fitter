"""Sigmoid smile model: round trip, interface conformance, benchmark sanity."""

import numpy as np

from tests import benchmarks as bm
from volfit.models.base import SmileModel
from volfit.models.lqd.quadrature import build_slice
from volfit.models.sigmoid import SigmoidSmile, calibrate_sigmoid


def test_round_trip_recovery():
    truth = SigmoidSmile(vol_left=0.32, vol_right=0.17, shift=0.03, width=0.12, t=0.5)
    k = np.linspace(-0.4, 0.4, 31)
    fitted = calibrate_sigmoid(k, truth.implied_w(k), t=0.5)
    np.testing.assert_allclose(fitted.to_vector(), truth.to_vector(), atol=1e-7)


def test_fits_svi_benchmark_reasonably():
    """Sigmoid is a 4-parameter marking curve; it should track the SPX-like
    smile within a couple of vol points but not to LQD accuracy."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    fitted = calibrate_sigmoid(k, w, t=bm.SVI_T)
    err = np.abs(fitted.vol(k) - np.sqrt(w / bm.SVI_T))
    assert err.max() < 0.02


def test_smile_model_protocol_conformance():
    """LQD slices, SVI and sigmoid all satisfy the SmileModel interface."""
    sigmoid = SigmoidSmile(vol_left=0.3, vol_right=0.2, shift=0.0, width=0.1, t=0.5)
    lqd = build_slice(bm.SVI_LQD_PARAMS)
    assert isinstance(sigmoid, SmileModel)
    assert isinstance(lqd, SmileModel)
    assert isinstance(bm.SVI_RAW, SmileModel)

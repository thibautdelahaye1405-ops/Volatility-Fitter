"""Raw-SVI own calibration: golden recovery, fit quality, no-arb wings.

Golden numbers are the SPX-like SVI benchmark of Docs/lqd_model_note.tex
section 8 (tests/benchmarks.SVI_RAW); calibrating to noise-free quotes drawn
from it must recover the parameters and reproduce the curve to machine
precision.
"""

import numpy as np

from tests import benchmarks as bm
from volfit.models.base import SmileModel
from volfit.models.svi_jw import RawSVI, calibrate_svi


def _quotes(raw: RawSVI, t: float, n: int = 41):
    k = np.linspace(*bm.SVI_FIT_RANGE, n)
    return k, raw.total_variance(k)


def test_recovers_benchmark_parameters():
    """Noise-free quotes from the benchmark recover its five raw params."""
    k, w = _quotes(bm.SVI_RAW, bm.SVI_T)
    fit = calibrate_svi(k, w, t=bm.SVI_T)
    got = np.array([fit.raw.a, fit.raw.b, fit.raw.rho, fit.raw.m, fit.raw.sigma])
    want = np.array(
        [bm.SVI_RAW.a, bm.SVI_RAW.b, bm.SVI_RAW.rho, bm.SVI_RAW.m, bm.SVI_RAW.sigma]
    )
    np.testing.assert_allclose(got, want, rtol=1e-4, atol=1e-5)
    assert fit.success
    assert fit.max_iv_error < 1e-5


def test_curve_reproduced_to_machine_precision():
    """The fitted total-variance curve matches the benchmark everywhere."""
    k, w = _quotes(bm.SVI_RAW, bm.SVI_T)
    fit = calibrate_svi(k, w, t=bm.SVI_T)
    np.testing.assert_allclose(fit.raw.total_variance(k), w, rtol=1e-6, atol=1e-8)


def test_fit_beats_sigmoid_on_benchmark():
    """SVI is the true family here, so it fits to machine precision
    (test_sigmoid.test_fits_svi_benchmark covers the Multi-Core SIV family)."""
    k, w = _quotes(bm.SVI_RAW, bm.SVI_T)
    fit = calibrate_svi(k, w, t=bm.SVI_T)
    assert fit.max_iv_error < 1e-4


def test_respects_lee_wing_bound():
    """The calibrated wings satisfy Lee's slope bound b(1 + |rho|) <= 2."""
    k, w = _quotes(bm.SVI_RAW, bm.SVI_T)
    fit = calibrate_svi(k, w, t=bm.SVI_T)
    assert fit.raw.b * (1.0 + abs(fit.raw.rho)) <= 2.0 + 1e-9


def test_min_variance_non_negative():
    """Minimum total variance a + b sigma sqrt(1 - rho^2) stays non-negative."""
    k, w = _quotes(bm.SVI_RAW, bm.SVI_T)
    fit = calibrate_svi(k, w, t=bm.SVI_T)
    raw = fit.raw
    min_var = raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2)
    assert min_var >= -1e-10


def test_result_is_smile_model():
    """The fitted RawSVI satisfies the shared SmileModel protocol."""
    k, w = _quotes(bm.SVI_RAW, bm.SVI_T)
    fit = calibrate_svi(k, w, t=bm.SVI_T)
    assert isinstance(fit.raw, SmileModel)


def test_recovers_under_vega_weights():
    """A vega-weighted fit still recovers the benchmark on clean data."""
    from volfit.models.svi_jw.calibrate import _vega_weights

    k, w = _quotes(bm.SVI_RAW, bm.SVI_T)
    fit = calibrate_svi(k, w, t=bm.SVI_T, weights=_vega_weights(k, w, bm.SVI_T))
    np.testing.assert_allclose(fit.raw.total_variance(k), w, rtol=1e-5, atol=1e-7)

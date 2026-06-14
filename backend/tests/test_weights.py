"""Time-value density quote weights (volfit.calib.weights).

Golden numbers come from Docs/iv_time_value_density_weights.tex: the worked
5-quote example and the uniform-grid benchmark (w_i = TV_i). Also checks the
OTM time-value definition and that the scheme actually moves a fit relative to
equal weighting across every model family.
"""

import numpy as np
import pytest

from volfit.calib.weights import otm_time_value, resolve_weights, tv_density_weights
from volfit.core.black import black_call
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import calibrate_svi


def test_doc_worked_example():
    """Reproduce the note's five-quote example exactly (uncapped)."""
    x = np.array([-0.50, -0.10, 0.00, 0.05, 0.80])
    tv = np.array([0.10, 0.40, 0.50, 0.45, 0.08])
    w = tv_density_weights(x, tv, max_mult=None)
    np.testing.assert_allclose(w, [0.107, 0.267, 0.100, 0.480, 0.160], atol=5e-4)


def test_uniform_grid_reduces_to_time_value():
    """On a uniform x-grid all spacings are equal, so w_i = TV_i (the benchmark)."""
    x = np.linspace(-2.0, 2.0, 21)
    tv = np.random.default_rng(1).uniform(0.05, 0.5, x.size)
    np.testing.assert_allclose(tv_density_weights(x, tv, max_mult=None), tv)


def test_dense_region_downweighted():
    """A crowded strike gets less weight than its raw time value implies."""
    x = np.array([-0.5, -0.02, 0.0, 0.02, 0.8])  # three points crowd ATM
    tv = np.full(5, 0.3)  # equal time value -> only spacing matters
    w = tv_density_weights(x, tv, max_mult=None)
    assert w[2] < w[0] and w[2] < w[4]  # the crowded centre is downweighted


def test_otm_time_value_matches_black():
    """TV is the OTM normalized option price: call for k>=0, put for k<0."""
    k = np.array([-0.3, 0.0, 0.3])
    w = np.array([0.04, 0.04, 0.04])
    tv = otm_time_value(k, w)
    call = black_call(k, w)
    assert tv[1] == pytest.approx(call[1])  # ATM
    assert tv[2] == pytest.approx(call[2])  # OTM call
    # OTM put = call - (1 - e^k), and positive.
    assert tv[0] == pytest.approx(call[0] - (1.0 - np.exp(-0.3)))
    assert np.all(tv > 0.0)


def test_resolve_weights_equal_is_none_and_tv_is_mean_one():
    k = np.linspace(-0.3, 0.3, 11)
    w = (0.2 - 0.3 * k) ** 2 * 0.25
    assert resolve_weights("equal", k, w) is None
    wts = resolve_weights("tv_density", k, w)
    assert wts is not None
    np.testing.assert_allclose(float(wts.mean()), 1.0, atol=1e-12)  # mean-normalized
    with pytest.raises(ValueError):
        resolve_weights("nope", k, w)


_FITTERS = {
    "svi": lambda k, w, t, wt: calibrate_svi(k, w, t, weights=wt).raw,
    "sigmoid": lambda k, w, t, wt: calibrate_sigmoid(k, w, t, weights=wt, n_cores=2),
    "lqd": lambda k, w, t, wt: calibrate_slice(k, w, t, weights=wt).slice,
}


@pytest.mark.parametrize("model", list(_FITTERS))
def test_weight_scheme_moves_every_model(model):
    """TV-density weighting changes the fit vs equal weighting (non-uniform k)."""
    t = 0.3
    # Deliberately non-uniform strikes: dense near ATM, sparse wings.
    k = np.array([-0.6, -0.30, -0.05, -0.02, 0.0, 0.03, 0.07, 0.35, 0.9])
    true_vol = 0.20 - 0.25 * k + 0.5 * k**2
    w = true_vol**2 * t

    equal = _FITTERS[model](k, w, t, None)
    tv = _FITTERS[model](k, w, t, resolve_weights("tv_density", k, w))
    eq_vol = np.sqrt(equal.implied_w(k) / t)
    tv_vol = np.sqrt(tv.implied_w(k) / t)
    assert np.max(np.abs(eq_vol - tv_vol)) > 1e-4

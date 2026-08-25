"""Time-value density quote weights (volfit.calib.weights).

Golden numbers come from Docs/iv_time_value_density_weights.tex: the worked
5-quote example and the uniform-grid benchmark (w_i = TV_i). Also checks the
OTM time-value definition and that the scheme actually moves a fit relative to
equal weighting across every model family.
"""

import numpy as np
import pytest

from volfit.calib.weights import (
    otm_delta,
    otm_time_value,
    resolve_weights,
    scheme_raw,
    tv_density_weights,
    vega_profile,
    weight_components,
)
from volfit.core.black import black_call, norm_cdf, norm_pdf
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


def test_vega_profile_matches_black_d_plus():
    """vega_profile is phi(d+) exactly (the per-slice sqrt(t) cancels)."""
    k = np.array([-0.4, 0.0, 0.4])
    w = np.array([0.09, 0.04, 0.09])
    d_plus = -k / np.sqrt(w) + 0.5 * np.sqrt(w)
    np.testing.assert_allclose(vega_profile(k, w), norm_pdf(d_plus), rtol=1e-14)


def test_otm_delta_shape():
    """OTM |delta|: N(d+) above the forward, 1 - N(d+) below, ~0.5 at ATM."""
    k = np.array([-0.4, 0.0, 0.4])
    w = np.array([0.09, 0.04, 0.09])
    d_plus = -k / np.sqrt(w) + 0.5 * np.sqrt(w)
    delta = otm_delta(k, w)
    assert delta[1] == pytest.approx(norm_cdf(d_plus[1]))  # ATM -> call side
    assert delta[2] == pytest.approx(norm_cdf(d_plus[2]))  # OTM call
    assert delta[0] == pytest.approx(1.0 - norm_cdf(d_plus[0]))  # OTM put
    assert np.all(delta > 0.0) and np.all(delta < 1.0)
    assert delta[1] == pytest.approx(0.5, abs=0.05)


def test_wing_decay_ordering_vega_delta_tv():
    """Wing-to-belly ratio orders vega (flattest) > delta > time value."""
    k = np.linspace(-0.8, 0.8, 17)
    w = np.full(k.size, 0.04)  # flat 20% vol at t = 1 -> symmetric profiles
    vega = resolve_weights("vega_density", k, w)
    delta = resolve_weights("delta_density", k, w)
    tv = resolve_weights("tv_density", k, w)
    mid, wing = k.size // 2, 0
    for wts in (vega, delta, tv):
        assert wts[wing] < wts[mid]  # all three are belly-peaked
    # phi(d) vs phi(d)/d vs phi(d)/d^2: one extra power of d per step.
    assert vega[wing] / vega[mid] > delta[wing] / delta[mid] > tv[wing] / tv[mid]


@pytest.mark.parametrize("scheme", ["vega_density", "delta_density"])
def test_new_schemes_mean_one_and_density_corrected(scheme):
    """New schemes: mean-1 weights equal to the density-corrected raw shape."""
    k = np.array([-0.5, -0.02, 0.0, 0.02, 0.8])  # crowded ATM, sparse wings
    w = (0.2 - 0.1 * k) ** 2 * 0.25
    wts = resolve_weights(scheme, k, w)
    assert wts is not None
    np.testing.assert_allclose(float(wts.mean()), 1.0, atol=1e-12)
    raw = scheme_raw(scheme, k, w)
    expect = tv_density_weights(k, raw)
    np.testing.assert_allclose(wts, expect / expect.mean(), rtol=1e-14)
    # The crowded centre is downweighted relative to its raw shape share.
    share = wts / raw
    assert share[2] < share[0] and share[2] < share[4]


@pytest.mark.parametrize("scheme", ["tv_density", "vega_density", "delta_density"])
def test_weight_components_invariant_all_schemes(scheme):
    """raw * capped spacing multiplier, mean-normalized, reproduces weights."""
    k = np.array([-0.5, -0.02, 0.0, 0.02, 0.8])
    w = (0.2 - 0.1 * k) ** 2 * 0.25
    comp = weight_components(scheme, k, w)
    assert comp.scheme == scheme
    mult = np.minimum(comp.spacing / comp.spacing.mean(), comp.max_mult)
    rebuilt = comp.raw * mult
    np.testing.assert_allclose(comp.weights, rebuilt / rebuilt.mean(), rtol=1e-12)


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

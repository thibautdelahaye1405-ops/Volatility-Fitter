"""eSSVI comparator family (volfit.models.essvi): the Gatheral-Jacquier SSVI slice.

Golden: the note's SPX-like SSVI-shaped strip (lqd_tail_study.ssvi_strip —
theta = 0.0356, rho = -0.68, phi = 2.40 at t = 0.25). The closed forms
(w', w'', Durrleman g, the wing slopes, the ATM handles) are checked against
finite differences, the raw-SVI embedding and the numeric diagnostics; the
calibrator must recover the three handles from noise-free quotes, stay inside
a bid-ask band, and repair a seed that violates GJ Theorem 4.2.
"""

import numpy as np
import pytest

from lqd_tail_study import ssvi_strip
from volfit.calib.band import BandTarget, band_violation
from volfit.models.base import SmileModel
from volfit.models.diagnostics import (
    analytic_butterfly,
    durrleman_g,
    numeric_handles,
    numeric_lee_slopes,
)
from volfit.models.essvi import ESSVISlice, calibrate_essvi
from volfit.models.essvi.calibrate import butterfly_hinges, seed_slice
from volfit.models.essvi.essvi import butterfly_lhs, is_butterfly_free
from volfit.models.svi_jw.svi import durrleman_g_raw
from volfit.models.wings import wing_laws_of

THETA, RHO, PHI, T = 0.0356, -0.68, 2.40, 0.25
GOLDEN = ESSVISlice(THETA, RHO, PHI, T)


def _golden_quotes():
    """The study's k grid with the EXACT (unperturbed) SSVI total variances."""
    k, _w, t = ssvi_strip()
    return k, GOLDEN.total_variance(k), t


# -- (a) golden ------------------------------------------------------------------


def test_golden_matches_the_tail_study_ssvi_strip():
    """ESSVISlice reproduces lqd_tail_study's SSVI formula on its k grid; the
    study's strip itself only adds a <= 1.75e-4 sinusoidal vol perturbation."""
    k, w_strip, t = ssvi_strip()
    assert t == T
    w_formula = 0.5 * THETA * (1.0 + RHO * PHI * k + np.sqrt((PHI * k + RHO) ** 2 + 1.0 - RHO**2))
    np.testing.assert_allclose(GOLDEN.implied_w(k), w_formula, rtol=0.0, atol=1e-12)
    # The strip perturbs sqrt(w) = sigma*sqrt(t) by <= 1.75e-4, i.e. the vol by
    # <= 1.75e-4 / sqrt(0.25) = 3.5e-4.
    assert np.max(np.abs(np.sqrt(w_strip / t) - GOLDEN.implied_vol(k))) <= 3.6e-4
    assert GOLDEN.total_variance(0.0) == pytest.approx(THETA, abs=1e-15)  # w(0) = theta
    assert isinstance(GOLDEN, SmileModel)


# -- (b) closed forms ------------------------------------------------------------


def test_closed_form_derivatives_match_finite_differences():
    k = np.linspace(-0.5, 0.5, 21)
    h = 1e-4
    w1_fd = (GOLDEN.total_variance(k + h) - GOLDEN.total_variance(k - h)) / (2.0 * h)
    w2_fd = (
        GOLDEN.total_variance(k + h) - 2.0 * GOLDEN.total_variance(k) + GOLDEN.total_variance(k - h)
    ) / (h * h)
    np.testing.assert_allclose(GOLDEN.w1(k), w1_fd, rtol=1e-6, atol=1e-9)
    np.testing.assert_allclose(GOLDEN.w2(k), w2_fd, rtol=1e-6, atol=1e-9)
    # ATM closed forms: w'(0) = rho phi theta, w''(0) = theta phi^2 (1 - rho^2) / 2.
    assert float(GOLDEN.w1(0.0)) == pytest.approx(RHO * PHI * THETA, rel=1e-12)
    assert float(GOLDEN.w2(0.0)) == pytest.approx(0.5 * THETA * PHI**2 * (1.0 - RHO**2), rel=1e-12)


def test_closed_form_g_matches_the_raw_svi_embedding_and_numeric_g():
    """The slice IS a raw SVI (a, b, rho, m, sigma of the module docstring):
    both curves and both closed-form g agree to machine precision, and the
    diagnostics' finite-difference g agrees to its stencil accuracy."""
    raw = GOLDEN.to_raw_svi()
    k = np.linspace(-1.0, 1.0, 4001)
    np.testing.assert_allclose(raw.total_variance(k), GOLDEN.total_variance(k), rtol=0, atol=1e-14)
    np.testing.assert_allclose(GOLDEN.durrleman_g(k), durrleman_g_raw(raw, k), rtol=0, atol=1e-12)
    np.testing.assert_allclose(
        GOLDEN.durrleman_g(k)[50:-50], durrleman_g(GOLDEN, k)[50:-50], rtol=0, atol=1e-5
    )
    assert np.all(GOLDEN.durrleman_g(k) > 0.0)  # the golden slice is butterfly-clean
    assert is_butterfly_free(GOLDEN)


def test_atm_handles_match_numeric_handles():
    exact = GOLDEN.atm_handles()
    num = numeric_handles(GOLDEN, T)
    assert exact.atm_vol == pytest.approx(np.sqrt(THETA / T), rel=1e-14)
    assert exact.atm_vol == pytest.approx(num.atm_vol, rel=1e-10)
    assert exact.skew == pytest.approx(num.skew, rel=1e-5)
    assert exact.curvature == pytest.approx(num.curvature, rel=1e-4)


# -- (e) wings -------------------------------------------------------------------


def test_wing_slopes_match_numeric_lee_slopes():
    """theta phi (1 -/+ rho) / 2 vs the far-grid FD slopes at |k| = 6 (the
    hyperbola is within 0.5 % of its asymptote there)."""
    left, right = GOLDEN.wing_slopes()
    assert left == pytest.approx(0.5 * THETA * PHI * (1.0 - RHO), rel=1e-14)
    assert right == pytest.approx(0.5 * THETA * PHI * (1.0 + RHO), rel=1e-14)
    num_l, num_r = numeric_lee_slopes(GOLDEN)
    assert left == pytest.approx(num_l, rel=1e-2)
    assert right == pytest.approx(num_r, rel=1e-2)
    assert GOLDEN.lee_slopes() == GOLDEN.wing_slopes()
    # The raw-SVI embedding carries the same wings: b (1 -/+ rho).
    assert GOLDEN.to_raw_svi().wing_slopes() == pytest.approx((left, right), rel=1e-12)


def test_registered_with_the_analytic_butterfly_and_wing_law_protocols():
    kind, min_g, neg = analytic_butterfly("essvi", GOLDEN, -0.28, 0.20)
    assert kind == "g" and min_g > 0.0 and neg == 0.0
    laws = wing_laws_of("essvi", GOLDEN)
    assert laws is not None
    assert (laws[0].tail_class, laws[1].tail_class) == ("exponential", "exponential")
    assert (laws[0].coeff, laws[1].coeff) == pytest.approx(GOLDEN.wing_slopes(), rel=1e-12)
    assert GOLDEN.to_vector().size == 3
    assert not hasattr(GOLDEN, "sigma")  # must not trip the raw-SVI duck test


# -- (c) calibration -------------------------------------------------------------


def test_seed_is_admissible_and_close_on_the_golden_strip():
    k, w, t = _golden_quotes()
    seed = seed_slice(k, w, t)
    assert is_butterfly_free(seed)
    assert seed.theta == pytest.approx(THETA, rel=1e-6)  # k = 0 is on the grid
    assert seed.rho == pytest.approx(RHO, rel=5e-2)
    assert seed.phi == pytest.approx(PHI, rel=5e-2)


def test_calibrate_recovers_parameters_in_mid_mode():
    k, w, t = _golden_quotes()
    fit = calibrate_essvi(k, w, t)
    assert fit.success
    np.testing.assert_allclose(fit.slice.to_vector(), [THETA, RHO, PHI], rtol=1e-4, atol=1e-6)
    assert fit.max_iv_error < 1e-6
    assert fit.slice.t == t
    np.testing.assert_allclose(fit.slice.total_variance(k), w, rtol=1e-6, atol=1e-10)


def test_calibrate_recovers_under_weights():
    k, w, t = _golden_quotes()
    weights = 1.0 + np.abs(k)  # any positive scheme leaves a clean fit exact
    fit = calibrate_essvi(k, w, t, weights=weights)
    np.testing.assert_allclose(fit.slice.to_vector(), [THETA, RHO, PHI], rtol=1e-4, atol=1e-6)


def test_band_mode_fit_stays_inside_the_band():
    k, w, t = _golden_quotes()
    vol = np.sqrt(w / t)
    band = BandTarget(iv_lo=vol - 0.002, iv_mid=vol, iv_hi=vol + 0.002)
    fit = calibrate_essvi(k, w, t, band=band)
    model_vol = fit.slice.implied_vol(k)
    assert float(band_violation(model_vol, band.iv_lo, band.iv_hi).max()) <= 1e-9
    assert fit.max_iv_error <= 1e-9  # scored against the band, zero inside
    assert float(np.max(np.abs(model_vol - vol))) < 1e-3  # the mid anchor keeps it centred


def test_too_few_quotes_are_refused_deterministically():
    k = np.array([-0.1, 0.1])
    with pytest.raises(ValueError, match="at least 3"):
        calibrate_essvi(k, GOLDEN.total_variance(k), T)


# -- (d) the GJ no-butterfly hinges ----------------------------------------------


def test_butterfly_hinge_activates_on_a_violating_seed_and_the_fit_is_admissible():
    """Quotes drawn from a slice breaking BOTH GJ Theorem 4.2 conditions
    (theta phi (1+|rho|) = 4.5 > 4, theta phi^2 (1+|rho|) = 13.5 > 4), seeded
    AT that slice: the hinges are active at the start and the fitted slice
    lands inside the region (condition (ii) is held at 4 - 0.02, so the soft
    hinge's ~1e-6 overshoot stays strictly inside the theorem's bound)."""
    bad = ESSVISlice(theta=1.0, rho=0.5, phi=3.0, t=1.0)
    assert np.all(butterfly_hinges(bad) > 0.0)
    assert not is_butterfly_free(bad)
    k = np.linspace(-1.5, 1.5, 31)
    # (1) Quotes NO admissible slice can reproduce: the hinges push the fit
    # inside the region. The solver may exhaust its budget hugging the kinked
    # boundary, so ``success`` is deliberately not asserted here — admissibility
    # and a binding constraint are.
    fit = calibrate_essvi(k, bad.total_variance(k), 1.0, seed=bad)
    c1, c2 = butterfly_lhs(fit.slice)
    assert c1 < 4.0
    assert c2 <= 4.0 and is_butterfly_free(fit.slice)  # strictly inside: the buffer
    assert float(butterfly_hinges(fit.slice).sum()) < 1e-4  # the soft overshoot
    assert fit.cost > 0.0  # the constraint binds: the quotes are not reproduced
    # (2) Admissible quotes seeded AT the violating slice: the hinges steer the
    # solver back inside and it converges on the quotes.
    good = ESSVISlice(theta=0.04, rho=-0.6, phi=2.0, t=1.0)
    assert is_butterfly_free(good)
    fit2 = calibrate_essvi(k, good.total_variance(k), 1.0, seed=bad)
    assert fit2.success and is_butterfly_free(fit2.slice)
    assert fit2.max_iv_error < 1e-3
    assert float(fit.slice.durrleman_g(np.linspace(-3.0, 3.0, 1201)).min()) >= -1e-5

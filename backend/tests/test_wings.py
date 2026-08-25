"""Model-agnostic wing-law descriptors (volfit.models.wings).

The three families occupy structurally different points of the tail spectrum
(book ch. 5 "the wing as a stated choice"): SVI-JW and MCS are exponential by
construction, LQD spans alpha in [0, 1/2], the bounded LV sheet is
Gaussian-class. ``wing_laws_of`` reads the contract off a fitted slice without
touching any tail — these tests lock the mapping to the analytic sources
(lqd.basis.wing_law, the raw-SVI closed form, MCS analytic Lee slopes).
"""

import numpy as np
import pytest

from volfit.models.lqd.basis import wing_law as lqd_wing_law
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw.svi import RawSVI
from volfit.models.wings import lv_wing_laws, wing_laws_of

K = np.linspace(-0.5, 0.5, 15)
T = 0.4
W = (0.22 - 0.2 * K + 0.35 * K**2) ** 2 * T


def test_svi_exponential_closed_form():
    svi = RawSVI(a=0.02, b=0.12, rho=-0.35, m=0.01, sigma=0.15)
    left, right = wing_laws_of("svi", svi)
    assert left.tail_class == right.tail_class == "exponential"
    assert left.exponent == right.exponent == 1.0
    assert left.coeff == pytest.approx(0.12 * 1.35)  # b (1 - rho)
    assert right.coeff == pytest.approx(0.12 * 0.65)  # b (1 + rho)


def test_sigmoid_exponential_matches_analytic_lee():
    slice_ = calibrate_sigmoid(K, W, T, n_cores=2)
    left, right = wing_laws_of("sigmoid", slice_)
    beta_l, beta_r = slice_.lee_slopes()
    assert left.tail_class == right.tail_class == "exponential"
    assert left.coeff == pytest.approx(beta_l)
    assert right.coeff == pytest.approx(beta_r)


def test_lqd_delegates_to_generalized_descriptor():
    for alphas in ((0.0, 0.0), (0.25, 0.5)):
        slice_ = calibrate_slice(
            K, W, t=T, alpha_left=alphas[0], alpha_right=alphas[1]
        ).slice
        assert wing_laws_of("lqd", slice_) == lqd_wing_law(slice_.params)
    left, right = wing_laws_of("lqd", slice_)  # the (0.25, 0.5) fit
    assert (left.tail_class, right.tail_class) == ("intermediate", "gaussian")


def test_lv_gaussian_class_cap():
    theta = np.array([[0.04, 0.09], [0.05, 0.0625]])
    left, right = lv_wing_laws(theta, tau=0.5)
    assert left == right
    assert left.tail_class == "gaussian" and left.exponent == 0.0
    assert left.coeff == pytest.approx(0.09 * 0.5)  # max local variance x tau


def test_unknown_family_claims_no_contract():
    assert wing_laws_of("localvol_recon", object()) is None

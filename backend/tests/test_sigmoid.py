"""Multi-Core SIV (the "sigmoid" family) model and calibrator.

Golden numbers come from ``Docs/Multi_Core_SIV_Technical_Note.tex`` section 5
(the synthetic WW-shaped smile): the linear-in-coefficients fit reproduces the
note's Table 1 coefficients, RMSE, feature table and the no-arbitrage
diagnostics (min v, min g) to the published precision. The calibrator tests
check that the user's "cores" slider monotonically buys fitting power, recovers
a known curve, and tracks the SPX-like SVI benchmark.
"""

import numpy as np

from tests import benchmarks as bm
from volfit.models.base import SmileModel
from volfit.models.lqd.quadrature import build_slice
from volfit.models.sigmoid import HatCore, MultiCoreSiv, calibrate_sigmoid
from volfit.models.sigmoid.kernels import (
    gatheral_g_from_z,
    hat,
    hat_p,
    hat_pp,
    phi,
    phi_p,
    phi_pp,
)


# ----------------------------------------------------------- note section 5
def _ww_target(z: np.ndarray) -> np.ndarray:
    """Synthetic WW-shaped vol target, eq (synthetic-target)."""
    return (
        0.203
        - 0.0025 * z
        + 0.0035 * np.sqrt(1.0 + 0.6 * z**2)
        + 0.0105 * np.exp(-0.5 * ((z + 0.72) / 0.24) ** 2)
        + 0.0085 * np.exp(-0.5 * ((z - 0.70) / 0.25) ** 2)
        - 0.0120 * np.exp(-0.5 * (z / 0.30) ** 2)
    )


def _ww_basis(z: np.ndarray) -> np.ndarray:
    """Linear basis of eq (ww-fit-model): a + b z + q Phi + three hats."""
    return np.vstack(
        [
            np.ones_like(z),
            z,
            phi(z + 0.15, 1.15),
            hat(z, -0.72, 0.42, 5.0),
            hat(z, 0.70, 0.42, 5.0),
            hat(z, 0.0, 0.55, 4.0),
        ]
    ).T


def test_note_table1_linear_coefficients():
    """Reproduce Table 1 of the note (the 61-node least-squares fit)."""
    z = np.linspace(-3.0, 3.0, 61)
    v_tgt = _ww_target(z) ** 2
    coef, *_ = np.linalg.lstsq(_ww_basis(z), v_tgt, rcond=None)
    expected = [0.0416089, -0.0011536, 0.0011371, 0.0061169, 0.0054099, -0.0052878]
    np.testing.assert_allclose(coef, expected, atol=5e-7)

    v_fit = _ww_basis(z) @ coef
    rmse = np.sqrt(np.mean((np.sqrt(v_fit) - np.sqrt(v_tgt)) ** 2))
    np.testing.assert_allclose(rmse, 8.62e-4, atol=1e-6)
    np.testing.assert_allclose(np.max(np.abs(np.sqrt(v_fit) - np.sqrt(v_tgt))), 2.14e-3, atol=1e-5)


def test_note_arbitrage_diagnostics():
    """Reproduce min v = 0.03824 and min g = 0.1553 on z in [-5, 5] (sec 5.2)."""
    zf = np.linspace(-3.0, 3.0, 61)
    coef, *_ = np.linalg.lstsq(_ww_basis(zf), _ww_target(zf) ** 2, rcond=None)
    a, b, q, aL, aR, a0 = coef

    z = np.linspace(-5.0, 5.0, 4001)
    v = (
        a + b * z + q * phi(z + 0.15, 1.15)
        + aL * hat(z, -0.72, 0.42, 5.0) + aR * hat(z, 0.70, 0.42, 5.0) + a0 * hat(z, 0.0, 0.55, 4.0)
    )
    vz = (
        b + q * phi_p(z + 0.15, 1.15)
        + aL * hat_p(z, -0.72, 0.42, 5.0) + aR * hat_p(z, 0.70, 0.42, 5.0) + a0 * hat_p(z, 0.0, 0.55, 4.0)
    )
    vzz = (
        q * phi_pp(z + 0.15, 1.15)
        + aL * hat_pp(z, -0.72, 0.42, 5.0) + aR * hat_pp(z, 0.70, 0.42, 5.0) + a0 * hat_pp(z, 0.0, 0.55, 4.0)
    )
    np.testing.assert_allclose(v.min(), 0.03824, atol=1e-5)
    g = gatheral_g_from_z(z, v, vz, vzz, t=7.0 / 365.0, sigma_ref=0.20)
    np.testing.assert_allclose(g.min(), 0.1553, atol=1e-4)
    # Zero-wing kernels leave the base linear+log-cosh wing slopes intact.
    np.testing.assert_allclose(b + q * 2.0 / 1.15, 0.000824, atol=1e-6)
    np.testing.assert_allclose(b - q * 2.0 / 1.15, -0.003131, atol=1e-6)


def test_hat_is_zero_wing_and_unit_height():
    """B(c) = 1, B'(c) = 0, and B,B',B'' -> 0 in the tails (eqs B-center, H-zero-wing)."""
    c, h, kappa = 0.3, 0.45, 4.0
    np.testing.assert_allclose(hat(c, c, h, kappa), 1.0, atol=1e-12)
    np.testing.assert_allclose(hat_p(c, c, h, kappa), 0.0, atol=1e-12)
    far = np.array([-40.0, 40.0])
    np.testing.assert_allclose(hat(far, c, h, kappa), 0.0, atol=1e-6)
    np.testing.assert_allclose(hat_p(far, c, h, kappa), 0.0, atol=1e-6)
    np.testing.assert_allclose(hat_pp(far, c, h, kappa), 0.0, atol=1e-6)


# --------------------------------------------------------------- calibrator
def test_more_cores_fit_better_on_ww_smile():
    """The cores slider monotonically reduces WW fitting error; R=3 nails it."""
    t = 0.25
    z = np.linspace(-2.5, 2.5, 41)
    k = z * 0.20 * np.sqrt(t)
    w = _ww_target(z) ** 2 * t

    errs = []
    for r in (0, 1, 2, 3):
        fit = calibrate_sigmoid(k, w, t, n_cores=r)
        errs.append(float(np.max(np.abs(fit.vol(k) - _ww_target(z)))))
    assert errs[0] > 50e-4  # base SIV cannot fit a WW smile (note sec 3)
    assert errs[1] < errs[0] and errs[2] < errs[1] and errs[3] < errs[2]
    assert errs[3] < 5e-4  # three cores (two shoulders + a notch) recover it


def test_round_trip_curve_recovery():
    """A known two-core slice is recovered as a curve (params are non-unique)."""
    truth = MultiCoreSiv(
        v0=0.04, s0=-0.004, k0=0.02, z0=0.0, kappa_p=2.5, kappa_c=3.0,
        sigma_ref=0.20, t=0.5,
        cores=(HatCore(0.005, -0.7, 0.4, 5.0), HatCore(-0.004, 0.0, 0.5, 4.0)),
    )
    k = np.linspace(-0.5, 0.5, 41)
    fit = calibrate_sigmoid(k, truth.implied_w(k), t=0.5, n_cores=2)
    assert np.max(np.abs(fit.vol(k) - truth.vol(k))) < 10e-4


def test_fits_svi_benchmark():
    """The 6-param SIV base already tracks the SPX-like smile to a few vol bp;
    cores tighten it further."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    quote_vol = np.sqrt(w / bm.SVI_T)
    base = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=0)
    cored = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=2)
    assert np.max(np.abs(base.vol(k) - quote_vol)) < 5e-3
    assert np.max(np.abs(cored.vol(k) - quote_vol)) < np.max(np.abs(base.vol(k) - quote_vol))


def test_cores_are_capped_to_quote_count():
    """6 + 4R <= N: a sparse chain cannot request more hats than it can support."""
    k = np.linspace(-0.2, 0.2, 9)  # 9 quotes -> at most (9-6)//4 = 0 cores
    w = (0.2 + 0.1 * k) ** 2 * 0.1
    fit = calibrate_sigmoid(k, w, t=0.1, n_cores=3)
    assert len(fit.cores) == 0


def test_smile_model_protocol_conformance():
    """LQD slices, SVI and the Multi-Core SIV all satisfy SmileModel."""
    siv = MultiCoreSiv(
        v0=0.04, s0=-0.003, k0=0.01, z0=0.0, kappa_p=3.0, kappa_c=3.0,
        sigma_ref=0.2, t=0.5, cores=(HatCore(-0.003, 0.0, 0.5, 4.0),),
    )
    lqd = build_slice(bm.SVI_LQD_PARAMS)
    assert isinstance(siv, SmileModel)
    assert isinstance(lqd, SmileModel)
    assert isinstance(bm.SVI_RAW, SmileModel)


def test_floored_diagnostic_is_priced_curve_functional():
    """Where the variance floor binds, pricing sees a locally CONSTANT curve, so
    the reported Durrleman g must be the constant-curve functional (== 1 with
    zero derivatives), not a mix of floored value and raw derivatives — and the
    slice must be flagged not-butterfly-free via the positivity check."""
    # A huge negative hat drives raw v(z) < 0 around its centre.
    siv = MultiCoreSiv(
        v0=0.04, s0=0.0, k0=0.02, z0=0.0, kappa_p=3.0, kappa_c=3.0,
        sigma_ref=0.20, t=0.25, cores=(HatCore(-0.5, -1.0, 0.4, 6.0),),
    )
    k = np.linspace(-0.30, 0.30, 201)
    v, _, _ = siv.variance_z(siv.z(k))
    binding = v <= siv._V_FLOOR
    assert binding.any(), "test premise: the floor must bind somewhere"
    assert not siv.is_butterfly_free(k)
    g = siv.gatheral_g(k)
    np.testing.assert_allclose(g[binding], 1.0, rtol=0, atol=1e-12)
    assert np.all(np.isfinite(g))


def test_note03_ww_two_core_example_regression():
    """Regression lock on Note 03's regenerated worked example: the exact WW
    target of Docs/notes/figures/gen_siv.py (the GLOBALLY-clean w-space
    construction), quotes on the note's grid. Locks (loosely,
    cross-platform): the base misses the shoulders by far more than the
    two-core fit, and the two-core fit is tight."""
    a_, b_, sig_ = 0.005, 0.055, 0.30
    amp_, c_, s_ = 0.007, 0.20, 0.12

    def target_w(k):
        k = np.asarray(k, dtype=float)
        w = a_ + b_ * np.sqrt(k * k + sig_ * sig_)
        for c in (-c_, c_):
            w = w + amp_ * np.exp(-(((k - c) / s_) ** 2))
        return w

    t = 0.25
    k = np.linspace(-0.40, 0.40, 41)
    w = target_w(k)
    target_vol = np.sqrt(w / t)
    base = calibrate_sigmoid(k, w, t, n_cores=0)
    fit = calibrate_sigmoid(k, w, t, n_cores=2)
    base_err = np.max(np.abs(base.vol(k) - target_vol))
    fit_err = np.max(np.abs(fit.vol(k) - target_vol))
    assert fit_err < 10e-4  # note's fresh run: ~2.6 vol bp; lock at 10 bp
    assert base_err > 5 * fit_err  # the shoulders are what the cores buy


def test_note03_ww_target_globally_clean():
    """The Note 03 target is GLOBALLY admissible by construction: total
    variance = hyperbolic base + Gaussian shoulders, so the w-wings are
    exactly linear with slope b = 0.055 (Lee-admissible for all k) and
    g -> (4 - b^2)/16 > 0 in both tails. Locks: two interior local maxima
    (a genuine WW), analytic g > 0 on a wide dense grid, and the two-core
    fit ALSO butterfly-free on that wide grid."""
    a_, b_, sig_ = 0.005, 0.055, 0.30
    amp_, c_, s_ = 0.007, 0.20, 0.12

    def target_wjets(k):
        k = np.asarray(k, dtype=float)
        r = np.sqrt(k * k + sig_ * sig_)
        w = a_ + b_ * r
        w1 = b_ * k / r
        w2 = b_ * sig_ * sig_ / r**3
        for c in (-c_, c_):
            u = k - c
            e = amp_ * np.exp(-((u / s_) ** 2))
            w = w + e
            w1 = w1 + e * (-2.0 * u / s_**2)
            w2 = w2 + e * (4.0 * u * u / s_**4 - 2.0 / s_**2)
        return w, w1, w2

    # Two interior local maxima on the plotted window: a genuine WW.
    win = np.linspace(-0.45, 0.45, 2001)
    ww = target_wjets(win)[0]
    assert int(((ww[1:-1] > ww[:-2]) & (ww[1:-1] > ww[2:])).sum()) == 2
    # Global cleanliness: dense wide grid + positive analytic tail limit.
    wide = np.linspace(-12.0, 12.0, 60001)
    w, w1, w2 = target_wjets(wide)
    g = (1.0 - wide * w1 / (2.0 * w)) ** 2 - 0.25 * w1**2 * (1.0 / w + 0.25) + 0.5 * w2
    assert g.min() > 0.0
    assert (4.0 - b_ * b_) / 16.0 > 0.0
    # The fitted slice inherits global cleanliness (zero-wing hats + linear base).
    t = 0.25
    k = np.linspace(-0.40, 0.40, 41)
    fit = calibrate_sigmoid(k, target_wjets(k)[0], t, n_cores=2)
    assert np.max(np.abs(fit.vol(k) - np.sqrt(target_wjets(k)[0] / t))) < 10e-4
    assert fit.is_butterfly_free(np.linspace(-12.0, 12.0, 20001))

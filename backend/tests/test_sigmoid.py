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

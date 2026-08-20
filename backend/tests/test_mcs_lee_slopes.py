"""Analytic k-space Lee slopes for the Multi-Core Sigmoid family (V3.1 leg 1).

Golden lock: the closed form (eq mcsbetak — w(k) = t v(z), z = k/(σ_ref√t),
so dw/dk -> √t/σ_ref (S0 ∓ 2K0/κ) with the kernels silent by lem zerowing)
matches the far-grid finite difference ``numeric_lee_slopes`` to tight
tolerance on FITTED slices — including multi-core and asymmetric-κ bases —
and the display path serves the analytic values for the sigmoid family.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.calib.fit_task import OverlaySettings
from volfit.models.diagnostics import numeric_lee_slopes
from volfit.models.display import build_display_fit
from volfit.models.sigmoid import HatCore, MultiCoreSiv, calibrate_sigmoid
from volfit.models.sigmoid.sigmoid import analytic_lee_slopes


def _settings(**over) -> OverlaySettings:
    base = dict(
        sviPenaltyWeight=1e3, leeSlopeMax=1.95, midAnchorWeight=0.05,
        nCores=2, sigmoidRidge=1e-2,
    )
    base.update(over)
    return OverlaySettings(**base)


def test_analytic_matches_numeric_on_fitted_slices():
    """Fitted MCS slices (0, 1 and 2 cores, on the SPX-like benchmark) agree
    with the FD measurement at k = ±6 to near machine precision — in the far
    tail the base is exactly linear-plus-exponentially-small (eq affine), so
    the central difference of the analytic asymptote is exact."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    for n_cores in (0, 1, 2):
        fit = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=n_cores)
        an = fit.lee_slopes()
        nu = numeric_lee_slopes(fit)
        np.testing.assert_allclose(an, nu, rtol=1e-8, atol=1e-10)


def test_analytic_matches_numeric_asymmetric_kappa():
    """Hand-built slices with strongly asymmetric wing steepnesses and live
    hats: the kernels contribute zero (lem zerowing), only the base decides."""
    cases = [
        MultiCoreSiv(
            v0=0.04, s0=-0.004, k0=0.02, z0=0.0, kappa_p=2.5, kappa_c=3.0,
            sigma_ref=0.20, t=0.5,
            cores=(HatCore(0.005, -0.7, 0.4, 5.0), HatCore(-0.004, 0.0, 0.5, 4.0)),
        ),
        MultiCoreSiv(
            v0=0.09, s0=0.01, k0=0.30, z0=0.10, kappa_p=4.0, kappa_c=1.2,
            sigma_ref=0.35, t=0.1,
        ),
        MultiCoreSiv(
            v0=0.05, s0=-0.02, k0=0.10, z0=-0.2, kappa_p=1.0, kappa_c=9.0,
            sigma_ref=0.25, t=1.0, cores=(HatCore(0.01, 0.8, 0.6, 6.0),),
        ),
    ]
    for m in cases:
        np.testing.assert_allclose(
            m.lee_slopes(), numeric_lee_slopes(m), rtol=1e-8, atol=1e-10
        )


def test_closed_form_is_eq_mcsbetak():
    """The formula itself: β_P = √t/σ_ref (2K0/κ_P − S0), β_C = √t/σ_ref
    (S0 + 2K0/κ_C) — checked against the module function symbol by symbol."""
    s0, k0, kp, kc, sig, t = -0.03, 0.22, 3.5, 1.7, 0.24, 0.37
    left, right = analytic_lee_slopes(s0 - 2 * k0 / kp, s0 + 2 * k0 / kc, sig, t)
    scale = np.sqrt(t) / sig
    assert left == pytest.approx(scale * (2 * k0 / kp - s0), rel=1e-15)
    assert right == pytest.approx(scale * (s0 + 2 * k0 / kc), rel=1e-15)


def test_display_fit_serves_analytic_lee_for_sigmoid():
    """The DisplayFit lee handles come from the closed form (byte-equal to the
    slice's own lee_slopes), not the FD path."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    fit = build_display_fit("sigmoid", k, w, bm.SVI_T, None, _settings())
    assert fit is not None
    left, right = fit.slice.lee_slopes()
    assert fit.lee_left == left and fit.lee_right == right

"""V3.1 leg 2: Multi-Core Sigmoid belly repair — the SVI R2 rider's mirror.

The sigmoid branch of build_display_fit runs the belly certificate on the
traded range; on failure it refits ONCE with the belly hinge
(calibrate_sigmoid's ``belly_grid``, rows WING_PENALTY_BASE·max(−g + 2e-4, 0)
through the wing-penalty row machinery) and keeps the repair only if it
re-certifies; DisplayFit.belly_repaired flows through. Gated on the SHARED
FitSettings.bellyRepair flag. Clean fits never see a second solve.
"""

from __future__ import annotations

import numpy as np

from tests import benchmarks as bm
from volfit.calib.fit_task import OverlaySettings
from volfit.models.diagnostics import belly_certificate
from volfit.models.display import build_display_fit
from volfit.models.sigmoid import HatCore, MultiCoreSiv, calibrate_sigmoid

#: A gently arbitraged slice: a shallow notch INSIDE the traded range that the
#: 2-core fit reproduces (min g ~ -1), yet whose nearest certified curve is a
#: few hundred bp away — repairable, unlike the violent R6 wing rig.
_ARB = MultiCoreSiv(
    v0=0.04, s0=-0.004, k0=0.15, z0=0.0, kappa_p=4.0, kappa_c=3.0,
    sigma_ref=0.2, t=0.25, cores=(HatCore(alpha=-0.008, c=-0.5, h=0.3, kappa=8.0),),
)
_K = np.linspace(-0.35, 0.30, 21)
_W = _ARB.implied_w(_K)
_T = 0.25


def _settings(**over) -> OverlaySettings:
    base = dict(
        sviPenaltyWeight=1e3, leeSlopeMax=1.95, midAnchorWeight=0.05,
        nCores=2, sigmoidRidge=1e-2,
    )
    base.update(over)
    return OverlaySettings(**base)


def test_arb_quotes_are_repaired_and_certified():
    """End to end through the display path: the first fit reproduces the
    negative belly, the repair refit certifies, the flag flows through."""
    # Without repair: the fit reproduces the arbitrage (certificate fails).
    unrepaired = build_display_fit("sigmoid", _K, _W, _T, None, _settings(bellyRepair=False))
    assert unrepaired is not None and not unrepaired.belly_repaired
    cert = belly_certificate(unrepaired.slice, float(_K.min()), float(_K.max()))
    assert cert is not None and not cert.certified

    # With repair (the default): certified, flagged, at bounded quote cost.
    repaired = build_display_fit("sigmoid", _K, _W, _T, None, _settings())
    assert repaired is not None and repaired.belly_repaired
    re_cert = belly_certificate(repaired.slice, float(_K.min()), float(_K.max()))
    assert re_cert is not None and re_cert.certified
    # The repair trades quote fidelity for a clean density; the rigged notch
    # is genuinely non-convex, so the nearest certified slice is a few hundred
    # bp away — the lock is that the cost is bounded, not exploding (the Vogt
    # lock pattern on the SVI side).
    assert repaired.max_iv_error * 1e4 < 600.0


def test_clean_fit_never_refits():
    """A certified first fit takes the byte-identical single-solve path: the
    display slice equals a direct calibrate_sigmoid of the same inputs."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    clean = build_display_fit("sigmoid", k, w, bm.SVI_T, None, _settings())
    assert clean is not None and not clean.belly_repaired
    direct = calibrate_sigmoid(k, w, bm.SVI_T, n_cores=2, lee_slope_max=1.95)
    np.testing.assert_array_equal(clean.slice.implied_w(k), direct.implied_w(k))
    cert = belly_certificate(clean.slice, float(k.min()), float(k.max()))
    assert cert is not None and cert.certified


def test_belly_grid_default_is_byte_identical():
    """The new calibrate_sigmoid kwarg defaults OFF: belly_grid=None is
    byte-for-byte the historical fit (the house additive-feature invariant)."""
    a = calibrate_sigmoid(_K, _W, _T, n_cores=2)
    b = calibrate_sigmoid(_K, _W, _T, n_cores=2, belly_grid=None)
    np.testing.assert_array_equal(a.implied_w(_K), b.implied_w(_K))


def test_belly_hinge_pushes_g_past_zero():
    """The hinge itself (library level): a repair refit's Durrleman g clears
    the certificate tolerance across the dense traded-range grid."""
    grid = np.linspace(float(_K.min()), float(_K.max()), 101)
    repaired = calibrate_sigmoid(_K, _W, _T, n_cores=2, belly_grid=grid)
    dense = np.linspace(float(_K.min()), float(_K.max()), 801)
    g = np.asarray(repaired.gatheral_g(dense), dtype=float)
    assert float(g[np.isfinite(g)].min()) >= -1e-4  # CERT_G_TOL

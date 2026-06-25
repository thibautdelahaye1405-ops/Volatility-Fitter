"""Backtest R2 — the analytic, FD-free static-arb metric (`_analytic_butterfly`).

The reconstructed Durrleman g(k) in ``dispatch._butterfly`` double-differences
``implied_w`` and over-counts arb at the traded-range edges — most acutely for LQD,
whose ``implied_w`` Black-inverts the call curve. ``_analytic_butterfly`` reads arb
off each model's analytic form instead. These gates lock the three R2 acceptance
criteria: LQD reads butterfly-free by construction, a genuine SVI/SIV violation is
still flagged, and the analytic g matches the reconstruction where the smile is clean.
"""

import numpy as np

from backtest.dispatch import _G_ARB_TOL, _analytic_butterfly, _butterfly
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv
from volfit.models.svi_jw.svi import RawSVI

_LQD = dict(reg_lambda=1e-6, reg_power=1.0, barrier_center=0.90, barrier_scale=50.0,
            mid_anchor_weight=0.05)


def _smooth_svi() -> RawSVI:
    """An arb-free raw-SVI smile (gentle equity skew, well inside the Lee bounds)."""
    return RawSVI(a=0.02, b=0.10, rho=-0.3, m=0.0, sigma=0.20)


# =========================================================================
# 1. LQD reads butterfly-free by construction (density positivity)
# =========================================================================
def test_lqd_analytic_is_density_and_arb_free():
    svi = _smooth_svi()
    k = np.linspace(-0.6, 0.6, 21)
    w = svi.total_variance(k)
    r = calibrate_slice(k, w, t=0.5, n_order=12, **_LQD)
    grid = np.linspace(float(k.min()), float(k.max()), 201)
    an_min, an_neg, kind = _analytic_butterfly(r.slice, grid)
    assert kind == "density"           # routed through the structural-positivity branch
    assert an_min >= -1e-12            # f = u(1-u)e^{-g} cannot be negative
    assert an_neg == 0.0               # so no butterfly arb, ever
    # the structural statement is independent of the fragile reconstruction
    assert r.slice.martingale_check() == __import__("pytest").approx(1.0, abs=5e-3)


# =========================================================================
# 2. A genuine violation is still flagged (SVI known-arb + SIV wing hat)
# =========================================================================
def test_svi_butterfly_violation_is_flagged():
    """A raw SVI breaching Lee's wing bound (b(1+|rho|) > 2) has g<0 — must trip."""
    arb = RawSVI(a=0.005, b=1.6, rho=-0.85, m=0.0, sigma=0.03)
    grid = np.linspace(-0.5, 0.5, 201)
    an_min, an_neg, kind = _analytic_butterfly(arb, grid)
    assert kind == "g"
    assert an_min < -_G_ARB_TOL        # genuine arb, detected analytically
    assert an_neg > 0.0


def test_siv_putwing_hat_violation_is_flagged():
    """A sharp narrow put-wing hat injects curvature that breaks convexity (F4)."""
    base = MultiCoreSiv(
        v0=0.04, s0=-0.10, k0=0.02, z0=0.0, kappa_p=2.0, kappa_c=2.0,
        sigma_ref=0.20, t=0.10, cores=(HatCore(alpha=0.05, c=-2.5, h=0.30, kappa=4.0),),
    )
    grid = np.linspace(-0.8, 0.4, 201)
    an_min, an_neg, kind = _analytic_butterfly(base, grid)
    assert kind == "g"                 # routed through the model's own analytic gatheral_g
    assert an_min < -_G_ARB_TOL        # the hat manufactures a real butterfly violation
    # the worst point sits in the put wing, where the hat lives
    g = np.asarray(base.gatheral_g(grid))
    assert grid[int(np.nanargmin(g))] < 0.0


def test_siv_smooth_base_is_arb_free():
    """The bare SIV base (no cores) on a calm skew is butterfly-free analytically."""
    base = MultiCoreSiv(
        v0=0.04, s0=-0.05, k0=0.01, z0=0.0, kappa_p=2.0, kappa_c=2.0,
        sigma_ref=0.20, t=0.50,
    )
    grid = np.linspace(-0.6, 0.6, 201)
    an_min, _, kind = _analytic_butterfly(base, grid)
    assert kind == "g"
    assert an_min >= -_G_ARB_TOL       # no spurious flag on a clean smile


# =========================================================================
# 3. Analytic g matches the reconstruction where the smile is clean
# =========================================================================
def test_analytic_g_matches_reconstruction_on_clean_svi():
    """On an arb-free SVI the analytic g and the reconstructed g agree closely — the
    analytic path is the same functional without the finite-difference noise."""
    svi = _smooth_svi()
    k_lo, k_hi = -0.5, 0.5
    recon_min, recon_neg = _butterfly(svi, k_lo, k_hi)
    an_min, an_neg, kind = _analytic_butterfly(svi, np.linspace(k_lo, k_hi, 201))
    assert kind == "g"
    assert an_neg == 0.0 and recon_neg == 0.0          # both see no arb
    # agree to within the reconstruction's finite-difference error (~1e-2 on g~0.4);
    # both are far from 0, so the difference is FD noise, not a disagreement on arb
    assert an_min == __import__("pytest").approx(recon_min, abs=1e-2)

"""Functional posterior band (models/lqd/band): delta method vs Monte-Carlo.

The band claims Var[F] = g^T Sigma g for every displayed functional F of the
slice. The honest check is empirical: sample handle vectors from the posterior,
push each through the SAME retarget map production uses, and compare the
sampled spread against the delta-method sd — smile, var-swap and tail masses
all validated on the golden 7-parameter LQD fit of eq. (svi_lqd_coeffs).
"""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.band import functional_band, psd_covariance
from volfit.models.lqd.ortho import build_atm_coordinates
from volfit.models.lqd.quadrature import build_slice

TAU = 0.5
K_GRID = np.linspace(-0.4, 0.35, 61)
#: Posterior sds in the linear regime (a third of the graph's natural move
#: scales) — large enough to be a real band, small enough that first order
#: is the right description.
SD = np.array([0.01, 0.02, 0.15])
N_MC = 500


@pytest.fixture(scope="module")
def chart():
    return build_atm_coordinates(bm.SVI_LQD_PARAMS, TAU)


@pytest.fixture(scope="module")
def handles(chart):
    h = atm_handles(build_slice(bm.SVI_LQD_PARAMS), TAU)
    return np.array([h.sigma0, h.skew, h.curvature])


@pytest.fixture(scope="module")
def band(chart, handles):
    fb = functional_band(chart, handles, np.diag(SD**2), TAU, K_GRID)
    assert fb is not None and fb.exact_legs == 6
    return fb


@pytest.fixture(scope="module")
def mc(chart, handles):
    """Monte-Carlo pushforward of the SAME posterior through the exact map."""
    rng = np.random.default_rng(20260717)
    ivs, vss, tls, trs = [], [], [], []
    for draw in rng.normal(handles, SD, size=(N_MC, 3)):
        target = np.array([max(draw[0], 1e-4) ** 2 * TAU, draw[1], draw[2]])
        try:
            slice_ = build_slice(chart.retarget(target))
        except (RuntimeError, ValueError):
            continue
        w = np.maximum(np.asarray(slice_.implied_w(K_GRID), dtype=float), 0.0)
        ivs.append(np.sqrt(w / TAU))
        vss.append(np.sqrt(max(slice_.var_swap_strike(), 0.0) / TAU))
        z = slice_.strike_to_z(np.array([K_GRID[0], K_GRID[-1]]))
        from scipy.special import expit

        tls.append(float(expit(z[0])))
        trs.append(float(expit(-z[1])))
    assert len(ivs) > 0.9 * N_MC  # the posterior mass is overwhelmingly reachable
    return (
        np.std(np.array(ivs), axis=0),
        float(np.std(vss)),
        float(np.std(tls)),
        float(np.std(trs)),
    )


def test_atm_level_gradient_is_unity(chart, handles):
    """dIV(0)/dsigma0 = 1 exactly (the level handle IS the ATM vol), so a
    level-only posterior reproduces the legacy parallel band at the money."""
    s = 0.015
    fb = functional_band(chart, handles, np.diag([s**2, 0.0, 0.0]), TAU, K_GRID)
    atm = int(np.argmin(np.abs(K_GRID)))
    assert fb.iv_sd[atm] == pytest.approx(s, rel=2e-2)


def test_zero_covariance_zero_band(chart, handles):
    fb = functional_band(chart, handles, np.zeros((3, 3)), TAU, K_GRID)
    assert np.all(fb.iv_sd == 0.0)
    assert fb.var_swap_vol_sd == 0.0
    assert fb.tail_mass_left_sd == 0.0 and fb.tail_mass_right_sd == 0.0
    assert np.all(fb.density_sd == 0.0)


def test_skew_only_uncertainty_spares_the_money(chart, handles):
    fb = functional_band(chart, handles, np.diag([0.0, 0.03**2, 0.0]), TAU, K_GRID)
    atm = int(np.argmin(np.abs(K_GRID)))
    assert fb.iv_sd[atm] < 0.1 * max(fb.iv_sd[0], fb.iv_sd[-1])
    assert fb.iv_sd[0] > 0.0 and fb.iv_sd[-1] > 0.0


def test_smile_band_matches_monte_carlo(band, mc):
    """Delta-method per-strike sd tracks the sampled spread across the grid."""
    mc_iv = mc[0]
    inner = np.abs(K_GRID) <= 0.3
    ratio = band.iv_sd[inner] / np.maximum(mc_iv[inner], 1e-12)
    assert np.all(ratio > 0.85) and np.all(ratio < 1.18)


def test_var_swap_band_matches_monte_carlo(band, mc):
    assert band.var_swap_vol_sd == pytest.approx(mc[1], rel=0.15)


def test_tail_mass_band_matches_monte_carlo(band, mc):
    assert band.tail_mass_left_sd == pytest.approx(mc[2], rel=0.20)
    assert band.tail_mass_right_sd == pytest.approx(mc[3], rel=0.20)


def test_density_band_positive_where_mass_lives(band):
    assert np.all(band.density >= 0.0)
    assert np.any(band.density_sd > 0.0)
    assert band.density_x.shape == band.density.shape == band.density_sd.shape


def test_reference_slice_reuse_is_identical(chart, handles):
    cov = np.diag(SD**2)
    ref = build_slice(
        chart.retarget(np.array([handles[0] ** 2 * TAU, handles[1], handles[2]]))
    )
    a = functional_band(chart, handles, cov, TAU, K_GRID)
    b = functional_band(chart, handles, cov, TAU, K_GRID, reference=ref)
    np.testing.assert_array_equal(a.iv_sd, b.iv_sd)
    assert a.var_swap_vol == b.var_swap_vol


def test_psd_clip_and_degenerate_inputs(chart, handles):
    # A covariance with a negative eigenvalue is clipped, never propagated.
    bad = np.array([[1e-4, 0.0, 0.0], [0.0, -1e-4, 0.0], [0.0, 0.0, 1e-2]])
    clipped = psd_covariance(bad)
    assert np.all(np.linalg.eigvalsh(clipped) >= -1e-16)
    fb = functional_band(chart, handles, bad, TAU, K_GRID)
    assert np.all(np.isfinite(fb.iv_sd))
    # Degenerate calls answer None rather than inventing a band.
    assert functional_band(chart, handles, np.eye(3), 0.0, K_GRID) is None
    assert functional_band(chart, handles, np.eye(3), TAU, np.array([])) is None

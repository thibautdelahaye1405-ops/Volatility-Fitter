"""Jacobian-propagated measurement covariance (Phase 2 of
Docs/observation_filter_roadmap.md; Note 15 eq. cov-delta + resid-inflation).

Locks:
  * exact agreement of the regularized eigen-inverse with G inv(I) G^T on a
    full-rank linear model, and with the Monte-Carlo estimator covariance;
  * the note's case-file geometry — a clustered, contradictory chain inflates
    CURVATURE variance and trips rho, level/skew stay tight;
  * band semantics for free — inactive hinge rows contribute nothing to
    J^T W J, so in-band information is just the small mid anchor (no
    special-case code anywhere);
  * rank deficiency inflates R (clamped eigenvalues + envelope), never
    explodes or reads as zero uncertainty;
  * the calibrator ``solver_diag`` seams (LQD / SVI / Multi-Core SIV) are pure
    side-channels: results byte-identical, J^T J PSD, and an end-to-end LQD
    R_t is dimensionally sane;
  * the factors fallback route (A/B smoke).
"""

import numpy as np
import pytest

from volfit.calib.band import band_residuals
from volfit.calib.observation_measurement import (
    apply_variance_envelope,
    covariance_from_information,
    handle_jacobian_fd,
    information_matrix,
    measurement_from_factors,
    measurement_from_jacobian,
    residual_inflation,
)
from volfit.graph.precision import OBS_PRECISION_FLOOR
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import build_slice
from volfit.models.sigmoid.calibrate import calibrate_sigmoid
from volfit.models.svi_jw.calibrate import calibrate_svi

RNG = np.random.default_rng(7)

# Quadratic toy smile sigma(k) = th0 + th1 k + th2 k^2: handles are exactly
# (sigma(0), sigma'(0), sigma''(0)) = (th0, th1, 2 th2) — an analytic G.
G_QUAD = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 2.0]])


def _design(k: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones_like(k), k, k**2])


# ------------------------------------------------------------- exact algebra
def test_covariance_matches_inverse_on_full_rank():
    """Full rank: the regularized eigen-inverse IS G inv(I) G^T (1e-12)."""
    a = RNG.normal(size=(20, 4))
    w = RNG.uniform(0.5, 2.0, size=20)
    jac = np.sqrt(w)[:, None] * a
    g = RNG.normal(size=(3, 4))
    info = information_matrix(jac)
    r_x, n_clamped = covariance_from_information(g, info)
    expected = g @ np.linalg.inv(info) @ g.T
    assert n_clamped == 0
    assert r_x == pytest.approx(expected, abs=1e-12)


def test_covariance_matches_monte_carlo():
    """The propagated covariance matches the empirical covariance of the
    weighted-lstsq handle estimator under the stated noise (the statistical
    meaning of eq. cov-delta)."""
    k = np.linspace(-0.4, 0.4, 25)
    a = _design(k)
    sigma_noise = 0.004  # homoskedastic quote noise, weights = 1
    theta_true = np.array([0.20, -0.05, 0.30])
    info = information_matrix(a)  # unit weights
    r_x, _ = covariance_from_information(G_QUAD, info)
    r_x = r_x * sigma_noise**2  # unit-weight rows => scale by the noise variance
    draws = np.empty((4000, 3))
    for i in range(draws.shape[0]):
        y = a @ theta_true + RNG.normal(0.0, sigma_noise, size=k.size)
        draws[i] = G_QUAD @ np.linalg.lstsq(a, y, rcond=None)[0]
    emp = np.cov(draws.T)
    assert np.diag(emp) == pytest.approx(np.diag(r_x), rel=0.15)


def test_handle_jacobian_fd_matches_analytic():
    """Central FD of a nonlinear handle map agrees with the closed form."""
    def handles(theta):
        return np.array([np.sin(theta[0]), theta[1] ** 2, theta[0] * theta[1]])

    theta = np.array([0.3, -1.2])
    fd = handle_jacobian_fd(handles, theta)
    exact = np.array([[np.cos(0.3), 0.0], [0.0, -2.4], [-1.2, 0.3]])
    assert fd == pytest.approx(exact, abs=1e-8)


# --------------------------------------------------------- the case-file test
def test_contradictory_cluster_inflates_curvature_not_level():
    """Note §6 case file, executable: nine clustered near-ATM quotes with one
    stale contradiction => curvature variance explodes relative to level, and
    rho > 1; the clean chain has rho == 1."""
    k = np.linspace(-0.05, 0.05, 9)  # dense but narrow: curvature ill-identified
    a = _design(k)
    theta_true = np.array([0.20, -0.05, 0.30])

    def fit(y):
        th = np.linalg.lstsq(a, y, rcond=None)[0]
        return th, y - a @ th

    y_clean = a @ theta_true
    _, res_clean = fit(y_clean)
    weights = np.full(k.size, 1.0 / 0.002**2)  # stated quote noise: 20 bp
    jac = np.sqrt(weights)[:, None] * a
    rows_clean = np.sqrt(weights) * res_clean
    rho_clean = residual_inflation(rows_clean, k.size, k.size)
    assert rho_clean == 1.0

    y_bad = y_clean.copy()
    y_bad[4] += 0.02  # one stale strike, 10x the stated noise
    _, res_bad = fit(y_bad)
    rows_bad = np.sqrt(weights) * res_bad
    rho_bad = residual_inflation(rows_bad, k.size, k.size)
    assert rho_bad > 5.0  # the contradiction is visible to the filter

    info = information_matrix(jac)
    r_x, _ = covariance_from_information(G_QUAD, info)
    # narrow cluster: curvature is orders of magnitude less identified
    assert r_x[2, 2] / r_x[0, 0] > 1e4
    m = measurement_from_jacobian(
        theta_true, jac, G_QUAD, rows_bad, k.size, k.size
    )
    assert m.breakdown["rho"] > 5.0
    assert m.cov[2, 2] > m.cov[0, 0]


# ----------------------------------------------------------- band-for-free
def test_band_mode_widens_R_with_no_special_casing():
    """Differentiate the ACTUAL band objective around an in-band fit: hinge
    rows are flat inside the spread, so the information drops to the mid
    anchor's share and R widens by ~1/mid_anchor_weight — no band-specific
    code in the covariance path."""
    k = np.linspace(-0.3, 0.3, 13)
    a = _design(k)
    theta = np.array([0.20, -0.05, 0.30])
    vol = a @ theta
    lo, hi = vol - 0.01, vol + 0.01  # model strictly inside the band
    anchor_w = 0.05

    def band_rows(th):
        return band_residuals(a @ th, lo, hi, vol, 1.0, anchor_w)

    jac_band = handle_jacobian_fd(band_rows, theta)  # generic FD of the rows
    jac_mid = a
    r_band, _ = covariance_from_information(G_QUAD, information_matrix(jac_band))
    r_mid, _ = covariance_from_information(G_QUAD, information_matrix(jac_mid))
    ratio = np.diag(r_band) / np.diag(r_mid)
    assert ratio == pytest.approx(np.full(3, 1.0 / anchor_w), rel=1e-6)


# ------------------------------------------------------------ rank deficiency
def test_rank_deficient_chain_inflates_not_explodes():
    """3 quotes cannot identify 5 parameters: clamped eigen-directions and the
    envelope produce a large FINITE R (and never a spuriously tiny one)."""
    k = np.array([-0.01, 0.0, 0.01])
    a = np.column_stack([np.ones_like(k), k, k**2, k**3, k**4])
    g = np.array([[1, 0, 0, 0, 0], [0, 1, 0, 0, 0], [0, 0, 2, 0, 0]], dtype=float)
    info = information_matrix(a)
    r_x, n_clamped = covariance_from_information(g, info)
    assert n_clamped >= 2
    assert np.all(np.isfinite(r_x))
    cov, _ = apply_variance_envelope(r_x)
    hi = 1.0 / OBS_PRECISION_FLOOR
    assert np.all(np.diag(cov) <= hi + 1e-12)  # envelope bounds the explosion
    assert np.all(np.diag(cov) > 0.0)


def test_variance_envelope_preserves_correlation():
    # ATM variance 4.0 sits far above the cap (1e-2), so the clip binds there.
    cov = np.array([[4.0, 1.0, 0.0], [1.0, 0.25, 0.0], [0.0, 0.0, 0.5]])
    corr = cov[0, 1] / np.sqrt(cov[0, 0] * cov[1, 1])
    out, n_clipped = apply_variance_envelope(cov)
    assert n_clipped >= 2
    new_corr = out[0, 1] / np.sqrt(out[0, 0] * out[1, 1])
    assert new_corr == pytest.approx(corr, rel=1e-12)


def test_residual_inflation_cap_binds():
    rows = np.full(9, 100.0)  # absurd chi^2
    assert residual_inflation(rows, 9, 9, cap=25.0) == 25.0


# --------------------------------------------------------- calibrator seams
def _lqd_inputs():
    k = np.linspace(-0.3, 0.3, 15)
    t = 0.25
    sigma = 0.20 + 0.10 * k**2 - 0.05 * k
    return k, sigma**2 * t, t


def test_lqd_seam_byte_identical_and_filled():
    k, w, t = _lqd_inputs()
    plain = calibrate_slice(k, w, t, n_order=6)
    diag: dict = {}
    seamed = calibrate_slice(k, w, t, n_order=6, solver_diag=diag)
    assert np.array_equal(plain.params.to_vector(), seamed.params.to_vector())
    assert diag["jac"].shape[1] == 7  # (L, R, a_2..a_6)
    assert diag["n_fit_rows"] == 15 and diag["n_quotes"] == 15
    info = information_matrix(diag["jac"])
    assert np.min(np.linalg.eigvalsh(info)) > -1e-8  # PSD


def test_svi_seam_byte_identical_and_filled():
    k, w, t = _lqd_inputs()
    plain = calibrate_svi(k, w, t)
    diag: dict = {}
    seamed = calibrate_svi(k, w, t, solver_diag=diag)
    assert plain.raw == seamed.raw
    assert diag["jac"].shape[1] == 5  # raw-SVI (a, b, rho, m, sigma)
    assert diag["residual"].ndim == 1


def test_sigmoid_seam_byte_identical_and_filled():
    k, w, t = _lqd_inputs()
    plain = calibrate_sigmoid(k, w, t, n_cores=1)
    diag: dict = {}
    seamed = calibrate_sigmoid(k, w, t, n_cores=1, solver_diag=diag)
    assert plain == seamed  # frozen dataclass equality = byte-identical fit
    assert diag["jac"].shape[1] == 10  # base 6 + 4 per core


def test_lqd_end_to_end_measurement_is_sane():
    """The full Phase-2 pipeline on a real LQD fit: FD handle Jacobian off the
    production build_slice/atm_handles, information from the retained solver
    Jacobian, rho from the solution residual — R_t comes out PSD with an ATM
    std between 0.1 bp and 5 vol points."""
    k, w, t = _lqd_inputs()
    diag: dict = {}
    # The production FitSettings reg (1e-6): without Lambda_intrinsic the deep
    # Legendre modes are near-unidentified and the envelope cap binds on ATM —
    # the clamp/envelope work as designed, but the SANITY check wants the
    # production configuration.
    result = calibrate_slice(k, w, t, n_order=6, reg_lambda=1e-6, solver_diag=diag)

    def handle_fn(theta):
        h = atm_handles(build_slice(LQDParams.from_vector(theta)), t)
        return np.array([h.sigma0, h.skew, h.curvature])

    g = handle_jacobian_fd(handle_fn, diag["theta"])
    assert g.shape == (3, 7) and np.all(np.isfinite(g))
    z = handle_fn(diag["theta"])
    m = measurement_from_jacobian(
        z, diag["jac"], g, diag["residual"], diag["n_fit_rows"], diag["n_quotes"],
        noise_scale=0.002,  # stated per-quote noise: a 20 bp half-spread
    )
    assert np.min(np.linalg.eigvalsh(m.cov)) >= -1e-15
    atm_std = float(np.sqrt(m.cov[0, 0]))
    # 15 clean quotes at 20 bp noise: the ATM level is identified to O(10 bp)
    assert 1e-4 < atm_std < 0.01
    assert m.breakdown["route"] == 1.0
    assert result.success


def test_noise_scale_moves_R_quadratically():
    """Doubling the stated quote noise quadruples the handle covariance (the
    UNITS contract: R is tied to the market's stated uncertainty)."""
    k, w, t = _lqd_inputs()
    diag: dict = {}
    calibrate_slice(k, w, t, n_order=6, reg_lambda=1e-6, solver_diag=diag)

    def handle_fn(theta):
        h = atm_handles(build_slice(LQDParams.from_vector(theta)), t)
        return np.array([h.sigma0, h.skew, h.curvature])

    g = handle_jacobian_fd(handle_fn, diag["theta"])
    z = handle_fn(diag["theta"])

    def build(noise):
        return measurement_from_jacobian(
            z, diag["jac"], g, diag["residual"], diag["n_fit_rows"],
            diag["n_quotes"], noise_scale=noise, inflate=False,
        )

    r1 = build(0.001).cov[0, 0]
    r2 = build(0.002).cov[0, 0]
    assert r2 / r1 == pytest.approx(4.0, rel=1e-6)


# ------------------------------------------------------------- factors route
def test_factors_route_smoke():
    """The A/B fallback: diagonal R = 1/precision with the factor audit."""
    z = np.array([0.20, -1.5, 4.0])
    m = measurement_from_factors(z, rms_vol=0.002, n_atm_quotes=12, rel_spread=0.03)
    assert m.cov.shape == (3, 3)
    assert np.all(np.diag(m.cov) > 0.0)
    assert np.count_nonzero(m.cov - np.diag(np.diag(m.cov))) == 0  # diagonal
    assert m.breakdown["route"] == 0.0
    assert "quoteDensity" in m.breakdown and "spread" in m.breakdown
    # curvature is the least-trusted coordinate on this route (HANDLE_CONFIDENCE)
    assert m.cov[2, 2] > m.cov[0, 0]


def test_contamination_flag_passthrough():
    z = np.zeros(3)
    jac = np.eye(3)
    m = measurement_from_jacobian(z, jac, np.eye(3), np.zeros(3), 3, 3, contaminated=True)
    assert m.contaminated is True
    m2 = measurement_from_factors(z, 0.01, 8, 0.05, contaminated=True)
    assert m2.contaminated is True

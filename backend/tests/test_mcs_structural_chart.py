"""V3.1 leg 3: the structural MCS base chart (β_L, β_R, z*, v*, κ_P, κ_C).

The SVI committee-arc port: the base's k-space Lee wing slopes (eq mcsbetak)
lifted logistically against the buffered leeSlopeMax cap so every finite
optimizer vector has strictly Lee-clean base wings; closed-form 6x6 chain for
the analytic Jacobian; float-boundary saturation guards. Opt-in
(FitSettings.mcsChart, default "raw" byte-identical — the sviChart precedent:
pre-registered benchmark, then a ratified flip).
"""

from __future__ import annotations

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.sigmoid.jacobian import siv_residual_jacobian
from volfit.models.sigmoid.structural import (
    pack_structural_mcs,
    siv_residual_jacobian_structural,
    structural_chain_mcs,
    unpack_structural_mcs,
)

CAP = 1.95
SCALE = float(np.sqrt(0.5)) / 0.2  # √t/σ_ref of the reference slice


def test_mcs_chart_default_is_raw():
    """Byte-identity governance: the chart ships default-OFF ("raw") until
    the adjudication sweep ratifies a flip (the sviChart precedent)."""
    from volfit.api.schemas import FitSettings

    assert FitSettings().mcsChart == "raw"


def test_chart_round_trip_and_wing_identities():
    """pack ∘ unpack is the identity on in-cap bases, and the chart's wing
    coordinates ARE the analytic Lee slopes: every finite theta maps to a base
    with both k-space slopes strictly inside (0, cap), k0 > 0 and v0 > 0."""
    rng = np.random.default_rng(7)
    for _ in range(25):
        theta = rng.normal(scale=1.5, size=6)
        raw = unpack_structural_mcs(theta, CAP, SCALE)
        v0, s0, k0, _z0, kp, kc = raw
        beta_l = SCALE * (2.0 * k0 / kp - s0)
        beta_r = SCALE * (s0 + 2.0 * k0 / kc)
        assert 0.0 < beta_l < CAP and 0.0 < beta_r < CAP
        assert v0 > 0.0 and k0 > 0.0 and kp > 0.0 and kc > 0.0
        back = unpack_structural_mcs(pack_structural_mcs(raw, CAP, SCALE), CAP, SCALE)
        np.testing.assert_allclose(back, raw, rtol=1e-9, atol=1e-12)
    # Saturation lock (the SVI round-1 sweep bug, ported): a trial ANYWHERE in
    # R^6 — exp/logistic under/overflow territory included — must map to a
    # finite admissible base, wings still STRICTLY under the cap.
    for extreme in (1e6, -1e6):
        raw = unpack_structural_mcs(np.full(6, extreme), CAP, SCALE)
        assert np.all(np.isfinite(raw))
        v0, s0, k0, _z0, kp, kc = raw
        beta_l = SCALE * (2.0 * k0 / kp - s0)
        beta_r = SCALE * (s0 + 2.0 * k0 / kc)
        assert 0.0 < beta_l < CAP and 0.0 < beta_r < CAP  # _INTERIOR_ONE clip
        assert v0 > 0.0 and k0 > 0.0


def test_chain_matches_fd_incl_near_cap():
    """The closed-form 6x6 chain d(raw)/d(chart) agrees with a central FD of
    ``unpack_structural_mcs`` at generic points AND with a wing lift pushed
    against the cap (the logistic saturation region)."""
    points = (
        np.array([0.3, -0.5, 0.1, -2.5, 1.0, 0.8]),
        np.array([5.0, -3.0, 0.0, 1.0, 2.0, 0.5]),
        np.array([30.0, 0.2, 0.4, -1.0, 1.5, 1.5]),  # left lift near the cap
        np.array([-30.0, 30.0, 0.2, 0.5, 0.5, 2.0]),  # asymmetric saturation
    )
    for theta in points:
        raw, chain = structural_chain_mcs(theta, CAP, SCALE)
        np.testing.assert_allclose(raw, unpack_structural_mcs(theta, CAP, SCALE))
        eps = 1e-7
        fd = np.empty((6, 6))
        for p in range(6):
            d = np.zeros(6)
            d[p] = eps
            fd[:, p] = (
                unpack_structural_mcs(theta + d, CAP, SCALE)
                - unpack_structural_mcs(theta - d, CAP, SCALE)
            ) / (2.0 * eps)
        np.testing.assert_allclose(chain, fd, rtol=5e-5, atol=1e-8)


def test_structural_residual_jacobian_matches_fd():
    """The chart-space analytic residual Jacobian (raw Jacobian × chain) locks
    against a finite difference of the composed residual — base and 2-core,
    mid objective (the calibrator's gated configuration)."""
    from volfit.calib.band import BandTarget, band_residuals
    from volfit.models.sigmoid.calibrate import _V_FLOOR, _eval_v

    z = np.linspace(-3.0, 3.0, 25)
    t, ridge, maw = 0.5, 1e-2, 0.05
    sqrt_w = np.ones_like(z)

    def residual(theta, n_cores, vol_q, band):
        raw6 = unpack_structural_mcs(theta[:6], CAP, SCALE)
        theta_r = np.concatenate([raw6, theta[6:]])
        mv = np.sqrt(np.maximum(_eval_v(theta_r, z, n_cores), _V_FLOOR))
        if band is None:
            res = sqrt_w * (mv - vol_q)
        else:
            res = band_residuals(mv, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_w, maw)
        if n_cores:
            res = np.concatenate([res, np.sqrt(ridge) * theta_r[6::4][:n_cores]])
        return res

    base_chart = pack_structural_mcs(
        np.array([0.04, 0.01, 0.30, 0.10, 4.0, 3.0]), CAP, SCALE
    )
    hats = np.array([0.20, -1.0, 0.40, 5.0, -0.15, 1.2, 0.50, 6.0])
    near_cap = base_chart.copy()
    near_cap[0] = 25.0  # push the left lift toward saturation
    for theta, n_cores, band_on in (
        (base_chart, 0, False),
        (np.concatenate([base_chart, hats]), 2, False),
        (np.concatenate([near_cap, hats]), 2, False),
        (np.concatenate([base_chart, hats]), 2, True),
    ):
        raw6 = unpack_structural_mcs(theta[:6], CAP, SCALE)
        vol_q = np.sqrt(
            np.maximum(_eval_v(np.concatenate([raw6, theta[6:]]), z, n_cores), _V_FLOOR)
        ) + 0.001
        band = None
        if band_on:
            band = BandTarget(iv_lo=vol_q + 0.01, iv_mid=vol_q + 0.015, iv_hi=vol_q + 0.02)
        an = siv_residual_jacobian_structural(
            theta, z, n_cores, t, sqrt_w, band, maw, ridge,
            None, None, 0.0, None, None, CAP, SCALE,
        )
        eps = 1e-7
        fd = np.empty((an.shape[0], theta.size))
        for p in range(theta.size):
            d = np.zeros_like(theta)
            d[p] = eps
            fd[:, p] = (
                residual(theta + d, n_cores, vol_q, band)
                - residual(theta - d, n_cores, vol_q, band)
            ) / (2.0 * eps)
        np.testing.assert_allclose(an, fd, rtol=5e-4, atol=5e-6)


def test_charts_agree_on_clean_quotes():
    """Chart equivalence (the sviChart lock pattern): on clean quotes the
    optimum is chart-independent — both fits reproduce the same smile to
    solver tolerance, and the structural base wings sit strictly in-cap."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    for n_cores in (0, 2):
        raw_fit = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=n_cores)
        struct_fit = calibrate_sigmoid(
            k, w, t=bm.SVI_T, n_cores=n_cores, chart="structural"
        )
        gap = float(np.max(np.abs(struct_fit.vol(k) - raw_fit.vol(k)))) * 1e4
        assert gap < 0.05, f"charts disagree by {gap:.3f} vol bp at R={n_cores}"
        left, right = struct_fit.lee_slopes()
        assert 0.0 < left < 1.95 and 0.0 < right < 1.95


def test_structural_wings_are_fenced_at_the_cap():
    """Quotes manufactured with a base wing ABOVE the cap: the structural fit
    lands strictly inside (0, cap) on both k-space slopes — the fence is the
    chart, not a penalty (the raw fit reproduces the violation)."""
    t = 0.25
    steep = np.array([0.04, -0.30, 1.20, 0.0, 1.2, 1.2])  # raw base, wings >> 2
    from volfit.models.sigmoid.calibrate import _eval_v

    sigma_ref = 0.2
    k = np.linspace(-1.2, 1.2, 31)
    z = k / (sigma_ref * np.sqrt(t))
    w = np.maximum(_eval_v(steep, z, 0), 1e-8) * t
    struct = calibrate_sigmoid(k, w, t, n_cores=0, chart="structural")
    left, right = struct.lee_slopes()
    assert 0.0 < left < 1.95 and 0.0 < right < 1.95
    raw = calibrate_sigmoid(k, w, t, n_cores=0)
    r_left, r_right = raw.lee_slopes()
    assert max(r_left, r_right) > 1.95  # the raw chart reproduces the breach


def test_default_chart_is_byte_identical():
    """chart="raw" (the default) is byte-for-byte the historical fit."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 41)
    w = bm.SVI_RAW.total_variance(k)
    a = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=2)
    b = calibrate_sigmoid(k, w, t=bm.SVI_T, n_cores=2, chart="raw")
    np.testing.assert_array_equal(a.implied_w(k), b.implied_w(k))
    assert a.to_vector() == pytest.approx(b.to_vector(), rel=0, abs=0)

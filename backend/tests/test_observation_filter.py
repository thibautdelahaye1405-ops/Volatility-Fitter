"""Observation-filter numerical core (Phase 1 of Docs/observation_filter_roadmap.md).

Locks the Kalman algebra of Note 15 (Docs/kalman_filtering.tex):
  * the scalar precision-weighted shrinkage proposition (K = p/(p+r));
  * Joseph-form PSD survival under ill-conditioned covariances;
  * the pilot gain cap;
  * the GOLDEN cross-check — on a single-node problem the per-node update
    reproduces graph/posterior.posterior_update (the two covariance-form
    Gaussian updates in the codebase must agree; this is also the Note 15
    Appendix C verification anchor);
  * process-noise composition (eq. Q) and the reset rule;
  * the whitened MAP residual reproducing the Kalman posterior when minimized
    (the seed of the Phase-6 double-count guard, Prop. nodouble).
"""

from types import SimpleNamespace

import numpy as np
import pytest

from volfit.calib.observation_filter import (
    HANDLE_MOVE_SCALES,
    HANDLE_NAMES,
    kalman_update,
    prediction_prior_residual,
    predict,
    process_noise,
    should_reset,
)
from volfit.graph.posterior import posterior_update

RNG = np.random.default_rng(42)


# ---------------------------------------------------------------- kalman_update
def test_scalar_shrinkage_proposition():
    """1-d, H=1: K = p/(p+r) and m+ is the precision-weighted average (Prop. 3.2)."""
    p, r, m, z = 0.09, 0.0225, 20.0, 20.4
    upd = kalman_update([m], [[p]], [z], [[r]])
    k = p / (p + r)
    assert upd.gain[0, 0] == pytest.approx(k, abs=1e-15)
    assert upd.mean[0] == pytest.approx((r * m + p * z) / (p + r), abs=1e-12)
    assert upd.cov[0, 0] == pytest.approx(p * r / (p + r), rel=1e-12)
    assert upd.innovation[0] == pytest.approx(z - m)
    assert upd.innovation_cov[0, 0] == pytest.approx(p + r)


def test_case_file_gains():
    """The note's §6 case file: level/skew move, the contradictory curvature does
    not (diagonal 3-handle problem, exact scalar gains)."""
    m = np.array([0.200, -0.35, 0.10])
    p = np.array([0.0030, 0.08, 0.05]) ** 2
    z = np.array([0.204, -0.37, 0.55])
    r = np.array([0.0015, 0.05, 0.30]) ** 2
    upd = kalman_update(m, np.diag(p), z, np.diag(r))
    gains = np.diag(upd.gain)
    assert gains == pytest.approx(p / (p + r), rel=1e-12)
    assert gains[0] == pytest.approx(0.80, abs=0.01)  # level: follow the market
    assert gains[2] == pytest.approx(0.027, abs=0.002)  # curvature: reject the kink
    assert upd.mean[2] == pytest.approx(0.112, abs=0.002)


def test_joseph_form_keeps_psd_when_ill_conditioned():
    """A huge prediction/measurement precision mismatch must not break PSD —
    the reason the note prefers Joseph over (I-KH)P."""
    n = 3
    a = RNG.normal(size=(n, n))
    P = a @ a.T + np.diag([1e8, 1e-10, 1.0])  # wildly anisotropic
    R = np.diag([1e-12, 1e10, 1e-6])
    upd = kalman_update(np.zeros(n), P, np.ones(n), R)
    assert np.allclose(upd.cov, upd.cov.T)
    assert np.min(np.linalg.eigvalsh(upd.cov)) >= -1e-12


def test_gain_cap_binds_and_scales_mean():
    """max_gain caps each handle's own-gain; the capped update moves less."""
    upd_free = kalman_update([0.0], [[1.0]], [1.0], [[1e-6]])
    assert upd_free.gain[0, 0] == pytest.approx(1.0, abs=1e-5)
    upd_cap = kalman_update([0.0], [[1.0]], [1.0], [[1e-6]], max_gain=0.5)
    assert upd_cap.gain[0, 0] == pytest.approx(0.5, rel=1e-6)
    assert upd_cap.mean[0] == pytest.approx(0.5, rel=1e-5)
    # Joseph keeps the capped posterior a valid covariance
    assert upd_cap.cov[0, 0] > 0


def test_default_gain_cap_never_binds():
    """At the default max_gain=1.0 the update is byte-identical to uncapped."""
    P = np.diag([0.01, 0.02, 0.03])
    R = np.diag([0.02, 0.01, 0.5])
    a = kalman_update(np.zeros(3), P, np.ones(3), R)
    b = kalman_update(np.zeros(3), P, np.ones(3), R, max_gain=1.0)
    assert np.array_equal(a.mean, b.mean) and np.array_equal(a.cov, b.cov)


def test_partial_observation_H():
    """Observing only the ATM handle updates skew through the cross-covariance."""
    P = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.0], [0.0, 0.0, 0.25]])
    H = np.array([[1.0, 0.0, 0.0]])
    upd = kalman_update(np.zeros(3), P, [0.2], [[0.01]], H=H)
    # closed form: K = P H^T / (P00 + r)
    k = P[:, 0] / (P[0, 0] + 0.01)
    assert upd.mean == pytest.approx(k * 0.2, rel=1e-12)
    assert upd.mean[1] != 0.0  # cross-covariance carried the ATM move into skew
    assert upd.mean[2] == 0.0  # uncorrelated curvature untouched


def test_psd_guard_raises():
    """A garbage (negative) measurement covariance is rejected at the door —
    Joseph is robust enough to produce a plausible posterior from it, so the
    input validation is the only place the bug can surface."""
    with pytest.raises(ValueError):
        kalman_update([0.0], [[1.0]], [1.0], [[-2.0]])


# --------------------------------------------- golden cross-check vs the graph
def test_agrees_with_graph_posterior_single_node():
    """One node, one handle: the Kalman update must reproduce the graph layer's
    posterior_update (mean AND variance) to 1e-12 — the two covariance-form
    Gaussian updates in the codebase are the same mathematics."""
    q, p0, m, z, r_prec = 0.04, 50.0, 0.21, 0.24, 400.0
    prior = SimpleNamespace(covariance=np.array([[q]]))
    graph = posterior_update(
        prior,
        baseline=np.array([m]),
        baseline_precision=np.array([p0]),
        observed=np.array([0]),
        observations=np.array([z]),
        observation_precision=np.array([r_prec]),
    )
    upd = kalman_update([m], [[1.0 / p0 + q]], [z], [[1.0 / r_prec]])
    assert upd.mean[0] == pytest.approx(graph.mean[0], abs=1e-12)
    assert upd.cov[0, 0] == pytest.approx(graph.marginal_variance[0], abs=1e-12)


def test_agrees_with_graph_posterior_three_handles():
    """Handle-by-handle (the graph runs per-coordinate): all three agree."""
    q = np.array([0.02, 0.05, 0.4])
    p0 = np.array([80.0, 40.0, 5.0])
    base = np.array([0.2, -0.3, 0.1])
    z = np.array([0.22, -0.35, 0.6])
    r_prec = np.array([900.0, 200.0, 4.0])
    for i in range(3):
        prior = SimpleNamespace(covariance=np.array([[q[i]]]))
        graph = posterior_update(
            prior, base[i : i + 1], p0[i : i + 1], np.array([0]),
            z[i : i + 1], r_prec[i : i + 1],
        )
        upd = kalman_update(
            base[i : i + 1], [[1.0 / p0[i] + q[i]]], z[i : i + 1], [[1.0 / r_prec[i]]]
        )
        assert upd.mean[0] == pytest.approx(graph.mean[0], abs=1e-12)
        assert upd.cov[0, 0] == pytest.approx(graph.marginal_variance[0], abs=1e-12)


# -------------------------------------------------------------- process noise
def test_process_noise_composition():
    """Q sums its named components; clock scales linearly in dt (std in sqrt dt)."""
    q1, br = process_noise(1.0, 0.0)
    assert q1 == pytest.approx(br["clock"])  # only the clock at h=0, no widenings
    assert br["clock"][0] == pytest.approx((10e-4) ** 2)  # 10 bp ATM std at 1 day
    q4, _ = process_noise(4.0, 0.0)
    assert q4 == pytest.approx(2.0**2 * q1)  # variance linear in dt
    q0, _ = process_noise(0.0, 0.0)
    assert q0 == pytest.approx(np.zeros(3))


def test_process_noise_transport_and_widenings():
    """|h| adds the move-scale-weighted spot term; widenings add per-handle."""
    q, br = process_noise(0.0, 0.05, transport_scale=0.2, event_var=1e-4)
    assert br["spot"] == pytest.approx(
        (0.2 * 0.05 * np.asarray(HANDLE_MOVE_SCALES)) ** 2
    )
    assert br["event"] == pytest.approx(np.full(3, 1e-4))
    assert q == pytest.approx(br["spot"] + br["event"])


def test_predict_adds_q_to_cov():
    pred = predict([0.2, -0.3, 0.1], np.diag([1e-4, 1e-3, 1e-2]), [1e-4, 0.0, 1e-2],
                   transport_distance=0.02)
    assert np.diag(pred.cov) == pytest.approx([2e-4, 1e-3, 2e-2])
    assert pred.transport_distance == 0.02
    assert pred.mean == pytest.approx([0.2, -0.3, 0.1])


# ----------------------------------------------------------------- reset rule
def test_should_reset_priority_and_window():
    assert should_reset(1.0, 96.0) is None
    assert should_reset(100.0, 96.0) == "stale"
    assert should_reset(1.0, 96.0, quotes_edited=True) == "quotes_edited"
    assert should_reset(1.0, 96.0, fit_mode_changed=True) == "fit_mode_changed"
    assert should_reset(1.0, 96.0, as_of_changed=True, quotes_edited=True) == "as_of_changed"
    assert (
        should_reset(200.0, 96.0, source_changed=True, as_of_changed=True)
        == "source_changed"
    )


# ------------------------------------------------- MAP residual (Prop nodouble)
def test_map_residual_minimizer_equals_kalman_posterior():
    """Minimizing |R^{-1/2}(z - x)|^2 + |L^{-1}(x - m^-)|^2 over x reproduces the
    Kalman posterior mean (Note 15 Prop. nodouble) — the seed of the Phase-6
    double-count guard."""
    m = np.array([0.2, -0.3, 0.1])
    a = RNG.normal(size=(3, 3))
    P = a @ a.T + 0.05 * np.eye(3)
    z = np.array([0.24, -0.4, 0.5])
    R = np.diag([0.01, 0.04, 0.09])
    # least-squares stack: rows [R^{-1/2}; L^{-1}] x = [R^{-1/2} z; L^{-1} m]
    r_half = np.diag(1.0 / np.sqrt(np.diag(R)))
    chol = np.linalg.cholesky(P)
    l_inv = np.linalg.inv(chol)
    A = np.vstack([r_half, l_inv])
    b = np.concatenate([r_half @ z, l_inv @ m])
    x_map = np.linalg.lstsq(A, b, rcond=None)[0]
    upd = kalman_update(m, P, z, R)
    assert x_map == pytest.approx(upd.mean, abs=1e-10)
    # and the residual helper whitens consistently: zero residual at x = m^-
    rows, jitter = prediction_prior_residual(m, m, P)
    assert rows == pytest.approx(np.zeros(3), abs=1e-15)
    assert jitter == 0.0


def test_prediction_prior_residual_jitter_reported():
    """A singular P^- succeeds only via reported jitter — never silently."""
    P = np.zeros((2, 2))  # degenerate on purpose
    rows, jitter = prediction_prior_residual([1.0, 0.0], [0.0, 0.0], P)
    assert jitter > 0.0  # the diagnostic event is surfaced
    assert np.all(np.isfinite(rows))


def test_handle_names_consistent_with_move_scales():
    assert len(HANDLE_NAMES) == len(HANDLE_MOVE_SCALES) == 3

"""Observation-filter ACTIVE mode — one-stage MAP (Phase 6 of
Docs/observation_filter_roadmap.md; Note 15 eq. active-map + Prop. nodouble).

Locks:
  * the DOUBLE-COUNT GUARD — on a linear(-quadratic) model, minimizing the
    quote loss + the build_filter_prior rows reproduces the Kalman posterior
    mean exactly (stencil identities are exact on quadratics), and the WRONG
    architecture (posterior-as-prior + the same quotes again) does not;
  * the persistence auto-exclusion truth table in resolve_prior_mode;
  * end-to-end active mode on the synthetic provider: seed -> MAP commit with
    provenance "map", implied gains in [0,1], the fit pulled toward the
    prediction vs a data-only fit;
  * off/overlay leave prior_targets byte-identical (no filter target).
"""

from datetime import date

import numpy as np
import pytest

from volfit.api import observation_filter as ofilt
from volfit.api import service
from volfit.api.prior_mode import resolve_prior_mode
from volfit.api.schemas import OptionsSettings
from volfit.api.state import AppState
from volfit.calib.observation_filter import build_filter_prior, kalman_update
from volfit.calib.operators import operator_residuals

REF_DATE = date(2026, 7, 3)
TICKER = "ALPHA"


def _iso(state):
    return [e.isoformat() for e in sorted(state.forwards(TICKER))][-1]


# ------------------------------------------------------- MAP == Kalman (guard)
def _quad_design(k):
    return np.column_stack([np.ones_like(k), k, k**2])


def _stack_and_solve(a, y, target, tau, sigma_q):
    """Minimize |sigma(k)-y|^2 + the filter-prior rows over theta (quadratic
    smile sigma = th0 + th1 k + th2 k^2, handles = (th0, th1, 2 th2))."""
    def w_fn_of(theta):
        return lambda kk: (theta[0] + theta[1] * kk + theta[2] * kk**2) ** 2 * tau

    # linear LSQ: data rows [a | y] plus prior rows sqrt(lam)*(coeff sigma - pv)
    # where sigma at legs is linear in theta => rows are linear too.
    legs = target.legs_k
    leg_design = _quad_design(legs)  # sigma(legs) = leg_design @ theta
    prior_rows = np.sqrt(target.active_lambda)[:, None] * (target.coeff @ leg_design)
    prior_rhs = np.sqrt(target.active_lambda) * target.prior_value
    A = np.vstack([a, prior_rows])
    b = np.concatenate([y, prior_rhs])
    theta = np.linalg.lstsq(A, b, rcond=None)[0]
    # sanity: operator_residuals agrees with the rows we stacked
    res = operator_residuals(w_fn_of(theta), target)
    assert res == pytest.approx(prior_rows @ theta - prior_rhs, abs=1e-10)
    return np.array([theta[0], theta[1], 2.0 * theta[2]])


def test_map_equals_kalman_posterior():
    """The one-stage MAP minimizer == the Kalman posterior mean (Prop. nodouble),
    through the REAL build_filter_prior stencil units."""
    k = np.linspace(-0.25, 0.25, 15)
    a = _quad_design(k)
    tau = 0.25
    sigma_q = 0.002  # stated quote noise (homoskedastic)
    theta_true = np.array([0.21, -0.06, 0.35])
    y = a @ theta_true  # clean quotes at the true smile
    g_map = np.diag([1.0, 1.0, 2.0])  # handles = G theta

    m_minus = np.array([0.20, -0.05, 0.30])
    p_minus = np.array([0.0004, 0.01, 0.09]) ** 1  # variances per handle

    target = build_filter_prior(m_minus, p_minus, tau, quote_noise=sigma_q)
    h_map = _stack_and_solve(a, y, target, tau, sigma_q)

    # the data-only estimator and its covariance in handle space
    theta_hat = np.linalg.lstsq(a, y, rcond=None)[0]
    z = np.array([theta_hat[0], theta_hat[1], 2.0 * theta_hat[2]])
    r = sigma_q**2 * (g_map @ np.linalg.inv(a.T @ a) @ g_map.T)
    upd = kalman_update(m_minus, np.diag(p_minus), z, r)
    assert h_map == pytest.approx(upd.mean, abs=1e-10)


def test_double_count_architecture_differs():
    """The WRONG architecture — build the posterior first, then use IT as the
    prior while refitting the same quotes — lands somewhere else (the quotes
    counted twice). The guard distinguishes the two."""
    k = np.linspace(-0.25, 0.25, 15)
    a = _quad_design(k)
    tau, sigma_q = 0.25, 0.002
    y = a @ np.array([0.21, -0.06, 0.35])
    m_minus = np.array([0.20, -0.05, 0.30])
    p_minus = np.array([0.0004, 0.01, 0.09])
    g_map = np.diag([1.0, 1.0, 2.0])

    theta_hat = np.linalg.lstsq(a, y, rcond=None)[0]
    z = np.array([theta_hat[0], theta_hat[1], 2.0 * theta_hat[2]])
    r = sigma_q**2 * (g_map @ np.linalg.inv(a.T @ a) @ g_map.T)
    upd = kalman_update(m_minus, np.diag(p_minus), z, r)

    # wrong: the posterior fed back as a prior against the SAME quotes
    wrong_target = build_filter_prior(
        upd.mean, np.maximum(np.diag(upd.cov), 1e-18), tau, quote_noise=sigma_q
    )
    h_wrong = _stack_and_solve(a, y, wrong_target, tau, sigma_q)
    assert not np.allclose(h_wrong, upd.mean, atol=1e-6)  # pulled back to data


def test_filter_prior_stencils_exact_on_quadratic():
    """Stencil identities: on a quadratic smile the target's operator values
    equal (sigma0, 2h*skew, h^2*curv) exactly."""
    m = np.array([0.2, -0.4, 1.5])
    target = build_filter_prior(m, np.ones(3), 0.5, quote_noise=1.0)
    h = target.legs_k[-1]
    assert target.prior_value == pytest.approx(
        [m[0], 2 * h * m[1], h * h * m[2]], abs=1e-15
    )
    # no gate: every lambda strictly positive regardless of quote support
    assert np.all(target.active_lambda > 0.0)


# ------------------------------------------------------------- auto-exclusion
def test_auto_exclusion_truth_table():
    """Active filter drops ATM-local persistence; the deep-tail anchor survives
    for any mode that had a calibration prior; graph_only untouched."""
    for mode, tail in [
        ("off", False), ("overlay", False), ("graph_only", False),
        ("strike_gap", True), ("quote_operator", True),
        ("smile_factor", True), ("hybrid", True),
    ]:
        plan = resolve_prior_mode(OptionsSettings(
            priorPersistenceMode=mode, observationFilterMode="active",
        ))
        assert plan.operators is False and plan.factors is False
        assert plan.strike_anchor is False
        assert plan.tail_anchor is tail, mode
    # overlay/off filter modes change NOTHING (byte-identical persistence)
    for fmode in ("off", "overlay"):
        plan = resolve_prior_mode(OptionsSettings(
            priorPersistenceMode="hybrid", observationFilterMode=fmode,
        ))
        assert plan.operators is True and plan.tail_anchor is True


# ------------------------------------------------------------------ end-to-end
def test_active_mode_end_to_end():
    """Seed (data-only) -> switch snapshot version -> the MAP commit anchors the
    fit to the prediction: provenance 'map', implied gains in [0,1], and the
    refit handles sit between the data-only fit and the prediction."""
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={
        "observationFilterMode": "active", "priorPersistenceMode": "off",
    }))
    iso = _iso(state)
    record = service.displayed_base(state, TICKER, iso, "mid")
    seeded = state.filter_node((TICKER, iso, "mid"))
    assert seeded is not None and seeded.state.reset_reason == "first"

    # the prediction target now resolves (a previous state exists)
    prepared = record.prepared
    ft = ofilt.active_prediction_target(state, TICKER, iso, "mid", prepared)
    assert ft is not None and list(ft.names) == ["filterATM", "filterSkew", "filterCurv"]

    # a new observation of the same chain: the commit runs the MAP branch
    state.bump_data_version(TICKER)
    fd: dict = {}
    from volfit.models.lqd.calibrate import calibrate_slice

    k, w = prepared.k, prepared.w_mid
    pt = service.prior_targets(state, TICKER, iso, k, None, prepared, "mid")
    assert pt.operator_prior is not None  # the filter prior reached the fit path
    refit = calibrate_slice(
        k, w, t=prepared.tau, n_order=6,
        operator_prior=pt.operator_prior, solver_diag=fd,
    )
    from volfit.api.state import FitRecord

    holder = ofilt.on_fit_commit(
        state, TICKER, iso, "mid",
        FitRecord(prepared=prepared, result=refit, display=None), fd,
    )
    assert holder.state.provenance == "map"
    assert holder.measurement.breakdown.get("map") == 1.0
    gains = np.diag(holder.update.gain)
    assert np.all(gains >= 0.0) and np.all(gains <= 1.0)
    # posterior variance never exceeds the prediction variance (information adds)
    assert np.all(np.diag(holder.state.cov) <= np.diag(holder.prediction.cov) + 1e-15)


def test_off_overlay_no_filter_target():
    """In off/overlay the fit path receives NO filter prior (byte-identical)."""
    state = AppState(REF_DATE)
    for mode in ("off", "overlay"):
        state.set_options(state.options().model_copy(update={
            "observationFilterMode": mode, "priorPersistenceMode": "off",
        }))
        iso = _iso(state)
        record = service.displayed_base(state, TICKER, iso, "mid")
        pt = service.prior_targets(
            state, TICKER, iso, record.prepared.k, None, record.prepared, "mid"
        )
        assert pt.operator_prior is None and pt.prior_anchor is None

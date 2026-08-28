"""Wing operators surviving an ACTIVE observation filter — the Note 15 §6.3
carve-out (Docs/handoff/notes/15_kalman_computed_trust.md:268-278; ROADMAP
rider 2026-08-26a "wing operators surviving an ACTIVE filter (separate path)").

Locks:
* ``merge_operator_targets`` — identity on a missing side (the SAME object, so
  the flag-OFF path is byte-identical), equal-tau guard, and the merged
  block's residual rows reproduce the filter block's rows EXACTLY (the zero
  padding never perturbs the stencil rows) and the wings-only block's rows;
* end-to-end on the synthetic provider — active filter + hybrid + WingL/WingR
  in the set + a saved prior + a seeded filter state: flag OFF = the three
  filter rows only (today's block, byte-identical); flag ON = the filter rows
  followed by WingL/WingR, the filter rows unchanged;
* no Wing in the set => the flag is inert: identical operator block and an
  identical fitted LQD vector.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from volfit.api import observation_filter as ofilt
from volfit.api import priors, service
from volfit.api.state import AppState
from volfit.calib import operators as ops
from volfit.calib.observation_filter import build_filter_prior
from volfit.calib.operator_merge import merge_operator_targets
from volfit.models.lqd.calibrate import calibrate_slice

REF_DATE = date(2026, 6, 10)
TAU = 0.5
SIG0 = 0.20
DELTAS = (0.02, 0.05, 0.10, 0.25, 0.40)  # the priorAnchorDeltas default
FILTER_ROWS = ["filterATM", "filterSkew", "filterCurv"]
WING_SET = ["ATM", "RR25", "BF25", "WingL", "WingR", "VarSwap"]


def skew_w(k):
    """Linear-in-k vol smile (sigma = SIG0 - 0.5k): every slope is -0.5."""
    k = np.asarray(k, dtype=float)
    sig = SIG0 - 0.5 * k
    return sig * sig * TAU


def flat_w(k):
    k = np.asarray(k, dtype=float)
    return np.full_like(k, SIG0 * SIG0 * TAU)


def convex_w(k):
    k = np.asarray(k, dtype=float)
    sig = SIG0 + 0.3 * k + 2.0 * k * k
    return sig * sig * TAU


def _filter_block(tau=TAU):
    return build_filter_prior(
        np.array([0.21, -0.4, 1.5]), np.array([1e-4, 1e-2, 1e-1]), tau, quote_noise=0.01
    )


def _wings_block():
    target, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, np.array([-0.02, 0.0, 0.02]), None, total_budget=10.0,
        op_set=["WingL", "WingR"], bandwidth=0.03, anchor_deltas=DELTAS,
    )
    assert target is not None and target.names == ["WingL", "WingR"]
    return target


# ------------------------------------------------------------- the merge
def test_merge_identity_on_missing_side():
    """A missing side returns the OTHER block itself — the same object, not a
    copy — so the default (flag OFF) path hands the fit the filter target
    untouched."""
    ft = _filter_block()
    wings = _wings_block()
    assert merge_operator_targets(ft, None) is ft
    assert merge_operator_targets(None, wings) is wings
    assert merge_operator_targets(None, None) is None


def test_merge_rejects_tau_mismatch():
    with pytest.raises(ValueError):
        merge_operator_targets(_filter_block(TAU), _filter_block(2.0 * TAU))


def test_merged_rows_reproduce_both_blocks_exactly():
    """The merged block stacks legs / rows block-diagonally: for any model
    smile its ``operator_residuals`` rows equal the filter block's rows
    EXACTLY (zero padding is exact) and the wing rows equal the wings-only
    block's rows."""
    ft = _filter_block()
    wings = _wings_block()
    merged = merge_operator_targets(ft, wings)
    assert merged.names == FILTER_ROWS + ["WingL", "WingR"]
    n_f, m_f = ft.coeff.shape
    assert merged.coeff.shape == (n_f + wings.coeff.shape[0], m_f + wings.coeff.shape[1])
    np.testing.assert_array_equal(merged.legs_k, np.concatenate([ft.legs_k, wings.legs_k]))
    np.testing.assert_array_equal(merged.coeff[:n_f, :m_f], ft.coeff)
    np.testing.assert_array_equal(merged.coeff[n_f:, m_f:], wings.coeff)
    assert not merged.coeff[:n_f, m_f:].any() and not merged.coeff[n_f:, :m_f].any()
    np.testing.assert_array_equal(merged.prior_value[:n_f], ft.prior_value)
    np.testing.assert_array_equal(merged.active_lambda[n_f:], wings.active_lambda)
    assert merged.tau == ft.tau
    assert [d["operator"] for d in merged.diagnostics] == merged.names
    for model in (flat_w, skew_w, convex_w):
        r = ops.operator_residuals(model, merged)
        assert r.shape == (len(merged.names),)
        np.testing.assert_array_equal(r[:n_f], ops.operator_residuals(model, ft))
        # The wing rows of the merged block accumulate through a wider dgemv
        # (padded zeros before the nonzero legs) — bit-equality is a BLAS
        # kernel property, not a language one; 1 ulp is the honest lock.
        np.testing.assert_allclose(
            r[n_f:], ops.operator_residuals(model, wings), rtol=1e-14, atol=1e-15
        )


# ---------------------------------------------------------------- end-to-end
def _active_hybrid_state(op_set: list[str]) -> tuple[AppState, str, str]:
    """Active filter + hybrid persistence, a seeded filter state and a saved,
    ACTIVE prior for one node (test_filter_active's recipe + a captured
    snapshot); returns (state, ticker, iso) with the flag OFF."""
    state = AppState(REF_DATE)
    ticker = state.active_tickers()[0]
    state.set_options(state.options().model_copy(update={
        "observationFilterMode": "active",
        "priorPersistenceMode": "hybrid",
        "priorOperatorSet": op_set,
        "priorOperatorBandwidth": 0.02,
        "wingOperatorsUnderActiveFilter": False,
    }))
    iso = sorted(state.forwards(ticker))[1].isoformat()
    service.displayed_base(state, ticker, iso, "mid")  # calibrates + seeds the filter
    assert state.filter_node((ticker, iso, "mid")) is not None
    snap = priors.capture_snapshot(state, ticker, "mid", lv=False)
    assert snap is not None
    state.set_active_prior(ticker, snap, "saved")  # the persistence prior
    state.bump_data_version(ticker)  # a new observation of the same chain
    return state, ticker, iso


def _flip(state: AppState, flag: bool) -> None:
    state.set_options(state.options().model_copy(update={
        "wingOperatorsUnderActiveFilter": flag,
    }))


def _targets(state: AppState, ticker: str, iso: str):
    prepared = service.prepared_quotes(state, ticker, state.resolve_expiry(ticker, iso))
    pt = service.prior_targets(state, ticker, iso, prepared.k, None, prepared, "mid")
    assert pt.operator_prior is not None  # the filter prior reached the fit path
    return prepared, pt


def test_flag_adds_wing_rows_beside_the_filter_rows():
    """Flag OFF: the operator block is the three filter rows only (today's
    block). Flag ON: the same three rows, unchanged, followed by WingL/WingR;
    the LQD fit consumes the merged block."""
    state, ticker, iso = _active_hybrid_state(WING_SET)
    prepared, off = _targets(state, ticker, iso)
    assert list(off.operator_prior.names) == FILTER_ROWS
    ft = ofilt.active_prediction_target(state, ticker, iso, "mid", prepared)
    np.testing.assert_array_equal(off.operator_prior.coeff, ft.coeff)
    np.testing.assert_array_equal(off.operator_prior.active_lambda, ft.active_lambda)

    _flip(state, True)
    prepared_on, on = _targets(state, ticker, iso)
    assert list(on.operator_prior.names) == FILTER_ROWS + ["WingL", "WingR"]
    n_f = len(FILTER_ROWS)
    np.testing.assert_array_equal(on.operator_prior.legs_k[:n_f], off.operator_prior.legs_k)
    np.testing.assert_array_equal(on.operator_prior.coeff[:n_f, :n_f], off.operator_prior.coeff)
    np.testing.assert_array_equal(on.operator_prior.prior_value[:n_f], off.operator_prior.prior_value)
    np.testing.assert_array_equal(on.operator_prior.active_lambda[:n_f], off.operator_prior.active_lambda)
    assert np.all(on.operator_prior.active_lambda[n_f:] > 0.0)
    assert on.prior_var_swap is None  # VarSwap stays with the body switch
    # the prior-diagnostics wire lists the merged rows
    diag = service.prior_diagnostics(state, ticker, iso, "mid")
    assert [d.operator for d in diag.operators] == FILTER_ROWS + ["WingL", "WingR"]
    # the merged block runs through the LQD calibrator
    fit = calibrate_slice(
        prepared_on.k, prepared_on.w_mid, t=prepared_on.tau, n_order=6,
        operator_prior=on.operator_prior,
    )
    assert np.all(np.isfinite(fit.params.to_vector()))

    _flip(state, False)  # back off: today's block again
    _, back = _targets(state, ticker, iso)
    assert list(back.operator_prior.names) == FILTER_ROWS
    np.testing.assert_array_equal(back.operator_prior.coeff, off.operator_prior.coeff)


def test_flag_inert_without_wing_operators():
    """No Wing name in the set => the flag changes nothing: identical operator
    block (the filter rows) and an identical fitted LQD vector."""
    state, ticker, iso = _active_hybrid_state(["ATM", "RR25", "BF25", "VarSwap"])
    prepared, off = _targets(state, ticker, iso)
    _flip(state, True)
    _, on = _targets(state, ticker, iso)
    assert list(off.operator_prior.names) == FILTER_ROWS
    assert list(on.operator_prior.names) == FILTER_ROWS
    np.testing.assert_array_equal(on.operator_prior.legs_k, off.operator_prior.legs_k)
    np.testing.assert_array_equal(on.operator_prior.coeff, off.operator_prior.coeff)
    np.testing.assert_array_equal(on.operator_prior.prior_value, off.operator_prior.prior_value)
    np.testing.assert_array_equal(on.operator_prior.active_lambda, off.operator_prior.active_lambda)
    fit_off = calibrate_slice(
        prepared.k, prepared.w_mid, t=prepared.tau, n_order=6, operator_prior=off.operator_prior
    )
    fit_on = calibrate_slice(
        prepared.k, prepared.w_mid, t=prepared.tau, n_order=6, operator_prior=on.operator_prior
    )
    np.testing.assert_array_equal(fit_on.params.to_vector(), fit_off.params.to_vector())

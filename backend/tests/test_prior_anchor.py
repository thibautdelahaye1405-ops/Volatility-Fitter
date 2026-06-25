"""Bayesian data-gap prior anchor (volfit.calib.prior, the autoLoadPrior feature).

The anchor pulls an LQD fit toward a (transported) prior at delta-locations, with a
per-location precision = the gap between the desired and the observed quote
density: dense-quote zones get ~0 prior weight (data wins), sparse wings lean on
the prior. The default (no anchor) leaves the fit byte-identical.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from tests import benchmarks as bm
from volfit.api import priors, service
from volfit.api.state import AppState
from volfit.calib.prior import (
    build_prior_anchor,
    delta_anchor_strikes,
    prior_anchor_residuals,
)
from volfit.models.lqd.calibrate import calibrate_slice

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _prior_w():
    """A prior total-variance function (the SVI benchmark curve)."""
    return bm.SVI_RAW.total_variance


# --------------------------------------------------------------- module units
def test_delta_strikes_span_puts_atm_calls_ascending():
    strikes = delta_anchor_strikes(_prior_w(), bm.SVI_T)
    assert strikes.ndim == 1 and strikes.size == 11  # 2/5/10/25/40 per side + ATM
    assert np.all(np.diff(strikes) > 0)  # ascending
    assert strikes[0] < 0.0 < strikes[-1]  # deep put .. deep call
    assert abs(strikes[strikes.size // 2]) < 0.1  # middle anchor ~ ATM


def test_deeper_deltas_reach_further_into_the_wings():
    """A deeper delta set (2-delta) places anchors further out than a shallow one."""
    shallow = delta_anchor_strikes(_prior_w(), bm.SVI_T, deltas=(0.25,))
    deep = delta_anchor_strikes(_prior_w(), bm.SVI_T, deltas=(0.02, 0.25))
    assert deep.min() < shallow.min() and deep.max() > shallow.max()


def test_inv_vega_cap_bounds_tail_amplification():
    """The deep-wing vega-normalizer is capped relative to the most-liquid anchor."""
    from volfit.calib.prior import MAX_INV_VEGA_RATIO

    k = np.linspace(-0.05, 0.05, 9)
    target, _ = build_prior_anchor(_prior_w(), bm.SVI_T, k, bm.SVI_T, 5.0)
    assert target is not None
    assert target.inv_vega.max() <= MAX_INV_VEGA_RATIO * target.inv_vega.min() + 1e-6


def test_build_prior_anchor_none_cases():
    k = np.linspace(-0.2, 0.2, 15)
    none_budget, _ = build_prior_anchor(_prior_w(), bm.SVI_T, k, bm.SVI_T, 0.0)
    assert none_budget is None  # no budget
    none_quotes, _ = build_prior_anchor(_prior_w(), bm.SVI_T, np.array([]), bm.SVI_T, 5.0)
    assert none_quotes is None  # no quotes


def test_data_gap_weights_concentrate_in_the_wings():
    """Quotes only near the money: the anchor weight lands in the sparse wings and
    is ~zero near ATM (where the observed density already meets the desired)."""
    k_quotes = np.linspace(-0.05, 0.05, 9)  # dense ATM, empty wings
    target, unmet = build_prior_anchor(_prior_w(), bm.SVI_T, k_quotes, bm.SVI_T, 5.0)
    assert target is not None
    assert unmet > 0.0  # the wings are unobserved
    # Every retained anchor is outside the densely-quoted ATM cluster.
    assert np.all(np.abs(target.k) > 0.05)
    assert float(target.weights.sum()) <= 5.0 + 1e-9  # within budget


def test_residuals_zero_when_model_matches_prior():
    k_quotes = np.linspace(-0.05, 0.05, 9)
    target, _ = build_prior_anchor(_prior_w(), bm.SVI_T, k_quotes, bm.SVI_T, 5.0)
    res = prior_anchor_residuals(target.target_price, target)  # model price == prior
    assert np.allclose(res, 0.0)


# ------------------------------------------------------------- byte-identical
def test_none_anchor_leaves_the_fit_byte_identical():
    k = np.linspace(*bm.SVI_FIT_RANGE, 50)
    w = bm.SVI_RAW.total_variance(k)
    base = calibrate_slice(k, w, t=bm.SVI_T, n_order=6)
    same = calibrate_slice(k, w, t=bm.SVI_T, n_order=6, prior_anchor=None, prior_var_swap=None)
    assert same.cost == base.cost
    assert np.array_equal(same.params.to_vector(), base.params.to_vector())


# ----------------------------------------------------------------- mechanism
def test_prior_anchor_fills_sparse_wings_toward_the_prior():
    """With quotes only near the money, the wings are unidentified; a prior with
    fatter wings pulls the fitted wings up toward it via the data-gap anchor."""
    t = bm.SVI_T
    k_quotes = np.linspace(-0.06, 0.06, 9)  # ATM-only observations
    w_quotes = bm.SVI_RAW.total_variance(k_quotes)

    def prior_w(kk: np.ndarray) -> np.ndarray:  # fatter-winged prior
        return bm.SVI_RAW.total_variance(kk) * 1.25

    base = calibrate_slice(k_quotes, w_quotes, t=t, n_order=6)
    target, _ = build_prior_anchor(prior_w, t, k_quotes, t, total_budget=2.0 * k_quotes.size)
    assert target is not None
    anchored = calibrate_slice(k_quotes, w_quotes, t=t, n_order=6, prior_anchor=target)

    kw = target.k  # the wing anchor points
    base_vol = np.sqrt(np.maximum(base.slice.implied_w(kw), 0.0) / t)
    anch_vol = np.sqrt(np.maximum(anchored.slice.implied_w(kw), 0.0) / t)
    prior_vol = np.sqrt(prior_w(kw) / t)

    assert np.mean(anch_vol) > np.mean(base_vol)  # moved up toward the fatter prior
    assert np.mean(np.abs(anch_vol - prior_vol)) < np.mean(np.abs(base_vol - prior_vol))


# ------------------------------------------------------------- service gating
def _strike_gap_state():
    """An AppState in strike_gap mode with a node resolved (for the gating tests)."""
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"priorPersistenceMode": "strike_gap"}))
    iso = [e.isoformat() for e in sorted(state.forwards(TICKER))][1]
    record = service.displayed_base(state, TICKER, iso, "mid")
    return state, iso, record.prepared, record.prepared.k


def test_prior_targets_gating():
    """service.prior_targets: empty unless autoLoadPrior is on AND a prior has been
    fetched (active); a real strike anchor once both hold (strike_gap mode)."""
    state, iso, prepared, k = _strike_gap_state()

    # Off by default (autoLoadPrior False).
    pt = service.prior_targets(state, TICKER, iso, k, None, prepared)
    assert pt.prior_anchor is None and pt.operator_prior is None and pt.prior_var_swap is None

    # autoLoadPrior on but no active (fetched) prior yet: still empty.
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    pt = service.prior_targets(state, TICKER, iso, k, None, prepared)
    assert pt.prior_anchor is None

    # Save + fetch -> active prior -> a real STRIKE anchor (not an operator target).
    priors.save_all(state)
    priors.fetch_all(state)
    pt = service.prior_targets(state, TICKER, iso, k, None, prepared)
    assert pt.prior_anchor is not None and pt.prior_anchor.k.size > 0
    assert pt.operator_prior is None  # strike_gap mode routes to the anchor, not operators


def test_prior_targets_operator_mode_routes_to_operators():
    """quote_operator mode routes to the signed operator prior, not the strike anchor.

    Driven with a SPARSE near-ATM quote set (+ a tight support bandwidth) so the
    RR/BF wing operators are under-observed and activate; a dense chain would
    correctly leave them off (the data wins)."""
    state, iso, prepared, _k = _strike_gap_state()
    state.set_options(state.options().model_copy(update={
        "priorPersistenceMode": "quote_operator", "autoLoadPrior": True,
        "priorOperatorBandwidth": 0.03,
    }))
    priors.save_all(state)
    priors.fetch_all(state)
    k_sparse = np.array([-0.01, 0.0, 0.01])  # ATM-only -> wings under-observed
    pt = service.prior_targets(state, TICKER, iso, k_sparse, None, prepared)
    assert pt.prior_anchor is None  # not the strike-gap path
    assert pt.operator_prior is not None and len(pt.operator_prior.names) > 0


def test_prior_targets_hybrid_sets_operator_and_tail_anchor():
    """hybrid mode returns BOTH the operator prior AND a residual deep-tail strike
    anchor (the deltas below the shallowest wing operator)."""
    state, iso, prepared, _k = _strike_gap_state()
    state.set_options(state.options().model_copy(update={
        "priorPersistenceMode": "hybrid", "autoLoadPrior": True,
        "priorOperatorBandwidth": 0.03,
    }))
    priors.save_all(state)
    priors.fetch_all(state)
    k_sparse = np.array([-0.01, 0.0, 0.01])  # sparse -> operators + tail both bite
    pt = service.prior_targets(state, TICKER, iso, k_sparse, None, prepared)
    assert pt.operator_prior is not None and len(pt.operator_prior.names) > 0
    assert pt.prior_anchor is not None and pt.prior_anchor.k.size > 0  # the deep-tail anchor


def test_prior_targets_smile_factor_routes_to_factors():
    """smile_factor mode routes to the factor prior (operator_prior slot), no strike anchor."""
    state, iso, prepared, _k = _strike_gap_state()
    state.set_options(state.options().model_copy(update={
        "priorPersistenceMode": "smile_factor", "autoLoadPrior": True,
        "priorOperatorBandwidth": 0.02,
    }))
    priors.save_all(state)
    priors.fetch_all(state)
    k_sparse = np.array([-0.004, 0.0, 0.004])  # very sparse -> ATM-local factors bite
    pt = service.prior_targets(state, TICKER, iso, k_sparse, None, prepared)
    assert pt.prior_anchor is None
    assert pt.operator_prior is not None and len(pt.operator_prior.names) > 0


def test_prior_targets_off_and_graph_only_are_empty():
    """off / overlay / graph_only add no calibration penalty even with a prior active."""
    state, iso, prepared, k = _strike_gap_state()
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    priors.save_all(state)
    priors.fetch_all(state)
    for mode in ("off", "overlay", "graph_only"):
        state.set_options(state.options().model_copy(update={"priorPersistenceMode": mode}))
        pt = service.prior_targets(state, TICKER, iso, k, None, prepared)
        assert pt.prior_anchor is None and pt.operator_prior is None and pt.prior_var_swap is None


def test_affine_prior_anchor_quotes_gated_and_present():
    """The affine LV fit gains delta-location prior anchor quotes only when
    autoLoadPrior is on and a prior is active (same data-gap framework)."""
    from volfit.api import affine_fit

    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    priors.save_all(state)
    priors.fetch_all(state)

    rows = affine_fit._gather(state, TICKER, "mid")
    extra_opts, _extra_vs = affine_fit._prior_anchor_quotes(state, TICKER, rows)
    assert len(extra_opts) > 0  # delta-location anchors added to the LV fit

    # Off -> no anchor quotes.
    state.set_options(state.options().model_copy(update={"autoLoadPrior": False}))
    assert affine_fit._prior_anchor_quotes(state, TICKER, rows) == ([], [])


def test_affine_prior_lv_targets_route_by_mode():
    """affine_fit._prior_lv_targets returns the right shape per mode (no errors):
    strike_gap -> option quotes; operator/factor -> baskets; hybrid -> baskets (+ a
    deep-tail anchor); off -> empty."""
    from volfit.api import affine_fit

    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    priors.save_all(state)
    priors.fetch_all(state)
    rows = affine_fit._gather(state, TICKER, "mid")

    def _set(mode, **extra):
        state.set_options(state.options().model_copy(update={"priorPersistenceMode": mode, **extra}))

    _set("strike_gap")
    o, b, _v = affine_fit._prior_lv_targets(state, TICKER, rows)
    assert len(o) > 0 and b == []  # legacy strike quotes

    _set("quote_operator", priorOperatorBandwidth=0.03)
    o, b, _v = affine_fit._prior_lv_targets(state, TICKER, rows)
    assert o == [] and isinstance(b, list)  # baskets path (may be empty on dense data)

    _set("hybrid", priorOperatorBandwidth=0.03)
    o, b, _v = affine_fit._prior_lv_targets(state, TICKER, rows)
    assert isinstance(o, list) and isinstance(b, list)  # operators + tail anchor, no error

    _set("smile_factor", priorOperatorBandwidth=0.02)
    o, b, _v = affine_fit._prior_lv_targets(state, TICKER, rows)
    assert o == [] and isinstance(b, list)  # factor baskets path

    _set("off")
    assert affine_fit._prior_lv_targets(state, TICKER, rows) == ([], [], [])


def test_fetched_prior_busts_the_fit_cache():
    """A fetch bumps the active-prior version so calibrate re-anchors instead of
    serving a stale cached fit (autoLoadPrior on)."""
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    v0 = state.active_prior_version(TICKER)
    priors.save_all(state)
    priors.fetch_all(state)
    assert state.active_prior_version(TICKER) > v0  # fit_key changes -> refit

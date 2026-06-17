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
    assert strikes.ndim == 1 and strikes.size == 7  # 10/25/40 per side + ATM
    assert np.all(np.diff(strikes) > 0)  # ascending
    assert strikes[0] < 0.0 < strikes[-1]  # deep put .. deep call
    assert abs(strikes[strikes.size // 2]) < 0.1  # middle anchor ~ ATM


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
def test_prior_anchor_targets_gating():
    """service.prior_anchor_targets: None unless autoLoadPrior is on AND a prior
    has been fetched (active); a real target once both hold."""
    state = AppState(REF_DATE)
    iso = [e.isoformat() for e in sorted(state.forwards(TICKER))][1]
    record = service.displayed_base(state, TICKER, iso, "mid")
    k = record.prepared.k

    # Off by default.
    anchor, vs = service.prior_anchor_targets(state, TICKER, iso, k, None, record.prepared)
    assert anchor is None and vs is None

    # autoLoadPrior on but no active (fetched) prior yet: still None.
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    anchor, vs = service.prior_anchor_targets(state, TICKER, iso, k, None, record.prepared)
    assert anchor is None and vs is None

    # Save + fetch -> active prior -> a real anchor target.
    priors.save_all(state)
    priors.fetch_all(state)
    anchor, _vs = service.prior_anchor_targets(state, TICKER, iso, k, None, record.prepared)
    assert anchor is not None and anchor.k.size > 0


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


def test_fetched_prior_busts_the_fit_cache():
    """A fetch bumps the active-prior version so calibrate re-anchors instead of
    serving a stale cached fit (autoLoadPrior on)."""
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    v0 = state.active_prior_version(TICKER)
    priors.save_all(state)
    priors.fetch_all(state)
    assert state.active_prior_version(TICKER) > v0  # fit_key changes -> refit

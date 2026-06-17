"""Prior-anchor penalty (the autoLoadPrior feature, volfit.calib.prior).

A saved prior pulls the LQD fit toward its shape in the quote-free WINGS only,
written in the same vega-normalized call-price space as the data residual. The
default (no anchor) must leave the fit byte-identical, so the golden tests stay
untouched.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from tests import benchmarks as bm
from volfit.api import service
from volfit.api.state import AppState, PriorRecord
from volfit.calib.prior import (
    build_prior_anchor,
    prior_anchor_residuals,
    wing_points,
)
from volfit.models.lqd.calibrate import calibrate_slice

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


# --------------------------------------------------------------- module units
def test_wing_points_lie_strictly_outside_the_quote_range():
    k = np.linspace(-0.25, 0.25, 40)
    wings = wing_points(k, span=0.6, gap=0.05, n_per_side=3)
    assert wings.size == 6  # 3 per side
    assert np.all((wings < k.min()) | (wings > k.max()))  # none inside the quotes
    assert wings.min() >= k.min() - 0.6 - 1e-9
    assert wings.max() <= k.max() + 0.6 + 1e-9


def test_wing_points_empty_without_quotes():
    assert wing_points(np.empty(0)).size == 0


def test_build_prior_anchor_inert_cases():
    k = np.linspace(-0.2, 0.2, 20)
    w = lambda kk: bm.SVI_RAW.total_variance(kk)  # noqa: E731
    assert build_prior_anchor(w, k, tau=bm.SVI_T, total_weight=0.0) is None  # no weight
    assert build_prior_anchor(w, np.empty(0), tau=bm.SVI_T, total_weight=5.0) is None  # no quotes
    assert build_prior_anchor(w, k, tau=0.0, total_weight=5.0) is None  # no time


def test_prior_anchor_residuals_zero_when_model_matches_prior():
    k = np.linspace(-0.2, 0.2, 20)
    target = build_prior_anchor(bm.SVI_RAW.total_variance, k, tau=bm.SVI_T, total_weight=5.0)
    assert target is not None
    res = prior_anchor_residuals(target.target_price, target)  # model price == prior price
    assert np.allclose(res, 0.0)


# ------------------------------------------------------------- byte-identical
def test_none_anchor_leaves_the_fit_byte_identical():
    """The default (prior_anchor=None) must not perturb the optimizer at all."""
    k = np.linspace(*bm.SVI_FIT_RANGE, 50)
    w = bm.SVI_RAW.total_variance(k)
    base = calibrate_slice(k, w, t=bm.SVI_T, n_order=6)
    explicit_none = calibrate_slice(k, w, t=bm.SVI_T, n_order=6, prior_anchor=None)
    assert explicit_none.cost == base.cost
    assert np.array_equal(explicit_none.params.to_vector(), base.params.to_vector())


# ----------------------------------------------------------------- mechanism
def test_prior_anchor_pulls_the_wings_toward_the_prior():
    """With quotes only near the money, the wings are weakly identified; a strong
    prior whose wings carry MORE variance pulls the fitted wings up toward it,
    while the in-sample fit is barely disturbed."""
    k = np.linspace(-0.25, 0.25, 40)  # deliberately narrow quoted range
    w = bm.SVI_RAW.total_variance(k)
    t = bm.SVI_T

    base = calibrate_slice(k, w, t=t, n_order=6)

    def prior_w(kk: np.ndarray) -> np.ndarray:  # a prior with slightly fatter wings
        return bm.SVI_RAW.total_variance(kk) * 1.15

    # total_weight = HALF the summed quote weights (== k.size for unit weights),
    # i.e. the default priorAnchorWeightPct = 50%.
    target = build_prior_anchor(prior_w, k, tau=t, total_weight=0.5 * k.size)
    assert target is not None
    anchored = calibrate_slice(k, w, t=t, n_order=6, prior_anchor=target)

    kw = target.k  # the near-wing anchor points (outside [-0.25, 0.25])
    base_vol = np.sqrt(base.slice.implied_w(kw) / t)
    anch_vol = np.sqrt(anchored.slice.implied_w(kw) / t)
    prior_vol = np.sqrt(prior_w(kw) / t)

    # The anchored wings move UP toward the (higher) prior, and end closer to it.
    assert np.mean(anch_vol) > np.mean(base_vol)
    assert np.mean(np.abs(anch_vol - prior_vol)) < np.mean(np.abs(base_vol - prior_vol))
    # The anchor lives in the near wings, so the quotes are still fit to ~1 vol %:
    # it couples to the body via the shared LQD params but does not fight the data.
    assert anchored.max_iv_error < 0.015


# ------------------------------------------------------------- service gating
def test_prior_anchor_target_gating():
    """service.prior_anchor_target: None unless autoLoadPrior is on AND a prior is
    saved; a real target otherwise."""
    state = AppState(REF_DATE)
    iso = [e.isoformat() for e in sorted(state.forwards(TICKER))][1]
    rec = service._compute_fit(state, TICKER, iso, "mid")
    k, tau = rec.prepared.k, rec.prepared.tau

    # Off (default): never a target.
    assert service.prior_anchor_target(state, TICKER, iso, k, None, tau) is None

    # On but no saved prior yet: still None.
    state.set_options(state.options().model_copy(update={"autoLoadPrior": True}))
    assert service.prior_anchor_target(state, TICKER, iso, k, None, tau) is None

    # On + a saved prior: a real anchor with wing points.
    state.save_prior(
        (TICKER, iso),
        PriorRecord(curve=service.model_curve(rec), params=rec.result.params, t=rec.prepared.t),
    )
    target = service.prior_anchor_target(state, TICKER, iso, k, None, tau)
    assert target is not None and target.k.size > 0

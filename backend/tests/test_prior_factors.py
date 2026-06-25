"""Smile-factor prior (calib/factors) + hybrid deep-tail anchor (roadmap Phase 6).

Factors are ATM-local signed σ-baskets (level / skew / curvature) reusing the
operator machinery; hybrid combines the quote operators with a residual deep-tail
strike anchor. Tests cover the builder math, the LV basket adapter, and the
service-level mode routing.
"""

import numpy as np

from volfit.api.prior_lv import build_factor_lv_targets
from volfit.api.schemas import OptionsSettings
from volfit.calib.factors import _resolve_factor_legs, build_factor_prior
from volfit.calib.operators import hybrid_tail_deltas
from volfit.models.localvol import BasketQuote
from volfit.models.lqd.calibrate import calibrate_slice

T = 0.5
SIG0 = 0.20


def flat_w(k):
    k = np.asarray(k, dtype=float)
    return np.full_like(k, SIG0 * SIG0 * T)


def skew_w(k):
    k = np.asarray(k, dtype=float)
    sig = SIG0 - 0.5 * k
    return sig * sig * T


# ------------------------------------------------------------- factor legs
def test_factor_legs_stencils():
    legs_k, coeff, names = _resolve_factor_legs(0.05, ["ATM", "skew", "curvature"])
    assert names == ["ATM", "skew", "curvature"]
    # ATM row sums to 1 (level); skew sums to 0 (difference); curvature sums to 0
    sums = coeff.sum(axis=1)
    assert abs(sums[0] - 1.0) < 1e-9
    assert abs(sums[1]) < 1e-9 and abs(sums[2]) < 1e-9
    assert 0.0 in np.round(legs_k, 6)  # ATM leg present


# ------------------------------------------------------------- builder
def test_factor_prior_activates_on_sparse_smile():
    """ATM-only quotes -> skew/curvature factors under-observed -> active."""
    k_quotes = np.array([-0.005, 0.0, 0.005])  # very tight ATM cluster
    target, vs = build_factor_prior(
        skew_w, T, T, k_quotes, None, total_budget=10.0,
        factor_set=["ATM", "skew", "curvature", "VarSwap"], step=0.05, bandwidth=0.02,
    )
    assert target is not None
    assert "skew" in target.names  # the ATM-local skew is under-observed
    assert (target.active_lambda > 0.0).all()
    assert vs.active


def test_factor_prior_quiet_on_dense_smile():
    k_quotes = np.linspace(-0.45, 0.45, 61)  # dense across the wings
    target, vs = build_factor_prior(
        skew_w, T, T, k_quotes, None, total_budget=10.0,
        factor_set=["ATM", "skew", "curvature", "VarSwap"], step=0.05, bandwidth=0.06,
    )
    assert target is None and not vs.active


# ------------------------------------------------------------- LV adapter
def test_factor_lv_targets_are_baskets():
    k_quotes = np.array([-0.005, 0.0, 0.005])
    opts = OptionsSettings(priorOperatorBandwidth=0.02, priorFactorStrengthPct=50.0)
    baskets, _vs = build_factor_lv_targets(skew_w, T, T, k_quotes, None, opts)
    assert baskets and all(isinstance(b, BasketQuote) for b in baskets)


# ------------------------------------------------------------- hybrid tail
def test_hybrid_tail_deltas_below_shallowest_operator():
    # default operators include RR25/BF25 (delta 0.25); deltas below 0.25 are tail
    tail = hybrid_tail_deltas(["ATM", "RR25", "BF25", "VarSwap"], [0.02, 0.05, 0.10, 0.25, 0.40])
    assert tail == (0.02, 0.05, 0.10)  # < 0.25
    # with RR10/BF10 present (delta 0.10) the floor drops to 0.10
    tail2 = hybrid_tail_deltas(["RR10", "BF10"], [0.02, 0.05, 0.10, 0.25])
    assert tail2 == (0.02, 0.05)  # < 0.10
    # no wing operator -> fallback
    assert hybrid_tail_deltas(["ATM"], [0.40]) == (0.02, 0.05)


# ------------------------------------------------------------- parametric pull
def test_factor_prior_pulls_lqd_toward_prior_skew():
    """A skew-factor prior moves an ATM-only LQD fit's local skew toward the prior."""
    k = np.linspace(-0.08, 0.08, 11)
    w = (0.22 - 0.20 * k) ** 2 * T  # mild live skew
    target, _ = build_factor_prior(
        skew_w, T, T, k, None, total_budget=50.0,
        factor_set=["skew", "curvature"], step=0.06, bandwidth=0.03,
    )
    assert target is not None
    base = calibrate_slice(k, w, t=T, n_order=6)
    pulled = calibrate_slice(k, w, t=T, n_order=6, operator_prior=target)
    # prior skew (sigma decreasing in k) is steeper than the live data; the factor
    # pull steepens the fitted local skew (sigma(-h) - sigma(+h) grows)
    h = 0.06
    sk_base = float(np.sqrt(base.slice.implied_w(np.array([-h]))[0] / T)
                    - np.sqrt(base.slice.implied_w(np.array([h]))[0] / T))
    sk_pull = float(np.sqrt(pulled.slice.implied_w(np.array([-h]))[0] / T)
                    - np.sqrt(pulled.slice.implied_w(np.array([h]))[0] / T))
    assert sk_pull > sk_base  # steeper toward the prior

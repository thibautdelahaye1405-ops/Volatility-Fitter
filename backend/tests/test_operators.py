"""Quote-operator prior library (Phase 2 of Docs/prior_persistence_roadmap.md).

Tests the model-agnostic operator math (design note §5): delta-strike location,
RR/BF signs + collar convention, the §9.3 activation gate (a tight ATM quote
turns the ATM prior off; missing wings keep RR/BF on), and the constant-length
residual.
"""

import math

import numpy as np

from volfit.calib import operators as ops

TAU = 0.5
SIG0 = 0.20


def flat_w(k):
    k = np.asarray(k, dtype=float)
    return np.full_like(k, SIG0 * SIG0 * TAU)


def skew_w(k):
    """Higher vol on the put side (sigma decreasing in k)."""
    k = np.asarray(k, dtype=float)
    sig = SIG0 - 0.5 * k
    return sig * sig * TAU


def convex_w(k):
    k = np.asarray(k, dtype=float)
    sig = SIG0 + 2.0 * k * k
    return sig * sig * TAU


# ----------------------------------------------------------- leg location
def test_delta_strike_signs_and_atm():
    # the 50-delta strike sits near ½σ²τ on a flat smile; calls k>0, puts k<0
    k50 = ops.delta_strike(flat_w, TAU, 0.5)
    assert abs(k50 - 0.5 * SIG0 * SIG0 * TAU) < 1e-6
    assert ops.delta_strike(flat_w, TAU, 0.25) > 0.0  # OTM call
    assert ops.delta_strike(flat_w, TAU, 0.75) < 0.0  # OTM put


# ----------------------------------------------------------- evaluation
def test_flat_smile_zero_skew_and_curvature():
    vals = ops.evaluate_operators(flat_w, TAU, ["ATM", "RR25", "BF25", "VarSwap"])
    assert abs(vals["ATM"] - SIG0) < 1e-6
    assert abs(vals["RR25"]) < 1e-6
    assert abs(vals["BF25"]) < 1e-6
    assert abs(vals["VarSwap"] - SIG0) < 5e-4  # var-swap of a flat smile ~ ATM


def test_risk_reversal_sign_and_collar():
    rr_cp = ops.evaluate_operators(skew_w, TAU, ["RR25"], collar_sign="call_put")["RR25"]
    rr_pc = ops.evaluate_operators(skew_w, TAU, ["RR25"], collar_sign="put_call")["RR25"]
    assert rr_cp < 0.0  # call vol < put vol on a put-skewed smile (call minus put)
    assert math.isclose(rr_pc, -rr_cp, rel_tol=1e-9)  # the convention flips the sign


def test_butterfly_positive_on_convex_smile():
    bf = ops.evaluate_operators(convex_w, TAU, ["BF25"])["BF25"]
    assert bf > 0.0


# ----------------------------------------------------------- the gate
def test_dense_atm_turns_off_atm_keeps_wings():
    """Quotes only near ATM -> ATM prior off (gap 0), RR/BF stay active.

    A tight bandwidth so the ATM cluster does not leak support into the wing legs
    (the kernel width is a tuned default; here we want a clean gate test)."""
    k_quotes = np.array([-0.01, 0.0, 0.01])
    target, vs = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
        op_set=["ATM", "RR25", "BF25", "VarSwap"], bandwidth=0.03,
    )
    assert target is not None
    assert "ATM" not in target.names  # well-observed -> zero prior weight
    assert "RR25" in target.names and "BF25" in target.names
    assert (target.active_lambda > 0.0).all()
    assert vs.active  # the wings/level are under-covered -> var-swap prior on


def test_full_coverage_returns_none():
    """Dense quotes across the wings -> every operator well-observed -> no prior."""
    k_quotes = np.linspace(-0.25, 0.25, 41)
    target, vs = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
        op_set=["ATM", "RR25", "BF25", "VarSwap"],
    )
    assert target is None
    assert not vs.active


def test_budget_splits_across_active_operators():
    k_quotes = np.array([-0.02, 0.0, 0.02])
    target, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
        op_set=["ATM", "RR25", "BF25"],
    )
    assert target is not None
    assert abs(float(target.active_lambda.sum()) - 10.0) < 1e-9  # budget conserved


# ----------------------------------------------------------- residuals
def test_residual_zero_against_self_nonzero_against_other():
    k_quotes = np.array([-0.02, 0.0, 0.02])
    target, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
        op_set=["ATM", "RR25", "BF25"],
    )
    assert target is not None
    # model == prior -> residuals vanish; constant length = # active operators
    r_self = ops.operator_residuals(skew_w, target)
    assert r_self.shape == (len(target.names),)
    assert np.allclose(r_self, 0.0, atol=1e-9)
    # a flat model has no skew/curvature -> nonzero pull toward the skewed prior
    r_flat = ops.operator_residuals(flat_w, target)
    assert np.any(np.abs(r_flat) > 1e-6)

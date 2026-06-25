"""The 'don't damp the signal' validation (roadmap Phase 8; design note §3/§5).

Synthetic overnight scenario: the smile SHAPE is unchanged but the LEVEL jumped up,
and today only the ATM region is quoted (the wings are unobserved). The prior is
yesterday's (un-jumped) smile. The design goal:

  * the calibrated LEVEL must follow today's ATM data (not be dragged back to
    yesterday's lower level) — operators/factors persist only the SHAPE (RR/BF and
    curvature are level-invariant), so a well-observed ATM move is not damped;
  * the unquoted WINGS must reconstruct today's true level (yesterday's shape lifted
    by the jump), which the signed-operator prior achieves but the legacy
    strike-gap anchor does NOT — it pins the wings to yesterday's ABSOLUTE prices,
    so it clings to the old level (the exact failure the operator design fixes).

This is the self-contained, runnable form of the prior-mode backtest comparison
(the fixture harness scores single-snapshot precision, not temporal persistence).
"""

import numpy as np

from volfit.calib.factors import build_factor_prior
from volfit.calib.operators import build_operator_prior
from volfit.calib.prior import build_prior_anchor
from volfit.models.lqd.calibrate import calibrate_slice

TAU = 0.5
D_LEVEL = 0.04  # the overnight ATM jump (4 vol points up)
KW = -0.10  # a put wing, OUTSIDE the quoted ATM region
K = np.linspace(-0.05, 0.05, 11)  # today's quotes: ATM region only


def base_sigma(k):
    """The (unchanged) smile shape: skew + curvature."""
    k = np.asarray(k, dtype=float)
    return 0.20 - 0.4 * k + 0.5 * k * k


def prior_w(k):  # yesterday: the base shape at the old level
    s = base_sigma(k)
    return s * s * TAU


def today_sigma(k):  # today: same shape, level lifted by D_LEVEL
    return base_sigma(k) + D_LEVEL


W_TODAY = today_sigma(K) ** 2 * TAU
BUDGET = 5.0 * K.size  # a strong prior so the effect is unambiguous


def _vol(fit, k):
    return float(np.sqrt(max(fit.slice.implied_w(np.array([k]))[0], 1e-12) / TAU))


def test_operator_prior_follows_level_and_reconstructs_jumped_wing():
    """Operators persist the (level-invariant) shape, so the wings track today's
    jumped level and the ATM level is not damped."""
    op, _vs = build_operator_prior(
        prior_w, TAU, TAU, K, None, BUDGET, op_set=["ATM", "RR25", "BF25"], bandwidth=0.03
    )
    assert op is not None and "ATM" not in op.names  # ATM is well-observed -> off

    f_data = calibrate_slice(K, W_TODAY, t=TAU, n_order=6)
    f_op = calibrate_slice(K, W_TODAY, t=TAU, n_order=6, operator_prior=op)
    f_sg = calibrate_slice(
        K, W_TODAY, t=TAU, n_order=6,
        prior_anchor=build_prior_anchor(prior_w, TAU, K, TAU, BUDGET, deltas=(0.05, 0.1, 0.25))[0],
    )

    true_wing = float(today_sigma(KW))   # yesterday's shape lifted by the jump
    old_wing = float(base_sigma(KW))     # yesterday's (un-jumped) level

    op_wing, sg_wing = _vol(f_op, KW), _vol(f_sg, KW)
    # the operator prior reconstructs the JUMPED wing better than the strike anchor
    assert abs(op_wing - true_wing) < abs(sg_wing - true_wing)
    # ...and the strike anchor clings to YESTERDAY's level more than the operator does
    assert abs(sg_wing - old_wing) < abs(op_wing - old_wing)

    # the ATM level follows today's data under the operator prior (not damped) —
    # at least as well as the data-only fit
    atm_true = float(today_sigma(0.0))
    assert abs(_vol(f_op, 0.0) - atm_true) <= abs(_vol(f_data, 0.0) - atm_true) + 1e-3


def test_factor_prior_also_preserves_shape_without_damping_level():
    """Smile factors (ATM-local skew/curvature) are level-invariant too, so they
    persist shape without pulling the ATM level back."""
    fac, _vs = build_factor_prior(
        prior_w, TAU, TAU, K, None, BUDGET,
        factor_set=["skew", "curvature"], step=0.06, bandwidth=0.03,
    )
    assert fac is not None
    f_fac = calibrate_slice(K, W_TODAY, t=TAU, n_order=6, operator_prior=fac)
    atm_true = float(today_sigma(0.0))
    # the level is not damped (factors carry no level term)
    assert abs(_vol(f_fac, 0.0) - atm_true) < 0.006


def test_operator_prior_matches_data_only_at_atm():
    """Sanity: with ATM well quoted, the operator prior leaves the ATM level
    essentially where the data put it (the 'do not damp' guarantee at ATM)."""
    op, _vs = build_operator_prior(
        prior_w, TAU, TAU, K, None, BUDGET, op_set=["ATM", "RR25", "BF25"], bandwidth=0.03
    )
    f_data = calibrate_slice(K, W_TODAY, t=TAU, n_order=6)
    f_op = calibrate_slice(K, W_TODAY, t=TAU, n_order=6, operator_prior=op)
    assert abs(_vol(f_op, 0.0) - _vol(f_data, 0.0)) < 0.004

"""Prior persistence in the parametric calibrators (roadmap Phase 3).

Two invariants:
  * an operator prior pulls LQD / SVI / Multi-Core SIV consistently toward the
    prior's operators where the live quotes are sparse (the model-agnostic goal);
  * the strike-gap prior anchor now reaches the SVI / SIG display overlays too —
    the asymmetry fix (before, only LQD/LV received it).

Construction: live quotes only near ATM (the wings are under-observed), a prior
smile with materially stronger skew. The prior should drag the fitted skew /
deep-put wing toward itself, and leaving every prior argument None must be a
no-op (the existing golden suite guards byte-identical defaults).
"""

import numpy as np

from volfit.calib.operators import build_operator_prior, evaluate_operators
from volfit.calib.prior import build_prior_anchor
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.sigmoid.calibrate import calibrate_sigmoid
from volfit.models.svi_jw.calibrate import calibrate_svi

T = 0.5
# live quotes near ATM only (mild skew); 25-delta wings (~|k| 0.10) are unquoted
K = np.linspace(-0.08, 0.08, 11)
LIVE_VOL = 0.22 - 0.20 * K
LIVE_W = LIVE_VOL * LIVE_VOL * T


def prior_w(k):
    """A prior smile with stronger (more negative) skew than the live data — kept
    well inside the Lee wing bound so SVI's unbounded LM stays well-posed."""
    k = np.asarray(k, dtype=float)
    sig = 0.25 - 0.45 * k
    return sig * sig * T


def _lqd_w(op):
    res = calibrate_slice(K, LIVE_W, t=T, n_order=6, operator_prior=op)
    return res.slice.implied_w


def _svi_w(op):
    return calibrate_svi(K, LIVE_W, t=T, operator_prior=op).raw.total_variance


def _sig_w(op):
    return calibrate_sigmoid(K, LIVE_W, t=T, n_cores=0, operator_prior=op).implied_w


def _rr25(w_fn):
    return evaluate_operators(w_fn, T, ["RR25"])["RR25"]


def test_operator_prior_pulls_all_models_toward_prior_skew():
    """For every parametric model, the operator prior moves RR25 toward the
    prior's RR25 vs the data-only fit (the wings are under-observed)."""
    rr_prior = _rr25(prior_w)
    op, _ = build_operator_prior(
        prior_w, T, T, K, None, total_budget=50.0,
        op_set=["RR25", "BF25"], bandwidth=0.03,
    )
    assert op is not None and "RR25" in op.names
    for fit_w in (_lqd_w, _svi_w, _sig_w):
        rr_data = _rr25(fit_w(None))
        rr_with = _rr25(fit_w(op))
        # the prior is more negative; the anchored fit sits closer to it
        assert abs(rr_with - rr_prior) < abs(rr_data - rr_prior)


def test_strike_anchor_reaches_svi_and_sigmoid():
    """The strike-gap anchor (legacy LQD/LV-only) now pulls the SVI / SIG deep-put
    wing toward the prior — roadmap Phase 3 asymmetry fix."""
    anchor, _ = build_prior_anchor(
        prior_w, T, K, T, total_budget=10.0, deltas=(0.10, 0.25), bandwidth=0.06
    )
    assert anchor is not None
    k_deep = np.array([-0.15])  # a deep put, well outside the quoted range
    prior_put = float(np.sqrt(prior_w(k_deep)[0] / T))

    svi_data = calibrate_svi(K, LIVE_W, t=T).raw.total_variance
    svi_with = calibrate_svi(K, LIVE_W, t=T, prior_anchor=anchor).raw.total_variance
    sig_data = calibrate_sigmoid(K, LIVE_W, t=T, n_cores=0).implied_w
    sig_with = calibrate_sigmoid(K, LIVE_W, t=T, n_cores=0, prior_anchor=anchor).implied_w

    for data_w, with_w in ((svi_data, svi_with), (sig_data, sig_with)):
        put_data = float(np.sqrt(max(data_w(k_deep)[0], 1e-12) / T))
        put_with = float(np.sqrt(max(with_w(k_deep)[0], 1e-12) / T))
        assert abs(put_with - prior_put) < abs(put_data - prior_put)


def test_none_arguments_are_noops():
    """Passing the prior arguments as None reproduces the plain fits exactly."""
    a = calibrate_slice(K, LIVE_W, t=T, n_order=6)
    b = calibrate_slice(K, LIVE_W, t=T, n_order=6, operator_prior=None, prior_anchor=None)
    assert np.allclose(a.params.to_vector(), b.params.to_vector())
    s1 = calibrate_svi(K, LIVE_W, t=T)
    s2 = calibrate_svi(K, LIVE_W, t=T, prior_anchor=None, operator_prior=None)
    assert np.allclose(s1.raw.total_variance(K), s2.raw.total_variance(K))

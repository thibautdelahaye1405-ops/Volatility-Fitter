"""Observation-filter temporal backtest harness (Phase 5 of
Docs/observation_filter_roadmap.md) — fixture-free unit coverage.

Drives the harness helpers on the synthetic provider (a same-day self-pair —
the real consecutive-day runs use captured fixtures via the CLI):
  * scenario builders (contradiction = a 2-strike opposite-sign kink; shock =
    a uniform true jump; thinned = identity);
  * the end-to-end filter step through the PRODUCTION commit path: gains in
    [0,1], complete scoring dict, wing scores present;
  * shock pass-through (protocol item 3): the ATM gain is high and the
    posterior follows the jump;
  * contradiction rejection (item 2): curvature gain below the level gain;
  * summarize() aggregation shapes.
"""

from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from backtest.observation_filter import (
    SHOCK_VOL,
    NodeResult,
    _apply_scenario,
    filter_step,
    prior_holder,
    summarize,
)
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"
# The synthetic ALPHA chain is sparse (~14 strikes): use the longest expiry
# and a 1-sigma ATM window so the thinned fit keeps >= 5 strikes.
STEP_KW = dict(c_atm=1.0, c_wing=2.0, min_atm=5, min_wing=2)


def _state():
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={
        "observationFilterMode": "overlay", "priorPersistenceMode": "off",
    }))
    return state


def _iso(state):
    return [e.isoformat() for e in sorted(state.forwards(TICKER))][-1]


def _aged(holder, days: float = 1.0):
    """Fake the T-1 -> T calendar gap on a same-day self-pair: age the carried
    state's snapshot timestamp so the prediction accrues one day of clock Q
    (dt = 0 would rightly give a near-zero gain — the filter trusting a
    same-instant prediction is correct, not a bug)."""
    return replace(
        holder,
        state=replace(holder.state, timestamp=holder.state.timestamp - days * 86400.0),
    )


# ------------------------------------------------------------------ scenarios
def test_scenarios():
    k = np.linspace(-0.2, 0.2, 9)
    tau = 0.25
    w = (0.2 + 0.1 * k**2) ** 2 * tau
    k2, w2, d = _apply_scenario("thinned", k, w, tau)
    assert d == 0.0 and np.array_equal(w2, w)
    _, w_kink, d = _apply_scenario("contradiction", k, w, tau)
    dv = np.sqrt(w_kink / tau) - np.sqrt(w / tau)
    assert d == 0.0
    assert np.count_nonzero(np.abs(dv) > 1e-12) == 2  # exactly two strikes
    assert dv.max() > 0 and dv.min() < 0  # opposite signs = a curvature kink
    _, w_shock, d = _apply_scenario("shock", k, w, tau)
    assert d == SHOCK_VOL
    assert np.sqrt(w_shock / tau) - np.sqrt(w / tau) == pytest.approx(
        np.full(k.size, SHOCK_VOL)
    )


# ------------------------------------------------------------ end-to-end step
def test_filter_step_end_to_end():
    state = _state()
    iso = _iso(state)
    prev = prior_holder(state, TICKER, iso)
    assert prev is not None and prev.update is not None
    s = filter_step(state, TICKER, iso, _aged(prev), "thinned", **STEP_KW)
    assert s is not None
    assert len(s["gain"]) == len(s["err_post"]) == len(s["zeta"]) == 3
    assert all(0.0 <= g <= 1.0 + 1e-9 for g in s["gain"])
    assert s["wing_meas_bp"] is not None
    assert np.all(np.isfinite(s["zeta"]))
    # the posterior is a blend: it cannot be worse than BOTH baselines together
    assert s["err_post"][0] <= s["err_meas"][0] + s["err_pred"][0] + 1e-6


def test_shock_passes_through():
    """A true tight-spread jump must be FOLLOWED: high ATM gain, small lag.

    A 5-point overnight jump is far outside a 10 bp/sqrt-day clock's prior, so
    the scenario premise (prediction uncertainty comparable to the move) is
    realized with a generous process noise — the pass-through property being
    tested is the GAIN's response to that configuration, not the default."""
    state = _state()
    state.set_options(state.options().model_copy(
        update={"filterProcessVolBpSqrtDay": 100.0}))  # 1 vol pt / sqrt day
    iso = _iso(state)
    prev = prior_holder(state, TICKER, iso)
    s = filter_step(state, TICKER, iso, _aged(prev), "shock", **STEP_KW)
    assert s is not None
    assert s["gain"][0] > 0.5  # the level gain is high
    assert s["err_post"][0] < 0.6 * SHOCK_VOL  # lag well under the jump size
    # and the raw measurement itself tracked the jump (sanity on the scenario)
    assert s["err_meas"][0] < 0.2 * SHOCK_VOL


def test_contradiction_rejected_more_than_level():
    """The kinked cluster: curvature is trusted LESS than the level (the whole
    point of the note's case file)."""
    state = _state()
    iso = _iso(state)
    prev = prior_holder(state, TICKER, iso)
    s = filter_step(state, TICKER, iso, _aged(prev), "contradiction", **STEP_KW)
    assert s is not None
    assert s["gain"][2] < s["gain"][0]


# -------------------------------------------------------------------- summary
def test_summarize_shapes():
    row = dict(
        asset=TICKER, as_of="2026-06-10", prior_as_of="2026-06-09",
        expiry="2026-07-17", regime="synthetic", t=0.1, n_atm=8, n_wing=4,
        gain=[0.8, 0.6, 0.1], rho=1.2,
        err_post=[0.001, 0.01, 0.1], err_meas=[0.002, 0.02, 0.4],
        err_pred=[0.003, 0.01, 0.2], zeta=[0.5, -0.3, 0.9],
        wing_post_bp=25.0, wing_meas_bp=40.0,
    )
    results = [
        NodeResult(scenario=sc, cov_mode="jacobian", process_bp=10.0, **row)
        for sc in ("thinned", "shock")
    ]
    out = summarize(results)
    assert len(out) == 2
    for s in out:
        assert s["n"] == 1
        assert len(s["med_err_post"]) == len(s["win_vs_meas"]) == 3
        assert s["win_vs_meas"][0] == 1.0  # post < meas on every handle here
        assert s["med_wing_post_bp"] == 25.0

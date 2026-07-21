"""Phase-1 tests for volfit.graph.temporal_state (dynamic-harmonic framework).

EXIT GATE (doc §17 Phase 1): the §5 asynchronous A/B running example is
reproduced by composing the production state objects alone — no graph solve —
against the SAME fixture as the Phase-0 goldens
(tests/fixtures/graph_dynamic_golden.json, D9 contract).

Also locks: D2 transition family (OU/random-walk values + semigroup through
the production dataclasses), D3 hard-vs-Kalman updates (hard == diffuse-prior
limit), D4 innovation-carrying leases, §10 causal guards (monotone time,
no look-ahead, advance-before-Kalman), §10 Step 8 persistence guard, golden
15.13 config rebase, and the Phase-1 item-7 ATM-floor migration.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from volfit.graph.temporal_state import (
    LeasePolicy,
    PersistenceGuardError,
    TemporalOrderError,
    assert_persistable,
    empty_residual,
    migrate_atm_floor_history,
    observation_state,
    observation_state_from_record,
    residual_dynamics,
    residual_from_record,
    residual_measurement,
    residual_measurement_variance,
    reuse_or_invalidate,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "graph_dynamic_golden.json").read_text()
)

APPROX = dict(rel=1e-12, abs=1e-12)


def _ab_fixture():
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    return fx, obs_a, obs_b


def _replay(obs_a, obs_b, snapshots, beta, dynamics):
    """Doc §10 Steps 2-4 driven directly through the state objects: source
    lease (carried flat, D4), advance-then-update ordering, hard certified
    residual updates (D3), published mark = beta * m_source + u."""
    res = empty_residual("cfg-v1")
    a_state = None
    a_marks, b_marks, updates, u_trace = [], [], [], []
    for t in snapshots:
        if t in obs_a:
            a_state = observation_state([obs_a[t], 0, 0], 1e-4, t, f"A@{t}")
        m_a, _ = a_state.carried_to(t)
        res = res.advance(t, dynamics)
        if t in obs_b:
            e = residual_measurement([obs_b[t], 0, 0], beta, m_a)
            r = residual_measurement_variance(1e-4, beta, a_state.variance, 1e4)
            res = res.updated_hard(e, r, t, f"B@{t}")
            updates.append(t)
        a_marks.append(m_a[0])
        b_marks.append(beta * m_a[0] + res.mean[0])
        u_trace.append(res.mean[0])
    return a_marks, b_marks, updates, u_trace


# ------------------------------------------------------------------ exit gate
def test_exit_gate_async_ab_sequence():
    fx, obs_a, obs_b = _ab_fixture()
    dyn = residual_dynamics()  # random walk, q=0: phi=1, Q=0
    a, b, updates, u = _replay(obs_a, obs_b, fx["snapshots"], fx["beta"], dyn)
    assert a == pytest.approx(fx["expected_a"], **APPROX)
    assert b == pytest.approx(fx["expected_b"], **APPROX)
    assert updates == fx["expected_update_times"]
    i35 = fx["snapshots"].index(3.5)
    assert u[i35] == pytest.approx(fx["expected_u_after_3_5"], **APPROX)
    assert u[i35] != pytest.approx(fx["forbidden_lookahead_u"])  # golden 15.7
    # published mark at an observation time IS the calibration (§4.3 clamp)
    assert b[i35] == pytest.approx(obs_b[3.5], **APPROX)


def test_exit_gate_async_ab_beta15():
    fx, obs_a, obs_b = _ab_fixture()
    v = FIXTURE["async_ab_beta15"]
    dyn = residual_dynamics()
    _, b, _, u = _replay(obs_a, obs_b, fx["snapshots"], v["beta"], dyn)
    assert b == pytest.approx(v["expected_b"], **APPROX)
    assert u[fx["snapshots"].index(0.0)] == pytest.approx(v["expected_u_after_0"])
    assert u[fx["snapshots"].index(3.5)] == pytest.approx(v["expected_u_after_3_5"])


def test_exit_gate_zero_reverse_influence():
    """Golden 15.2: A's path is identical with and without B's observations —
    structurally, because no B state ever enters A's lease."""
    fx, obs_a, obs_b = _ab_fixture()
    dyn = residual_dynamics()
    a_with, _, _, _ = _replay(obs_a, obs_b, fx["snapshots"], fx["beta"], dyn)
    a_without, _, _, _ = _replay(obs_a, {}, fx["snapshots"], fx["beta"], dyn)
    assert a_with == a_without == fx["expected_a"]


def test_exit_gate_half_life_variant():
    """Golden 15.5 through stepwise advancement — the D2 semigroup is what
    makes the 0.5-step replay hit the point formula exactly."""
    fx, obs_a, obs_b = _ab_fixture()
    hl = FIXTURE["residual_half_life"]
    dyn = residual_dynamics(half_life=hl["half_life"], v_inf=0.09)
    _, b, _, u = _replay(obs_a, obs_b, fx["snapshots"], fx["beta"], dyn)
    assert u[fx["snapshots"].index(4.5)] == pytest.approx(
        hl["expected_u_at_4_5"], **APPROX
    )
    assert b[fx["snapshots"].index(4.0)] == pytest.approx(
        hl["expected_b_at_4_0"], rel=1e-9
    )


# ------------------------------------------------------------------ D2 family
def test_transition_variances_match_phase0_goldens():
    hl = FIXTURE["residual_half_life"]
    ou = hl["ou_transition"]
    dyn = residual_dynamics(half_life=hl["half_life"], v_inf=ou["v_inf"])
    phi2 = dyn.phi(ou["delta"]) ** 2
    v_minus = phi2 * ou["v_plus"] + dyn.process_variance(ou["delta"])
    assert v_minus == pytest.approx(np.full(3, ou["expected_v_minus"]), **APPROX)

    rw = hl["random_walk_transition"]
    dyn_rw = residual_dynamics(q_rate=rw["q_rate"])
    assert dyn_rw.phi(rw["delta"]) == pytest.approx(np.ones(3))
    v_minus = rw["v_plus"] + dyn_rw.process_variance(rw["delta"])
    assert v_minus == pytest.approx(np.full(3, rw["expected_v_minus"]), **APPROX)


def test_transition_semigroup_through_advance():
    """Two half-steps of advance() == one full step, both branches (D2)."""
    for dyn in (
        residual_dynamics(half_life=1.0, v_inf=0.09),
        residual_dynamics(q_rate=0.02),
    ):
        seed = empty_residual("cfg").advance(0.0, dyn)
        seed = seed.updated_hard([-3.0, 0.1, 0.02], 0.04, 0.0, "obs")
        one = seed.advance(0.5, dyn)
        two = seed.advance(0.25, dyn).advance(0.5, dyn)
        assert two.mean == pytest.approx(one.mean, **APPROX)
        assert two.variance == pytest.approx(one.variance, **APPROX)


def test_dynamics_validation():
    with pytest.raises(ValueError):
        residual_dynamics(half_life=0.0)
    with pytest.raises(ValueError):
        residual_dynamics(v_inf=-1.0)
    with pytest.raises(TemporalOrderError):
        residual_dynamics().phi(-0.1)


# ------------------------------------------------------------------ D3 updates
def test_hard_update_is_diffuse_prior_limit():
    e, r = [-3.0, 0.2, -0.1], [0.04, 0.05, 0.06]
    hard = empty_residual("cfg").advance(1.0, residual_dynamics())
    hard = hard.updated_hard(e, r, 1.0, "obs")
    diffuse = empty_residual("cfg", variance=1e12).advance(1.0, residual_dynamics())
    diffuse = diffuse.updated_kalman(e, r, 1.0, "obs")
    assert diffuse.mean == pytest.approx(hard.mean, rel=1e-6)
    assert diffuse.variance == pytest.approx(hard.variance, rel=1e-6)
    assert hard.mean == pytest.approx(e, **APPROX)
    assert hard.variance == pytest.approx(r, **APPROX)


def test_kalman_update_formula():
    """§6.3: K = V/(V+r); posterior mean/variance per handle."""
    dyn = residual_dynamics()
    state = empty_residual("cfg", variance=0.09).advance(2.0, dyn)
    state = state.updated_hard([-1.0, 0, 0], 0.09, 2.0, "seed")
    state = state.advance(3.0, dyn)
    updated = state.updated_kalman([-3.0, 0, 0], 0.01, 3.0, "obs")
    k = 0.09 / (0.09 + 0.01)
    assert updated.mean[0] == pytest.approx(-1.0 + k * (-3.0 - (-1.0)), **APPROX)
    assert updated.variance[0] == pytest.approx((1 - k) * 0.09, **APPROX)


def test_residual_measurement_composition():
    """§6.3 / D5: e = d − β·m_source; Var(e) = V_obs + β²·V_src + 1/p."""
    e = residual_measurement([10.0, 0, 0], 1.0, [13.0, 0, 0])
    assert e[0] == pytest.approx(-3.0)
    var = residual_measurement_variance(0.01, 1.2, 0.04, 1.0)
    assert var == pytest.approx(np.full(3, 0.01 + 1.44 * 0.04 + 1.0), **APPROX)
    with pytest.raises(ValueError):
        residual_measurement_variance(0.01, 1.0, 0.04, 0.0)


# -------------------------------------------------------------- causal guards
def test_temporal_guards():
    dyn = residual_dynamics()
    state = empty_residual("cfg").advance(2.0, dyn)
    with pytest.raises(TemporalOrderError):
        state.advance(1.5, dyn)  # backwards
    with pytest.raises(TemporalOrderError):
        state.updated_kalman([0, 0, 0], 0.01, 2.5, "obs")  # not advanced to t
    with pytest.raises(TemporalOrderError):
        state.updated_hard([0, 0, 0], 0.01, 1.0, "obs")  # before as_of
    obs = observation_state([1.0, 0, 0], 0.01, 3.0, "A@3")
    with pytest.raises(TemporalOrderError):
        obs.carried_to(2.5)  # look-ahead: using a future observation


def test_lease_carries_innovation_and_grows_variance():
    """D4: mean flat (the mark rides the transported baseline), variance +q·dt."""
    obs = observation_state([0.7, -0.1, 0.05], 0.01, 1.0, "A@1")
    mean, var = obs.carried_to(3.0, q_rate=0.02)
    assert mean == pytest.approx([0.7, -0.1, 0.05], **APPROX)
    assert var == pytest.approx(np.full(3, 0.01 + 0.02 * 2.0), **APPROX)


def test_lease_policy_classification():
    policy = LeasePolicy(fresh_max_age=0.5, carried_max_age=2.0, soft_max_age=5.0)
    assert policy.classify(0.0, certified=True) == "fresh_certified"
    assert policy.classify(1.0, certified=True) == "carried"
    assert policy.classify(3.0, certified=True) == "soft_stale"
    assert policy.classify(6.0, certified=True) == "unobserved"
    # §4.2: freshness alone never grants a hard boundary
    assert policy.classify(0.0, certified=False) == "soft_stale"
    with pytest.raises(TemporalOrderError):
        policy.classify(-0.1, certified=True)
    with pytest.raises(ValueError):
        LeasePolicy(fresh_max_age=2.0, carried_max_age=1.0, soft_max_age=5.0)


# ------------------------------------------------------- persistence + rebase
def test_actual_observation_only_persistence():
    dyn = residual_dynamics()
    state = empty_residual("cfg").advance(1.0, dyn)
    assert not state.persistable()
    with pytest.raises(PersistenceGuardError):
        assert_persistable(state)
    with pytest.raises(PersistenceGuardError):
        state.updated_hard([0, 0, 0], 0.01, 1.0, "")  # no provenance id
    updated = state.updated_hard([-3, 0, 0], 0.01, 1.0, "B@1")
    assert updated.persistable()
    assert_persistable(updated)
    assert updated.source_observation_ids == ("B@1",)


def test_config_rebase_invalidates_residual():
    """Golden 15.13 through the production helper."""
    fx = FIXTURE["config_rebase"]
    dyn = residual_dynamics()
    state = empty_residual("v1").advance(0.0, dyn)
    state = state.updated_hard([fx["u_old"], 0, 0], 0.01, 0.0, "B@0")
    same, invalidated = reuse_or_invalidate(state, "v1")
    assert same is state and not invalidated
    fresh, invalidated = reuse_or_invalidate(state, "v2")
    assert invalidated and not fresh.persistable()
    mark = fx["beta_new"] * fx["source_state"] + fresh.mean[0]
    assert mark == pytest.approx(fx["expected_mark_after_invalidation"], **APPROX)


# --------------------------------------------------- serialization + migration
def test_serialization_round_trips():
    dyn = residual_dynamics()
    state = empty_residual("v3").advance(4.0, dyn)
    state = state.updated_hard([-3.0, 0.1, 0.0], [0.04, 0.05, 0.06], 4.0, "B@4")
    back = residual_from_record(state.to_record())
    assert back.mean == pytest.approx(state.mean, **APPROX)
    assert back.variance == pytest.approx(state.variance, **APPROX)
    assert back.observed_at == state.observed_at and back.as_of == state.as_of
    assert back.source_observation_ids == state.source_observation_ids
    assert back.config_version == state.config_version

    fresh = empty_residual("v3")
    fresh_back = residual_from_record(fresh.to_record())
    assert math.isinf(fresh_back.as_of) and not fresh_back.persistable()

    obs = observation_state([0.7, 0, 0], 0.01, 2.0, "A@2", config_version="v3")
    obs_back = observation_state_from_record(obs.to_record())
    assert obs_back.innovation == pytest.approx(obs.innovation, **APPROX)
    assert obs_back.observation_id == obs.observation_id
    assert obs_back.certified is True


def test_migrate_atm_floor_history():
    """Phase-1 item 7: latest day wins; ATM mean preserved; wide variance;
    tagged provenance makes migrated state persistable but distinguishable."""
    rows = [
        ("SPY", "2026-12-18", "2026-07-18", 0.004),
        ("SPY", "2026-12-18", "2026-07-19", 0.006),
        ("AAPL", "2026-08-21", "2026-07-19", -0.01),
    ]
    out = migrate_atm_floor_history(rows, config_version="v1")
    spy = out[("SPY", "2026-12-18")]
    assert spy.mean == pytest.approx([0.006, 0.0, 0.0], **APPROX)
    assert spy.variance == pytest.approx(np.ones(3), **APPROX)
    assert spy.persistable() and spy.config_version == "v1"
    assert spy.source_observation_ids == (
        "legacy_atm_floor:SPY:2026-12-18:2026-07-19",
    )
    aapl = out[("AAPL", "2026-08-21")]
    assert aapl.mean[0] == pytest.approx(-0.01)
    assert aapl.observed_at == float(
        __import__("datetime").date(2026, 7, 19).toordinal()
    )

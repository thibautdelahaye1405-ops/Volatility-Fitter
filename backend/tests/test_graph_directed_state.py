"""Phase-2 tests for volfit.graph.directed_state (dynamic-harmonic framework).

EXIT GATE (doc §17 Phase 2): zero reverse sensitivity is exact, and directed
predictions match independent state-space references — here, the Phase-0
golden fixture (tests/fixtures/graph_dynamic_golden.json, D9 contract):
15.2 (zero reverse influence), 15.6 (precision separation, single + multi
INCLUDING the correlated-parents number reproduced through shared-ancestor
gains), 15.10 (directed cascade row solution), and the §5 asynchronous A/B
sequence driven end-to-end through the engine + temporal_state.

Also locks: DAG rejection of directed cycles (§6.5), observed-wins semantics,
missing-parent renormalization, the D7 parentless-residual (ghost) case,
exact attribution (§6.6), and the §12.2 residual-surprise diagnostic.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from volfit.graph.directed_state import (
    DirectedCycleError,
    build_directed_graph,
    directed_pass,
    directed_relation,
    residual_surprise,
)
from volfit.graph.temporal_state import (
    empty_residual,
    observation_state,
    residual_dynamics,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "graph_dynamic_golden.json").read_text()
)

APPROX = dict(rel=1e-12, abs=1e-12)


# ------------------------------------------------------------------ topology
def test_dag_validation():
    a_b = directed_relation("B", "A")
    b_a = directed_relation("A", "B")
    with pytest.raises(DirectedCycleError):
        build_directed_graph(["A", "B"], [a_b, b_a])
    with pytest.raises(ValueError):
        build_directed_graph(["A"], [directed_relation("B", "A")])
    with pytest.raises(ValueError):
        directed_relation("A", "A")
    with pytest.raises(ValueError):
        directed_relation("B", "A", precision=0.0)
    with pytest.raises(ValueError):
        build_directed_graph(["A", "A"], [])


def test_topological_order():
    g = build_directed_graph(
        ["T", "P2", "C", "P1"],
        [
            directed_relation("P1", "C"),
            directed_relation("P2", "P1"),
            directed_relation("T", "P1"),
            directed_relation("T", "P2"),
        ],
    )
    order = {n: i for i, n in enumerate(g.order)}
    assert order["C"] < order["P1"] < order["P2"] < order["T"]


# ------------------------------------------------------------- goldens 15.10
def test_directed_cascade_discriminator():
    fx = FIXTURE["discriminator"]
    p = fx["edge_precision"]
    g = build_directed_graph(
        ["L", "u1", "u2", "R"],
        [directed_relation(t, s, 1.0, p) for s, t in fx["directed_arcs"]],
    )
    result = directed_pass(
        g, {"L": ([fx["boundary"]["L"], 0, 0], 0.0), "R": ([fx["boundary"]["R"], 0, 0], 0.0)}
    )
    for node, expected in fx["expected_directed"].items():
        assert result.predictions[node].mean[0] == pytest.approx(expected, **APPROX)
    assert result.predictions["u2"].q_incoming[0] == pytest.approx(2 * p)


# -------------------------------------------------------------- goldens 15.6
def test_precision_separation_single_source():
    fx = FIXTURE["precision_separation"]["single"]
    for p, expected_var in zip(fx["p_sweep"], fx["expected_variance"]):
        g = build_directed_graph(
            ["J", "T"], [directed_relation("T", "J", fx["beta"], p)]
        )
        result = directed_pass(
            g,
            {"J": ([fx["m_source"], 0, 0], fx["v_source"])},
            {"T": ([fx["m_residual"], 0, 0], fx["v_residual"])},
        )
        pred = result.predictions["T"]
        assert pred.mean[0] == pytest.approx(fx["expected_mean"], **APPROX)
        assert pred.variance[0] == pytest.approx(expected_var, **APPROX)


def test_precision_separation_multi_source_correlated():
    """The locked 0.310625 through SHARED-ANCESTOR gains: P2 = 1.5·P1 − 4
    (near-exact relation), so Var(P1,P2) = (0.04, 0.09), cov = 0.06 —
    perfectly correlated parents exactly as in the fixture."""
    fx = FIXTURE["precision_separation"]["multi"]
    g = build_directed_graph(
        ["P1", "P2", "T"],
        [
            directed_relation("P2", "P1", 1.5, 1e12),
            directed_relation("T", "P1", fx["beta"][0], fx["p"][0]),
            directed_relation("T", "P2", fx["beta"][1], fx["p"][1]),
        ],
    )
    result = directed_pass(
        g,
        {"P1": ([fx["z_parents"][0], 0, 0], fx["v_parents"][0])},
        {
            "P2": ([-4.0, 0, 0], 0.0),  # deterministic shift: mean −1, no extra var
            "T": ([0.0, 0, 0], fx["v_residual"]),
        },
    )
    assert result.state_mean("P2")[0] == pytest.approx(fx["z_parents"][1], **APPROX)
    assert result.state_variance("P2")[0] == pytest.approx(fx["v_parents"][1], rel=1e-9)
    assert result.covariance("P1", "P2")[0] == pytest.approx(0.06, rel=1e-9)
    pred = result.predictions["T"]
    assert pred.mean[0] == pytest.approx(fx["expected_mean"], **APPROX)
    assert pred.variance[0] == pytest.approx(fx["expected_variance_correlated"], rel=1e-9)
    # correlated parents must never look MORE certain than independent ones
    assert pred.variance[0] > fx["expected_variance_independent"]


def test_attribution_sums_to_mean():
    """§6.6: contributions per observed source + residual == mean, exactly."""
    fx = FIXTURE["precision_separation"]["multi"]
    g = build_directed_graph(
        ["P1", "P2", "T"],
        [
            directed_relation("P2", "P1", 1.5, 1e12),
            directed_relation("T", "P1", 1.0, fx["p"][0]),
            directed_relation("T", "P2", 1.0, fx["p"][1]),
        ],
    )
    result = directed_pass(
        g,
        {"P1": ([2.0, 0, 0], 0.04)},
        {"P2": ([-4.0, 0, 0], 0.0), "T": ([0.0, 0, 0], 0.01)},
    )
    pred = result.predictions["T"]
    total = sum(c[0] for _, _, c in pred.attribution)
    assert total == pytest.approx(pred.mean[0], **APPROX)
    by_root = {(kind, name): c[0] for kind, name, c in pred.attribution}
    assert by_root[("obs", "P1")] == pytest.approx(1.125 * 2.0, **APPROX)
    assert by_root[("res", "P2")] == pytest.approx(0.25 * -4.0, **APPROX)


# -------------------------------------------------- 15.2 + A/B through engine
def _replay_engine(obs_a, obs_b, snapshots, beta, dynamics):
    """§10 Steps 2-5 driven through the ENGINE: lease → advance → pass →
    residual_observation → hard update. Marks read off the pass."""
    g = build_directed_graph(["A", "B"], [directed_relation("B", "A", beta, 1e4)])
    res_b = empty_residual("cfg-v1")
    a_state = None
    a_marks, b_marks = [], []
    for t in snapshots:
        if t in obs_a:
            a_state = observation_state([obs_a[t], 0, 0], 1e-6, t, f"A@{t}")
        res_b = res_b.advance(t, dynamics)
        run = directed_pass(g, {"A": a_state.carried_to(t)}, {"B": res_b})
        if t in obs_b:
            e, var_e = run.residual_observation("B", [obs_b[t], 0, 0], 1e-6)
            res_b = res_b.updated_hard(e, var_e, t, f"B@{t}")
            b_marks.append(obs_b[t])  # §4.3 clamp; equals β·m_A + u by identity
        else:
            b_marks.append(run.predictions["B"].mean[0])
        a_marks.append(run.state_mean("A")[0])
    return a_marks, b_marks


def test_engine_async_ab_sequence():
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    dyn = residual_dynamics()
    a, b = _replay_engine(obs_a, obs_b, fx["snapshots"], fx["beta"], dyn)
    assert a == pytest.approx(fx["expected_a"], **APPROX)
    assert b == pytest.approx(fx["expected_b"], **APPROX)

    v15 = FIXTURE["async_ab_beta15"]
    _, b15 = _replay_engine(obs_a, obs_b, fx["snapshots"], v15["beta"], dyn)
    assert b15 == pytest.approx(v15["expected_b"], **APPROX)


def test_engine_half_life_variant():
    fx = FIXTURE["async_ab"]
    hl = FIXTURE["residual_half_life"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    dyn = residual_dynamics(half_life=hl["half_life"], v_inf=0.09)
    _, b = _replay_engine(obs_a, obs_b, fx["snapshots"], fx["beta"], dyn)
    assert b[fx["snapshots"].index(4.0)] == pytest.approx(
        hl["expected_b_at_4_0"], rel=1e-9
    )


def test_engine_zero_reverse_influence():
    """Golden 15.2 through the engine: A's marks and variance are identical
    with and without B's observations, at every snapshot — structural cut."""
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    dyn = residual_dynamics()
    a_with, _ = _replay_engine(obs_a, obs_b, fx["snapshots"], fx["beta"], dyn)
    a_without, _ = _replay_engine(obs_a, {}, fx["snapshots"], fx["beta"], dyn)
    assert a_with == a_without == fx["expected_a"]


def test_observed_node_owns_its_value():
    """An observed node IS its observation — parents never blend into it."""
    g = build_directed_graph(["L", "T"], [directed_relation("T", "L", 1.0, 100.0)])
    result = directed_pass(g, {"L": ([5.0, 0, 0], 0.01), "T": ([1.0, 0, 0], 0.01)})
    assert result.state_mean("T")[0] == pytest.approx(1.0, **APPROX)
    assert "T" not in result.predictions
    # the residual measurement is still available for the state update
    e, var_e = result.residual_observation("T", [1.0, 0, 0], 0.01)
    assert e[0] == pytest.approx(1.0 - 5.0, **APPROX)
    assert var_e[0] == pytest.approx(0.01 + 0.01 + 1.0 / 100.0, **APPROX)


# -------------------------------------------------------- support edge cases
def test_missing_parent_renormalizes():
    g = build_directed_graph(
        ["J", "X", "T"],
        [directed_relation("T", "J", 2.0, 3.0), directed_relation("T", "X", 1.0, 1.0)],
    )
    result = directed_pass(g, {"J": ([1.0, 0, 0], 0.0)})
    pred = result.predictions["T"]
    assert pred.mean[0] == pytest.approx(2.0, **APPROX)  # weight renormalized to J
    assert pred.missing_parents == ("X",)
    assert pred.parents == ("J",)
    assert pred.q_incoming[0] == pytest.approx(3.0)
    assert result.unsupported == ("X",)


def test_parentless_residual_is_ghost_case():
    """D7: no parents + residual state → prediction from the residual alone."""
    g = build_directed_graph(["G"], [])
    result = directed_pass(g, {}, {"G": ([0.7, 0, 0], 0.2)})
    pred = result.predictions["G"]
    assert pred.mean[0] == pytest.approx(0.7, **APPROX)
    assert pred.variance[0] == pytest.approx(0.2, **APPROX)
    assert pred.q_incoming is None and pred.systematic[0] == 0.0
    e, var_e = result.residual_observation("G", [0.5, 0, 0], 0.01)
    assert e[0] == pytest.approx(0.5, **APPROX)  # u = z for a parentless node
    assert var_e[0] == pytest.approx(0.01, **APPROX)


def test_unsupported_component_contract():
    """Golden 15.12 at this layer: no observation, no residual, no parents →
    unsupported, no prediction invented."""
    g = build_directed_graph(["Z"], [])
    result = directed_pass(g, {})
    assert result.unsupported == ("Z",)
    assert not result.predictions


# ---------------------------------------------------------------- diagnostics
def test_residual_surprise():
    """§12.2: chi = (d − m_D)/sqrt(V_obs + V_D)."""
    g = build_directed_graph(["J", "T"], [directed_relation("T", "J", 1.0, 100.0)])
    result = directed_pass(
        g, {"J": ([13.0, 0, 0], 0.02)}, {"T": ([0.0, 0, 0], 0.02)}
    )
    pred = result.predictions["T"]
    chi = residual_surprise([10.0, 0, 0], 0.01, pred)
    expected = (10.0 - 13.0) / np.sqrt(0.01 + pred.variance[0])
    assert chi[0] == pytest.approx(expected, **APPROX)
    assert chi[0] < -8.0  # a 3-point dislocation on these variances is loud

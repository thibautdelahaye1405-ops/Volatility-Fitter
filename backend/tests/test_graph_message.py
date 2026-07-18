"""Phase-1 tests: the precision-message operator (volfit/graph/message.py).

Exit gate of Docs/graph_precision_message_framework.md §23 Phase 1: every
golden case of tests/fixtures/graph_message_golden.json — locked in Phase 0
against an independent brute-force reference — must reproduce to machine
precision THROUGH the production operator assembly. Plus the operator-level
contracts: PSD for arbitrary real betas, the §8.2 calendar-beta example,
canonical-orientation ladder expansion with reciprocal implied betas (§21.9),
the §9.2 precision families, §9.4 per-handle scaling, the §14.2 node-linked
anchor, and the §16.4 cycle diagnostics."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from volfit.graph.message import (
    CALENDAR_PRECISION_EPSILON,
    CALENDAR_PRECISION_SCALE,
    HANDLE_PRECISION_SCALE,
    anchor_precisions,
    build_message_operator,
    calendar_beta,
    calendar_message_precision,
    cycle_beta_products,
    expand_calendar_ladder,
    message_edge,
)

FIXTURE = Path(__file__).parent / "fixtures" / "graph_message_golden.json"
with open(FIXTURE, encoding="utf-8") as _fh:
    _CASES = {c["name"]: c for c in json.load(_fh)["cases"]}


# ------------------------------------------------------------------- helpers
def _case_edges(case: dict) -> list:
    return [
        message_edge(f["receiver"], f["informer"], f["precision"], f["beta"])
        for f in case["factors"]
    ]


def _solve(case: dict, anchors: dict | None = None):
    """Condition the OPERATOR-built Q on the case's clamps/observations —
    the same tiny linear algebra as the Phase-0 reference, but with Q_msg
    sourced from build_message_operator instead of hand-built factors."""
    clamps = case.get("clamps", {})
    nodes = list(case["nodes"]) + [c for c in clamps if c not in case["nodes"]]
    op = build_message_operator(nodes, _case_edges(case))
    idx = op.index
    free = [n for n in nodes if n not in clamps]
    fi = [idx[n] for n in free]
    ci = [idx[n] for n in clamps]
    q = op.q_matrix[np.ix_(fi, fi)].copy()
    b = (
        -op.q_matrix[np.ix_(fi, ci)] @ np.array([clamps[n] for n in clamps])
        if ci
        else np.zeros(len(fi))
    )
    for node, ob in case.get("observations", {}).items():
        k = free.index(node)
        q[k, k] += ob["precision"]
        b[k] += ob["precision"] * ob["value"]
    for node, kappa in (anchors or {}).items():
        if node in free:
            q[free.index(node), free.index(node)] += kappa
    cov = np.linalg.inv(q)
    mean = cov @ b
    return (
        {n: float(mean[k]) for k, n in enumerate(free)},
        {n: float(cov[k, k]) for k, n in enumerate(free)},
        op,
    )


# ------------------------------------------------- golden cases, exit gate
@pytest.mark.parametrize("name", [n for n, c in _CASES.items() if "expected" in c])
def test_golden_through_operator(name: str) -> None:
    case = _CASES[name]
    means, variances, op = _solve(case)
    exp = case["expected"]
    for node, m in exp.get("mean", {}).items():
        assert means[node] == pytest.approx(m, abs=1e-12), node
    for node, v in exp.get("var", {}).items():
        assert variances[node] == pytest.approx(v, abs=1e-12), node
    for node, q_expected in exp.get("q", {}).items():
        assert op.receiver_precision[op.index[node]] == pytest.approx(
            q_expected, abs=1e-12
        ), node


@pytest.mark.parametrize("name", [n for n, c in _CASES.items() if "rho_cases" in c])
def test_golden_rho_cases_through_operator(name: str) -> None:
    """Shrunk-mode goldens with the fixture's explicit fixed kappa, plus the
    cross-check that anchor_precisions derives the SAME kappa from the class
    multiplier — identical for one and two corroborating sources (§14.2)."""
    case = _CASES[name]
    for sub in case["rho_cases"]:
        anchors = dict(sub.get("kappa") or {})
        means, variances, _op = _solve(case, anchors=anchors or None)
        for node, m in sub["expected_mean"].items():
            assert means[node] == pytest.approx(m, abs=1e-12)
        for node, v in sub["expected_var"].items():
            assert variances[node] == pytest.approx(v, abs=1e-12)
        clamps = case.get("clamps", {})
        nodes = list(case["nodes"]) + [c for c in clamps if c not in case["nodes"]]
        derived = anchor_precisions(
            nodes, _case_edges(case), {"custom": sub["rho"]}
        )
        for node, kappa in anchors.items():
            assert derived[nodes.index(node)] == pytest.approx(kappa, rel=1e-12)
        if not anchors:  # rho = 1 → kappa exactly zero everywhere
            assert not derived.any()


def test_dead_informer_conditional_is_pd() -> None:
    """§21.11: the conditional system with a dead informer stays PD under the
    pairwise assembly (the rejected row form is improper here)."""
    case = _CASES["dead_informer"]
    clamps = case["clamps"]
    nodes = list(case["nodes"]) + [c for c in clamps if c not in case["nodes"]]
    op = build_message_operator(nodes, _case_edges(case))
    fi = [op.index[n] for n in case["nodes"]]
    np.linalg.cholesky(op.q_matrix[np.ix_(fi, fi)])  # raises if not PD


# ------------------------------------------------------------ operator core
def test_psd_for_arbitrary_real_betas() -> None:
    rng = np.random.RandomState(7)
    nodes = [f"n{k}" for k in range(30)]
    edges = [
        message_edge(
            nodes[i], nodes[j], float(rng.uniform(0.1, 50.0)), float(rng.randn() * 2.0)
        )
        for i, j in rng.randint(0, 30, size=(80, 2))
        if i != j
    ]
    op = build_message_operator(nodes, edges)
    assert np.allclose(op.q_matrix, op.q_matrix.T)
    assert np.linalg.eigvalsh(op.q_matrix).min() >= -1e-9


def test_edge_validation() -> None:
    with pytest.raises(ValueError, match="self-relation"):
        message_edge("A", "A", 1.0)
    with pytest.raises(ValueError, match="precision"):
        message_edge("A", "B", 0.0)
    with pytest.raises(ValueError, match="unknown node"):
        build_message_operator(["A"], [message_edge("A", "B", 1.0)])
    with pytest.raises(ValueError, match="duplicate"):
        build_message_operator(["A", "A"], [])


def test_handle_precision_scaling() -> None:
    """§9.4: skew/curv operators scale by (s_sigma/s_h)^2; the conditional
    mean is unit-invariant, the variance scales inversely."""
    case = _CASES["competing_unequal"]
    nodes = list(case["nodes"])
    edges = _case_edges(case)
    op0 = build_message_operator(nodes, edges, handle=0)
    op1 = build_message_operator(nodes, edges, handle=1)
    op2 = build_message_operator(nodes, edges, handle=2)
    assert np.allclose(op1.q_matrix, HANDLE_PRECISION_SCALE[1] * op0.q_matrix, rtol=1e-14)
    assert np.allclose(op2.q_matrix, HANDLE_PRECISION_SCALE[2] * op0.q_matrix, rtol=1e-14)


# ------------------------------------------------------------------ calendar
def test_calendar_beta_spec_example() -> None:
    """§8.2: T = (0.25, 0.5, 1.0), 6M lit → beta(3M←6M) = 2, beta(1Y←6M) = 0.5."""
    assert calendar_beta(0.25, 0.5) == pytest.approx(2.0)
    assert calendar_beta(1.0, 0.5) == pytest.approx(0.5)
    assert calendar_beta(0.25, 0.5, alpha=0.0) == pytest.approx(1.0)
    assert calendar_beta(0.25, 0.5, alpha=0.5) == pytest.approx(math.sqrt(2.0))
    with pytest.raises(ValueError):
        calendar_beta(0.0, 0.5)


def test_calendar_precision_families() -> None:
    p = calendar_message_precision(0.25, 0.5)
    assert p == pytest.approx(
        CALENDAR_PRECISION_SCALE / (CALENDAR_PRECISION_EPSILON + 0.5)
    )
    # epsilon caps near-identical expiries at a finite scale/epsilon
    assert calendar_message_precision(0.5, 0.5) == pytest.approx(
        CALENDAR_PRECISION_SCALE / CALENDAR_PRECISION_EPSILON
    )
    assert calendar_message_precision(0.25, 0.5, rule="constant") == pytest.approx(
        CALENDAR_PRECISION_SCALE
    )
    p_near = calendar_message_precision(0.4, 0.5, rule="log_distance")
    p_far = calendar_message_precision(0.1, 0.5, rule="log_distance")
    assert p_near > p_far  # decays in log-maturity distance
    with pytest.raises(ValueError, match="rule"):
        calendar_message_precision(0.25, 0.5, rule="bogus")


def test_expand_calendar_ladder_canonical_orientation() -> None:
    """§7.6: one factor per adjacent pair, receiver = shorter maturity; the
    implied reverse precision is p·beta² (checked through receiver_precision)
    and the implied directional betas are reciprocal (§21.9)."""
    ladder = expand_calendar_ladder(
        {"1Y": 1.0, "3M": 0.25, "6M": 0.5}, alpha=(1.0, 0.5, 0.0)
    )
    assert [(e.receiver, e.informer) for e in ladder] == [("3M", "6M"), ("6M", "1Y")]
    assert all(e.relation_class == "calendar" for e in ladder)
    assert ladder[0].beta == pytest.approx((2.0, math.sqrt(2.0), 1.0))
    assert ladder[0].precision == pytest.approx(calendar_message_precision(0.25, 0.5))
    # §21.9 reciprocity: forward beta × implied reverse beta = 1 by construction
    for e in ladder:
        assert e.beta[0] * (1.0 / e.beta[0]) == pytest.approx(1.0)
    op = build_message_operator(["3M", "6M", "1Y"], ladder)
    p1, p2 = ladder[0].precision, ladder[1].precision
    assert op.receiver_precision[op.index["1Y"]] == pytest.approx(p2 * 4.0)
    assert op.receiver_precision[op.index["6M"]] == pytest.approx(p2 + p1 * 4.0)


# ------------------------------------------------------------------- anchors
def test_anchor_primary_class_selection() -> None:
    """§14.2: kappa uses the PRIMARY (max in-units precision) relation's
    class; rho=1 classes and isolated nodes give exactly zero."""
    nodes = ["R", "CAL", "IDX", "LONE"]
    edges = [
        message_edge("R", "CAL", 10.0, 1.0, "calendar"),
        message_edge("R", "IDX", 2.0, 1.0, "broad_index"),
    ]
    rho = {"calendar": 0.5, "broad_index": 0.2}
    kappa = anchor_precisions(nodes, edges, rho)
    assert kappa[0] == pytest.approx(10.0 * (1 - 0.5) / 0.5)  # calendar wins
    assert kappa[3] == 0.0  # isolated
    assert not anchor_precisions(nodes, edges, {}).any()  # default rho = 1
    with pytest.raises(ValueError, match="multiplier"):
        anchor_precisions(nodes, edges, {"calendar": 0.0})


def test_anchor_informer_side_units() -> None:
    """A node that is the INFORMER of the canonical factor sees the relation
    at p·beta² in its own units (§7.6) — its kappa follows the same mapping."""
    nodes = ["S", "L"]
    edges = [message_edge("S", "L", 4.0, 2.0, "calendar")]
    kappa = anchor_precisions(nodes, edges, {"calendar": 0.5})
    assert kappa[0] == pytest.approx(4.0)   # receiver: p=4, (1-ρ)/ρ = 1
    assert kappa[1] == pytest.approx(16.0)  # informer: p·β² = 16


# ---------------------------------------------------------- cycle diagnostics
def test_cycle_consistent_lattice_has_no_flags() -> None:
    """Gauge-consistent default topology (calendar T-shape betas + beta-one
    cross edges): every cycle product is exactly 1 → no diagnostics."""
    nodes = ["A25", "A50", "B25", "B50"]
    edges = [
        message_edge("A25", "A50", 5.0, 2.0, "calendar"),
        message_edge("B25", "B50", 5.0, 2.0, "calendar"),
        message_edge("A25", "B25", 2.0, 1.0, "sector_peer"),
        message_edge("A50", "B50", 2.0, 1.0, "sector_peer"),
    ]
    assert cycle_beta_products(nodes, edges) == []


def test_cycle_inconsistent_triangle_flagged_with_product() -> None:
    nodes = ["A", "B", "C"]
    edges = [
        message_edge("B", "A", 1.0, 2.0),
        message_edge("C", "B", 1.0, 2.0),
        message_edge("A", "C", 1.0, 2.0),
    ]
    diags = cycle_beta_products(nodes, edges)
    assert len(diags) == 1
    assert (diags[0].receiver, diags[0].informer) == ("A", "C")
    assert diags[0].product == pytest.approx(8.0)


def test_cycle_reciprocal_pair_clean_nonreciprocal_flagged() -> None:
    ok = cycle_beta_products(
        ["X", "Y"],
        [message_edge("X", "Y", 1.0, 2.0), message_edge("Y", "X", 1.0, 0.5)],
    )
    assert ok == []
    bad = cycle_beta_products(
        ["X", "Y"],
        [message_edge("X", "Y", 1.0, 2.0), message_edge("Y", "X", 1.0, 2.0)],
    )
    assert len(bad) == 1
    assert bad[0].product == pytest.approx(4.0)  # both directions claim 2x


def test_cycle_nonpositive_beta_reported_nan() -> None:
    diags = cycle_beta_products(
        ["X", "Y"], [message_edge("X", "Y", 1.0, 0.0)]
    )
    assert len(diags) == 1 and math.isnan(diags[0].product)

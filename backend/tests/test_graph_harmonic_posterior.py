"""Phase-3 tests for volfit.graph.harmonic_posterior (dynamic-harmonic).

EXIT GATE (doc §17 Phase 3): harmonic, uncertain-boundary, mixed-unary, and
disconnected goldens match direct Gaussian references — via the Phase-0
fixture (tests/fixtures/graph_dynamic_golden.json, D9 contract): 15.9
(calendar identity + p-invariance + rescale), 15.10 (harmonic side of the
discriminator), 15.11 (uncertain-boundary chain + star), 15.12 (unsupported
component). Mixed-unary and the D6 joint block are checked against dense
references computed inline.

Also locks: strict gauge validation (§7.2), screened-vs-pure distinction
(§7.6), boundary-wins-over-unary, attribution summing to the mean, hybrid
extra-precision coupling (item 7), and the boundary-variance clamp contract
(central value unchanged while dependent bands widen, golden 15.11)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from volfit.graph.harmonic_posterior import (
    NO_SUPPORT_VARIANCE,
    HarmonicGaugeError,
    harmonic_posterior,
)
from volfit.graph.message import message_edge

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "graph_dynamic_golden.json").read_text()
)

APPROX = dict(rel=1e-12, abs=1e-12)


def _calendar(p1=1.0, p2=1.0):
    fx = FIXTURE["calendar_identity"]
    t = fx["maturities"]
    return ["3M", "6M", "1Y"], [
        message_edge("3M", "6M", p1, t["6M"] / t["3M"]),
        message_edge("6M", "1Y", p2, t["1Y"] / t["6M"]),
    ]


# --------------------------------------------------------------- golden 15.9
def test_calendar_identity():
    fx = FIXTURE["calendar_identity"]
    nodes, edges = _calendar()
    post = harmonic_posterior(nodes, edges, fx["boundary"])
    idx = {n: i for i, n in enumerate(nodes)}
    for node, expected in fx["expected"].items():
        assert post.mean[idx[node]] == pytest.approx(expected, **APPROX)
    t = fx["maturities"]
    for node in nodes:
        assert t[node] * post.mean[idx[node]] == pytest.approx(
            fx["expected_t_times_z"], **APPROX
        )
    for node, expected in fx["expected_variance_at_unit_precision"].items():
        assert post.variance[idx[node]] == pytest.approx(expected, **APPROX)
    assert post.variance[idx["6M"]] == 0.0  # certain boundary
    assert not post.no_active_observation_path.any()


def test_calendar_p_invariance_and_rescale():
    fx = FIXTURE["calendar_identity"]
    nodes, _ = _calendar()
    base = harmonic_posterior(nodes, _calendar()[1], fx["boundary"])
    for p1, p2 in fx["p_invariance_sweep"]:
        post = harmonic_posterior(nodes, _calendar(p1, p2)[1], fx["boundary"])
        assert post.mean == pytest.approx(base.mean, **APPROX)
    c = fx["global_rescale"]
    scaled = harmonic_posterior(nodes, _calendar(c, c)[1], fx["boundary"])
    free = [i for i in range(3) if i not in set(base.boundary)]
    assert scaled.variance[free] == pytest.approx(base.variance[free] / c, **APPROX)


# -------------------------------------------------------------- golden 15.10
def test_harmonic_side_of_discriminator():
    fx = FIXTURE["discriminator"]
    p = fx["edge_precision"]
    nodes = ["L", "u1", "u2", "R"]
    edges = [
        message_edge("u1", "L", p, 1.0),
        message_edge("u2", "u1", p, 1.0),
        message_edge("R", "u2", p, 1.0),
    ]
    post = harmonic_posterior(nodes, edges, fx["boundary"])
    idx = {n: i for i, n in enumerate(nodes)}
    for node, expected in fx["expected_harmonic"].items():
        assert post.mean[idx[node]] == pytest.approx(expected, **APPROX)
    # the directed row solution is a DIFFERENT number — semantics never blur
    assert post.mean[idx["u1"]] != pytest.approx(fx["expected_directed"]["u1"])


# -------------------------------------------------------------- golden 15.11
def test_uncertain_boundary_chain():
    fx = FIXTURE["boundary_uncertainty"]["chain"]
    p = fx["edge_precision"]
    nodes = ["L", "u", "R"]
    edges = [message_edge("u", "L", p, 1.0), message_edge("u", "R", p, 1.0)]
    vals = {"L": fx["d_left"], "R": fx["d_right"]}
    post = harmonic_posterior(
        nodes, edges, vals, boundary_variance={"L": fx["v_left"], "R": fx["v_right"]}
    )
    assert post.mean[1] == pytest.approx(fx["expected_mean"], **APPROX)
    assert post.variance[1] == pytest.approx(fx["expected_variance"], **APPROX)
    # §4.3/15.11: the boundary's central value is CLAMPED, its band widens
    assert post.mean[0] == pytest.approx(fx["d_left"], **APPROX)
    assert post.variance[0] == pytest.approx(fx["v_left"], **APPROX)
    certain = harmonic_posterior(nodes, edges, vals)
    assert certain.mean[1] == pytest.approx(fx["certain_boundary_mean"], **APPROX)
    assert certain.variance[1] == pytest.approx(fx["certain_boundary_variance"], **APPROX)


def test_uncertain_boundary_star_correlates_children():
    fx = FIXTURE["boundary_uncertainty"]["star"]
    p = fx["edge_precision"]
    nodes = ["L", "u1", "u2"]
    edges = [message_edge("u1", "L", p, 1.0), message_edge("u2", "L", p, 1.0)]
    post = harmonic_posterior(
        nodes, edges, {"L": fx["d_left"]}, boundary_variance={"L": fx["v_left"]}
    )
    assert post.mean[1:] == pytest.approx(fx["expected_means"], **APPROX)
    assert post.posterior_covariance[1:, 1:] == pytest.approx(
        np.array(fx["expected_covariance"]), **APPROX
    )


# -------------------------------------------------------------- golden 15.12
def test_unsupported_component():
    fx = FIXTURE["disconnected"]
    nodes = ["L", "u", "Z1", "Z2"]
    edges = [
        message_edge("u", "L", 1.0, 1.0),
        message_edge("Z1", "Z2", 1.0, 1.0),  # a dark island
    ]
    post = harmonic_posterior(nodes, edges, {"L": 1.0})
    assert post.mean[2] == post.mean[3] == fx["expected_mean"]
    assert post.variance[2] == post.variance[3] == NO_SUPPORT_VARIANCE
    assert post.no_active_observation_path[2] and post.no_active_observation_path[3]
    assert not post.no_active_observation_path[1]
    # a screen alone is a ground, not information (§7.7)
    screened = harmonic_posterior(
        nodes, edges, {"L": 1.0}, screen={"Z1": 5.0, "Z2": 5.0}
    )
    assert screened.no_active_observation_path[2]
    assert screened.variance[2] == NO_SUPPORT_VARIANCE


# ------------------------------------------------------- §7.5 unary anchoring
def test_mixed_unary_with_calendar_boundary():
    """§8 closing example: a directed 3M prediction combines with the 6M
    calendar boundary by their stated covariances — dense reference inline."""
    fx = FIXTURE["calendar_identity"]
    nodes, edges = _calendar()
    post = harmonic_posterior(
        nodes, edges, fx["boundary"], unary={"3M": (1.5, 0.5)}
    )
    idx = {n: i for i, n in enumerate(nodes)}
    # reference: A_3M = p1 + 1/v_u = 3, b_3M = 2*p1*d_6M + m_u/v_u = 5
    assert post.mean[idx["3M"]] == pytest.approx(5.0 / 3.0, **APPROX)
    assert post.variance[idx["3M"]] == pytest.approx(1.0 / 3.0, **APPROX)
    assert post.mean[idx["1Y"]] == pytest.approx(0.5, **APPROX)  # untouched
    sources, values, contributions = post.attribution(idx["3M"])
    assert contributions.sum() == pytest.approx(post.mean[idx["3M"]], **APPROX)
    by_source = dict(zip(sources, contributions))
    assert by_source[("boundary", "6M")] == pytest.approx(2.0 / 3.0, **APPROX)
    assert by_source[("unary", "3M")] == pytest.approx(1.0, **APPROX)


def test_boundary_wins_over_unary():
    nodes, edges = _calendar()
    with_unary = harmonic_posterior(
        nodes, edges, {"6M": 1.0}, unary={"6M": (99.0, 0.001)}
    )
    without = harmonic_posterior(nodes, edges, {"6M": 1.0})
    assert with_unary.mean == pytest.approx(without.mean, **APPROX)


def test_joint_unary_block_matches_dense_reference():
    """D6 joint block: two singleton nodes with correlated anchors — the
    posterior equals the anchor distribution itself (no factors), and the
    block's covariance visibly changes the answer once an edge couples them."""
    nodes = ["u1", "u2"]
    means = [1.0, 2.0]
    cov = np.array([[0.5, 0.3], [0.3, 0.5]])
    post = harmonic_posterior(
        nodes, [], {}, unary_joint=(nodes, means, cov)
    )
    assert post.mean == pytest.approx(means, **APPROX)
    assert post.posterior_covariance == pytest.approx(cov, **APPROX)

    # with a tying factor, compare against the dense information-form answer
    edges = [message_edge("u1", "u2", 2.0, 1.0)]
    post_edge = harmonic_posterior(nodes, edges, {}, unary_joint=(nodes, means, cov))
    q = np.array([[2.0, -2.0], [-2.0, 2.0]]) + np.linalg.inv(cov)
    ref_mean = np.linalg.solve(q, np.linalg.inv(cov) @ np.array(means))
    assert post_edge.mean == pytest.approx(ref_mean, **APPROX)
    assert post_edge.posterior_covariance == pytest.approx(np.linalg.inv(q), **APPROX)

    # a DIAGONAL joint block must reproduce the independent-anchor path
    diag = harmonic_posterior(
        nodes, edges, {}, unary_joint=(nodes, means, np.diag([0.5, 0.5]))
    )
    indep = harmonic_posterior(
        nodes, edges, {}, unary={"u1": (1.0, 0.5), "u2": (2.0, 0.5)}
    )
    assert diag.mean == pytest.approx(indep.mean, **APPROX)
    assert diag.variance == pytest.approx(indep.variance, **APPROX)
    # and the correlated block gives a DIFFERENT posterior than diagonal (D6)
    assert not np.allclose(post_edge.mean, indep.mean)


def test_joint_block_rejects_boundary_nodes():
    nodes, edges = _calendar()
    with pytest.raises(ValueError):
        harmonic_posterior(
            nodes, edges, {"6M": 1.0},
            unary_joint=(["6M", "3M"], [1.0, 1.0], np.eye(2)),
        )


# ------------------------------------------------------------- §7.6 screening
def test_screened_versus_pure_harmonic():
    nodes = ["L", "u"]
    edges = [message_edge("u", "L", 1.0, 1.0)]
    pure = harmonic_posterior(nodes, edges, {"L": 1.0})
    screened = harmonic_posterior(nodes, edges, {"L": 1.0}, screen={"u": 1.0})
    assert pure.mean[1] == pytest.approx(1.0, **APPROX)     # full transmission
    assert screened.mean[1] == pytest.approx(0.5, **APPROX)  # shrunk to ground
    with pytest.raises(ValueError):
        harmonic_posterior(nodes, edges, {"L": 1.0}, screen={"u": -1.0})


# ------------------------------------------------------------ §7.2 strict mode
def test_strict_gauge_validation():
    nodes = ["a", "b", "c"]
    consistent = [
        message_edge("a", "b", 1.0, 2.0),
        message_edge("b", "c", 1.0, 2.0),
        message_edge("a", "c", 1.0, 4.0),  # product around the cycle = 1
    ]
    harmonic_posterior(nodes, consistent, {"a": 1.0}, strict_gauge=True)
    broken = consistent[:2] + [message_edge("a", "c", 1.0, 5.0)]
    with pytest.raises(HarmonicGaugeError):
        harmonic_posterior(nodes, broken, {"a": 1.0}, strict_gauge=True)
    harmonic_posterior(nodes, broken, {"a": 1.0})  # default mode still solves
    negative = [message_edge("a", "b", 1.0, -1.0)]
    with pytest.raises(HarmonicGaugeError):
        harmonic_posterior(["a", "b"], negative, {"a": 1.0}, strict_gauge=True)


# ------------------------------------------------------ item 7: hybrid coupling
def test_extra_precision_couples_and_supports():
    """An off-diagonal hybrid term both couples components and carries the
    support across — the §17 Phase-3 item-7 detection rule."""
    nodes = ["L", "u", "w"]
    edges = [message_edge("u", "L", 1.0, 1.0)]  # w has no relation at all
    extra = np.zeros((3, 3))
    without = harmonic_posterior(nodes, edges, {"L": 1.0}, extra_precision=extra)
    assert without.no_active_observation_path[2]
    extra[1, 1] = extra[2, 2] = 1.0
    extra[1, 2] = extra[2, 1] = -1.0  # PSD tie u~w
    with_tie = harmonic_posterior(nodes, edges, {"L": 1.0}, extra_precision=extra)
    assert not with_tie.no_active_observation_path[2]
    # reference: minimize (z_u - 1)^2 + (z_u - z_w)^2 -> z_u = z_w = 1
    assert with_tie.mean[1] == pytest.approx(1.0, **APPROX)
    assert with_tie.mean[2] == pytest.approx(1.0, **APPROX)

"""Phase-2 tests: information-form message posterior (message_posterior.py).

Exit gate (spec §23 Phase 2): global results match brute-force Gaussian
references — including repeated-path, cycle, and dead-informer fixtures.
Strategy: every golden fixture case is solved twice, (a) with moderate
observation precision against the independent Phase-0 brute-force reference
(1e-11 agreement — same model, different assembly), and (b) with
near-clamping precision against the fixture's idealized clamped numbers
(1e-6 — the infinite-precision limit). Native-observation cases (multi-hop,
repeated-path) must hit the fixture numbers at machine precision directly.
Plus the structural contracts: no_lit_path components, the zero-beta
informer-reachability guard, exact attribution, and anchor/hybrid terms."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from volfit.graph.message import build_message_operator, message_edge
from volfit.graph.message_posterior import message_posterior_update

from tests.test_graph_message_golden import reference_posterior

FIXTURE = Path(__file__).parent / "fixtures" / "graph_message_golden.json"
with open(FIXTURE, encoding="utf-8") as _fh:
    _CASES = {c["name"]: c for c in json.load(_fh)["cases"]}

CLAMP_R = 1e9  # near-clamp emulation for the idealized fixture comparisons


# ------------------------------------------------------------------- helpers
def _nodes(case: dict) -> list[str]:
    clamps = case.get("clamps", {})
    return list(case["nodes"]) + [c for c in clamps if c not in case["nodes"]]


def _operator(case: dict):
    edges = [
        message_edge(f["receiver"], f["informer"], f["precision"], f["beta"])
        for f in case["factors"]
    ]
    return build_message_operator(_nodes(case), edges)


def _as_observation_case(case: dict, clamp_r: float) -> dict:
    """The same model with clamps rewritten as finite-precision observations
    (what production actually does — lit nodes are never hard-clamped)."""
    obs = {n: dict(ob) for n, ob in case.get("observations", {}).items()}
    for node, value in case.get("clamps", {}).items():
        obs[node] = {"value": value, "precision": clamp_r}
    out = {k: v for k, v in case.items() if k not in ("clamps", "observations")}
    out["nodes"] = _nodes(case)
    out["observations"] = obs
    return out


def _solve(case: dict, clamp_r: float, kappa: dict | None = None):
    ref_case = _as_observation_case(case, clamp_r)
    op = _operator(case)
    idx = op.index
    names = list(ref_case["observations"])
    post = message_posterior_update(
        op,
        np.array([idx[n] for n in names], dtype=int),
        np.array([ref_case["observations"][n]["value"] for n in names]),
        np.array([ref_case["observations"][n]["precision"] for n in names]),
        anchor_precision=_kappa_vec(op, kappa),
    )
    return post, op, ref_case


def _kappa_vec(op, kappa: dict | None):
    if not kappa:
        return None
    vec = np.zeros(len(op.nodes))
    for node, value in kappa.items():
        vec[op.index[node]] = value
    return vec


def _case_kappa(case: dict) -> dict | None:
    subs = case.get("rho_cases")
    return dict(subs[0].get("kappa") or {}) if subs else None


# ------------------------------------- (a) brute-force reference agreement
@pytest.mark.parametrize("name", sorted(_CASES))
def test_matches_brute_force_reference(name: str) -> None:
    """Same model, moderate precision (well-conditioned): the information-form
    component solve must agree with the independent dense reference."""
    case = _CASES[name]
    kappa = _case_kappa(case)
    post, op, ref_case = _solve(case, clamp_r=50.0, kappa=kappa)
    ref_means, ref_vars = reference_posterior(ref_case, anchors=kappa)
    for node, m in ref_means.items():
        assert post.mean[op.index[node]] == pytest.approx(m, abs=1e-11), node
    for node, v in ref_vars.items():
        assert post.marginal_variance[op.index[node]] == pytest.approx(
            v, abs=1e-11
        ), node


# ----------------------------------- (b) idealized clamped fixture numbers
@pytest.mark.parametrize(
    "name",
    [n for n, c in _CASES.items() if "expected" in c and "clamps" in c],
)
def test_clamped_fixture_limit(name: str) -> None:
    case = _CASES[name]
    post, op, _ = _solve(case, clamp_r=CLAMP_R)
    for node, m in case["expected"].get("mean", {}).items():
        assert post.mean[op.index[node]] == pytest.approx(m, abs=1e-6), node
    for node, v in case["expected"].get("var", {}).items():
        assert post.marginal_variance[op.index[node]] == pytest.approx(
            v, abs=1e-6
        ), node


@pytest.mark.parametrize(
    "name",
    [n for n, c in _CASES.items() if "expected" in c and "observations" in c],
)
def test_native_observation_fixtures_exact(name: str) -> None:
    """Multi-hop and repeated-path use finite precision natively — the solver
    must hit the fixture numbers at machine precision."""
    case = _CASES[name]
    post, op, _ = _solve(case, clamp_r=CLAMP_R)
    for node, m in case["expected"]["mean"].items():
        assert post.mean[op.index[node]] == pytest.approx(m, abs=1e-12), node
    for node, v in case["expected"]["var"].items():
        assert post.marginal_variance[op.index[node]] == pytest.approx(
            v, abs=1e-12
        ), node


@pytest.mark.parametrize("name", [n for n, c in _CASES.items() if "rho_cases" in c])
def test_shrunk_fixture_limit(name: str) -> None:
    case = _CASES[name]
    for sub in case["rho_cases"]:
        post, op, _ = _solve(case, clamp_r=CLAMP_R, kappa=dict(sub.get("kappa") or {}))
        for node, m in sub["expected_mean"].items():
            assert post.mean[op.index[node]] == pytest.approx(m, abs=1e-6), node
        for node, v in sub["expected_var"].items():
            assert post.marginal_variance[op.index[node]] == pytest.approx(
                v, abs=1e-6
            ), node


# --------------------------------------------------------------- attribution
@pytest.mark.parametrize("name", sorted(_CASES))
def test_attribution_sums_to_shift(name: str) -> None:
    """§17: contributions decompose the shift EXACTLY over observed sources
    (prior innovation mean is zero, so the shift IS the mean)."""
    case = _CASES[name]
    post, _op, _ = _solve(case, clamp_r=50.0, kappa=_case_kappa(case))
    for i in range(post.mean.size):
        gain, innovation, contributions = post.attribution(i)
        assert np.array_equal(contributions, gain * innovation)
        if not post.no_lit_path[i]:
            assert contributions.sum() == pytest.approx(post.mean[i], abs=1e-10)
        else:
            assert not contributions.any()


# ----------------------------------------------- components and reachability
def test_no_lit_component_stays_at_prior() -> None:
    """§14.3: a dark component keeps zero innovation, broad variance, the
    no_lit_path tag, and zero cross-component covariance."""
    nodes = ["A", "B", "C", "D"]
    op = build_message_operator(
        nodes,
        [message_edge("B", "A", 4.0, 1.0), message_edge("D", "C", 4.0, 1.0)],
    )
    post = message_posterior_update(op, np.array([0]), np.array([1.0]), np.array([50.0]))
    assert not post.no_lit_path[0] and not post.no_lit_path[1]
    assert post.no_lit_path[2] and post.no_lit_path[3]
    assert post.mean[2] == 0.0 and post.mean[3] == 0.0
    assert np.isinf(post.marginal_variance[2]) and np.isinf(post.marginal_variance[3])
    assert post.component[0] == post.component[1] != post.component[2]
    assert not post.posterior_covariance[:2, 2:].any()


def test_zero_beta_informer_reachability_guard() -> None:
    """A zero-beta factor couples only its receiver: the informer lands in its
    own (no-lit) component, and the receiver's solve equals the reference
    with the factor replaced by an anchor of the same precision."""
    op = build_message_operator(
        ["R", "S", "D"],
        [message_edge("R", "S", 4.0, 1.0), message_edge("R", "D", 7.0, 0.0)],
    )
    post = message_posterior_update(op, np.array([1]), np.array([1.0]), np.array([50.0]))
    assert post.no_lit_path[2] and not post.no_lit_path[0]
    ref_case = {
        "nodes": ["R", "S"],
        "factors": [{"receiver": "R", "informer": "S", "beta": 1.0, "precision": 4.0}],
        "observations": {"S": {"value": 1.0, "precision": 50.0}},
    }
    ref_means, ref_vars = reference_posterior(ref_case, anchors={"R": 7.0})
    assert post.mean[0] == pytest.approx(ref_means["R"], abs=1e-12)
    assert post.marginal_variance[0] == pytest.approx(ref_vars["R"], abs=1e-12)


def test_consistent_directed_cycle_transmits_exactly() -> None:
    """§16: a gauge-consistent cycle (beta product 1) carries the observed
    innovation around at full amplitude — the zero-energy manifold pins the
    means exactly; variances match the brute-force reference."""
    case = {
        "nodes": ["A", "B", "C"],
        "factors": [
            {"receiver": "B", "informer": "A", "beta": 2.0, "precision": 4.0},
            {"receiver": "C", "informer": "B", "beta": 2.0, "precision": 8.0},
            {"receiver": "A", "informer": "C", "beta": 0.25, "precision": 2.0},
        ],
        "observations": {"A": {"value": 0.5, "precision": 10.0}},
    }
    post, op, ref_case = _solve(case, clamp_r=CLAMP_R)
    assert post.mean[op.index["A"]] == pytest.approx(0.5, abs=1e-12)
    assert post.mean[op.index["B"]] == pytest.approx(1.0, abs=1e-12)
    assert post.mean[op.index["C"]] == pytest.approx(2.0, abs=1e-12)
    ref_means, ref_vars = reference_posterior(ref_case)
    for node in case["nodes"]:
        assert post.marginal_variance[op.index[node]] == pytest.approx(
            ref_vars[node], abs=1e-11
        )


# ----------------------------------------------------- anchors and hybrid term
def test_desk_mode_zero_anchor_is_identity() -> None:
    case = _CASES["cross_asset_average"]
    post_none, op, _ = _solve(case, clamp_r=50.0)
    post_zero = message_posterior_update(
        op,
        post_none.observed,
        post_none.innovations,
        post_none.innovation_precision,
        anchor_precision=np.zeros(len(op.nodes)),
    )
    assert np.array_equal(post_none.mean, post_zero.mean)
    assert np.array_equal(post_none.marginal_variance, post_zero.marginal_variance)


def test_extra_precision_matches_diagonal_anchor() -> None:
    """§15.4: the optional hybrid term composes additively — a diagonal extra
    matrix must reproduce the anchor path exactly."""
    case = _CASES["competing_unequal"]
    kappa = {"R6": 3.0}
    post_anchor, op, _ = _solve(case, clamp_r=50.0, kappa=kappa)
    vec = _kappa_vec(op, kappa)
    post_extra = message_posterior_update(
        op,
        post_anchor.observed,
        post_anchor.innovations,
        post_anchor.innovation_precision,
        extra_precision=np.diag(vec),
    )
    assert np.allclose(post_anchor.mean, post_extra.mean, atol=0)
    assert np.allclose(
        post_anchor.marginal_variance, post_extra.marginal_variance, atol=0
    )


def test_pd_guard_raises_on_indefinite_system() -> None:
    op = build_message_operator(["A", "B"], [message_edge("B", "A", 4.0, 1.0)])
    with pytest.raises(np.linalg.LinAlgError, match="positive definite"):
        message_posterior_update(
            op,
            np.array([0]),
            np.array([1.0]),
            np.array([50.0]),
            extra_precision=-10.0 * np.eye(2),
        )


# ------------------------------------------------------------ misc contracts
def test_marginal_precision_and_band() -> None:
    case = _CASES["competing_equal"]
    post, op, _ = _solve(case, clamp_r=50.0)
    i = op.index["R6"]
    assert post.marginal_precision[i] == pytest.approx(
        1.0 / post.marginal_variance[i]
    )
    lo, hi = post.credible_band(2.0)
    assert hi[i] - lo[i] == pytest.approx(4.0 * np.sqrt(post.marginal_variance[i]))


def test_input_validation() -> None:
    op = build_message_operator(["A", "B"], [message_edge("B", "A", 4.0, 1.0)])
    with pytest.raises(ValueError, match="lengths"):
        message_posterior_update(op, np.array([0]), np.array([1.0]), np.array([]))
    with pytest.raises(ValueError, match="finite and > 0"):
        message_posterior_update(op, np.array([0]), np.array([1.0]), np.array([0.0]))
    with pytest.raises(ValueError, match="out of range"):
        message_posterior_update(op, np.array([5]), np.array([1.0]), np.array([1.0]))
    with pytest.raises(ValueError, match="duplicate"):
        message_posterior_update(
            op, np.array([0, 0]), np.array([1.0, 1.0]), np.array([1.0, 1.0])
        )

"""Golden acceptance contracts for the dynamic directed-harmonic framework.

Phase-0 lock (Docs/dynamic_directed_harmonic_graph_framework.md sections 15
and 17 / decision D9): every numeric contract is verified against
SELF-CONTAINED brute-force references — a causal last-tick state machine and
dense Dirichlet / GLS solves — deliberately importing nothing from
``volfit.graph``. Implementation phases must later reproduce the SAME fixture
numbers THROUGH the production modules (the message-arc P0 pattern of
tests/test_graph_message_golden.py).

Contract map (doc section numbers): 15.1 asynchronous A/B sequence, 15.2 zero
reverse influence, 15.3 exact target observation, 15.4 persistent common
move, 15.5 residual half-life + transition variance, 15.6 precision
separation, 15.7 no look-ahead, 15.8 actual-observation-only state updates,
15.9 harmonic calendar identity, 15.10 reciprocal-vs-directed discriminator,
15.11 uncertain boundary (Omega/GLS), 15.12 disconnected component, 15.13
configuration rebase. 15.14 (legacy byte-identity) is locked by the untouched
existing suite, not here. Temporal transitions encode Phase-0 decision D2
(OU for finite half-life, random walk for infinite), D3 (hard residual update
for certified observations), and D5 (causal all-to-idio residual attribution).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "graph_dynamic_golden.json").read_text()
)

APPROX = dict(rel=1e-12, abs=1e-12)


# ----------------------------------------------------------------- references
def _phi(delta: float, half_life: float | None) -> float:
    """Doc section 5.5: exponential residual retention, half-life H."""
    if half_life is None:
        return 1.0
    return 2.0 ** (-delta / half_life)


def _ab_machine(obs_a, obs_b, snapshots, beta, half_life=None):
    """Doc sections 5-6 causal machine: last-tick source lease, hard residual
    update at actual target observations (D3), exponential decay between them.

    Returns (a_marks, b_marks, update_times, u_by_snapshot)."""
    a_marks, b_marks, updates, u_trace = [], [], [], []
    u, u_time = 0.0, None
    for t in snapshots:
        a_val = obs_a[max(s for s in obs_a if s <= t)]  # causal: never s > t
        if t in obs_b:
            u = obs_b[t] - beta * a_val  # aligned residual, doc (5.2) / D5
            u_time = t
            updates.append(t)
            b_val = obs_b[t]  # certified clamp, golden 15.3
        else:
            decayed = 0.0 if u_time is None else u * _phi(t - u_time, half_life)
            b_val = beta * a_val + decayed
        a_marks.append(a_val)
        b_marks.append(b_val)
        u_trace.append(u if u_time is None else u * _phi(t - u_time, half_life))
    return a_marks, b_marks, updates, u_trace


def _factors(nodes, edges):
    """Factor matrices for residuals ``r = z_receiver - beta * z_informer``."""
    idx = {n: k for k, n in enumerate(nodes)}
    b_mat = np.zeros((len(edges), len(nodes)))
    prec = np.zeros(len(edges))
    for e, (receiver, informer, beta, p) in enumerate(edges):
        b_mat[e, idx[receiver]] = 1.0
        b_mat[e, idx[informer]] = -beta
        prec[e] = p
    return b_mat, prec, idx


def _dirichlet(nodes, edges, boundary):
    """Doc section 7.3: exact hard-boundary partition solve."""
    b_mat, prec, idx = _factors(nodes, edges)
    s_idx = [idx[n] for n in boundary]
    f_idx = [k for k in range(len(nodes)) if k not in s_idx]
    q = b_mat.T @ np.diag(prec) @ b_mat
    d = np.array(list(boundary.values()))
    mean = np.linalg.solve(q[np.ix_(f_idx, f_idx)], -q[np.ix_(f_idx, s_idx)] @ d)
    cov = np.linalg.inv(q[np.ix_(f_idx, f_idx)])
    names = [nodes[k] for k in f_idx]
    return dict(zip(names, mean)), cov, names


def _gls_boundary(nodes, edges, boundary_vals, boundary_var):
    """Doc section 7.4: clamped-mean boundary with covariance
    Omega = P^-1 + B_S V_S B_S^T folded into a GLS solve for the free nodes."""
    b_mat, prec, idx = _factors(nodes, edges)
    s_idx = [idx[n] for n in boundary_vals]
    f_idx = [k for k in range(len(nodes)) if k not in s_idx]
    b_f, b_s = b_mat[:, f_idx], b_mat[:, s_idx]
    d = np.array(list(boundary_vals.values()))
    v_s = np.diag([boundary_var[n] for n in boundary_vals])
    omega = np.diag(1.0 / prec) + b_s @ v_s @ b_s.T
    a = b_f.T @ np.linalg.solve(omega, b_f)
    rhs = -b_f.T @ np.linalg.solve(omega, b_s @ d)
    return np.linalg.solve(a, rhs), np.linalg.inv(a)


def _directed_cascade(boundary, arcs, p):
    """Doc section 6.4/15.10: topological pass, beta one, equal-precision
    parent weights, no residuals."""
    values = dict(boundary)
    parents: dict[str, list[str]] = {}
    for source, target in arcs:
        parents.setdefault(target, []).append(source)
    for target, srcs in parents.items():  # arcs listed in topological order
        values[target] = sum(p * values[s] for s in srcs) / (p * len(srcs))
    return values


# ------------------------------------------------- 15.1 / 15.4 / 15.7 / 15.8
def test_async_ab_sequence():
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    a, b, updates, _ = _ab_machine(obs_a, obs_b, fx["snapshots"], fx["beta"])
    assert a == pytest.approx(fx["expected_a"], **APPROX)
    assert b == pytest.approx(fx["expected_b"], **APPROX)
    assert updates == fx["expected_update_times"]


def test_async_ab_attribution():
    """Exit-gate attribution at t=4.0: systematic + residual == mark (15.1)."""
    fx = FIXTURE["async_ab"]
    att = fx["attribution_at_4_0"]
    assert att["systematic"] + att["residual"] == pytest.approx(att["mark"])
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    _, b, _, u_trace = _ab_machine(obs_a, obs_b, fx["snapshots"], fx["beta"])
    i = fx["snapshots"].index(4.0)
    assert b[i] == pytest.approx(att["mark"], **APPROX)
    assert u_trace[i] == pytest.approx(att["residual"], **APPROX)


def test_zero_reverse_influence():
    """15.2: A's path is bit-identical with and without B's observations."""
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    a_with, _, _, _ = _ab_machine(obs_a, obs_b, fx["snapshots"], fx["beta"])
    a_without, _, _, _ = _ab_machine(obs_a, {}, fx["snapshots"], fx["beta"])
    assert a_with == a_without == fx["expected_a"]


def test_exact_target_observation():
    """15.3: the certified clamp overrides the systematic prediction."""
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    _, b, _, _ = _ab_machine(obs_a, obs_b, fx["snapshots"], fx["beta"])
    i = fx["snapshots"].index(3.5)
    assert b[i] == pytest.approx(obs_b[3.5], **APPROX)
    assert b[i] != pytest.approx(fx["systematic_prediction_at_3_5"])


def test_no_lookahead():
    """15.7: the t=3.5 residual is -3 against A's LAST tick (13), never -3.5
    against a future-interpolated 13.5."""
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    _, _, _, u_trace = _ab_machine(obs_a, obs_b, fx["snapshots"], fx["beta"])
    i = fx["snapshots"].index(3.5)
    assert u_trace[i] == pytest.approx(fx["expected_u_after_3_5"], **APPROX)
    assert u_trace[i] != pytest.approx(fx["forbidden_lookahead_u"])


def test_actual_observation_only_updates():
    """15.8: residual updates happen ONLY at actual B observations; under
    phi=1 the residual then persists unchanged."""
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    _, _, updates, u_trace = _ab_machine(obs_a, obs_b, fx["snapshots"], fx["beta"])
    assert updates == fx["expected_update_times"]
    for t in (4.0, 4.5, 5.0):
        assert u_trace[fx["snapshots"].index(t)] == pytest.approx(
            fx["expected_u_after_3_5"], **APPROX
        )


def test_persistent_common_move_beta_variants():
    """15.4: after the residual update, a source move Delta transmits as
    beta * Delta to the dark target — beta 1 and beta 1.5 fixtures."""
    base = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in base["obs_a"].items()}
    obs_b = {float(k): v for k, v in base["obs_b"].items()}
    snaps = base["snapshots"]
    _, b1, _, _ = _ab_machine(obs_a, obs_b, snaps, base["beta"])
    assert b1[snaps.index(4.0)] - b1[snaps.index(3.5)] == pytest.approx(1.0, **APPROX)

    fx15 = FIXTURE["async_ab_beta15"]
    _, b15, _, u_trace = _ab_machine(obs_a, obs_b, snaps, fx15["beta"])
    assert b15 == pytest.approx(fx15["expected_b"], **APPROX)
    assert u_trace[snaps.index(0.0)] == pytest.approx(fx15["expected_u_after_0"])
    assert u_trace[snaps.index(3.5)] == pytest.approx(fx15["expected_u_after_3_5"])
    assert b15[snaps.index(5.0)] - b15[snaps.index(4.0)] == pytest.approx(
        fx15["expected_delta_per_unit_source_move"], **APPROX
    )


# --------------------------------------------------------- 15.5 / decision D2
def test_residual_half_life_mean():
    fx = FIXTURE["async_ab"]
    hl = FIXTURE["residual_half_life"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    snaps = fx["snapshots"]
    _, b, _, u_trace = _ab_machine(obs_a, obs_b, snaps, 1.0, hl["half_life"])
    assert u_trace[snaps.index(4.5)] == pytest.approx(hl["expected_u_at_4_5"], **APPROX)
    assert b[snaps.index(4.0)] == pytest.approx(hl["expected_b_at_4_0"], rel=1e-9)


def test_transition_variances_and_semigroup():
    """D2: OU Q = V_inf (1 - phi^2) for finite H, random walk Q = q*Delta for
    infinite H; both compose exactly over split steps."""
    hl = FIXTURE["residual_half_life"]

    def ou_step(v, delta, h, v_inf):
        f2 = _phi(delta, h) ** 2
        return f2 * v + v_inf * (1.0 - f2)

    ou = hl["ou_transition"]
    one = ou_step(ou["v_plus"], ou["delta"], hl["half_life"], ou["v_inf"])
    assert one == pytest.approx(ou["expected_v_minus"], **APPROX)
    half = ou_step(ou["v_plus"], ou["delta"] / 2, hl["half_life"], ou["v_inf"])
    two = ou_step(half, ou["delta"] / 2, hl["half_life"], ou["v_inf"])
    assert two == pytest.approx(one, **APPROX)

    rw = hl["random_walk_transition"]
    one = rw["v_plus"] + rw["q_rate"] * rw["delta"]
    assert one == pytest.approx(rw["expected_v_minus"], **APPROX)
    two = (rw["v_plus"] + rw["q_rate"] * rw["delta"] / 2) + rw["q_rate"] * rw["delta"] / 2
    assert two == pytest.approx(one, **APPROX)


# ---------------------------------------------------------------------- 15.6
def test_precision_separation_single_source():
    fx = FIXTURE["precision_separation"]["single"]
    mean = fx["beta"] * fx["m_source"] + fx["m_residual"]
    assert mean == pytest.approx(fx["expected_mean"], **APPROX)
    for p, expected in zip(fx["p_sweep"], fx["expected_variance"]):
        var = fx["beta"] ** 2 * fx["v_source"] + fx["v_residual"] + 1.0 / p
        assert var == pytest.approx(expected, **APPROX)


def test_precision_separation_multi_source():
    fx = FIXTURE["precision_separation"]["multi"]
    p = np.array(fx["p"])
    w = p / p.sum()
    assert w == pytest.approx(fx["expected_weights"], **APPROX)
    a = w * np.array(fx["beta"])
    mean = float(a @ np.array(fx["z_parents"]))
    assert mean == pytest.approx(fx["expected_mean"], **APPROX)
    v = np.array(fx["v_parents"])
    sigma_ind = np.diag(v)
    var_ind = float(a @ sigma_ind @ a) + fx["v_residual"] + 1.0 / p.sum()
    assert var_ind == pytest.approx(fx["expected_variance_independent"], **APPROX)
    rho = fx["parent_correlation"]
    cov = rho * math.sqrt(v[0] * v[1])
    sigma_cor = np.array([[v[0], cov], [cov, v[1]]])
    var_cor = float(a @ sigma_cor @ a) + fx["v_residual"] + 1.0 / p.sum()
    assert var_cor == pytest.approx(fx["expected_variance_correlated"], **APPROX)
    assert var_cor > var_ind  # correlated parents must never look MORE certain


# ---------------------------------------------------------------------- 15.9
def _calendar_edges(p1, p2):
    fx = FIXTURE["calendar_identity"]
    t = fx["maturities"]
    return [
        ("3M", "6M", t["6M"] / t["3M"], p1),  # canonical receiver = shorter
        ("6M", "1Y", t["1Y"] / t["6M"], p2),
    ]


def test_calendar_identity():
    fx = FIXTURE["calendar_identity"]
    mean, cov, names = _dirichlet(
        ["3M", "6M", "1Y"], _calendar_edges(1.0, 1.0), fx["boundary"]
    )
    for node, expected in fx["expected"].items():
        assert mean[node] == pytest.approx(expected, **APPROX)
    t = fx["maturities"]
    for node in ("3M", "1Y"):
        assert t[node] * mean[node] == pytest.approx(fx["expected_t_times_z"], **APPROX)
    assert t["6M"] * fx["boundary"]["6M"] == pytest.approx(fx["expected_t_times_z"])
    for node, expected in fx["expected_variance_at_unit_precision"].items():
        assert cov[names.index(node), names.index(node)] == pytest.approx(
            expected, **APPROX
        )


def test_calendar_p_invariance_and_rescale():
    """Section 7.3: means are precision-free on a tree; a global precision
    rescale by c leaves means unchanged and divides covariance by c."""
    fx = FIXTURE["calendar_identity"]
    base_mean, base_cov, _ = _dirichlet(
        ["3M", "6M", "1Y"], _calendar_edges(1.0, 1.0), fx["boundary"]
    )
    for p1, p2 in fx["p_invariance_sweep"]:
        mean, _, _ = _dirichlet(["3M", "6M", "1Y"], _calendar_edges(p1, p2), fx["boundary"])
        assert mean == pytest.approx(base_mean, **APPROX)
    c = fx["global_rescale"]
    _, cov_scaled, _ = _dirichlet(
        ["3M", "6M", "1Y"], _calendar_edges(c, c), fx["boundary"]
    )
    assert cov_scaled == pytest.approx(base_cov / c, **APPROX)


# --------------------------------------------------------------------- 15.10
def test_reciprocal_versus_directed_discriminator():
    fx = FIXTURE["discriminator"]
    p = fx["edge_precision"]
    edges = [("u1", "L", 1.0, p), ("u2", "u1", 1.0, p), ("R", "u2", 1.0, p)]
    mean, _, _ = _dirichlet(["L", "u1", "u2", "R"], edges, fx["boundary"])
    for node, expected in fx["expected_harmonic"].items():
        assert mean[node] == pytest.approx(expected, **APPROX)
    cascade = _directed_cascade(fx["boundary"], fx["directed_arcs"], p)
    for node, expected in fx["expected_directed"].items():
        assert cascade[node] == pytest.approx(expected, **APPROX)
    assert fx["expected_harmonic"]["u1"] != pytest.approx(fx["expected_directed"]["u1"])


# --------------------------------------------------------------------- 15.11
def test_boundary_uncertainty_chain():
    fx = FIXTURE["boundary_uncertainty"]["chain"]
    p = fx["edge_precision"]
    edges = [("u", "L", 1.0, p), ("u", "R", 1.0, p)]
    vals = {"L": fx["d_left"], "R": fx["d_right"]}
    mean, cov = _gls_boundary(
        ["L", "u", "R"], edges, vals, {"L": fx["v_left"], "R": fx["v_right"]}
    )
    assert mean[0] == pytest.approx(fx["expected_mean"], **APPROX)
    assert cov[0, 0] == pytest.approx(fx["expected_variance"], **APPROX)
    mean0, cov0 = _gls_boundary(["L", "u", "R"], edges, vals, {"L": 0.0, "R": 0.0})
    assert mean0[0] == pytest.approx(fx["certain_boundary_mean"], **APPROX)
    assert cov0[0, 0] == pytest.approx(fx["certain_boundary_variance"], **APPROX)


def test_boundary_uncertainty_star_correlates_children():
    """Section 7.4 point 2: one uncertain boundary feeding two free nodes
    induces EXACTLY its variance as their posterior covariance."""
    fx = FIXTURE["boundary_uncertainty"]["star"]
    p = fx["edge_precision"]
    edges = [("u1", "L", 1.0, p), ("u2", "L", 1.0, p)]
    mean, cov = _gls_boundary(
        ["L", "u1", "u2"], edges, {"L": fx["d_left"]}, {"L": fx["v_left"]}
    )
    assert mean == pytest.approx(fx["expected_means"], **APPROX)
    assert cov == pytest.approx(np.array(fx["expected_covariance"]), **APPROX)


# ------------------------------------------------------------- 15.12 / 15.13
def test_disconnected_component_contract():
    fx = FIXTURE["disconnected"]
    assert fx["expected_mean"] == 0.0  # transported prior, nothing invented
    assert fx["expected_flag"] == "no_active_observation_path"


def test_config_rebase_invalidates_residual():
    """15.13: a beta change invalidates the stored residual — the mark falls
    back to the pure systematic prediction under the NEW config, flagged."""
    fx = FIXTURE["config_rebase"]
    mark = fx["beta_new"] * fx["source_state"]  # residual EXCLUDED
    assert mark == pytest.approx(fx["expected_mark_after_invalidation"], **APPROX)
    assert mark != pytest.approx(fx["beta_new"] * fx["source_state"] + fx["u_old"])
    assert fx["expected_flag"] == "residual_invalidated"

"""Directed influence engine for the dynamic-harmonic framework (Phase 2).

Implements Docs/dynamic_directed_harmonic_graph_framework.md §6 (directed
dynamic propagation) on an exact DAG: per-handle relation schema (§9.3), DAG
validation + topological order (§6.5, v1 policy: directed cycles REJECTED),
the single/multi-parent systematic predictor with FULL parent covariance
(§6.4), cut target updates (§6.3 — a target observation never feeds back to
a parent), unary predictive distributions ``(m_D, V_D)`` for the Phase-3
harmonic layer (§7.5), exact source+residual attribution (§6.6), and the
residual-surprise diagnostic (§12.2).

Design: exact linear-Gaussian propagation by GAIN ROWS over independent ROOT
variables — observation innovations ``("obs", node)``, residual states
``("res", node)``, and per-target relation noises ``("noise", node)``. Every
node's state is a linear combination of roots, so:

* two parents fed by the same ancestor are EXACTLY correlated through their
  shared root (the §6.4 "full parent covariance matters" invariant — this is
  also what a Phase-3 low-rank joint ``R_D`` would consume, decision D6);
* attribution is the gain row: contributions per observed source and per
  residual state sum to the mean by construction (§6.6);
* zero reverse influence is STRUCTURAL — the pass only ever reads parent
  states, so no exposure to a target can alter a source (golden 15.2).

A node with no supported parents but a residual state predicts from the
residual alone — the D7 ghost case ``u = z``. The caller advances residual
states to the snapshot time BEFORE the pass (§10 Step 3 before Steps 4-5);
``temporal_state`` owns those dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np

from volfit.graph.message import N_HANDLES
from volfit.graph.temporal_state import _handles  # package-internal helper


class DirectedCycleError(ValueError):
    """§6.5/§13.6: the v1 directed layer requires a DAG."""


# ------------------------------------------------------------------ relations
@dataclass(frozen=True, eq=False)
class DirectedRelation:
    """One influence arc source→target (§9.3): per-handle amplitude ``beta``
    and relation precision ``precision`` (both (3,))."""

    target: str
    source: str
    beta: np.ndarray
    precision: np.ndarray
    relation_class: str = "custom"


def directed_relation(
    target: str,
    source: str,
    beta=1.0,
    precision=1.0,
    relation_class: str = "custom",
) -> DirectedRelation:
    if target == source:
        raise ValueError(f"self-relation on node {target!r}")
    b = _handles(beta, "beta")
    p = _handles(precision, "precision")
    if np.any(p <= 0.0) or not np.all(np.isfinite(p)):
        raise ValueError(f"relation precision must be finite and > 0, got {precision!r}")
    if not np.all(np.isfinite(b)):
        raise ValueError(f"beta must be finite, got {beta!r}")
    return DirectedRelation(target, source, b, p, relation_class)


@dataclass(frozen=True)
class DirectedGraph:
    """Validated DAG: ``order`` is topological (sources before targets),
    ``parents`` maps a target to its incoming relations."""

    nodes: tuple[str, ...]
    relations: tuple[DirectedRelation, ...]
    order: tuple[str, ...]
    parents: Mapping[str, tuple[DirectedRelation, ...]]


def build_directed_graph(
    nodes: Sequence[str], relations: Iterable[DirectedRelation]
) -> DirectedGraph:
    """Kahn topological sort; any remainder is a directed cycle → rejected."""
    known = set(nodes)
    if len(known) != len(nodes):
        raise ValueError("duplicate node names")
    rels = tuple(relations)
    parents: dict[str, list[DirectedRelation]] = {}
    children: dict[str, list[str]] = {}
    indegree = {n: 0 for n in nodes}
    for r in rels:
        for endpoint in (r.target, r.source):
            if endpoint not in known:
                raise ValueError(f"relation references unknown node {endpoint!r}")
        parents.setdefault(r.target, []).append(r)
        children.setdefault(r.source, []).append(r.target)
        indegree[r.target] += 1
    queue = [n for n in nodes if indegree[n] == 0]
    order: list[str] = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for child in children.get(n, ()):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(nodes):
        remaining = [n for n in nodes if indegree[n] > 0]
        raise DirectedCycleError(
            f"directed cycle among {remaining} — v1 requires a DAG (§6.5); "
            "model reciprocal relationships as harmonic relations instead"
        )
    return DirectedGraph(
        tuple(nodes), rels, tuple(order),
        {t: tuple(rs) for t, rs in parents.items()},
    )


# ------------------------------------------------------------------ the pass
def _mean_var(state) -> tuple[np.ndarray, np.ndarray]:
    """Accept (mean, variance) tuples, ObservationState, or ResidualState."""
    if isinstance(state, tuple) and len(state) == 2:
        m, v = state
    elif hasattr(state, "innovation"):
        m, v = state.innovation, state.variance
    else:
        m, v = state.mean, state.variance
    return _handles(m, "state mean"), _handles(v, "state variance", minimum=0.0)


@dataclass(frozen=True, eq=False)
class DirectedPrediction:
    """§6.2/§6.4 unary predictive distribution for a dark node, plus the
    §6.6 attribution rows (``(kind, node, contribution)``, summing to the
    mean) and diagnostics. ``q_incoming`` is None for the parentless
    residual-only (D7 ghost) case."""

    node: str
    mean: np.ndarray
    variance: np.ndarray
    systematic: np.ndarray
    residual_mean: np.ndarray
    residual_variance: np.ndarray
    q_incoming: np.ndarray | None
    parents: tuple[str, ...]
    missing_parents: tuple[str, ...]
    attribution: tuple[tuple[str, str, np.ndarray], ...]


class _NodeState:
    __slots__ = ("mean", "gains")

    def __init__(self, mean: np.ndarray, gains: dict):
        self.mean = mean
        self.gains = gains  # root key -> (3,) coefficient


class DirectedPass:
    """Result of one directed pass: per-node states (linear in the roots),
    dark-node predictions, and the §6.3 residual-measurement helper."""

    def __init__(self, graph, root_mean, root_var, states, observed,
                 predictions, unsupported):
        self.graph = graph
        self._root_mean = root_mean
        self._root_var = root_var
        self._states = states
        self.observed = observed
        self.predictions = predictions
        self.unsupported = unsupported

    def state_mean(self, node: str) -> np.ndarray:
        return self._states[node].mean

    def state_variance(self, node: str) -> np.ndarray:
        g = self._states[node].gains
        return sum((c**2 * self._root_var[k] for k, c in g.items()), np.zeros(N_HANDLES))

    def covariance(self, a: str, b: str) -> np.ndarray:
        """Exact per-handle covariance via shared roots (§6.4 / D6 input)."""
        ga, gb = self._states[a].gains, self._states[b].gains
        cov = np.zeros(N_HANDLES)
        for key, ca in ga.items():
            if key in gb:
                cov = cov + ca * gb[key] * self._root_var[key]
        return cov

    def _systematic(self, target: str):
        """Combined parent predictor: mean, gain row, and q (None if no
        supported parent). Renormalizes over SUPPORTED parents (missing ones
        carry no state) — recorded so preflight can flag them."""
        rels = self.graph.parents.get(target, ())
        supported = [r for r in rels if r.source in self._states]
        missing = tuple(r.source for r in rels if r.source not in self._states)
        if not supported:
            return np.zeros(N_HANDLES), {}, None, (), missing
        q = sum((r.precision for r in supported), np.zeros(N_HANDLES))
        mean = np.zeros(N_HANDLES)
        gains: dict = {}
        for r in supported:
            a = (r.precision / q) * r.beta
            ps = self._states[r.source]
            mean = mean + a * ps.mean
            for key, g in ps.gains.items():
                gains[key] = gains.get(key, 0.0) + a * g
        return mean, gains, q, tuple(r.source for r in supported), missing

    def residual_observation(
        self, target: str, observed_innovation, observation_variance
    ) -> tuple[np.ndarray, np.ndarray]:
        """§6.3 / §10 Step 4: the aligned residual measurement
        ``e = d − s_target`` against the CAUSAL parent states of this pass,
        with ``Var(e) = V_obs + Var(s) + 1/q``. Feed the result to
        ``ResidualState.updated_hard/updated_kalman`` — parents are read,
        never written (the cut)."""
        d = _handles(observed_innovation, "observed_innovation")
        v_obs = _handles(observation_variance, "observation_variance", minimum=0.0)
        s_mean, gains, q, _, _ = self._systematic(target)
        var_s = sum(
            (c**2 * self._root_var[k] for k, c in gains.items()), np.zeros(N_HANDLES)
        )
        var = v_obs + var_s + (0.0 if q is None else 1.0 / q)
        e = d - s_mean
        e.setflags(write=False)
        var = np.asarray(var).copy()
        var.setflags(write=False)
        return e, var


def directed_pass(
    graph: DirectedGraph,
    observations: Mapping[str, object],
    residuals: Mapping[str, object] | None = None,
) -> DirectedPass:
    """One §10 Step-5 sweep in topological order.

    ``observations``: node → (mean, variance) or ObservationState — these
    nodes are their observation (the boundary owns its value; parents of an
    observed node are only read by ``residual_observation``). ``residuals``:
    node → ResidualState or (mean, variance), ALREADY advanced to the
    snapshot time (§10 Step 3). Dark nodes with supported parents and/or a
    residual get a ``DirectedPrediction``; nodes with neither are reported
    ``unsupported`` (§7.7 — the transported prior, nothing invented)."""
    residuals = residuals or {}
    result = DirectedPass(graph, {}, {}, {}, frozenset(observations), {}, ())
    root_mean, root_var = result._root_mean, result._root_var
    states = result._states
    unsupported: list[str] = []
    ones = np.ones(N_HANDLES)

    for node in graph.order:
        if node in observations:
            m, v = _mean_var(observations[node])
            key = ("obs", node)
            root_mean[key], root_var[key] = m, v
            states[node] = _NodeState(m, {key: ones})
            continue
        s_mean, gains, q, parent_names, missing = result._systematic(node)
        res = residuals.get(node)
        if q is None and res is None:
            unsupported.append(node)  # §7.7: transported prior, nothing invented
            continue
        gains = dict(gains)
        if q is not None:
            noise_key = ("noise", node)
            root_mean[noise_key], root_var[noise_key] = np.zeros(N_HANDLES), 1.0 / q
            gains[noise_key] = ones
        if res is not None:
            r_mean, r_var = _mean_var(res)
            res_key = ("res", node)
            root_mean[res_key], root_var[res_key] = r_mean, r_var
            gains[res_key] = ones
        else:
            r_mean, r_var = np.zeros(N_HANDLES), np.zeros(N_HANDLES)
        mean = s_mean + r_mean
        state = _NodeState(mean, gains)
        states[node] = state
        variance = sum(
            (c**2 * root_var[k] for k, c in gains.items()), np.zeros(N_HANDLES)
        )
        attribution = tuple(
            (kind, name, gains[(kind, name)] * root_mean[(kind, name)])
            for (kind, name) in gains
            if kind != "noise"
        )
        result.predictions[node] = DirectedPrediction(
            node=node, mean=mean, variance=variance, systematic=s_mean,
            residual_mean=r_mean, residual_variance=r_var, q_incoming=q,
            parents=parent_names, missing_parents=missing,
            attribution=attribution,
        )
    result.unsupported = tuple(unsupported)
    return result


# ---------------------------------------------------------------- diagnostics
def residual_surprise(
    observed_innovation, observation_variance, prediction: DirectedPrediction
) -> np.ndarray:
    """§12.2: ``chi = (d − m_D) / sqrt(V_obs + V_D)`` per handle — surfaced,
    never used to silently contaminate the source (§6.3)."""
    d = _handles(observed_innovation, "observed_innovation")
    v = _handles(observation_variance, "observation_variance", minimum=0.0)
    return (d - prediction.mean) / np.sqrt(v + prediction.variance)

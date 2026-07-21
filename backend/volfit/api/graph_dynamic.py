"""Layered dynamic-harmonic production solve (framework §10, Phase 4).

The ``propagationMode="layered_dynamic_harmonic"`` counterpart of
``graph_message.solve_message_field`` — same seam, same consumers:

    transported prior -> timestamped calibration innovations
        -> residual advance (§10 Step 3, temporal_state)
        -> directed source-to-target pass (§10 Step 5, directed_state)
        -> reciprocal beta-harmonic completion (§10 Step 6, harmonic_posterior)
        -> HandleField for the existing reconstruction/band/attribution layers

Relation semantics (§9.2): rows carry ``relationSemantics``; None applies the
class default — calendar / sector_peer / custom are reciprocal_harmonic
(custom conservatively matches today's pairwise factor), broad_index /
sector_etf are directed_state. AUTO relations are all reciprocal — directed
arcs are always an explicit configuration. Directed cycles are rejected
(§6.5); model reciprocity as harmonic relations instead.

Boundary policy (§4.2 v1): a lit calibration whose data age is within
``clampMaxAgeDays`` is a hard Dirichlet boundary (central value clamped, its
§15.2 combined uncertainty widens dependents through the §7.4 Omega);
older observations demote to soft unary anchors. Directed predictions enter
the harmonic layer as unary anchors (D6 v1: diagonal — the joint low-rank
form is wired in harmonic_posterior and adjudicated in Phase 5).

Persistent residual state (§13.5): ``residual_store`` maps node name ->
ResidualState. Certified target observations update it (hard update, D3)
via the CUT measurement — parents are never written. The store is stamped
with a config version; changed relations invalidate affected residuals
(golden 15.13). What-if pulses and holdout solves never touch the store.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from volfit.api.graph_message import (
    DISCONNECTED_Z_SD,
    MessageDiagnostics,
    auto_message_edges,
    message_edges_from_schema,
)
from volfit.graph.directed_state import (
    DirectedRelation,
    build_directed_graph,
    directed_pass,
    directed_relation,
)
from volfit.graph.harmonic_posterior import harmonic_posterior
from volfit.graph.message import HANDLE_PRECISION_SCALE, MessageEdge
from volfit.graph.message_posterior import MessagePosterior
from volfit.graph.smile_universe import HandleField, N_HANDLES
from volfit.graph.temporal_state import (
    empty_residual,
    residual_dynamics,
    reuse_or_invalidate,
)

#: §9.2 class defaults when a row carries no explicit relationSemantics.
SEMANTICS_BY_CLASS = {
    "calendar": "reciprocal_harmonic",
    "sector_peer": "reciprocal_harmonic",
    "custom": "reciprocal_harmonic",
    "broad_index": "directed_state",
    "sector_etf": "directed_state",
}


def row_semantics(row) -> str:
    return row.relationSemantics or SEMANTICS_BY_CLASS[row.relationClass]


def _config_version(directed, request) -> str:
    """Golden 15.13: the residual state is defined under one relation config.
    Betas, precisions, topology, and the temporal law are all part of it."""
    payload = {
        "directed": sorted(
            (str(r.target), str(r.source), tuple(r.beta), tuple(r.precision))
            for r in directed
        ),
        "halfLife": request.residualHalfLifeDays,
    }
    return hashlib.sha1(json.dumps(payload, default=str).encode()).hexdigest()[:12]


def _directed_from_rows(rows, request) -> list[DirectedRelation]:
    out = []
    for row in rows:
        scale = tuple(row.messagePrecision * s for s in HANDLE_PRECISION_SCALE)
        out.append(
            directed_relation(
                target=(row.targetTicker, row.targetExpiry),
                source=(row.sourceTicker, row.sourceExpiry),
                beta=(row.betaAtmVol, row.betaSkew, row.betaCurv),
                precision=scale,
                relation_class=row.relationClass,
            )
        )
    return out


def _scaled_edges(edges, handle: int) -> list[MessageEdge]:
    """Apply the §9.4 per-handle precision units for the harmonic layer (the
    message operator does this internally; the BVP solver takes raw rows)."""
    s = HANDLE_PRECISION_SCALE[handle]
    return [
        MessageEdge(e.receiver, e.informer, e.precision * s, e.beta, e.relation_class)
        for e in edges
    ]


def solve_dynamic_field(
    universe,
    t_by_node,
    request,
    baseline: np.ndarray,
    baseline_precision: np.ndarray,
    obs_idx: np.ndarray,
    obs_values: np.ndarray,
    obs_precision: np.ndarray,
    persisted_edges=None,
    firm_observations: bool = False,
    obs_age_days: np.ndarray | None = None,
    residual_store: dict | None = None,
    now_day: float = 0.0,
) -> tuple[HandleField, MessageDiagnostics]:
    """The §10 Steps 2-6 production solve for one snapshot.

    Same contract as ``solve_message_field``: absolute handle field out,
    baseline noise combined per §15.2, §15.3 band placement. ``obs_age_days``
    is per-observation data age (None = fresh); ``residual_store`` is the
    persistent §13.5 state (None = stateless solve, nothing recorded)."""
    names = list(universe.names)
    index = {n: i for i, n in enumerate(names)}
    rows = list(request.messageEdges) or list(persisted_edges or [])
    if rows:
        directed_rows = [r for r in rows if row_semantics(r) == "directed_state"]
        reciprocal_rows = [r for r in rows if row_semantics(r) == "reciprocal_harmonic"]
        reciprocal = (
            message_edges_from_schema(reciprocal_rows, t_by_node, request)
            if reciprocal_rows
            else []
        )
        directed = [
            r for r in _directed_from_rows(directed_rows, request)
            if r.target in index and r.source in index
        ]
    else:  # auto relations are ALL reciprocal — directed arcs are explicit
        reciprocal = auto_message_edges(universe, t_by_node, request)
        directed = []
    reciprocal = [
        e for e in reciprocal if e.receiver in index and e.informer in index
    ]
    dag = build_directed_graph(names, directed)  # rejects directed cycles

    # §15.2 combined innovation observation precision (mirrors message mode).
    d = obs_values - baseline[obs_idx] if obs_idx.size else obs_values
    if firm_observations or not obs_idx.size:
        r_d = obs_precision
    else:
        r_d = 1.0 / (1.0 / obs_precision + 1.0 / baseline_precision[obs_idx])

    # §4.2 boundary certification: fresh within the clamp window -> Dirichlet.
    ages = (
        np.zeros(obs_idx.size)
        if obs_age_days is None
        else np.asarray(obs_age_days, dtype=float)
    )
    certified = ages <= float(request.clampMaxAgeDays)

    # §10 Step 3: advance persisted residuals under the CURRENT config.
    config_version = _config_version(directed, request)
    dynamics = residual_dynamics(
        half_life=(request.residualHalfLifeDays or math.inf),
        v_inf=np.asarray(DISCONNECTED_Z_SD, dtype=float) ** 2,
    )
    residuals = {}
    if residual_store:
        for name in list(residual_store):
            kept, invalidated = reuse_or_invalidate(
                residual_store[name], config_version
            )
            if invalidated:
                del residual_store[name]  # golden 15.13: never silently reused
            elif name in index:
                residuals[name] = kept.advance(now_day, dynamics)

    # §10 Step 5: the directed pass (observed nodes are their observation).
    observations = {
        names[int(i)]: (d[k], 1.0 / r_d[k]) for k, i in enumerate(obs_idx)
    }
    dpass = directed_pass(dag, observations, residuals)

    obs_pos = {int(i): k for k, i in enumerate(obs_idx)}
    cert_idx = [int(i) for k, i in enumerate(obs_idx) if certified[k]]

    # A STALE observed node keeps its role as a source, but its own mark must
    # compete with the systematic prediction from its parents (§4.2 class 3).
    # residual_observation with zero obs variance returns (d − s, Var(s)+1/q),
    # from which the prediction (s + m_u, Var(s)+1/q+V_u) is reconstructed.
    stale_predictions: dict = {}
    for k, i in enumerate(obs_idx):
        name = names[int(i)]
        if certified[k] or (
            not dag.parents.get(name) and name not in residuals
        ):
            continue
        e, var_e = dpass.residual_observation(name, d[k], 0.0)
        res = residuals.get(name)
        p_mean = (d[k] - e) + (res.mean if res is not None else 0.0)
        p_var = var_e + (res.variance if res is not None else 0.0)
        stale_predictions[name] = (p_mean, np.maximum(p_var, 1e-18))
    mean = np.empty((len(names), N_HANDLES))
    var = np.empty((len(names), N_HANDLES))
    posteriors = []
    for c in range(N_HANDLES):
        boundary = {names[i]: float(d[obs_pos[i], c]) for i in cert_idx}
        boundary_var = {
            names[i]: float(1.0 / r_d[obs_pos[i], c]) for i in cert_idx
        }
        unary: dict = {}
        for k, i in enumerate(obs_idx):  # aged soft observations (§4.2 class 3)
            if not certified[k]:
                unary[names[int(i)]] = (float(d[k, c]), float(1.0 / r_d[k, c]))
        anchors = {
            name: (float(p.mean[c]), float(p.variance[c]))
            for name, p in dpass.predictions.items()
        }
        anchors.update(
            (name, (float(m[c]), float(v[c])))
            for name, (m, v) in stale_predictions.items()
        )
        for name, anchor in anchors.items():  # §7.5 unary anchoring
            if name in unary:  # both a stale reading and a prediction: combine
                m0, v0 = unary[name]
                w = 1.0 / v0 + 1.0 / anchor[1]
                unary[name] = ((m0 / v0 + anchor[0] / anchor[1]) / w, 1.0 / w)
            elif name not in boundary:
                unary[name] = anchor
        post = harmonic_posterior(
            names,
            _scaled_edges(reciprocal, c),
            boundary,
            handle=c,
            boundary_variance=boundary_var,
            unary=unary,
            no_support_variance=float(DISCONNECTED_Z_SD[c]) ** 2,
        )
        mean[:, c] = baseline[:, c] + post.mean
        v = post.variance.copy()
        unobserved = np.ones(len(names), dtype=bool)
        unobserved[obs_idx] = False  # §15.3: baseline noise once, at the band
        v[unobserved] += 1.0 / baseline_precision[unobserved, c]
        var[:, c] = v
        gain = np.zeros((len(names), obs_idx.size))
        for col, (kind, node) in enumerate(post.sources):
            if kind == "boundary":
                gain[:, obs_pos[index[node]]] = post.gain[:, col]
        posteriors.append(
            MessagePosterior(
                mean=post.mean,
                marginal_variance=post.variance,
                observed=obs_idx.astype(int),
                innovations=d[:, c],
                innovation_precision=r_d[:, c],
                gain=gain,
                posterior_covariance=post.posterior_covariance,
                no_lit_path=post.no_active_observation_path,
                component=post.component,
            )
        )

    # §10 Step 4 + Step 8: certified target observations update the residual
    # store through the CUT measurement; predictions never persist.
    if residual_store is not None and not firm_observations:
        for k, i in enumerate(obs_idx):
            if not certified[k]:
                continue
            name = names[int(i)]
            e, var_e = dpass.residual_observation(name, d[k], 1.0 / r_d[k])
            prev = residuals.get(name, empty_residual(config_version))
            residual_store[name] = prev.updated_hard(
                e, var_e, now_day, f"cal:{name[0]}:{name[1]}:{now_day}"
            )

    diagnostics = MessageDiagnostics(
        mode=request.propagationMode,
        q_incoming=None,
        no_lit_path=posteriors[0].no_lit_path,
        cycle_flags=(),
    )
    return HandleField(mean=mean, sd=np.sqrt(var), posteriors=tuple(posteriors)), diagnostics

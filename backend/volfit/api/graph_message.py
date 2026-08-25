"""Production assembly for the precision-message propagation mode (arc P3).

Spec: Docs/graph_precision_message_framework.md §18-19. This module turns a
production request into the message-operator solve, reusing everything the
smooth-field path already computes (selected universe, transported priors,
lit innovations, data-derived precisions) and returning the same
``HandleField`` seam the reconstruction/band/attribution layers consume.

Responsibilities:

* auto relation set (§3.4 under v2 semantics): one calendar factor per
  adjacent selected expiry pair per ticker (canonical receiver = shorter
  maturity, §9.2 distance-rule precision) + one beta-one cross factor per
  same-expiry ticker pair (constant precision, lexicographic orientation —
  orientation-neutral at beta one);
* schema-v2 edge expansion (``GraphMessageEdge``, source=informer →
  target=receiver) and the EXPLICIT legacy-import conversion (§18.3);
* §15.2 innovation observation precision: ``r_d = (1/r_cal + 1/p0)^{-1}`` on
  lit nodes — baseline uncertainty enters HERE for observed nodes and only
  in the reconstruction band for the rest (§15.3 placement rule);
* the per-handle operator/posterior solve with the §14.2 node-linked anchor
  (amplitude multipliers) and §16.4 cycle diagnostics.

Stateless by design: the caller (graph_extrapolation.solve) passes the
persisted edge rules and any hybrid extra term in, so unit tests drive this
module with hand-built universes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.api.graph_params import GRAPH_PRIOR_HYPER
from volfit.api.graph_universe import SelectedUniverse
from volfit.api.schemas import GraphEdgeInput, GraphMessageEdge
from volfit.graph.build import NodeId
from volfit.graph.message import (
    MessageEdge,
    anchor_precisions,
    build_message_operator,
    calendar_beta,
    calendar_message_precision,
    cross_expiry_precision,
    cycle_beta_products,
    expand_calendar_ladder,
)
from volfit.graph.message_posterior import message_posterior_update
from volfit.graph.smile_universe import HandleField, N_HANDLES

#: §14.3 disconnected (no-lit-path) innovation sd per handle — the legacy
#: prior's own per-handle scale s (GRAPH_PRIOR_HYPER), i.e. "one typical
#: handle magnitude": explicitly broad, never artificially precise.
DISCONNECTED_Z_SD = tuple(s for s, _eta in GRAPH_PRIOR_HYPER)


@dataclass(frozen=True)
class MessageDiagnostics:
    """Message-mode wire diagnostics (§17): the ATM receiver conditional
    incoming precisions q_i, the §14.3 no-lit-path mask, and the §16.4
    inconsistent-cycle flags ((receiver, informer, beta product); the product
    is NaN for a nonpositive beta)."""

    mode: str
    q_incoming: np.ndarray
    no_lit_path: np.ndarray
    cycle_flags: tuple[tuple[NodeId, NodeId, float], ...]


# ------------------------------------------------------------ edge assembly
def calendar_policy_for(request, ticker: str) -> tuple[bool, float, float]:
    """Effective per-ticker calendar policy ``(enabled, scale, alpha)``.

    U2 policy resolution: the global ``calendarEnabled`` switch gates
    everything; a ``calendarPolicyOverrides[ticker]`` entry refines enable /
    §9.2 precision scale / §8.1 shape exponent for that ticker, unset fields
    inheriting the request-level dials. ``getattr`` defaults keep hand-built
    test requests (pre-U2 shape) valid."""
    override = getattr(request, "calendarPolicyOverrides", {}).get(ticker)
    enabled = bool(getattr(request, "calendarEnabled", True)) and (
        override is None or override.enabled
    )
    scale = request.calendarPrecisionScale
    alpha = request.calendarBetaExponent
    if override is not None and override.precisionScale is not None:
        scale = override.precisionScale
    if override is not None and override.betaExponent is not None:
        alpha = override.betaExponent
    return enabled, scale, alpha


def auto_message_edges(
    universe: SelectedUniverse, t_by_node: dict[NodeId, float], request
) -> list[MessageEdge]:
    """The default relation set over the selected universe.

    Calendar: adjacent selected expiries per ticker, one factor per pair in
    canonical short-receiver orientation (§7.6), precision from the §9.2
    distance family under the ticker's effective policy (U2: global enable +
    per-ticker overrides). Nodes with a non-positive year fraction get no
    calendar factor (an expired receiver has no maturity shape). Cross:
    same-expiry ticker pairs, one beta-one factor each (lexicographic
    orientation, class ``custom``, constant ``crossPrecisionScale``). With
    ``crossExpiryToleranceDays`` > 0 an asynchronous cross-venue rung (no
    same-date partner) is also paired with the other ticker's NEAREST expiry
    within tolerance: canonical short-receiver orientation, precision =
    ``crossPrecisionScale`` decayed by the |dT| family (normalized to the
    synchronous value at zero gap), beta = the §8.1 maturity-shape amplitude
    ``(T_informer / T_receiver)^alphaT`` on every handle — the composite a
    cross-maturity relation needs, where the same-expiry pair could hardcode
    beta one."""
    edges: list[MessageEdge] = []
    ladders: dict[str, dict[NodeId, float]] = {}
    by_iso: dict[str, list[NodeId]] = {}
    for node in universe.nodes:
        t = t_by_node[node.name]
        if t > 0.0:
            ladders.setdefault(node.ticker, {})[node.name] = t
        by_iso.setdefault(node.expiry, []).append(node.name)

    for ticker, maturities in ladders.items():
        enabled, scale, alpha = calendar_policy_for(request, ticker)
        if enabled and len(maturities) >= 2:
            edges.extend(
                expand_calendar_ladder(
                    maturities,
                    alpha=alpha,
                    scale=scale,
                    epsilon=request.calendarPrecisionEpsilon,
                    rule=request.calendarPrecisionDecay,
                )
            )
    for names in by_iso.values():
        names = sorted(names)
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                edges.append(
                    MessageEdge(
                        names[a], names[b], request.crossPrecisionScale,
                        (1.0, 1.0, 1.0), "custom",
                    )
                )
    edges.extend(_cross_expiry_message_edges(ladders, request))
    return edges


def _cross_expiry_message_edges(
    ladders: dict[str, dict[NodeId, float]], request
) -> list[MessageEdge]:
    """Nearest-expiry cross factors for asynchronous cross-venue rungs.

    Pairing mirrors ``graph_params.nearest_cross_expiry_pairs`` but runs on
    the maturities the message operator already carries (year fractions, so
    the tolerance converts at ACT/365). Empty at the default tolerance 0 —
    the auto relation set is then byte-identical to the historical one.
    ``getattr`` default keeps hand-built test requests (pre-field shape) valid.
    """
    tol_years = float(getattr(request, "crossExpiryToleranceDays", 0.0)) / 365.0
    if tol_years <= 0.0:
        return []
    alpha = float(getattr(request, "calendarBetaExponent", 1.0))
    tickers = sorted(ladders)
    pairs: set[tuple[NodeId, NodeId]] = set()
    for i, a in enumerate(tickers):
        for b in tickers[i + 1 :]:
            la, lb = ladders[a], ladders[b]
            shared = {n[1] for n in la} & {n[1] for n in lb}
            for lx, ly, flip in ((la, lb, False), (lb, la, True)):
                for node, t in lx.items():
                    if node[1] in shared:
                        continue
                    other, t_other = min(ly.items(), key=lambda kv: abs(kv[1] - t))
                    if abs(t_other - t) <= tol_years:
                        pairs.add((other, node) if flip else (node, other))
    edges: list[MessageEdge] = []
    for node_a, node_b in sorted(pairs):
        t_a, t_b = ladders[node_a[0]][node_a], ladders[node_b[0]][node_b]
        # Canonical receiver = the shorter maturity (§7.6), like calendar.
        recv, t_r, inf, t_i = (
            (node_a, t_a, node_b, t_b) if t_a <= t_b else (node_b, t_b, node_a, t_a)
        )
        p = cross_expiry_precision(
            t_r,
            t_i,
            scale=request.crossPrecisionScale,
            epsilon=request.calendarPrecisionEpsilon,
            rule=request.calendarPrecisionDecay,
        )
        beta = calendar_beta(t_r, t_i, alpha)
        edges.append(MessageEdge(recv, inf, p, (beta, beta, beta), "custom"))
    return edges


def message_edges_from_schema(
    rows: list[GraphMessageEdge], t_by_node: dict[NodeId, float], request
) -> list[MessageEdge]:
    """Expand schema-v2 rows into engine factors. Rows naming a node outside
    the selected universe are dropped (the legacy edge-list contract);
    ``calendar_distance`` rows derive their precision from the §9.2 family
    under the RECEIVER ticker's effective policy, and a policy-disabled
    ticker (U2) suppresses its calendar-class rows entirely — persisted rows
    included (the switch is a policy, not a row edit)."""
    out: list[MessageEdge] = []
    for e in rows:
        receiver = (e.targetTicker, e.targetExpiry)
        informer = (e.sourceTicker, e.sourceExpiry)
        if receiver == informer:
            continue
        if receiver not in t_by_node or informer not in t_by_node:
            continue
        enabled, scale, _alpha = calendar_policy_for(request, e.targetTicker)
        if e.relationClass == "calendar" and not enabled:
            continue
        if e.precisionRule == "calendar_distance":
            p = calendar_message_precision(
                t_by_node[receiver],
                t_by_node[informer],
                scale=scale,
                epsilon=request.calendarPrecisionEpsilon,
                rule=request.calendarPrecisionDecay,
            )
        else:
            p = e.messagePrecision
        out.append(
            MessageEdge(
                receiver, informer, p,
                (e.betaAtmVol, e.betaSkew, e.betaCurv), e.relationClass,
            )
        )
    return out


def message_edges_from_legacy(
    edges: list[GraphEdgeInput], precision_per_weight: float
) -> list[GraphMessageEdge]:
    """EXPLICIT one-shot import of a legacy smooth-field edge list (§18.3) —
    never applied silently; the legacy blob itself round-trips untouched.

    Engine truth (build.py ``W[from][to]`` with "j informs i"): the ``to``
    endpoint INFORMS the ``from`` endpoint. So target/receiver = legacy
    ``from`` and source/informer = legacy ``to`` — the labels invert, the
    economics do not (test-locked). Precision = weight × the caller-chosen
    ``precision_per_weight``: legacy weight is a relative trust, not a
    precision, so there is no canonical map and the rule stays explicit."""
    return [
        GraphMessageEdge(
            sourceTicker=e.toTicker,
            sourceExpiry=e.toExpiry,
            targetTicker=e.fromTicker,
            targetExpiry=e.fromExpiry,
            messagePrecision=e.weight * precision_per_weight,
            betaAtmVol=e.betaAtmVol,
            betaSkew=e.betaSkew,
            betaCurv=e.betaCurv,
        )
        for e in edges
        if e.weight > 0.0
    ]


def _amplitude_rho(request) -> dict[str, float]:
    """§8.4 per-class amplitude multipliers: calendar has its own dial, every
    cross class shares ``crossAmplitude`` in v1."""
    rho = {cls: request.crossAmplitude
           for cls in ("broad_index", "sector_etf", "sector_peer", "custom")}
    rho["calendar"] = request.calendarAmplitude
    return rho


def auto_message_edge_rows(state) -> list[GraphMessageEdge]:
    """The auto relations over the CURRENT selected universe as editable
    schema rows — the message editor's "seed from auto relations"
    (GET /graph/edges/messages/auto). Calendar rows keep
    ``precisionRule="calendar_distance"`` (inherited semantics: the shown
    precision is today's derived value and re-derives on save); cross rows
    are explicit at the default scale."""
    from volfit.api.graph_extrapolation import _node_t
    from volfit.api.graph_universe import build_selected_universe
    from volfit.api.schemas import GraphExtrapolateRequest

    request = GraphExtrapolateRequest()
    universe = build_selected_universe(state)
    if universe.graph is None:
        return []
    t_by = {node.name: _node_t(state, node.expiry) for node in universe.nodes}
    return [
        GraphMessageEdge(
            sourceTicker=e.informer[0],
            sourceExpiry=e.informer[1],
            targetTicker=e.receiver[0],
            targetExpiry=e.receiver[1],
            messagePrecision=e.precision,
            betaAtmVol=e.beta[0],
            betaSkew=e.beta[1],
            betaCurv=e.beta[2],
            relationClass=e.relation_class,
            precisionRule=(
                "calendar_distance" if e.relation_class == "calendar" else "explicit"
            ),
        )
        for e in auto_message_edges(universe, t_by, request)
    ]


# ------------------------------------------------------------------- solve
def solve_message_field(
    universe: SelectedUniverse,
    t_by_node: dict[NodeId, float],
    request,
    baseline: np.ndarray,
    baseline_precision: np.ndarray,
    obs_idx: np.ndarray,
    obs_values: np.ndarray,
    obs_precision: np.ndarray,
    persisted_edges: list[GraphMessageEdge] | None = None,
    hybrid_extra: list[np.ndarray] | None = None,
    firm_observations: bool = False,
) -> tuple[HandleField, MessageDiagnostics]:
    """The message-mode counterpart of ``_propagate_field`` (§15).

    ``baseline``/``baseline_precision`` are the transported priors and their
    precisions (N, 3); ``obs_*`` are the lit calibrations (absolute handles)
    with their calibration-only precisions. Edge precedence mirrors the
    legacy path: request.messageEdges → persisted rules → auto relations.
    ``firm_observations`` (U3 what-if pulses) skips the §15.2 baseline
    combination — a typed hypothesis carries no baseline noise, so its
    innovation is observed at the raw pulse precision. Returns the ABSOLUTE
    handle field (baseline + posterior innovation) plus the wire
    diagnostics."""
    names = list(universe.names)
    rows = list(request.messageEdges) or list(persisted_edges or []) or None
    edges = (
        message_edges_from_schema(rows, t_by_node, request)
        if rows
        else auto_message_edges(universe, t_by_node, request)
    )

    # §15.2 combined innovation observation precision (lit nodes only);
    # firm (what-if) observations keep their raw pulse precision.
    d = obs_values - baseline[obs_idx] if obs_idx.size else obs_values
    if firm_observations or not obs_idx.size:
        r_d = obs_precision
    else:
        p0_obs = baseline_precision[obs_idx]
        r_d = 1.0 / (1.0 / obs_precision + 1.0 / p0_obs)

    rho = _amplitude_rho(request)
    mean = np.empty((len(names), N_HANDLES))
    sd = np.empty((len(names), N_HANDLES))
    posteriors = []
    q_incoming = None
    for c in range(N_HANDLES):
        op = build_message_operator(names, edges, handle=c)
        if request.innovationAnchorPrecision is not None:
            kappa = np.full(len(names), float(request.innovationAnchorPrecision))
        else:
            kappa = anchor_precisions(names, edges, rho, handle=c)
        post = message_posterior_update(
            op,
            obs_idx,
            d[:, c],
            r_d[:, c],
            anchor_precision=kappa,
            extra_precision=None if hybrid_extra is None else hybrid_extra[c],
            no_lit_variance=DISCONNECTED_Z_SD[c] ** 2,
        )
        posteriors.append(post)
        mean[:, c] = baseline[:, c] + post.mean
        # §15.3 placement: observed nodes carry baseline uncertainty inside
        # r_d (above); everyone else adds it to the reconstruction band once.
        var = post.marginal_variance.copy()
        unobserved = np.ones(len(names), dtype=bool)
        unobserved[obs_idx] = False
        var[unobserved] += 1.0 / baseline_precision[unobserved, c]
        sd[:, c] = np.sqrt(var)
        if c == 0:
            q_incoming = op.receiver_precision

    cycles = tuple(
        (
            flag.receiver, flag.informer, flag.product,
        )
        for flag in cycle_beta_products(
            names, edges, handle=0, tol=request.cycleBetaTolerance
        )
    )
    diagnostics = MessageDiagnostics(
        mode=request.propagationMode,
        q_incoming=q_incoming,
        no_lit_path=posteriors[0].no_lit_path,
        cycle_flags=cycles,
    )
    return HandleField(mean=mean, sd=sd, posteriors=tuple(posteriors)), diagnostics

"""Production graph smile-extrapolation service (plan Phases 1-6).

This is the *production* counterpart to ``volfit.api.graph_service`` (which
stays the manual-shift sandbox, plan Amendment A). The two never share an
endpoint or semantics:

    transported prior -> lit calibration innovation -> graph posterior increment
                      -> dark reconstructed smile    -> quote comparison

Phase 1 (this commit) builds the graph over the **user-selected lit+dark
universe only** (plan Amendment C): the product boundary is the universe the
user picked, not every node the provider happens to expose. Later phases attach
transported-prior baselines (Phase 2), the lit-calibration innovation feed and
the solve (Phase 3), data-derived precision (Phase 4), reconstructed smiles +
quote metrics (Phase 5) and per-edge beta (Phase 6).

The lattice topology (calendar chains within a ticker + cross-ticker same-expiry
edges) reuses the sandbox's ``_lattice_weights`` helper restricted to the
selected node set, so both paths build edges identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from volfit.api.graph_service import (
    CROSS_TICKER_WEIGHT,
    GRAPH_PRECISION,
    SAME_TICKER_WEIGHT,
    _build_priors,
    _lattice_weights,
)
from volfit.api.schemas import (
    GraphExtrapolateNode,
    GraphExtrapolateRequest,
    GraphExtrapolateResponse,
)
from volfit.api.service import fit_or_get
from volfit.api.state import AppState
from volfit.graph.build import NodeId, SmileGraph, build_graph
from volfit.graph.posterior import posterior_update
from volfit.graph.smile_universe import HandleField, N_HANDLES
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.quadrature import build_slice


@dataclass(frozen=True)
class SelectedNode:
    """One node of the selected production universe: ``(ticker, expiry-ISO)``
    plus its lit/dark designation (lit = a calibration observation; dark = an
    extrapolation target whose quotes, if any, are used only for validation)."""

    ticker: str
    expiry: str  # ISO date
    lit: bool

    @property
    def name(self) -> NodeId:
        return (self.ticker, self.expiry)


@dataclass(frozen=True)
class SelectedUniverse:
    """The production graph built over the selected lit+dark nodes only.

    Carries the node list (with lit/dark flags) and the prepared ``SmileGraph``
    topology. Deliberately separate from the sandbox ``SmileUniverse`` so the
    two paths never couple; later phases hang per-node prior/precision and
    reconstruction off the same node ordering. ``graph`` is ``None`` for an
    empty selection (a degenerate graph cannot be built, plan Phase 1 test).
    """

    nodes: tuple[SelectedNode, ...]
    graph: SmileGraph | None

    @property
    def names(self) -> tuple[NodeId, ...]:
        """Node names in graph order ``(ticker, expiry-ISO)``."""
        return tuple(node.name for node in self.nodes)

    @property
    def lit_names(self) -> tuple[NodeId, ...]:
        return tuple(node.name for node in self.nodes if node.lit)

    @property
    def dark_names(self) -> tuple[NodeId, ...]:
        return tuple(node.name for node in self.nodes if not node.lit)

    def node_index(self, name: NodeId) -> int:
        if self.graph is None:
            raise KeyError(name)
        return self.graph.index[name]


def _selected_ladders(state: AppState) -> dict[str, list[str]]:
    """``{ticker: [expiry-ISO, ...]}`` over the active tickers' SELECTED
    expiries only (cheap selection metadata — no chain fetch, no fit). Empty
    ladders are dropped so a ticker with no resolved selection adds no nodes."""
    ladders: dict[str, list[str]] = {}
    for ticker in state.active_tickers():
        isos = [expiry.isoformat() for expiry in sorted(state.selected_expiries(ticker))]
        if isos:
            ladders[ticker] = isos
    return ladders


def build_selected_universe(
    state: AppState,
    calendar_weight: float | None = None,
    cross_weight: float | None = None,
) -> SelectedUniverse:
    """Build the production graph over the selected lit+dark universe.

    Nodes = every active ticker x its selected expiries (lit/dark read from
    ``state.node_lit``); edges = the lattice (calendar chains + cross-ticker
    same-expiry) restricted to that node set, with optional ``calendar_weight`` /
    ``cross_weight`` overrides (null keeps the service defaults). Unselected
    provider expiries are never included (plan Amendment C). An empty selection
    yields an empty universe with ``graph=None`` rather than crashing.
    """
    ladders = _selected_ladders(state)
    nodes: list[SelectedNode] = []
    for ticker, isos in ladders.items():
        for iso in isos:
            nodes.append(SelectedNode(ticker, iso, lit=state.node_lit(ticker, iso)))

    if not nodes:
        return SelectedUniverse(nodes=(), graph=None)

    calendar_w = SAME_TICKER_WEIGHT if calendar_weight is None else calendar_weight
    cross_w = CROSS_TICKER_WEIGHT if cross_weight is None else cross_weight
    weights = _lattice_weights(list(ladders), ladders, calendar_w, cross_w)
    graph = build_graph([node.name for node in nodes], weights)
    return SelectedUniverse(nodes=tuple(nodes), graph=graph)


# ----------------------------------------------- Phase 3: lit-innovation solve
def _calibrated_handles(state: AppState, ticker: str, iso: str, fit_mode: str):
    """ATM handles ``(sigma0, skew, curvature)`` of a lit node's CALIBRATED slice
    (LQD backbone, the carrier), in the node's variance clock — or None if the
    node has no calibration yet (gated workflow before Calibrate)."""
    record = fit_or_get(state, ticker, iso, fit_mode)
    if record is None:
        return None
    h = atm_handles(build_slice(record.result.params), record.prepared.tau)
    return np.array([h.sigma0, h.skew, h.curvature])


def _node_t(state: AppState, iso: str) -> float:
    """A display calendar year-fraction for a node from its ISO expiry (works for
    dark, uncalibrated nodes that have no prepared slice)."""
    try:
        days = (date.fromisoformat(iso) - state.reference_date).days
    except ValueError:
        return 0.0
    return max(days, 0) / 365.25


def _propagate_field(
    graph: SmileGraph,
    priors,
    baseline: np.ndarray,
    baseline_precision: np.ndarray,
    obs_idx: np.ndarray,
    obs_values: np.ndarray,
    obs_precision: np.ndarray,
) -> HandleField:
    """Per-coordinate Gaussian posterior with an EXPLICIT prior baseline.

    Unlike the sandbox ``propagate_handles`` (which centres on today's mid fit),
    the baseline here is the transported prior, so ``posterior_update``'s
    innovation ``y - baseline`` is exactly the lit-calibration innovation
    ``d = calibrated - transported_prior``. Zero observations is the no-signal
    predictive prior (mean = baseline, prior marginal variance)."""
    n = graph.n_nodes
    mean = np.empty((n, N_HANDLES))
    sd = np.empty((n, N_HANDLES))
    posteriors = []
    for c in range(N_HANDLES):
        if obs_idx.size == 0:
            k_minus = 1.0 / baseline_precision[:, c] + np.diag(priors[c].covariance)
            mean[:, c] = baseline[:, c]
            sd[:, c] = np.sqrt(k_minus)
            posteriors.append(None)
            continue
        post = posterior_update(
            priors[c],
            baseline=baseline[:, c],
            baseline_precision=baseline_precision[:, c],
            observed=obs_idx,
            observations=obs_values[:, c],
            observation_precision=obs_precision[:, c],
        )
        posteriors.append(post)
        mean[:, c] = post.mean
        sd[:, c] = np.sqrt(post.marginal_variance)
    return HandleField(mean=mean, sd=sd, posteriors=tuple(posteriors))


def extrapolate(
    state: AppState, request: GraphExtrapolateRequest
) -> GraphExtrapolateResponse:
    """Production prior-anchored extrapolation (plan Phase 3, Amendment A).

    transported prior baselines -> lit-calibration innovations -> graph posterior
    increment -> per-node posterior ATM handles + credible bands. Dark nodes are
    never observations; they only receive propagation.
    """
    # Local import avoids a module-load cycle (graph_nodes imports us for typing).
    from volfit.api.graph_nodes import resolve_priors

    universe = build_selected_universe(state, request.calendarWeight, request.crossWeight)
    if universe.graph is None:
        return GraphExtrapolateResponse(nodes=[])

    fit_mode = state.last_fit_mode
    priors_meta = resolve_priors(state, universe, flat_atm=request.flatAtm)
    baseline = np.vstack([p.handles for p in priors_meta])
    baseline_precision = np.vstack([p.precision for p in priors_meta])

    # Lit nodes with a calibration become observations; dark nodes never do.
    obs_idx_list: list[int] = []
    obs_values_list: list[np.ndarray] = []
    calibrated = [False] * len(universe.nodes)
    for i, node in enumerate(universe.nodes):
        if not node.lit:
            continue
        y = _calibrated_handles(state, node.ticker, node.expiry, fit_mode)
        if y is None:
            continue
        calibrated[i] = True
        obs_idx_list.append(i)
        obs_values_list.append(y)

    obs_idx = np.asarray(obs_idx_list, dtype=int)
    obs_values = (
        np.vstack(obs_values_list) if obs_values_list else np.empty((0, N_HANDLES))
    )
    obs_precision = np.broadcast_to(GRAPH_PRECISION, (obs_idx.size, N_HANDLES))

    increment_priors = _build_priors(universe.graph, request)
    field = _propagate_field(
        universe.graph,
        increment_priors,
        baseline,
        baseline_precision,
        obs_idx,
        obs_values,
        obs_precision,
    )
    band_lo, band_hi = field.atm_vol_band()

    obs_value_by_idx = dict(zip(obs_idx_list, obs_values_list))
    nodes = []
    for i, node in enumerate(universe.nodes):
        meta = priors_meta[i]
        prior_h = meta.handles
        post_h = field.mean[i]
        innovation_bp = None
        if i in obs_value_by_idx:
            innovation_bp = float((obs_value_by_idx[i][0] - prior_h[0]) * 1e4)
        nodes.append(
            GraphExtrapolateNode(
                ticker=node.ticker,
                expiry=node.expiry,
                t=_node_t(state, node.expiry),
                lit=node.lit,
                calibrated=calibrated[i],
                priorSource=meta.source,
                priorAsOf=meta.as_of,
                transportDistance=meta.transport_distance,
                validForValidation=meta.valid_for_validation,
                priorAtmVol=float(prior_h[0]),
                priorSkew=float(prior_h[1]),
                priorCurv=float(prior_h[2]),
                postAtmVol=float(post_h[0]),
                postSkew=float(post_h[1]),
                postCurv=float(post_h[2]),
                shiftBp=float((post_h[0] - prior_h[0]) * 1e4),
                sd=float(field.sd[i, 0]),
                bandLo=float(band_lo[i]),
                bandHi=float(band_hi[i]),
                innovationBp=innovation_bp,
            )
        )
    return GraphExtrapolateResponse(nodes=nodes)

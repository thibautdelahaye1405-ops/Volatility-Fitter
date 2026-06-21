"""Production graph smile-extrapolation service (plan Phases 1-6).

This is the *production* counterpart to ``volfit.api.graph_service`` (which
stays the manual-shift sandbox, plan Amendment A). The two never share an
endpoint or semantics:

    transported prior -> lit calibration innovation -> graph posterior increment
                      -> dark reconstructed smile    -> quote comparison

This module is the orchestration core. The selected lit+dark universe (Phase 1)
lives in ``graph_universe``; per-node transported-prior baselines (Phase 2) in
``graph_nodes``; smile reconstruction + quote metrics (Phase 5) in
``graph_reconstruct``. Here: the lit-calibration innovation feed (Phase 3),
data-derived precision (Phase 4) and per-edge beta (Phase 6) — assembled into the
posterior solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from volfit.api.graph_service import GRAPH_PRIOR_HYPER
from volfit.api.graph_universe import (
    SelectedUniverse,
    build_selected_universe,
)
from volfit.api.schemas import (
    GraphExtrapolateNode,
    GraphExtrapolateRequest,
    GraphExtrapolateResponse,
)
from volfit.api.service import fit_or_get, weighted_rms_error
from volfit.api.state import AppState
from volfit.graph import build_increment_prior
from volfit.graph import precision as gprec
from volfit.graph.beta import beta_matrix
from volfit.graph.build import SmileGraph
from volfit.graph.posterior import posterior_update
from volfit.graph.smile_universe import HandleField, N_HANDLES
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.quadrature import build_slice

#: Near-ATM half-window (log-moneyness) for the quote-density / spread factors.
ATM_BAND = 0.10


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


def _quote_stats(prepared) -> tuple[float, float]:
    """(near-ATM quote count, relative bid-ask spread) for the precision factors.

    Spread is mean ``(iv_ask - iv_bid) / iv_mid`` over the near-ATM window (all
    quotes if none fall inside it). Drives the quote-density + spread precision
    factors (plan Phase 4)."""
    k = np.asarray(prepared.k, dtype=float)
    near = np.abs(k) <= ATM_BAND
    if not near.any():
        near = np.ones_like(k, dtype=bool)
    n_atm = float(np.count_nonzero(near))
    mid = np.maximum(np.asarray(prepared.iv_mid, dtype=float)[near], 1e-6)
    width = np.asarray(prepared.iv_ask, dtype=float)[near] - np.asarray(
        prepared.iv_bid, dtype=float
    )[near]
    rel_spread = float(np.mean(np.maximum(width, 0.0) / mid))
    return n_atm, rel_spread


def _prior_age_days(state: AppState, as_of: str | None) -> float:
    """Days between the reference date and a prior snapshot's market moment."""
    if not as_of:
        return 0.0
    try:
        as_of_date = date.fromisoformat(as_of[:10])
    except ValueError:
        return 0.0
    return max((state.reference_date - as_of_date).days, 0)


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


def _handle_beta_matrices(universe: "SelectedUniverse", request) -> list[np.ndarray] | None:
    """Per-handle beta matrices (atm_vol, skew, curvature), or None when no beta is
    requested (the byte-identical no-beta path, plan Phase 6).

    ``crossBeta`` broadcasts to every cross-ticker edge / handle / direction;
    ``edgeBetas`` then overrides named directed edges per handle."""
    cross_beta = request.crossBeta
    edge_betas = request.edgeBetas
    if (cross_beta is None or cross_beta == 1.0) and not edge_betas:
        return None

    graph = universe.graph
    mats = [beta_matrix(graph) for _ in range(N_HANDLES)]  # all-ones per handle
    if cross_beta is not None:
        for i, j in graph.edges:  # undirected support; set both directions
            if universe.nodes[i].ticker != universe.nodes[j].ticker:
                for m in mats:
                    m[i, j] = m[j, i] = float(cross_beta)
    for eb in edge_betas:
        src = (eb.fromTicker, eb.fromExpiry)
        dst = (eb.toTicker, eb.toExpiry)
        if src in graph.index and dst in graph.index:
            i, j = graph.index[src], graph.index[dst]
            mats[0][i, j] = eb.betaAtmVol
            mats[1][i, j] = eb.betaSkew
            mats[2][i, j] = eb.betaCurv
    return mats


def _build_increment_priors(universe: "SelectedUniverse", request):
    """Per-handle increment priors with optional per-edge beta (plan Phase 6).

    Mirrors ``graph_service._build_priors`` (the same kappa/eta/lambda regime) but
    threads each handle's beta matrix into the directed residual ``L_dir^β``."""
    betas = _handle_beta_matrices(universe, request)
    priors = []
    for c, (s, eta) in enumerate(GRAPH_PRIOR_HYPER):
        ot_weight = request.lambdaScale / s**2 if request.lambdaScale > 0.0 else 0.0
        priors.append(
            build_increment_prior(
                universe.graph,
                kappa=request.kappaScale / s**2,
                eta=eta * request.etaScale,
                ot_weight=ot_weight,
                source_allowance=request.nu,
                beta=None if betas is None else betas[c],
            )
        )
    return priors


@dataclass(frozen=True)
class ExtrapolationSolution:
    """The full solved field for one extrapolation request — shared by the bulk
    summary (``extrapolate``) and the per-node smile reconstruction (Phase 5)."""

    universe: "SelectedUniverse"
    priors_meta: tuple  # tuple[NodePrior]
    field: HandleField
    base_breakdowns: list
    obs_breakdowns: dict  # node index -> PrecisionBreakdown
    obs_value_by_idx: dict  # node index -> calibrated handles (3,)
    calibrated: list  # bool per node
    fit_mode: str


def solve(
    state: AppState,
    request: GraphExtrapolateRequest,
    hold_out: frozenset = frozenset(),
) -> ExtrapolationSolution | None:
    """Run the production prior-anchored solve (plan Phase 3/4); None if empty.

    transported prior baselines -> lit-calibration innovations -> graph posterior
    increment, with data-derived precision. Dark nodes are never observations.
    ``hold_out`` is a set of node names withheld from the observations (used by the
    leave-one-node-out backtest, plan Phase 8); their calibrated handles are still
    computed (for scoring) but do not feed the propagation.
    """
    # Local import avoids a module-load cycle (graph_nodes imports us for typing).
    from volfit.api.graph_nodes import resolve_priors

    universe = build_selected_universe(state, request.calendarWeight, request.crossWeight)
    if universe.graph is None:
        return None

    fit_mode = state.last_fit_mode
    priors_meta = resolve_priors(state, universe, flat_atm=request.flatAtm)
    baseline = np.vstack([p.handles for p in priors_meta])

    # Data-derived baseline precision per node (plan Phase 4): provenance tier x
    # prior age x transport distance, with floors/caps.
    base_breakdowns = [
        gprec.baseline_precision(
            p.source, _prior_age_days(state, p.as_of), p.transport_distance
        )
        for p in priors_meta
    ]
    baseline_precision = np.vstack([b.precision for b in base_breakdowns])

    # Lit nodes with a calibration become observations; dark nodes never do.
    # Each observation's precision is derived from fit quality + quote coverage.
    obs_idx_list: list[int] = []
    obs_values_list: list[np.ndarray] = []
    calibrated = [False] * len(universe.nodes)
    obs_breakdowns: dict[int, gprec.PrecisionBreakdown] = {}
    calibrated_by_idx: dict[int, np.ndarray] = {}
    for i, node in enumerate(universe.nodes):
        if not node.lit:
            continue
        record = fit_or_get(state, node.ticker, node.expiry, fit_mode)
        if record is None:
            continue
        h = atm_handles(build_slice(record.result.params), record.prepared.tau)
        y = np.array([h.sigma0, h.skew, h.curvature])
        rms = weighted_rms_error(state, node.ticker, node.expiry, record, fit_mode)
        n_atm, rel_spread = _quote_stats(record.prepared)
        obs_breakdowns[i] = gprec.observation_precision(rms, n_atm, rel_spread)
        calibrated[i] = True
        calibrated_by_idx[i] = y
        if node.name in hold_out:  # withheld from the propagation (LOO scoring)
            continue
        obs_idx_list.append(i)
        obs_values_list.append(y)

    obs_idx = np.asarray(obs_idx_list, dtype=int)
    obs_values = (
        np.vstack(obs_values_list) if obs_values_list else np.empty((0, N_HANDLES))
    )
    obs_precision = (
        np.vstack([obs_breakdowns[i].precision for i in obs_idx_list])
        if obs_idx_list
        else np.empty((0, N_HANDLES))
    )

    increment_priors = _build_increment_priors(universe, request)
    field = _propagate_field(
        universe.graph,
        increment_priors,
        baseline,
        baseline_precision,
        obs_idx,
        obs_values,
        obs_precision,
    )
    return ExtrapolationSolution(
        universe=universe,
        priors_meta=priors_meta,
        field=field,
        base_breakdowns=base_breakdowns,
        obs_breakdowns=obs_breakdowns,
        obs_value_by_idx=calibrated_by_idx,
        calibrated=calibrated,
        fit_mode=fit_mode,
    )


def extrapolate(
    state: AppState, request: GraphExtrapolateRequest
) -> GraphExtrapolateResponse:
    """Bulk ATM-summary response over every selected node (plan Phase 3, Amendment E:
    summaries only; full curves are fetched per node via the node-smile route)."""
    sol = solve(state, request)
    if sol is None:
        return GraphExtrapolateResponse(nodes=[])
    universe, field = sol.universe, sol.field
    base_breakdowns, obs_breakdowns = sol.base_breakdowns, sol.obs_breakdowns
    obs_value_by_idx = sol.obs_value_by_idx
    band_lo, band_hi = field.atm_vol_band()

    nodes = []
    for i, node in enumerate(universe.nodes):
        meta = sol.priors_meta[i]
        prior_h = meta.handles
        post_h = field.mean[i]
        innovation_bp = None
        if i in obs_value_by_idx:
            innovation_bp = float((obs_value_by_idx[i][0] - prior_h[0]) * 1e4)
        obs_bd = obs_breakdowns.get(i)
        factors = dict(base_breakdowns[i].factors)
        if obs_bd is not None:
            factors.update(obs_bd.factors)
        nodes.append(
            GraphExtrapolateNode(
                baselinePrecision=[float(v) for v in base_breakdowns[i].precision],
                obsPrecision=(
                    [float(v) for v in obs_bd.precision] if obs_bd is not None else None
                ),
                precisionFactors=factors,
                ticker=node.ticker,
                expiry=node.expiry,
                t=_node_t(state, node.expiry),
                lit=node.lit,
                calibrated=sol.calibrated[i],
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

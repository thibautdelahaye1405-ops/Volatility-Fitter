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

from volfit.api.graph_service import GRAPH_PRECISION, GRAPH_PRIOR_HYPER
from volfit.api.graph_universe import (
    SelectedUniverse,
    build_selected_universe,
)
from volfit.api.schemas import (
    GraphCycleFlag,
    GraphEdgeInput,
    GraphExtrapolateNode,
    GraphExtrapolateRequest,
    GraphExtrapolateResponse,
)
from volfit.api.service import fit_or_get, weighted_rms_error
from volfit.api.state import AppState
from volfit.graph import build_increment_prior
from volfit.graph import precision as gprec
from volfit.graph.idio import apply_idio_floor
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


def lattice_edges(state: AppState) -> list[GraphEdgeInput]:
    """The auto-lattice directed edges over the selected universe as editable
    GraphEdgeInputs (weight from the lattice, betas 1) — the edge editor's
    "seed from lattice" source (plan Phase 7)."""
    from volfit.api.graph_universe import lattice_weights_for

    return [
        GraphEdgeInput(
            fromTicker=src[0], fromExpiry=src[1], toTicker=dst[0], toExpiry=dst[1], weight=w
        )
        for (src, dst), w in lattice_weights_for(state).items()
    ]


def _handle_beta_matrices(
    universe: "SelectedUniverse", request, edges=None
) -> list[np.ndarray] | None:
    """Per-handle beta matrices (atm_vol, skew, curvature), or None when no beta is
    requested (the byte-identical no-beta path, plan Phase 6/7).

    When an explicit ``edges`` list is in effect, betas come from the edges (each
    edge carries weight + per-handle beta). Otherwise ``crossBeta`` broadcasts to
    every cross-ticker edge / handle / direction and ``edgeBetas`` overrides named
    directed edges per handle."""
    graph = universe.graph

    if edges is not None:
        mats = [beta_matrix(graph) for _ in range(N_HANDLES)]
        any_beta = False
        for e in edges:
            src, dst = (e.fromTicker, e.fromExpiry), (e.toTicker, e.toExpiry)
            if src in graph.index and dst in graph.index:
                i, j = graph.index[src], graph.index[dst]
                mats[0][i, j] = e.betaAtmVol
                mats[1][i, j] = e.betaSkew
                mats[2][i, j] = e.betaCurv
                if e.betaAtmVol != 1.0 or e.betaSkew != 1.0 or e.betaCurv != 1.0:
                    any_beta = True
        return mats if any_beta else None

    cross_beta = request.crossBeta
    edge_betas = request.edgeBetas
    if (cross_beta is None or cross_beta == 1.0) and not edge_betas:
        return None

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


def _build_increment_priors(universe: "SelectedUniverse", request, edges=None):
    """Per-handle increment priors with optional per-edge beta (plan Phase 6/7).

    Mirrors ``graph_service._build_priors`` (the same kappa/eta/lambda regime) but
    threads each handle's beta matrix into the directed residual ``L_dir^β``."""
    betas = _handle_beta_matrices(universe, request, edges)
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
    # The per-handle increment priors + baseline precisions the field was
    # solved with — retained for closed-form follow-up algebra on the same
    # posterior (active observation selection, R3 item 13). increment_priors
    # is None in precision-message mode (the improper message prior has no
    # covariance form; the observation plan reads Σ⁺ instead).
    increment_priors: list = None  # list[IncrementPrior], one per handle
    baseline_precision: np.ndarray = None  # (N, 3)
    # Message-mode diagnostics (arc P3); None in smooth_field mode — the
    # discriminator every consumer branches on.
    message_diagnostics: object = None  # graph_message.MessageDiagnostics | None


def solve(
    state: AppState,
    request: GraphExtrapolateRequest,
    hold_out: frozenset = frozenset(),
    idio_atm_sigma: dict[str, float] | None = None,
) -> ExtrapolationSolution | None:
    """Run the production prior-anchored solve (plan Phase 3/4); None if empty.

    transported prior baselines -> lit-calibration innovations -> graph posterior
    increment, with data-derived precision. Dark nodes are never observations.
    ``hold_out`` is a set of node names withheld from the observations (used by the
    leave-one-node-out backtest, plan Phase 8); their calibrated handles are still
    computed (for scoring) but do not feed the propagation.

    ``idio_atm_sigma`` maps ticker -> trailing idio sigma for the band floor
    (volfit.graph.idio); None pulls the state's recorded history (production),
    the offline harness passes its own strictly-causal estimate. Band-only:
    posterior means are identical with or without it.
    """
    # Local import avoids a module-load cycle (graph_nodes imports us for typing).
    from volfit.api.graph_nodes import resolve_priors

    # Resolve the edge topology: request edges win, then the persisted overrides,
    # else None ⇒ the auto-lattice (plan Phase 7).
    edges = list(request.edges) or state.graph_edges() or None
    edge_tuples = (
        [((e.fromTicker, e.fromExpiry), (e.toTicker, e.toExpiry), e.weight) for e in edges]
        if edges
        else None
    )
    universe = build_selected_universe(
        state, request.calendarWeight, request.crossWeight, edges=edge_tuples
    )
    if universe.graph is None:
        return None

    fit_mode = state.last_fit_mode
    priors_meta = resolve_priors(state, universe, flat_atm=request.flatAtm)
    baseline = np.vstack([p.handles for p in priors_meta])

    # Data-derived baseline precision per node (plan Phase 4): provenance tier x
    # prior age x transport distance, with floors/caps. Dark nodes get the
    # DARK_BASE_SCALE tier reduction (graph-LOO follow-up): their transported
    # prior is the target to move, not a quote-corroborated anchor.
    base_breakdowns = [
        gprec.baseline_precision(
            p.source, _prior_age_days(state, p.as_of), p.transport_distance,
            dark=not node.lit,
        )
        for p, node in zip(priors_meta, universe.nodes)
    ]
    baseline_precision = np.vstack([b.precision for b in base_breakdowns])

    # Observation feed. U3 unified what-if: typed synthetic pulses REPLACE
    # the lit-calibration innovations when present — any selected node may be
    # pulsed, no fits are triggered, and the pulse is hypothesis-firm (the
    # sandbox's GRAPH_PRECISION by default; a typed ATM precision scales the
    # other handles proportionally). Otherwise: lit nodes with a calibration
    # become observations (dark nodes never do), each with data-derived
    # precision from fit quality + quote coverage.
    synthetic = list(request.syntheticObservations)
    obs_idx_list: list[int] = []
    obs_values_list: list[np.ndarray] = []
    calibrated = [False] * len(universe.nodes)
    obs_breakdowns: dict[int, gprec.PrecisionBreakdown] = {}
    calibrated_by_idx: dict[int, np.ndarray] = {}
    syn_prec_list: list[np.ndarray] = []
    if synthetic:
        pulses: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for syn in synthetic:
            name = (syn.ticker, syn.expiry)
            if name not in universe.graph.index:
                continue  # outside the selection — dropped (legacy contract)
            i = universe.graph.index[name]
            y = baseline[i] + np.array([syn.dAtmVol, syn.dSkew, syn.dCurv])
            r = (
                GRAPH_PRECISION.astype(float)
                if syn.precision is None
                else GRAPH_PRECISION * (syn.precision / GRAPH_PRECISION[0])
            )
            pulses[i] = (y, r)  # duplicate pulses on one node: last wins
        for i in sorted(pulses):
            y, r = pulses[i]
            calibrated[i] = True
            calibrated_by_idx[i] = y
            obs_idx_list.append(i)
            obs_values_list.append(y)
            syn_prec_list.append(r)
    else:
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
    if synthetic:
        obs_precision = (
            np.vstack(syn_prec_list) if syn_prec_list else np.empty((0, N_HANDLES))
        )
    else:
        obs_precision = (
            np.vstack([obs_breakdowns[i].precision for i in obs_idx_list])
            if obs_idx_list
            else np.empty((0, N_HANDLES))
        )

    # Propagation fork (arc P3): smooth_field is the untouched legacy path;
    # precision_messages solves the pairwise-factor operator; hybrid adds the
    # legacy directed-smoothness/OT term on top of the message factors
    # (spec §15.4 — WITHOUT the legacy zero-innovation anchor).
    message_diagnostics = None
    if request.propagationMode == "smooth_field":
        increment_priors = _build_increment_priors(universe, request, edges)
        field = _propagate_field(
            universe.graph,
            increment_priors,
            baseline,
            baseline_precision,
            obs_idx,
            obs_values,
            obs_precision,
        )
    else:
        from volfit.api.graph_message import solve_message_field

        hybrid_extra = None
        increment_priors = None
        if request.propagationMode == "hybrid":
            increment_priors = _build_increment_priors(universe, request, edges)
            n = len(universe.nodes)
            hybrid_extra = [
                p.precision - np.diag(np.full(n, request.kappaScale / s**2))
                for p, (s, _eta) in zip(increment_priors, GRAPH_PRIOR_HYPER)
            ]
        t_by_node = {node.name: _node_t(state, node.expiry) for node in universe.nodes}
        field, message_diagnostics = solve_message_field(
            universe,
            t_by_node,
            request,
            baseline,
            baseline_precision,
            obs_idx,
            obs_values,
            obs_precision,
            persisted_edges=state.graph_message_edges(),
            hybrid_extra=hybrid_extra,
            # A what-if pulse defines its innovation directly — there is no
            # baseline noise in a hypothesis, so §15.2 does not apply.
            firm_observations=bool(synthetic),
        )

    # Idio band floor (volfit.graph.idio): every node that did NOT contribute an
    # observation (dark, held out, or lit-but-uncalibrated) has its ATM band std
    # floored at sqrt(IDIO_FLOOR_LAMBDA) x the ticker's trailing innovation RMS.
    # Band-only — the posterior means above are final. Cold start (no history)
    # leaves the field byte-identical.
    if request.idioFloor:
        if idio_atm_sigma is None:
            idio_atm_sigma = state.graph_idio_sigma()
        if idio_atm_sigma:
            observed = set(obs_idx_list)
            sigmas = np.full(len(universe.nodes), np.nan)
            for i, node in enumerate(universe.nodes):
                if i not in observed and node.ticker in idio_atm_sigma:
                    sigmas[i] = idio_atm_sigma[node.ticker]
            field, bound = apply_idio_floor(field, sigmas)
            for i in np.flatnonzero(bound):  # surfaced in node diagnostics
                base_breakdowns[i].factors["idioSigma"] = float(sigmas[i])

    # Record today's lit innovations (calibrated - transported prior, ATM) so a
    # node that goes dark on a LATER day gets floored from the days it was lit.
    # Idempotent per (ticker, day, expiry); a no-op without a store on scratch
    # states (the benchmark harness builds throwaway states and feeds the floor
    # its own strictly-causal history instead). What-if pulses are NEVER
    # recorded — non-persisting by construction (P5b U3).
    if not synthetic:
        state.record_graph_innovations(
            {
                (universe.nodes[i].ticker, universe.nodes[i].expiry): float(
                    y[0] - baseline[i, 0]
                )
                for i, y in calibrated_by_idx.items()
            }
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
        increment_priors=increment_priors,
        baseline_precision=baseline_precision,
        message_diagnostics=message_diagnostics,
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
    diag = sol.message_diagnostics

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
                qIncoming=(float(diag.q_incoming[i]) if diag is not None else None),
                noLitPath=(bool(diag.no_lit_path[i]) if diag is not None else None),
            )
        )
    cycle_flags = []
    if diag is not None:
        for receiver, informer, product in diag.cycle_flags:
            cycle_flags.append(
                GraphCycleFlag(
                    receiverTicker=receiver[0],
                    receiverExpiry=receiver[1],
                    informerTicker=informer[0],
                    informerExpiry=informer[1],
                    # 0.0 = the nonpositive-beta sentinel (NaN is not JSON).
                    betaProduct=float(product) if np.isfinite(product) else 0.0,
                )
            )
    return GraphExtrapolateResponse(
        nodes=nodes,
        propagationMode=request.propagationMode,
        cycleDiagnostics=cycle_flags,
    )

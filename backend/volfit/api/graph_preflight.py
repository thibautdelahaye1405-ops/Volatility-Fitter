"""Pre-run diagnostics for the graph workspace (P5b U5 — POST /graph/preflight).

The DRY-RUN contract: nothing is fitted, solved, or recorded. Every check
reads cheap state only —

* the selected universe + the effective relation set (the same precedence the
  solve uses: request edges → persisted rules → auto relations);
* prior PRESENCE via the snapshot tiers alone (``allow_bootstrap=False`` —
  the bootstrap tier would fit on demand);
* calibration PRESENCE via the calibrated pointer (never a fit).

Issues carry a machine ``code`` + a human sentence. Run is blocked ONLY on
genuine blockers (an empty universe); everything else is a warning or info —
the arc's ratified contract.
"""

from __future__ import annotations

import numpy as np

from volfit.api.graph_message import (
    _amplitude_rho,
    auto_message_edges,
    calendar_policy_for,
    message_edges_from_schema,
)
from volfit.api.graph_universe import build_selected_universe
from volfit.api.schemas import (
    GraphExtrapolateRequest,
    GraphPreflightIssue,
    GraphPreflightResponse,
)
from volfit.api.state import AppState
from volfit.graph.message import (
    MessageEdge,
    anchor_precisions,
    build_message_operator,
    cycle_beta_products,
)

#: Mirror of the frontend lib/calendarPolicy BETA_CAP.
BETA_CAP = 3.0
#: Relationship-uncertainty outlier rails (vol points): beyond LOOSE the
#: relation carries ~nothing (p < 100); below TIGHT it is suspiciously firm.
SIGMA_LOOSE_PTS = 10.0
SIGMA_TIGHT_PTS = 0.05
#: One incoming factor carrying more than this share of q = fragile receiver.
DOMINANCE_SHARE = 0.9
#: Conditioning is an O(N³) SVD — skip above this universe size.
COND_MAX_NODES = 400
COND_WARN = 1e10


def _issue(severity: str, code: str, message: str, count: int = 1) -> GraphPreflightIssue:
    return GraphPreflightIssue(severity=severity, code=code, message=message, count=count)


def _sigma_pts(precision: float) -> float:
    return float("inf") if precision <= 0.0 else 100.0 / np.sqrt(precision)


class _UnionFind:
    """Tiny union-find for the no-lit-path component sweep."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _connectivity_issues(
    n_nodes: int,
    pairs: list[tuple[int, int]],
    observed: set[int],
    issues: list[GraphPreflightIssue],
) -> None:
    """§14.3 sweep: components with no observation stay at their transported
    prior with explicitly broad uncertainty — surfaced, never blocked."""
    if n_nodes == 0 or not observed:
        return  # the no-observation warning already covers the whole field
    uf = _UnionFind(n_nodes)
    for a, b in pairs:
        uf.union(a, b)
    observed_roots = {uf.find(i) for i in observed}
    stranded = [i for i in range(n_nodes) if uf.find(i) not in observed_roots]
    if stranded:
        roots = {uf.find(i) for i in stranded}
        issues.append(
            _issue(
                "warning",
                "no_lit_path",
                f"{len(stranded)} node(s) in {len(roots)} component(s) have no "
                "path to an observation — they stay at their transported prior "
                "with explicitly broad uncertainty (§14.3).",
                count=len(stranded),
            )
        )


def _message_edge_issues(
    names: list, edges: list[MessageEdge], request, issues: list[GraphPreflightIssue]
) -> None:
    """Relation-quality sweeps over the effective message factors."""
    extremes = [e for e in edges if abs(e.beta[0]) > BETA_CAP]
    if extremes:
        worst = max(abs(e.beta[0]) for e in extremes)
        issues.append(
            _issue(
                "warning",
                "beta_extreme",
                f"{len(extremes)} relation(s) amplify |β| > {BETA_CAP:g} "
                f"(worst {worst:.2f}) — wide maturity gaps; consider an αT "
                "override or an explicit row.",
                count=len(extremes),
            )
        )
    loose = [e for e in edges if _sigma_pts(e.precision) > SIGMA_LOOSE_PTS]
    if loose:
        issues.append(
            _issue(
                "warning",
                "sigma_loose",
                f"{len(loose)} relation(s) with uncertainty σ > "
                f"{SIGMA_LOOSE_PTS:g} vol pts — they carry almost nothing.",
                count=len(loose),
            )
        )
    tight = [e for e in edges if _sigma_pts(e.precision) < SIGMA_TIGHT_PTS]
    if tight:
        issues.append(
            _issue(
                "warning",
                "sigma_tight",
                f"{len(tight)} relation(s) with uncertainty σ < "
                f"{SIGMA_TIGHT_PTS:g} vol pts — suspiciously firm; a typo in "
                "the raw precision units?",
                count=len(tight),
            )
        )

    flags = cycle_beta_products(
        names, edges, handle=0, tol=request.cycleBetaTolerance
    )
    if flags:
        products = [f.product for f in flags if np.isfinite(f.product)]
        worst = max((abs(p) for p in products), default=0.0)
        issues.append(
            _issue(
                "warning",
                "beta_cycle",
                f"{len(flags)} inconsistent β cycle(s) (worst product "
                f"{worst:.2f}) — internally contradictory relation "
                "configuration (§16.4).",
                count=len(flags),
            )
        )

    # Fragile receivers: one incoming factor dominating q (≥2 factors only —
    # a single-informer receiver is a topology fact, not a fragility).
    incoming: dict[object, list[float]] = {}
    for e in edges:
        incoming.setdefault(e.receiver, []).append(e.precision)
        # The implied reverse read (§7.6): the informer also receives.
        rev = e.precision * e.beta[0] * e.beta[0]
        incoming.setdefault(e.informer, []).append(rev)
    dominated = [
        r
        for r, ps in incoming.items()
        if len(ps) >= 2 and max(ps) / sum(ps) > DOMINANCE_SHARE
    ]
    if dominated:
        issues.append(
            _issue(
                "info",
                "dominated_receiver",
                f"{len(dominated)} receiver(s) get > {DOMINANCE_SHARE:.0%} of "
                "their incoming confidence from a single relation — fragile "
                "to that one edge.",
                count=len(dominated),
            )
        )


def _conditioning_issue(
    names: list,
    edges: list[MessageEdge],
    observed: set[int],
    request,
    issues: list[GraphPreflightIssue],
) -> None:
    """Conditioning of the handle-0 information matrix Q + diag(κ) + R.

    Observation precision is approximated with the firm sandbox scale (real
    r is fit-quality-derived and would require fits — a dry run never fits)."""
    if len(names) > COND_MAX_NODES:
        issues.append(
            _issue(
                "info",
                "conditioning_skipped",
                f"Conditioning check skipped above {COND_MAX_NODES} nodes.",
            )
        )
        return
    op = build_message_operator(names, edges, handle=0)
    kappa = anchor_precisions(names, edges, _amplitude_rho(request), handle=0)
    info = op.q_matrix + np.diag(kappa)
    for i in observed:
        info[i, i] += 1.0e6  # GRAPH_PRECISION[0] — the firm observation scale
    cond = float(np.linalg.cond(info))
    if not np.isfinite(cond) or cond > COND_WARN:
        issues.append(
            _issue(
                "warning",
                "ill_conditioned",
                f"Posterior information matrix conditioning ≈ {cond:.2e} — "
                "near-singular; check for zero-precision islands or wildly "
                "mixed precisions.",
            )
        )


def preflight(state: AppState, request: GraphExtrapolateRequest) -> GraphPreflightResponse:
    """The dry-run report (see the module docstring for the contract)."""
    from volfit.api.graph_extrapolation import _node_t
    from volfit.api.graph_nodes import resolve_node_prior

    issues: list[GraphPreflightIssue] = []

    edges_in = list(request.edges) or state.graph_edges() or None
    edge_tuples = (
        [((e.fromTicker, e.fromExpiry), (e.toTicker, e.toExpiry), e.weight) for e in edges_in]
        if edges_in
        else None
    )
    universe = build_selected_universe(
        state, request.calendarWeight, request.crossWeight, edges=edge_tuples
    )
    if universe.graph is None:
        return GraphPreflightResponse(
            universeNodes=0,
            litCount=0,
            darkCount=0,
            observationCount=0,
            propagationMode=request.propagationMode,
            ok=False,
            issues=[
                _issue(
                    "blocker",
                    "empty_universe",
                    "The selected universe is empty — pick tickers/expiries "
                    "under Universe ▸ Selection.",
                )
            ],
        )

    names = list(universe.names)
    index = universe.graph.index
    lit_idx = [i for i, node in enumerate(universe.nodes) if node.lit]
    gated = bool(getattr(state, "_gated", False))
    fit_mode = state.last_fit_mode

    # Observation set — synthetic pulses (the what-if) or the lit feed.
    synthetic = list(request.syntheticObservations)
    if synthetic:
        pulse_idx = {
            index[(s.ticker, s.expiry)]
            for s in synthetic
            if (s.ticker, s.expiry) in index
        }
        dropped = len(synthetic) - len(
            [s for s in synthetic if (s.ticker, s.expiry) in index]
        )
        if dropped > 0:
            issues.append(
                _issue(
                    "warning",
                    "pulses_outside_universe",
                    f"{dropped} pulse(s) name nodes outside the selected "
                    "universe — they are dropped.",
                    count=dropped,
                )
            )
        observed = pulse_idx
    else:
        # Calibration PRESENCE via the pointer — never a fit. Ungated servers
        # bootstrap lazily at Run, so unfitted lit nodes still observe there.
        with_ptr = {
            i
            for i in lit_idx
            if state.get_calibrated_ptr(
                universe.nodes[i].ticker, universe.nodes[i].expiry, fit_mode
            )
            is not None
        }
        missing = len(lit_idx) - len(with_ptr)
        if missing > 0:
            issues.append(
                _issue(
                    "warning" if gated else "info",
                    "lit_uncalibrated",
                    f"{missing} lit node(s) have no calibration yet — "
                    + (
                        "they contribute nothing until Calibrate (gated server)."
                        if gated
                        else "they will calibrate lazily at Run."
                    ),
                    count=missing,
                )
            )
        observed = with_ptr if gated else set(lit_idx)

    if not observed:
        issues.append(
            _issue(
                "warning",
                "no_observations",
                "No observations — Run returns the transported priors with "
                "prior uncertainty (nothing propagates).",
            )
        )

    # Prior presence via the snapshot tiers only (bootstrap would fit).
    if not request.flatAtm:
        weak = 0
        for node in universe.nodes:
            prior = resolve_node_prior(
                state, node.ticker, node.expiry, allow_bootstrap=False
            )
            if prior.source == "none":
                weak += 1
        if weak > 0:
            issues.append(
                _issue(
                    "warning",
                    "missing_priors",
                    f"{weak} node(s) have no saved prior — they fall back to "
                    "today-bootstrap/flat baselines at Run and are excluded "
                    "from validation.",
                    count=weak,
                )
            )

    # Effective relations + mode-specific sweeps.
    if request.propagationMode == "smooth_field":
        pairs = [(i, j) for i, j in universe.graph.edges]
        if request.crossBeta is not None and abs(request.crossBeta) > BETA_CAP:
            issues.append(
                _issue(
                    "warning",
                    "beta_extreme",
                    f"Cross-ticker β {request.crossBeta:.2f} exceeds "
                    f"{BETA_CAP:g} — every cross edge amplifies that hard.",
                )
            )
    else:
        t_by = {node.name: _node_t(state, node.expiry) for node in universe.nodes}
        persisted = (
            state.graph_message_draft_edges()
            if request.useDraftConfig
            else state.graph_message_edges()
        )
        rows = list(request.messageEdges) or persisted or None
        edges = (
            message_edges_from_schema(rows, t_by, request)
            if rows
            else auto_message_edges(universe, t_by, request)
        )
        pairs = [
            (index[e.receiver], index[e.informer])
            for e in edges
            if e.receiver in index and e.informer in index
        ]
        _message_edge_issues(names, edges, request, issues)
        _conditioning_issue(names, edges, observed, request, issues)
        if not request.calendarEnabled:
            issues.append(
                _issue(
                    "info",
                    "calendar_disabled",
                    "Calendar policy is OFF — smiles only talk across tickers.",
                )
            )
        else:
            off = [
                t
                for t in {node.ticker for node in universe.nodes}
                if not calendar_policy_for(request, t)[0]
            ]
            if off:
                issues.append(
                    _issue(
                        "info",
                        "calendar_disabled",
                        f"Calendar policy is OFF for {', '.join(sorted(off))}.",
                        count=len(off),
                    )
                )

    _connectivity_issues(len(names), pairs, observed, issues)

    return GraphPreflightResponse(
        universeNodes=len(names),
        litCount=len(lit_idx),
        darkCount=len(names) - len(lit_idx),
        observationCount=len(observed),
        propagationMode=request.propagationMode,
        ok=not any(i.severity == "blocker" for i in issues),
        issues=issues,
    )

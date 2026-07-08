"""Graph-extrapolation service functions (ROADMAP Phase 5/7).

Split out of volfit.api.service to keep both modules under the file-size
policy. Backs the Graph Viewer routes: build the smile universe over all
tickers x expiries (baseline mid fits), propagate sparse handle observations
through the OT-Bayesian solver (POST /graph/solve), and auto-tune the
propagation reach by leave-one-out cross-validation (POST /graph/autotune).

The universe's baseline slice fits flow through ``service.fit_or_get`` (so
they share the fit cache); only the cheap graph topology/weights are rebuilt
when the user edits edge weights, never the fits.
"""

from __future__ import annotations

import itertools

import numpy as np

from volfit.api.schemas import (
    AutotuneCandidate,
    GraphAutotuneRequest,
    GraphAutotuneResponse,
    GraphNodeResult,
    GraphObservation,
    GraphSolveRequest,
    GraphSolveResponse,
    GraphSolverParams,
)
from volfit.api.service import fit_or_get
from volfit.api.state import AppState, UnknownNodeError
from volfit.graph import build_graph, build_increment_prior
from volfit.graph.smile_universe import (
    SmileNode,
    SmileUniverse,
    build_universe,
    propagate_handles,
)

#: Graph weights: strong calendar chain within a ticker, weaker cross-ticker
#: edges at equal expiry (regime validated in tests/test_smile_universe.py).
SAME_TICKER_WEIGHT = 10.0
CROSS_TICKER_WEIGHT = 2.0

#: Per-handle increment hyperparameters (scale s, eta) with kappa = 1/s^2:
#: ~3 vol pts level, looser skew/curvature — the demo.py regime.
GRAPH_PRIOR_HYPER = ((0.03, 2.0e4), (0.05, 7.0e3), (0.5, 70.0))

#: Baseline/observation precisions per handle coordinate.
GRAPH_PRECISION = np.array([1.0e6, 1.0e6, 1.0e4])

#: Auto-tune sweep: geometric grid of etaScale candidates (reach multipliers).
AUTOTUNE_ETA_GRID = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0)


def ensure_universe(state: AppState) -> SmileUniverse:
    """Build (lazily) the smile universe over all tickers x expiries.

    Node names are (ticker, expiry-ISO); slices are the fits of the mode the
    user is VIEWING (``state.last_fit_mode`` — hardcoding mid left the whole
    sandbox empty on the gated server whenever the user calibrated in another
    mode). The cache is keyed on ``state.calib_signature`` so a Calibrate, a
    re-calibration, or a fit-mode switch rebuilds it — previously a universe
    built BEFORE the first Calibrate was cached empty forever. The build is
    deterministic and the slice fits are themselves cached, so a concurrent
    double build only costs time, never consistency.
    """
    if state.universe is not None and state.universe_sig == state.calib_signature:
        return state.universe

    # Iterate the user's ACTIVE universe, not the provider's static watchlist:
    # the two diverge once the user adds/removes tickers (e.g. SPY+NVDA active
    # while the provider still lists QQQ), and forwards() on an inactive ticker
    # raises UnknownNodeError -> a 500 the browser shows as "Failed to fetch".
    tickers = state.active_tickers()
    fit_mode = state.last_fit_mode
    smiles: list[SmileNode] = []
    ladders: dict[str, list[str]] = {}
    for ticker in tickers:
        isos: list[str] = []
        try:
            expiries = sorted(state.forwards(ticker))
        except Exception:  # noqa: BLE001 — a ticker with no fetched chain is skipped
            expiries = []
        for expiry in expiries:
            iso = expiry.isoformat()
            record = fit_or_get(state, ticker, iso, fit_mode)
            if record is None:
                continue  # uncalibrated node (gated, pre-Calibrate): not in the graph
            isos.append(iso)
            smiles.append(
                SmileNode(name=(ticker, iso), t=record.prepared.t, params=record.result.params)
            )
        ladders[ticker] = isos

    weights = _lattice_weights(tickers, ladders, SAME_TICKER_WEIGHT, CROSS_TICKER_WEIGHT)
    universe = build_universe(smiles, weights)
    state.universe = universe
    # Capture AFTER the build: on the ungated app the bootstrap fits above set
    # calibrated pointers themselves (the signature settles once they exist).
    state.universe_sig = state.calib_signature
    return universe


def _lattice_weights(
    tickers, ladders: dict[str, list[str]], calendar_w: float, cross_w: float
) -> dict[tuple, float]:
    """Edge-weight dict for the universe lattice: symmetric calendar chains
    within a ticker (weight ``calendar_w``) plus equal-expiry cross-ticker
    edges (weight ``cross_w``). Pure and cheap — no slice fits — so it can be
    rebuilt per solve when the user edits the weights."""
    weights: dict[tuple, float] = {}
    for ticker, isos in ladders.items():
        for near, far in zip(isos[:-1], isos[1:]):
            weights[((ticker, near), (ticker, far))] = calendar_w
            weights[((ticker, far), (ticker, near))] = calendar_w
    for a, b in itertools.combinations(tickers, 2):
        for iso in sorted(set(ladders.get(a, [])) & set(ladders.get(b, []))):
            weights[((a, iso), (b, iso))] = cross_w
            weights[((b, iso), (a, iso))] = cross_w
    return weights


def _ladders_of(universe: SmileUniverse) -> dict[str, list[str]]:
    """Per-ticker expiry ladders in node order (preserves the cached handle
    ordering, so a reweighted graph indexes identically to the baseline)."""
    ladders: dict[str, list[str]] = {}
    for smile in universe.smiles:
        ladders.setdefault(smile.name[0], []).append(smile.name[1])
    return ladders


def _reweighted_universe(
    universe: SmileUniverse, calendar_w: float, cross_w: float
) -> SmileUniverse:
    """Rebuild only the graph with custom edge weights, reusing the cached
    baseline fits/handles. Returns the input untouched when both weights match
    the service defaults (the common no-edit path)."""
    if calendar_w == SAME_TICKER_WEIGHT and cross_w == CROSS_TICKER_WEIGHT:
        return universe
    ladders = _ladders_of(universe)
    tickers = list(ladders)
    weights = _lattice_weights(tickers, ladders, calendar_w, cross_w)
    graph = build_graph([s.name for s in universe.smiles], weights)
    return SmileUniverse(graph=graph, smiles=universe.smiles, handles=universe.handles)


def _solver_universe(state: AppState, params: GraphSolverParams) -> SmileUniverse:
    """Universe whose graph reflects the request's edge-weight overrides."""
    universe = ensure_universe(state)
    calendar_w = SAME_TICKER_WEIGHT if params.calendarWeight is None else params.calendarWeight
    cross_w = CROSS_TICKER_WEIGHT if params.crossWeight is None else params.crossWeight
    return _reweighted_universe(universe, calendar_w, cross_w)


def _build_priors(graph, params: GraphSolverParams):
    """Per-handle increment priors for the requested solver hyperparameters.

    kappa = kappaScale / s^2 (the GRAPH_PRIOR_HYPER base), eta scaled by
    etaScale, and the OT flux term enabled only when lambdaScale > 0 (its
    weight likewise expressed per-coordinate as lambdaScale / s^2 so it is
    commensurate with kappa).
    """
    priors = []
    for s, eta in GRAPH_PRIOR_HYPER:
        ot_weight = params.lambdaScale / s**2 if params.lambdaScale > 0.0 else 0.0
        priors.append(
            build_increment_prior(
                graph,
                kappa=params.kappaScale / s**2,
                eta=eta * params.etaScale,
                ot_weight=ot_weight,
                source_allowance=params.nu,
            )
        )
    return priors


def _observed_handles(
    universe: SmileUniverse, observations: list[GraphObservation]
) -> dict[tuple, np.ndarray]:
    """Map handle *shifts* to absolute observed handles, validating nodes."""
    observed: dict[tuple, np.ndarray] = {}
    for obs in observations:
        name = (obs.ticker, obs.expiry)
        try:
            index = universe.node_index(name)
        except KeyError:
            raise UnknownNodeError(f"unknown node {name!r}") from None
        observed[name] = universe.handles[index] + np.array([obs.dAtmVol, obs.dSkew, obs.dCurv])
    return observed


def solve_graph(state: AppState, request: GraphSolveRequest) -> GraphSolveResponse:
    """Propagate sparse handle observations to every node of the universe."""
    universe = _solver_universe(state, request)
    priors = _build_priors(universe.graph, request)
    observed = _observed_handles(universe, request.observations)
    field = propagate_handles(
        universe,
        priors,
        observed,
        baseline_precision=GRAPH_PRECISION,
        observation_precision=GRAPH_PRECISION,
    )
    band_lo, band_hi = field.atm_vol_band()

    nodes = []
    for j, smile in enumerate(universe.smiles):
        ticker, expiry_iso = smile.name
        base, post = float(universe.handles[j, 0]), float(field.mean[j, 0])
        nodes.append(
            GraphNodeResult(
                ticker=ticker,
                expiry=expiry_iso,
                t=smile.t,
                baseAtmVol=base,
                postAtmVol=post,
                shiftBp=(post - base) * 1e4,
                sd=float(field.sd[j, 0]),
                bandLo=float(band_lo[j]),
                bandHi=float(band_hi[j]),
                observed=smile.name in observed,
            )
        )
    return GraphSolveResponse(nodes=nodes)


def autotune_graph(state: AppState, request: GraphAutotuneRequest) -> GraphAutotuneResponse:
    """Choose etaScale by leave-one-out cross-validation on the observations.

    For each candidate reach in AUTOTUNE_ETA_GRID, every observed node is held
    out in turn, the field is propagated from the rest, and the held-out node's
    posterior ATM vol is compared with its actual observed ATM vol. The RMS of
    those errors (in basis points) scores the candidate; the minimizer is
    returned along with the full scored grid for the UI to plot.
    """
    universe = _solver_universe(state, request)
    observed = _observed_handles(universe, request.observations)
    names = list(observed)  # >= 2 (schema-enforced)

    candidates: list[AutotuneCandidate] = []
    for eta_scale in AUTOTUNE_ETA_GRID:
        params = request.model_copy(update={"etaScale": eta_scale})
        priors = _build_priors(universe.graph, params)
        sq_sum = 0.0
        for held in names:
            train = {name: observed[name] for name in names if name != held}
            field = propagate_handles(
                universe,
                priors,
                train,
                baseline_precision=GRAPH_PRECISION,
                observation_precision=GRAPH_PRECISION,
            )
            i = universe.node_index(held)
            sq_sum += (float(field.mean[i, 0]) - float(observed[held][0])) ** 2
        rmse_bp = float(np.sqrt(sq_sum / len(names)) * 1e4)
        candidates.append(AutotuneCandidate(etaScale=eta_scale, rmseBp=rmse_bp))

    best = min(candidates, key=lambda c: c.rmseBp)
    return GraphAutotuneResponse(
        etaScale=best.etaScale, rmseBp=best.rmseBp, candidates=candidates
    )

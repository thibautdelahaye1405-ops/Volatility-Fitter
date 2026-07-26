"""Leave-one-node-out backtest of the graph extrapolator (plan Phase 8, Q6).

Live overlay answers "does this dark node look sane right now?"; the backtest
answers "does this graph methodology predict held-out smiles reliably?" — the loop
that calibrates the hyperparameters (eta/lambda/kappa/beta) and the precision
formulas.

Each validation-clean calibrated node is withheld in turn, the field is propagated
from the rest, and the held-out node's posterior ATM vol is compared with its actual
calibration. We report per-node residuals + standardized residuals (eq.
standardized-residual-final) and an aggregate calibration summary — if the model and
its uncertainties are right, the standardized residuals ζ look like N(0, 1).

Nodes whose prior is ``today_bootstrap`` (or flat) are EXCLUDED from the clean score:
their baseline IS today's fit, so a "prior vs market" test would be circular
(``valid_for_validation=False``, plan Amendment B).
"""

from __future__ import annotations

import numpy as np

from volfit.api.graph_extrapolation import solve
from volfit.api.graph_params import AUTOTUNE_ETA_GRID
from volfit.api.schemas import (
    AutotuneCandidate,
    GraphAutotuneResponse,
    GraphBacktestNode,
    GraphBacktestResponse,
    GraphExtrapolateRequest,
)
from volfit.api.state import AppState
from volfit.graph.hyper import standardized_residuals


def backtest(state: AppState, request: GraphExtrapolateRequest) -> GraphBacktestResponse:
    """Leave-one-node-out backtest over the calibrated, validation-clean nodes."""
    full = solve(state, request)
    if full is None:
        return GraphBacktestResponse(
            nodes=[], nScored=0, nExcludedBootstrap=0, rmseBp=0.0, zetaMean=0.0, zetaStd=0.0
        )

    universe = full.universe
    candidates: list[int] = []
    excluded = 0
    for i, node in enumerate(universe.nodes):
        if not full.calibrated[i]:
            continue
        if not full.priors_meta[i].valid_for_validation:
            excluded += 1  # bootstrap/flat prior: circular as a prior-vs-market test
            continue
        candidates.append(i)

    nodes: list[GraphBacktestNode] = []
    zetas: list[float] = []
    sq_sum = 0.0
    for i in candidates:
        node = universe.nodes[i]
        held = solve(state, request, hold_out=frozenset({node.name}))
        if held is None:
            continue
        calibrated_atm = float(full.obs_value_by_idx[i][0])
        post_atm = float(held.field.mean[i, 0])
        residual_bp = (post_atm - calibrated_atm) * 1e4
        obs_prec = held.obs_breakdowns[i].precision[0]
        zeta = float(
            standardized_residuals(
                np.array([calibrated_atm]),
                np.array([post_atm]),
                np.array([held.field.sd[i, 0] ** 2]),
                np.array([obs_prec]),
            )[0]
        )
        zetas.append(zeta)
        sq_sum += (post_atm - calibrated_atm) ** 2
        nodes.append(
            GraphBacktestNode(
                ticker=node.ticker,
                expiry=node.expiry,
                priorSource=full.priors_meta[i].source,
                calibratedAtmVol=calibrated_atm,
                postAtmVol=post_atm,
                residualBp=residual_bp,
                standardizedResidual=zeta,
                priorAtmVol=float(full.priors_meta[i].handles[0]),
            )
        )

    n = len(nodes)
    rmse_bp = float(np.sqrt(sq_sum / n) * 1e4) if n else 0.0
    zeta_arr = np.asarray(zetas, dtype=float)
    return GraphBacktestResponse(
        nodes=nodes,
        nScored=n,
        nExcludedBootstrap=excluded,
        rmseBp=rmse_bp,
        zetaMean=float(zeta_arr.mean()) if n else 0.0,
        zetaStd=float(zeta_arr.std()) if n else 0.0,
    )


def autotune(state: AppState, request: GraphExtrapolateRequest) -> GraphAutotuneResponse:
    """Choose etaScale by leave-one-node-out CV on the PRODUCTION solve.

    P6 re-point of the retired sandbox autotune: same AUTOTUNE_ETA_GRID, but
    the held-out prediction now runs the full production pipeline (transported
    priors, lit-calibration innovations, data-derived precision) — the tuned
    reach optimizes exactly the objective the LOO backtest above reports.

    Smooth-field only: eta is the directed-smoothness reach of the increment
    prior; the knob does not exist under the message operator. ValueError on
    that (and on a too-small candidate set) — the route maps it to a 400.
    """
    if request.propagationMode != "smooth_field":
        raise ValueError(
            "autotune tunes the smooth-field reach eta; propagationMode="
            f"{request.propagationMode!r} has no eta knob"
        )
    if request.syntheticObservations:
        # A pulse is hypothesis-firm on EVERY solve — hold_out only removes
        # real calibration observations, so LOO over pulses scores nothing.
        raise ValueError("autotune scores real calibrations, not what-if pulses")
    full = solve(state, request)
    if full is None:
        raise ValueError("empty universe — nothing to tune")
    universe = full.universe
    # Same candidate rule as the backtest: calibrated AND validation-clean
    # (a bootstrap prior would tune eta on a circular today-vs-today score).
    names = [
        node.name
        for i, node in enumerate(universe.nodes)
        if full.calibrated[i] and full.priors_meta[i].valid_for_validation
    ]
    if len(names) < 2:
        raise ValueError(
            "autotune needs at least two validation-clean calibrated lit "
            f"nodes (have {len(names)})"
        )

    candidates: list[AutotuneCandidate] = []
    for eta_scale in AUTOTUNE_ETA_GRID:
        params = request.model_copy(update={"etaScale": float(eta_scale)})
        sq_sum, scored = 0.0, 0
        for name in names:
            held = solve(state, params, hold_out=frozenset({name}))
            if held is None:
                continue
            i = universe.node_index(name)
            sq_sum += (float(held.field.mean[i, 0]) - float(full.obs_value_by_idx[i][0])) ** 2
            scored += 1
        if scored == 0:  # unreachable once `full` solved; keep the 400 honest
            raise ValueError("leave-one-out solve produced no held-out scores")
        rmse_bp = float(np.sqrt(sq_sum / scored) * 1e4)
        candidates.append(AutotuneCandidate(etaScale=float(eta_scale), rmseBp=rmse_bp))

    best = min(candidates, key=lambda c: c.rmseBp)
    return GraphAutotuneResponse(
        etaScale=best.etaScale, rmseBp=best.rmseBp, candidates=candidates
    )

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
from volfit.api.schemas import (
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

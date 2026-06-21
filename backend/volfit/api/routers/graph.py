"""Graph routes — universe lattice and sparse-observation propagation.

Backs the Graph Viewer: GET /graph/nodes serves the baseline lattice (the
universe over all tickers x expiries, mid fits, built lazily once — first
call pays the ~12 slice fits), POST /graph/solve takes handle *shifts* on
named nodes and returns per-node posterior ATM vol with credible bands.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import graph_extrapolation, graph_service
from volfit.api.schemas import (
    GraphAutotuneRequest,
    GraphAutotuneResponse,
    GraphExtrapolateRequest,
    GraphExtrapolateResponse,
    GraphNodeInfo,
    GraphNodesResponse,
    GraphSolveRequest,
    GraphSolveResponse,
)
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/graph/nodes", response_model=GraphNodesResponse)
def graph_nodes(request: Request) -> GraphNodesResponse:
    state = request.app.state.volfit
    universe = graph_service.ensure_universe(state)
    nodes = [
        GraphNodeInfo(
            ticker=smile.name[0],
            expiry=smile.name[1],
            t=smile.t,
            atmVol=float(universe.handles[i, 0]),
            skew=float(universe.handles[i, 1]),
            curvature=float(universe.handles[i, 2]),
            lit=state.node_lit(smile.name[0], smile.name[1]),
        )
        for i, smile in enumerate(universe.smiles)
    ]
    return GraphNodesResponse(nodes=nodes)


@router.post("/graph/solve", response_model=GraphSolveResponse)
def solve_graph(body: GraphSolveRequest, request: Request) -> GraphSolveResponse:
    try:
        return graph_service.solve_graph(request.app.state.volfit, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/graph/autotune", response_model=GraphAutotuneResponse)
def autotune_graph(body: GraphAutotuneRequest, request: Request) -> GraphAutotuneResponse:
    try:
        return graph_service.autotune_graph(request.app.state.volfit, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/graph/extrapolate", response_model=GraphExtrapolateResponse)
def extrapolate(body: GraphExtrapolateRequest, request: Request) -> GraphExtrapolateResponse:
    """Production prior-anchored extrapolation over the selected lit+dark universe
    (plan Phase 3): transported priors -> lit-calibration innovations -> graph
    posterior. Distinct from the manual-shift sandbox ``POST /graph/solve``."""
    return graph_extrapolation.extrapolate(request.app.state.volfit, body)

"""Graph routes — universe lattice and sparse-observation propagation.

Backs the Graph Viewer: GET /graph/nodes serves the baseline lattice (the
universe over all tickers x expiries, mid fits, built lazily once — first
call pays the ~12 slice fits), POST /graph/solve takes handle *shifts* on
named nodes and returns per-node posterior ATM vol with credible bands.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import graph_service
from volfit.api.schemas import (
    GraphAutotuneRequest,
    GraphAutotuneResponse,
    GraphNodeInfo,
    GraphNodesResponse,
    GraphSolveRequest,
    GraphSolveResponse,
)
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.get("/graph/nodes", response_model=GraphNodesResponse)
def graph_nodes(request: Request) -> GraphNodesResponse:
    universe = graph_service.ensure_universe(request.app.state.volfit)
    nodes = [
        GraphNodeInfo(
            ticker=smile.name[0],
            expiry=smile.name[1],
            t=smile.t,
            atmVol=float(universe.handles[i, 0]),
            skew=float(universe.handles[i, 1]),
            curvature=float(universe.handles[i, 2]),
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

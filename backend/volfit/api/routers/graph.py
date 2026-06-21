"""Graph routes — universe lattice and sparse-observation propagation.

Backs the Graph Viewer: GET /graph/nodes serves the baseline lattice (the
universe over all tickers x expiries, mid fits, built lazily once — first
call pays the ~12 slice fits), POST /graph/solve takes handle *shifts* on
named nodes and returns per-node posterior ATM vol with credible bands.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from volfit.api import (
    graph_backtest,
    graph_extrapolation,
    graph_reconstruct,
    graph_service,
)
from volfit.api.schemas import (
    GraphAutotuneRequest,
    GraphAutotuneResponse,
    GraphBacktestResponse,
    GraphEdgesRequest,
    GraphEdgesResponse,
    GraphExtrapolateRequest,
    GraphExtrapolateResponse,
    GraphNodeInfo,
    GraphNodesResponse,
    GraphNodeSmile,
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


@router.get(
    "/graph/extrapolate/nodes/{ticker}/{expiry}", response_model=GraphNodeSmile
)
def extrapolate_node_smile(
    ticker: str,
    expiry: str,
    request: Request,
    params: GraphExtrapolateRequest = Depends(),
) -> GraphNodeSmile:
    """One node's full reconstructed smile + prior/lit overlays + quote metrics
    (plan Phase 5, lazy per-node payload). Solver knobs come from query params."""
    try:
        return graph_reconstruct.node_smile(
            request.app.state.volfit, ticker, expiry, params
        )
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/graph/backtest", response_model=GraphBacktestResponse)
def backtest(body: GraphExtrapolateRequest, request: Request) -> GraphBacktestResponse:
    """Leave-one-node-out backtest over the validation-clean calibrated nodes
    (plan Phase 8): per-node residuals + an aggregate calibration summary."""
    return graph_backtest.backtest(request.app.state.volfit, body)


@router.get("/graph/edges", response_model=GraphEdgesResponse)
def get_graph_edges(request: Request) -> GraphEdgesResponse:
    """The persisted per-edge overrides (weight + beta); empty ⇒ auto-lattice."""
    return GraphEdgesResponse(edges=request.app.state.volfit.graph_edges())


@router.put("/graph/edges", response_model=GraphEdgesResponse)
def put_graph_edges(body: GraphEdgesRequest, request: Request) -> GraphEdgesResponse:
    """Replace the per-edge overrides (persisted). Empty list ⇒ back to the lattice."""
    state = request.app.state.volfit
    state.set_graph_edges(body.edges)
    return GraphEdgesResponse(edges=state.graph_edges())


@router.get("/graph/edges/lattice", response_model=GraphEdgesResponse)
def get_lattice_edges(request: Request) -> GraphEdgesResponse:
    """The auto-lattice edges as editable rows — the editor's 'seed from lattice'."""
    return GraphEdgesResponse(edges=graph_extrapolation.lattice_edges(request.app.state.volfit))

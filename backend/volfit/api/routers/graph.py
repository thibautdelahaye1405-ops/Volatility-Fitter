"""POST /graph/solve — propagate sparse smile observations to the universe.

Backs the Graph Viewer: the universe (all tickers x expiries, mid fits) is
built lazily once, observations arrive as handle *shifts* on named nodes,
and the response carries per-node posterior ATM vol with credible bands.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import service
from volfit.api.schemas import GraphSolveRequest, GraphSolveResponse
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.post("/graph/solve", response_model=GraphSolveResponse)
def solve_graph(body: GraphSolveRequest, request: Request) -> GraphSolveResponse:
    try:
        return service.solve_graph(request.app.state.volfit, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

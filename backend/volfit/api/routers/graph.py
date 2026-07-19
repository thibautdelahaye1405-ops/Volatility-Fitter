"""Graph routes — universe lattice and sparse-observation propagation.

Backs the Graph Viewer: GET /graph/nodes serves the baseline lattice (the
universe over all tickers x expiries, mid fits, built lazily once — first
call pays the ~12 slice fits), POST /graph/solve takes handle *shifts* on
named nodes and returns per-node posterior ATM vol with credible bands.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from volfit.api import (
    graph_backtest,
    graph_blocks,
    graph_extrapolation,
    graph_lv,
    graph_preflight,
    graph_reconstruct,
    graph_select,
    graph_service,
)
from volfit.api.schemas_affine import AffineFitRequest, AffineFitResponse
from volfit.api.schemas import (
    GraphAutotuneRequest,
    GraphAutotuneResponse,
    GraphBacktestResponse,
    GraphBlockRule,
    GraphBlockRuleResponse,
    GraphEdgesRequest,
    GraphEdgesResponse,
    GraphExtrapolateRequest,
    GraphExtrapolateResponse,
    GraphMessageConfigActivateRequest,
    GraphMessageConfigResponse,
    GraphMessageEdgesRequest,
    GraphMessageEdgesResponse,
    GraphNodeInfo,
    GraphNodesResponse,
    GraphNodeSmile,
    GraphObservationPlanRequest,
    GraphObservationPlanResponse,
    GraphPreflightResponse,
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


@router.post("/graph/preflight", response_model=GraphPreflightResponse)
def preflight_graph(
    body: GraphExtrapolateRequest, request: Request
) -> GraphPreflightResponse:
    """Pre-run diagnostics (P5b U5): a DRY RUN over the same request Run would
    ship — nothing fitted, solved, or recorded. Run is blocked only on
    blocker-severity issues."""
    return graph_preflight.preflight(request.app.state.volfit, body)


@router.get(
    "/graph/extrapolate/nodes/{ticker}/{expiry}", response_model=GraphNodeSmile
)
def extrapolate_node_smile(
    ticker: str,
    expiry: str,
    request: Request,
    params: GraphExtrapolateRequest = Depends(),
    calendarPolicyOverrides: str | None = None,
) -> GraphNodeSmile:
    """One node's full reconstructed smile + prior/lit overlays + quote metrics
    (plan Phase 5, lazy per-node payload). Solver knobs come from query params;
    the U2 per-ticker policy map is a nested object FastAPI cannot lift from a
    query string via ``Depends()``, so it travels as an explicit JSON-string
    param and is merged through model revalidation (the schema's before-
    validator parses it) — the drill-in must reconstruct with EXACTLY the
    knobs the solved table used."""
    if calendarPolicyOverrides:
        params = GraphExtrapolateRequest.model_validate(
            {**params.model_dump(), "calendarPolicyOverrides": calendarPolicyOverrides}
        )
    try:
        return graph_reconstruct.node_smile(
            request.app.state.volfit, ticker, expiry, params
        )
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/graph/observation-plan", response_model=GraphObservationPlanResponse)
def observation_plan(
    body: GraphObservationPlanRequest, request: Request
) -> GraphObservationPlanResponse:
    """Rank the non-observed nodes by closed-form exposure-weighted
    posterior-variance reduction — "which dark node to quote next"
    (R3 item 13; rank-one Schur on the solved posterior, no refit)."""
    return graph_select.observation_plan(request.app.state.volfit, body)


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


@router.get("/graph/edges/messages", response_model=GraphMessageEdgesResponse)
def get_message_edges(request: Request) -> GraphMessageEdgesResponse:
    """The DRAFT message-relation rows (falling back to the active config —
    editing starts from what runs; U6 lifecycle). Empty ⇒ auto relations."""
    return GraphMessageEdgesResponse(
        edges=request.app.state.volfit.graph_message_draft_edges()
    )


@router.put("/graph/edges/messages", response_model=GraphMessageEdgesResponse)
def put_message_edges(
    body: GraphMessageEdgesRequest, request: Request
) -> GraphMessageEdgesResponse:
    """Stage rows on the DRAFT config (U6): the solve keeps using the ACTIVE
    config until Activate. Empty list ⇒ a draft of the auto relations."""
    state = request.app.state.volfit
    state.set_graph_message_draft(body.edges)
    return GraphMessageEdgesResponse(edges=state.graph_message_draft_edges())


@router.get("/graph/config/messages", response_model=GraphMessageConfigResponse)
def get_message_config(request: Request) -> GraphMessageConfigResponse:
    """Both U6 lifecycle slots (draft + active), rows included."""
    draft, active = request.app.state.volfit.graph_message_config()
    return GraphMessageConfigResponse(draft=draft, active=active)


@router.post("/graph/config/messages/activate", response_model=GraphMessageConfigResponse)
def activate_message_config(
    body: GraphMessageConfigActivateRequest, request: Request
) -> GraphMessageConfigResponse:
    """Promote the draft to ACTIVE (event-logged); 400 when nothing staged."""
    state = request.app.state.volfit
    try:
        state.activate_message_config(body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    draft, active = state.graph_message_config()
    return GraphMessageConfigResponse(draft=draft, active=active)


@router.post("/graph/config/messages/revert", response_model=GraphMessageConfigResponse)
def revert_message_config(request: Request) -> GraphMessageConfigResponse:
    """Discard the draft — back to a clean copy of the active config."""
    state = request.app.state.volfit
    state.revert_message_config()
    draft, active = state.graph_message_config()
    return GraphMessageConfigResponse(draft=draft, active=active)


@router.get("/graph/edges/messages/auto", response_model=GraphMessageEdgesResponse)
def get_auto_message_edges(request: Request) -> GraphMessageEdgesResponse:
    """The auto relations over the selected universe as editable rows — the
    message editor's 'seed from auto relations' source."""
    from volfit.api.graph_message import auto_message_edge_rows

    return GraphMessageEdgesResponse(
        edges=auto_message_edge_rows(request.app.state.volfit)
    )


#: Offline benchmark-pack artifacts (backtest/results/benchmark). The
#: pre-registered multi-regime story runs OFFLINE (run_benchmark_pack.ps1);
#: this route only SERVES the newest emitted HTML so the validation drawer
#: can link it. Module-level so tests can point it at a temp dir.
BENCHMARK_ARTIFACT_DIR = (
    Path(__file__).resolve().parents[3] / "backtest" / "results" / "benchmark"
)


@router.get("/graph/benchmark/artifact")
def benchmark_artifact() -> FileResponse:
    """The newest offline benchmark-pack HTML artifact; 404 until a pack ran."""
    candidates = (
        sorted(
            BENCHMARK_ARTIFACT_DIR.glob("*.html"),
            key=lambda p: p.stat().st_mtime,
        )
        if BENCHMARK_ARTIFACT_DIR.is_dir()
        else []
    )
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="no benchmark artifact — run backend/backtest/run_benchmark_pack.ps1",
        )
    return FileResponse(candidates[-1], media_type="text/html")


@router.get("/graph/edges/blocks", response_model=GraphBlockRuleResponse)
def get_graph_blocks(request: Request) -> GraphBlockRuleResponse:
    """The persisted ticker-block rule VERBATIM (an empty rule when none is
    stored) plus the size of its expansion over the current selected universe."""
    state = request.app.state.volfit
    rule = state.graph_block_rule() or GraphBlockRule()
    return GraphBlockRuleResponse(
        rule=rule, expandedCount=len(graph_blocks.expand_block_rule(state, rule))
    )


@router.put("/graph/edges/blocks", response_model=GraphBlockRuleResponse)
def put_graph_blocks(body: GraphBlockRule, request: Request) -> GraphBlockRuleResponse:
    """Persist the block rule AND install its expansion as the per-edge overrides
    in one step, so /graph/edges immediately serves the expanded list. An
    ALL-EMPTY rule clears both — back to the auto-lattice."""
    state = request.app.state.volfit
    expanded = graph_blocks.expand_block_rule(state, body)
    state.set_graph_block_rule(None if body.is_empty() else body, expanded)
    return GraphBlockRuleResponse(
        rule=state.graph_block_rule() or GraphBlockRule(), expandedCount=len(expanded)
    )


@router.post("/graph/extrapolate/lv/{ticker}", response_model=AffineFitResponse)
def extrapolate_lv(
    ticker: str, body: AffineFitRequest, request: Request
) -> AffineFitResponse:
    """Project the ticker's graph-extrapolated smiles onto an affine Local-Vol
    surface (plan Phase 9 / Amendment G): the extrapolation is the target, then a
    standard LV calibration runs against it."""
    return graph_lv.project_to_lv(request.app.state.volfit, ticker.upper(), body)

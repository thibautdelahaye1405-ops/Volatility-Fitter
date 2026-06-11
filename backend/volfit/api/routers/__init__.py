"""Thin HTTP/WebSocket routers over volfit.api.service (ROADMAP Phase 5)."""

from volfit.api.routers.edits import router as edits_router
from volfit.api.routers.fit import router as fit_router
from volfit.api.routers.graph import router as graph_router
from volfit.api.routers.scenario import router as scenario_router
from volfit.api.routers.smiles import router as smiles_router
from volfit.api.routers.universe import router as universe_router

#: Routers in include order for create_app.
ALL_ROUTERS = (
    universe_router,
    smiles_router,
    edits_router,
    fit_router,
    graph_router,
    scenario_router,
)

__all__ = [
    "ALL_ROUTERS",
    "edits_router",
    "fit_router",
    "graph_router",
    "scenario_router",
    "smiles_router",
    "universe_router",
]

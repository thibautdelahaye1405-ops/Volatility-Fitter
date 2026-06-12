"""Thin HTTP/WebSocket routers over volfit.api.service (ROADMAP Phase 5-6)."""

from volfit.api.routers.edits import router as edits_router
from volfit.api.routers.fit import router as fit_router
from volfit.api.routers.forwards import router as forwards_router
from volfit.api.routers.graph import router as graph_router
from volfit.api.routers.localvol import router as localvol_router
from volfit.api.routers.scenario import router as scenario_router
from volfit.api.routers.settings import router as settings_router
from volfit.api.routers.smiles import router as smiles_router
from volfit.api.routers.term import router as term_router
from volfit.api.routers.universe import router as universe_router

#: Routers in include order for create_app.
ALL_ROUTERS = (
    universe_router,
    smiles_router,
    edits_router,
    fit_router,
    forwards_router,
    graph_router,
    localvol_router,
    scenario_router,
    settings_router,
    term_router,
)

__all__ = [
    "ALL_ROUTERS",
    "edits_router",
    "fit_router",
    "forwards_router",
    "graph_router",
    "localvol_router",
    "scenario_router",
    "settings_router",
    "smiles_router",
    "term_router",
    "universe_router",
]

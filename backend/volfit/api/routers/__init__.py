"""Thin HTTP/WebSocket routers over volfit.api.service (ROADMAP Phase 5-6)."""

from volfit.api.routers.affine import router as affine_router
from volfit.api.routers.asof import router as asof_router
from volfit.api.routers.datasource import router as datasource_router
from volfit.api.routers.edits import router as edits_router
from volfit.api.routers.events import router as events_router
from volfit.api.routers.fit import router as fit_router
from volfit.api.routers.forwards import router as forwards_router
from volfit.api.routers.graph import router as graph_router
from volfit.api.routers.history import router as history_router
from volfit.api.routers.localvol import router as localvol_router
from volfit.api.routers.massive_iv import router as massive_iv_router
from volfit.api.routers.priors import router as priors_router
from volfit.api.routers.quality import router as quality_router
from volfit.api.routers.scenario import router as scenario_router
from volfit.api.routers.settings import router as settings_router
from volfit.api.routers.smiles import router as smiles_router
from volfit.api.routers.spot import router as spot_router
from volfit.api.routers.surface import router as surface_router
from volfit.api.routers.term import router as term_router
from volfit.api.routers.universe import router as universe_router
from volfit.api.routers.varswap import router as varswap_router
from volfit.api.routers.workflow import router as workflow_router

#: Routers in include order for create_app.
ALL_ROUTERS = (
    universe_router,
    datasource_router,
    asof_router,
    smiles_router,
    edits_router,
    events_router,
    fit_router,
    affine_router,
    forwards_router,
    graph_router,
    history_router,
    localvol_router,
    massive_iv_router,
    priors_router,
    quality_router,
    scenario_router,
    settings_router,
    spot_router,
    surface_router,
    term_router,
    varswap_router,
    workflow_router,
)

__all__ = [
    "ALL_ROUTERS",
    "affine_router",
    "asof_router",
    "datasource_router",
    "edits_router",
    "events_router",
    "fit_router",
    "forwards_router",
    "graph_router",
    "history_router",
    "localvol_router",
    "massive_iv_router",
    "priors_router",
    "quality_router",
    "scenario_router",
    "settings_router",
    "smiles_router",
    "spot_router",
    "surface_router",
    "term_router",
    "universe_router",
    "varswap_router",
    "workflow_router",
]

"""volfit FastAPI application factory (ROADMAP Phase 5).

`create_app(reference_date)` wires AppState (provider + caches) onto
`app.state.volfit` and includes the thin routers; tests pin the reference
date for determinism while the module-level `app` (used by uvicorn / serve.py)
defaults to today. CORS is open to the Vite dev server only.
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from volfit.api.routers import ALL_ROUTERS
from volfit.api.state import AppState

#: Vite dev-server origins allowed to call the API from the browser.
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app(reference_date: date | None = None) -> FastAPI:
    """Build the API app around one AppState instance."""
    app = FastAPI(title="volfit")
    app.state.volfit = AppState(reference_date or date.today())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in ALL_ROUTERS:
        app.include_router(router)
    return app


#: Uvicorn entry point: `uvicorn volfit.api.app:app` (see backend/serve.py).
app = create_app()

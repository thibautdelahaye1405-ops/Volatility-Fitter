"""volfit FastAPI application factory (ROADMAP Phase 5).

`create_app(reference_date, provider)` wires AppState (provider + caches)
onto `app.state.volfit` and includes the thin routers; tests pin the
reference date for determinism while the module-level `app` (used by
uvicorn) defaults to today + synthetic data. serve.py builds its own app to
select a live provider from the environment. CORS is open to the Vite dev
server only.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from volfit.api.routers import ALL_ROUTERS
from volfit.api.scheduler import Scheduler
from volfit.api.state import AppState
from volfit.data.provider import OptionChainProvider

#: Vite dev-server origins allowed to call the API from the browser.
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app(
    reference_date: date | None = None,
    provider: OptionChainProvider | None = None,
    store_path: str | os.PathLike | None = None,
    providers: dict[str, OptionChainProvider] | None = None,
    active_source: str | None = None,
    enable_scheduler: bool = False,
) -> FastAPI:
    """Build the API app around one AppState instance.

    `provider=None` keeps the offline SyntheticProvider default; pass a
    YahooProvider (or any OptionChainProvider) to serve live data. Pass
    `providers` (a {id: provider} registry) + `active_source` for the in-app
    Data Source selector (serve.py does this). `store_path` (an SQLite file)
    opts in to fit-history persistence (volfit.api.history); None keeps the
    app side-effect free.
    """
    state = AppState(
        reference_date or date.today(),
        provider=provider,
        store_path=store_path,
        providers=providers,
        active_source=active_source,
    )
    #: Timed spot/options fetch scheduler — created always (so /scheduler reports
    #: the modes) but the thread runs only when enabled (serve.py turns it on;
    #: the test app and offline mode never fetch in the background).
    state.scheduler = Scheduler(state)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if enable_scheduler:
            state.scheduler.start()
        try:
            yield
        finally:
            state.scheduler.stop()

    app = FastAPI(title="volfit", lifespan=lifespan)
    app.state.volfit = state
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

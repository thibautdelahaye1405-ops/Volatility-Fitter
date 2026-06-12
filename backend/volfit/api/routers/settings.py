"""GET/PUT /settings/fit — global slice-fit hyperparameters (Phase 6 panel).

The Smile Viewer's hyperparameter panel reads and writes these. A PUT with
changed values bumps AppState's settings version (part of every fit-cache
key), so all subsequent fetches refit under the new hyperparameters while
warm caches for the old settings stay valid for undo-style flips back.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from volfit.api.schemas import FitSettings

router = APIRouter()


@router.get("/settings/fit", response_model=FitSettings)
def get_fit_settings(request: Request) -> FitSettings:
    return request.app.state.volfit.fit_settings()


@router.put("/settings/fit", response_model=FitSettings)
def put_fit_settings(body: FitSettings, request: Request) -> FitSettings:
    return request.app.state.volfit.set_fit_settings(body)

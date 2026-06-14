"""GET/PUT /settings/fit + /settings/options — global settings (Phase 6 + 10).

* ``/settings/fit`` — the live slice-fit hyperparameters (the Parametric aside
  + the Options "calibration defaults" section). A changed PUT bumps AppState's
  settings version (part of every fit-cache key), so all subsequent fetches
  refit while warm caches for the old settings stay valid for flips back.
* ``/settings/options`` — the global meta / UX settings + engine defaults (the
  Options workspace, ROADMAP Phase 10). Only the calibration-affecting field
  (calendarWeight) bumps the options version; the rest are defaults / display
  toggles read live, so toggling them never invalidates warm fits.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from volfit.api.schemas import FitSettings, OptionsSettings

router = APIRouter()


@router.get("/settings/fit", response_model=FitSettings)
def get_fit_settings(request: Request) -> FitSettings:
    return request.app.state.volfit.fit_settings()


@router.put("/settings/fit", response_model=FitSettings)
def put_fit_settings(body: FitSettings, request: Request) -> FitSettings:
    return request.app.state.volfit.set_fit_settings(body)


@router.get("/settings/options", response_model=OptionsSettings)
def get_options_settings(request: Request) -> OptionsSettings:
    return request.app.state.volfit.options()


@router.put("/settings/options", response_model=OptionsSettings)
def put_options_settings(body: OptionsSettings, request: Request) -> OptionsSettings:
    return request.app.state.volfit.set_options(body)

"""POST /scenario/ssr — vol-spot dynamics scenario on one fitted smile.

Backs the product's vol-spot dynamics toggle (SSR on ATM vol, sticky strike,
sticky local vol): the fitted slice is shifted for a spot move under the
requested regime via volfit.dynamics.ssr.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api import service
from volfit.api.schemas import ScenarioRequest, ScenarioResponse
from volfit.api.state import UnknownNodeError

router = APIRouter()


@router.post("/scenario/ssr", response_model=ScenarioResponse)
def run_scenario(body: ScenarioRequest, request: Request) -> ScenarioResponse:
    try:
        return service.run_scenario(request.app.state.volfit, body)
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

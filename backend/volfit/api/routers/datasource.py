"""GET /datasources, POST /datasource/{id} — the Data Source selector.

Lists the configured market-data feeds (Yahoo / Bloomberg / Massive /
Synthetic) with a status light each and switches the active one at runtime.
Thin wrapper over volfit.api.datasource; the heavy lifting (probing, cache,
cache-clearing switch) lives there and on AppState.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from volfit.api.datasource import datasources_payload, switch_source
from volfit.api.state import UnknownNodeError

router = APIRouter()


class DataSource(BaseModel):
    """One selectable feed and its current status light."""

    id: str
    label: str
    status: str  # "green" (real-time) | "amber" (delayed) | "red" (unavailable)
    detail: str
    active: bool


class DataSourcesResponse(BaseModel):
    active: str
    sources: list[DataSource]


@router.get("/datasources", response_model=DataSourcesResponse)
def get_datasources(
    request: Request, refresh: bool = Query(False)
) -> DataSourcesResponse:
    """All configured sources with status lights (`?refresh=true` re-probes)."""
    return DataSourcesResponse(**datasources_payload(request.app.state.volfit, refresh))


@router.post("/datasource/{source_id}", response_model=DataSourcesResponse)
def post_datasource(source_id: str, request: Request) -> DataSourcesResponse:
    """Switch the active data source; refetches on the new feed."""
    try:
        return DataSourcesResponse(
            **switch_source(request.app.state.volfit, source_id)
        )
    except UnknownNodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

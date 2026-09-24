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


class StreamHealth(BaseModel):
    """A streaming source's live health (volfit.data.massive_stream.stream_stats):
    the socket(s), the acknowledged / refused / over-cap counts against the
    cap, the message rate over the last 10 s, ages in seconds, the last error,
    the per-ticker served flags and the light's own reading."""

    connected: bool
    running: bool = True
    connections: int = 1
    connectedCount: int = 0
    url: str | None = None
    cluster: str | None = None  # "realtime" | "delayed"
    messages: int = 0
    quotes: int = 0
    rate: float = 0.0  # messages per second (10-s window)
    lastMessageAge: float | None = None
    lastQuoteAge: float | None = None
    lastMessageUtc: str | None = None
    reconnects: int = 0
    lastError: str | None = None
    lastErrorAge: float | None = None
    authFailed: bool = False
    subscribed: int = 0
    acknowledged: int = 0
    refused: int = 0
    overCap: int = 0
    requested: int = 0
    cap: int = 0
    sessionOpen: bool = False
    tickers: dict[str, bool] = {}
    #: The allocation policy's answer (volfit.data.stream_allocation): per
    #: ticker ``{requested, live, focus}``, the focus nodes ("TICKER|ISO"),
    #: the per-ticker floor and the REST cadence behind the book.
    allocation: dict[str, dict[str, int]] = {}
    focus: list[str] = []
    floor: int = 0
    restSeconds: float | None = None
    level: str = "amber"
    detail: str = ""


class DataSource(BaseModel):
    """One selectable feed and its current status light."""

    id: str
    label: str
    status: str  # "green" (real-time) | "amber" (delayed) | "red" (unavailable)
    detail: str
    active: bool
    #: The active tickers this source serves now — pinned to it, or following
    #: it as the universe's default (volfit.api.state_sources).
    tickers: list[str] = []
    #: The live-stream health while the source streams (None otherwise).
    stream: StreamHealth | None = None


class DataAge(BaseModel):
    """Worst loaded live-chain age across the active universe (data_age)."""

    ageMin: float
    level: str  # "fresh" | "amber" | "red" (OptionsSettings thresholds)
    label: str  # human age: "4m" / "13.5h" / "3.2d"
    worstTicker: str


class DataSourcesResponse(BaseModel):
    active: str
    sources: list[DataSource]
    #: None when not applicable: historical as-of, nothing fetched yet, or
    #: exact-price (synthetic) chains only.
    dataAge: DataAge | None = None


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

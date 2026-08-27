"""Snapshot-file endpoints (UI shell v2 wave 3, A2) — quotes + prevailing
calibrations as a FILE, and the ``file`` data source that serves them back.

* ``POST /snapshot/export``  the ``volfit-snapshot/1`` bundle of the loaded
                             chains + committed fits (cached state only — never
                             fetches, never refits); ``tickers`` narrows it.
* ``POST /snapshot/import``  load a bundle: registers / extends the ``file``
                             data source, switches to it, points the universe
                             at the file's tickers and reinstalls the embedded
                             calibrations as the committed fits (provenance
                             ``loaded``). 422 with a diagnostic on a file this
                             server cannot read.
Logic in volfit.api.snapshot_files.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from volfit.api import snapshot_files as svc

router = APIRouter(tags=["snapshot"])


class SnapshotExportRequest(BaseModel):
    tickers: list[str] | None = None
    fitMode: str | None = None


class SnapshotImportResult(BaseModel):
    source: str
    label: str
    asOf: str
    tickers: list[str]
    calibrations: int
    failed: list[str]


@router.post("/snapshot/export")
def export_snapshot(request: Request, body: SnapshotExportRequest | None = None) -> JSONResponse:
    state = request.app.state.volfit
    b = body or SnapshotExportRequest()
    bundle = svc.export_snapshot(state, b.tickers, b.fitMode)
    if not bundle["tickers"]:
        raise HTTPException(status_code=409, detail="nothing to snapshot: no chain has been fetched yet")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f'attachment; filename="volfit_snapshot_{stamp}.json"'},
    )


@router.post("/snapshot/import", response_model=SnapshotImportResult)
def import_snapshot(
    request: Request, body: dict = Body(...), name: str = Query("snapshot")
) -> SnapshotImportResult:
    try:
        return SnapshotImportResult(**svc.import_snapshot(request.app.state.volfit, body, name))
    except svc.SnapshotFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

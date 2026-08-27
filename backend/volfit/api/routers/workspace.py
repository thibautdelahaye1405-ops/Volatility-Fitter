"""Workspace-file endpoints (UI shell v2 wave 3, A1) — the File menu's server side.

* ``GET  /workspace/export``  the ``volfit-workspace/1`` bundle (backend doc filled;
                              the client merges its shell state before saving).
* ``POST /workspace/import``  install a bundle (or a bare backend doc); 422 with
                              a schema / version diagnostic on a file this server
                              cannot restore. A state RESET (see workspace.py).
* ``POST /workspace/new``     File ▸ New — code-default settings on the current
                              ticker set.
* ``GET  /workspace/status``  content fingerprint (dirty tracking) + counts.
* ``GET/POST/GET/DELETE /workspaces[/{name}]``  the named store (VOLFIT_DB):
                              list · save the posted bundle · read one · delete.
Logic in volfit.api.workspace_files.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from volfit.api import workspace_files as svc
from volfit.api.schemas_workspace import (
    WorkspaceImportResult,
    WorkspaceListResponse,
    WorkspaceSavedResponse,
    WorkspaceStatus,
)

router = APIRouter(tags=["workspace"])


def _state(request: Request):
    return request.app.state.volfit


@router.get("/workspace/export")
def export_workspace(request: Request) -> JSONResponse:
    return JSONResponse(content=svc.export_bundle(_state(request)))


@router.get("/workspace/status", response_model=WorkspaceStatus)
def workspace_status(request: Request) -> WorkspaceStatus:
    return svc.status(_state(request))


@router.post("/workspace/import", response_model=WorkspaceImportResult)
def import_workspace(request: Request, body: dict = Body(...)) -> WorkspaceImportResult:
    try:
        return svc.import_bundle(_state(request), body)
    except svc.WorkspaceFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/workspace/new", response_model=WorkspaceStatus)
def new_workspace(request: Request) -> WorkspaceStatus:
    return svc.new_workspace(_state(request))


# ------------------------------------------------------------- named store
@router.get("/workspaces", response_model=WorkspaceListResponse)
def list_saved(request: Request) -> WorkspaceListResponse:
    return svc.saved(_state(request))


@router.post("/workspaces/{name}", response_model=WorkspaceSavedResponse)
def save_named(name: str, request: Request, body: dict = Body(...)) -> WorkspaceSavedResponse:
    try:
        return svc.save_named(_state(request), name, body)
    except (ValueError, svc.WorkspaceFormatError) as exc:  # no store / empty name / bad file
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/workspaces/{name}")
def load_named(name: str, request: Request) -> JSONResponse:
    try:
        return JSONResponse(content=svc.load_named(_state(request), name))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no saved workspace named {name!r}") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.delete("/workspaces/{name}", response_model=WorkspaceListResponse)
def delete_named(name: str, request: Request) -> WorkspaceListResponse:
    try:
        return svc.delete_named(_state(request), name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

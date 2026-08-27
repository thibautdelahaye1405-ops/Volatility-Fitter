"""Wire schemas of the workspace-file endpoints (UI shell v2 wave 3, A1).

The bundle itself (``volfit-workspace/1``) is a plain dict — the backend
workspace doc is already JSON-safe by construction (``build_doc``) and the
shell part is opaque to the server — so only the small envelopes are typed.
"""

from __future__ import annotations

from pydantic import BaseModel


class WorkspaceStatus(BaseModel):
    """Dirty-tracking handle of the live workspace: a content fingerprint of
    the backend workspace doc (stable across identical states, so a
    save → reopen round trip reads back as clean)."""

    fingerprint: str
    tickers: int
    sessions: int
    activePriors: int


class WorkspaceImportResult(WorkspaceStatus):
    """What an import installed (counts) + the resulting fingerprint."""

    schemaTag: str  # the bundle schema tag that was accepted
    savedAt: str | None


class WorkspaceEntry(BaseModel):
    name: str
    savedTs: str


class WorkspaceListResponse(BaseModel):
    """Named workspaces stored on the server (empty when no store)."""

    entries: list[WorkspaceEntry]
    storeEnabled: bool  # False when VOLFIT_DB is unset — save/load disabled


class WorkspaceSavedResponse(WorkspaceListResponse):
    name: str
    savedTs: str

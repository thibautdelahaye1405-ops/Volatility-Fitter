"""Workspace FILES — export / import / new / named store (UI shell v2 wave 3, A1).

The File menu saves and loads the whole configuration as one bundle::

    { "schema": "volfit-workspace/1", "savedAt": ISO, "app": {"version"},
      "backend": <volfit.api.workspace.build_doc>,   # the desk's authored state
      "shell":   {...} }                               # opaque to the server

* ``export_bundle`` wraps ``build_doc`` (settings, universe picks, lit/dark,
  forward policies, quote / var-swap edit sessions, priors, filter states,
  graph overrides, spot shifts, fit mode, as-of); the frontend fills ``shell``.
* ``import_bundle`` validates the envelope (schema family + major version,
  doc version) and installs the backend doc through ``restore_workspace`` — a
  state RESET with lazy universe re-resolution (no network at import time).
  Accepts either the full bundle or a bare backend doc (``{"v": …}``).
* ``new_workspace`` restores an EMPTY doc: code-default settings, no edits /
  priors / overrides, the CURRENT ticker set kept (ladders re-resolve on the
  default rule) — the File ▸ New verb.
* ``fingerprint`` is the dirty-tracking handle: a SHA-1 over the canonical
  JSON of ``build_doc``. Identical authored state ⇒ identical fingerprint, so
  a save → new → open round trip reads back as clean.
* The named store (``VOLFIT_DB``) keeps bundles verbatim next to the named
  universes (``volfit.data.workspaces``) for "Save to server…".
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from volfit import __version__
from volfit.api.schemas_workspace import (
    WorkspaceEntry,
    WorkspaceImportResult,
    WorkspaceListResponse,
    WorkspaceSavedResponse,
    WorkspaceStatus,
)
from volfit.api.workspace import WORKSPACE_DOC_VERSION
from volfit.data.store import VolStore
from volfit.data.workspaces import (
    delete_workspace,
    list_workspaces,
    load_workspace,
    save_workspace,
)

#: Bundle schema tag: family "volfit-workspace", major version 1. A reader
#: accepts any bundle of the same family whose major version it knows.
WORKSPACE_SCHEMA = "volfit-workspace/1"
_SCHEMA_FAMILY, _SCHEMA_MAJOR = WORKSPACE_SCHEMA.split("/")


class WorkspaceFormatError(ValueError):
    """The bundle is not something this server can restore (→ HTTP 422)."""


# ------------------------------------------------------------------ export
def export_bundle(state) -> dict:
    """The bundle with the backend doc filled in (``shell`` = None: the
    frontend owns that part and merges its own state before saving)."""
    return {
        "schema": WORKSPACE_SCHEMA,
        "savedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "app": {"version": __version__},
        "backend": state.workspace_doc(),
        "shell": None,
    }


def fingerprint(state) -> str:
    """SHA-1 of the canonical JSON of the workspace doc (see module doc)."""
    return fingerprint_of_doc(state.workspace_doc())


def fingerprint_of_doc(doc: dict) -> str:
    canon = json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()


def status(state) -> WorkspaceStatus:
    doc = state.workspace_doc()
    return WorkspaceStatus(
        fingerprint=fingerprint_of_doc(doc),
        tickers=len(doc["universe"]["tickers"]),
        sessions=sum(len(per) for per in doc["sessions"].values()),
        activePriors=len(doc["activePriors"]),
    )


# ------------------------------------------------------------------ import
def _backend_doc_of(body) -> tuple[dict, str, str | None]:
    """Validate the envelope; return ``(backend_doc, schema_tag, saved_at)``.

    Raises WorkspaceFormatError with a diagnostic naming what was wrong
    (schema family / major version / doc version / shape)."""
    if not isinstance(body, dict):
        raise WorkspaceFormatError("workspace file must be a JSON object")
    if "backend" in body or "schema" in body:
        tag = body.get("schema")
        if not isinstance(tag, str) or "/" not in tag:
            raise WorkspaceFormatError("missing or malformed 'schema' tag (expected 'volfit-workspace/1')")
        family, _, major = tag.partition("/")
        if family != _SCHEMA_FAMILY:
            raise WorkspaceFormatError(f"not a workspace file: schema {tag!r} (expected '{WORKSPACE_SCHEMA}')")
        if major != _SCHEMA_MAJOR:
            raise WorkspaceFormatError(
                f"workspace schema {tag!r} is not supported by this server (supports '{WORKSPACE_SCHEMA}')"
            )
        doc = body.get("backend")
        if not isinstance(doc, dict):
            raise WorkspaceFormatError("workspace file carries no 'backend' document")
        saved_at = body.get("savedAt") if isinstance(body.get("savedAt"), str) else None
    else:
        doc, tag, saved_at = body, "backend-doc", None
    v = doc.get("v")
    if not isinstance(v, int):
        raise WorkspaceFormatError("backend document has no integer 'v' version")
    if v > WORKSPACE_DOC_VERSION:
        raise WorkspaceFormatError(
            f"backend document version {v} is newer than this server supports ({WORKSPACE_DOC_VERSION})"
        )
    return doc, tag, saved_at


def import_bundle(state, body) -> WorkspaceImportResult:
    """Validate + install a bundle (or bare doc); see the module docstring."""
    doc, tag, saved_at = _backend_doc_of(body)
    try:
        state.restore_workspace(doc)
    except (KeyError, TypeError, ValueError) as exc:  # a malformed inner doc
        raise WorkspaceFormatError(f"backend document could not be restored: {exc}") from exc
    st = status(state)
    state.log_event("workspace_import", payload={"schema": tag, "savedAt": saved_at})
    return WorkspaceImportResult(**st.model_dump(), schemaTag=tag, savedAt=saved_at)


def new_workspace(state) -> WorkspaceStatus:
    """File ▸ New: code-default settings on the current ticker set."""
    tickers = list(state.active_tickers())
    state.restore_workspace({"v": WORKSPACE_DOC_VERSION, "universe": {"tickers": tickers}})
    state.log_event("workspace_new", payload={"tickers": len(tickers)})
    return status(state)


# ------------------------------------------------------------- named store
def _store_required(state) -> None:
    if state.store_path is None:
        raise ValueError("fit-history store not configured (set VOLFIT_DB)")


def saved(state) -> WorkspaceListResponse:
    if state.store_path is None:
        return WorkspaceListResponse(entries=[], storeEnabled=False)
    with VolStore(state.store_path) as store:
        return WorkspaceListResponse(
            entries=[WorkspaceEntry(**e) for e in list_workspaces(store)], storeEnabled=True
        )


def save_named(state, name: str, bundle: dict) -> WorkspaceSavedResponse:
    """Store a bundle verbatim under ``name`` (validated first so a broken
    file can never be saved — the name is the desk's, the content ours)."""
    _store_required(state)
    name = name.strip()
    if not name:
        raise ValueError("workspace name must not be empty")
    _backend_doc_of(bundle)
    with VolStore(state.store_path) as store:
        ts = save_workspace(store, name, bundle)
        entries = [WorkspaceEntry(**e) for e in list_workspaces(store)]
    state.log_event("workspace_save", scope=name)
    return WorkspaceSavedResponse(entries=entries, storeEnabled=True, name=name, savedTs=ts)


def load_named(state, name: str) -> dict:
    """The stored bundle (KeyError when absent) — the client imports it."""
    _store_required(state)
    with VolStore(state.store_path) as store:
        bundle = load_workspace(store, name)
    if bundle is None:
        raise KeyError(name)
    return bundle


def delete_named(state, name: str) -> WorkspaceListResponse:
    _store_required(state)
    with VolStore(state.store_path) as store:
        delete_workspace(store, name)
        entries = [WorkspaceEntry(**e) for e in list_workspaces(store)]
    return WorkspaceListResponse(entries=entries, storeEnabled=True)

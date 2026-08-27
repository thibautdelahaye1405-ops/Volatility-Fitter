"""Named workspace FILES in the app store (UI shell v2 wave 3, item A1).

A workspace file is the ``volfit-workspace/1`` bundle the frontend's File
menu saves: the backend workspace doc (``volfit.api.workspace.build_doc`` —
settings, universe picks, edits, priors, …) plus the shell state (activity,
tabs, layout, view preferences). "Save to server…" stores that bundle under a
name in the ``workspaces(name PK, saved_ts, doc_json)`` table of the VolStore
schema (v9), next to the named universes, so a desk can reopen the same
configuration from any browser. The bundle is stored VERBATIM (JSON text):
this module never interprets it — validation lives in
``volfit.api.workspace_files``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from volfit.data.store import VolStore


def save_workspace(store: VolStore, name: str, bundle: dict) -> str:
    """Insert-or-replace the bundle under ``name``; returns the saved stamp."""
    saved_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    store.conn.execute(
        "INSERT INTO workspaces (name, saved_ts, doc_json) VALUES (?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET saved_ts = excluded.saved_ts, "
        "doc_json = excluded.doc_json",
        (name, saved_ts, json.dumps(bundle, separators=(",", ":"))),
    )
    store.conn.commit()
    return saved_ts


def load_workspace(store: VolStore, name: str) -> dict | None:
    """The stored bundle, or None when absent."""
    row = store.conn.execute(
        "SELECT doc_json FROM workspaces WHERE name = ?", (name,)
    ).fetchone()
    return json.loads(row[0]) if row else None


def list_workspaces(store: VolStore) -> list[dict]:
    """``[{name, savedTs}]`` newest first."""
    rows = store.conn.execute(
        "SELECT name, saved_ts FROM workspaces ORDER BY saved_ts DESC, name"
    ).fetchall()
    return [{"name": r[0], "savedTs": r[1]} for r in rows]


def delete_workspace(store: VolStore, name: str) -> bool:
    """Delete one stored bundle; True when a row was removed."""
    cur = store.conn.execute("DELETE FROM workspaces WHERE name = ?", (name,))
    store.conn.commit()
    return cur.rowcount > 0

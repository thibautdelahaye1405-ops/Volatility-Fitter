"""Governance kernel persistence (roadmap R1 item 8, store schema v8).

Two tables on the app store, kept OUT of ``store.py`` (file-size policy):

``events`` — the APPEND-ONLY audit log. Every intervention (quote exclusion
or amendment, forward/dividend/settings override, prior selection, graph
edge edit, publish, recall) records actor, timestamp, action, scope and an
old/new payload. This module deliberately exposes NO update or delete for
events — the log is the audit trail, and corrections are new events.
``actor`` is a constant "desk" today; the field exists so the hosted
multi-tenant product (roadmap R4) inherits a log that already names who.

``manifests`` — one row per PUBLISHED surface (the export artifact), keyed
by the content hash of its manifest document and chained to its parent
(the previously latest publish). A new publish SUPERSEDES the previous
latest; a recall flips state without deleting anything (published →
superseded / recalled — a published surface is never mutated or removed).
The row stores the manifest document (inputs, settings, snapshot ids,
artifact hash) AND the full artifact, so ``python -m volfit.replay_report``
can rebuild the surface from stored inputs and diff it against what was
actually published. Artifact blobs beyond ``ARTIFACT_RETAIN`` publishes are
pruned (rows and documents are kept forever — only the heavyweight JSON is
subject to retention, the named intraday-volume risk).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from volfit.data.store import VolStore

#: How many most-recent publishes keep their full artifact JSON.
ARTIFACT_RETAIN = 50

#: The single-user actor label; the hosted product replaces it per session.
DEFAULT_ACTOR = "desk"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def canonical_json(doc) -> str:
    """Deterministic JSON (sorted keys, no whitespace) for hashing."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)


def content_id(doc) -> str:
    """The manifest id: sha256 of the canonical document."""
    return hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------- events
def append_event(
    store: VolStore, action: str, scope: str = "", payload: dict | None = None,
    actor: str = DEFAULT_ACTOR,
) -> int:
    """Append one audit event; returns its id. There is no update/delete."""
    cur = store.conn.execute(
        "INSERT INTO events (ts, actor, action, scope, payload_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (_now_iso(), actor, action, scope,
         None if payload is None else json.dumps(payload, default=str)),
    )
    store.conn.commit()
    return int(cur.lastrowid)


def list_events(
    store: VolStore, limit: int = 100, scope: str | None = None
) -> list[dict]:
    """Newest-first audit events, optionally filtered by scope prefix."""
    if scope is None:
        rows = store.conn.execute(
            "SELECT id, ts, actor, action, scope, payload_json FROM events "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = store.conn.execute(
            "SELECT id, ts, actor, action, scope, payload_json FROM events "
            "WHERE scope LIKE ? ORDER BY id DESC LIMIT ?",
            (scope + "%", limit),
        )
    return [
        {
            "id": rid, "ts": ts, "actor": actor, "action": action, "scope": scope_,
            "payload": None if payload is None else json.loads(payload),
        }
        for rid, ts, actor, action, scope_, payload in rows
    ]


# ----------------------------------------------------------------- manifests
def chain_ids(store: VolStore, doc: dict) -> tuple[str, str | None]:
    """(manifest_id, parent_id) this document would chain to right now — the
    id is the content hash of the doc WITH the parent folded in, so callers
    can stamp the artifact before persisting and the chain is tamper-evident."""
    parent = latest_manifest_id(store)
    return content_id(dict(doc, parentId=parent)), parent


def save_manifest(
    store: VolStore,
    doc: dict,
    artifact_json: str,
    mid: str | None = None,
    parent: str | None = None,
) -> tuple[str, str | None]:
    """Persist a publish: hash-chain to the previous latest and supersede it.

    Returns ``(manifest_id, parent_id)``. Callers that stamped the artifact
    pass the ``chain_ids`` result back in; otherwise both are derived here.
    Re-publishing identical content replaces the row idempotently.
    """
    if mid is None or parent is None:
        mid, parent = chain_ids(store, doc)
    doc = dict(doc, parentId=parent)
    if parent is not None and parent != mid:
        store.conn.execute(
            "UPDATE manifests SET state = 'superseded' "
            "WHERE id = ? AND state = 'published'",
            (parent,),
        )
    store.conn.execute(
        "INSERT INTO manifests (id, ts, parent, state, doc_json, artifact_json) "
        "VALUES (?, ?, ?, 'published', ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET ts = excluded.ts, state = 'published', "
        "artifact_json = excluded.artifact_json",
        (mid, _now_iso(), parent, json.dumps(doc, default=str), artifact_json),
    )
    # Retention: only the ARTIFACT blobs age out; rows/documents are forever.
    store.conn.execute(
        "UPDATE manifests SET artifact_json = NULL WHERE id NOT IN "
        "(SELECT id FROM manifests ORDER BY ts DESC, id DESC LIMIT ?)",
        (ARTIFACT_RETAIN,),
    )
    store.conn.commit()
    return mid, parent


def latest_manifest_id(store: VolStore) -> str | None:
    row = store.conn.execute(
        "SELECT id FROM manifests ORDER BY ts DESC, id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else str(row[0])


def load_manifest(store: VolStore, manifest_id: str) -> dict | None:
    row = store.conn.execute(
        "SELECT id, ts, parent, state, doc_json, artifact_json FROM manifests "
        "WHERE id = ?",
        (manifest_id,),
    ).fetchone()
    if row is None:
        return None
    mid, ts, parent, state, doc, artifact = row
    return {
        "id": mid, "ts": ts, "parent": parent, "state": state,
        "doc": json.loads(doc),
        "artifact": None if artifact is None else json.loads(artifact),
    }


def list_manifests(store: VolStore, limit: int = 50) -> list[dict]:
    rows = store.conn.execute(
        "SELECT id, ts, parent, state, doc_json FROM manifests "
        "ORDER BY ts DESC, id DESC LIMIT ?",
        (limit,),
    )
    out = []
    for mid, ts, parent, state, doc in rows:
        d = json.loads(doc)
        out.append({
            "id": mid, "ts": ts, "parent": parent, "state": state,
            "tickers": d.get("tickers", []), "fittedNodes": d.get("fittedNodes"),
        })
    return out


def set_manifest_state(store: VolStore, manifest_id: str, state: str) -> bool:
    """Lifecycle transition (recall / supersede). Rows are never deleted."""
    if state not in ("published", "superseded", "recalled"):
        raise ValueError(f"unknown manifest state {state!r}")
    cur = store.conn.execute(
        "UPDATE manifests SET state = ? WHERE id = ?", (state, manifest_id)
    )
    store.conn.commit()
    return cur.rowcount > 0

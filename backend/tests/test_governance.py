"""Governance kernel (R1 item 8): event log, manifests, lifecycle, replay.

Contracts: (1) interventions append audit events (settings diffs, quote
edits, forward policies, publishes) — the log is append-only, there is no
update/delete surface; (2) a publish with a store persists a hash-chained
manifest, a second publish supersedes the first, recall flips state without
deleting; (3) without a store the export succeeds with manifestId=None;
(4) THE acceptance test — a published surface replays from stored inputs
after a full process-restart-equivalent (fresh AppState) to within 1e-9 IV.
"""

from __future__ import annotations

from datetime import date

from volfit.api import service
from volfit.api.export import build_surface_export
from volfit.api.state import AppState
from volfit.data import governance
from volfit.data.store import VolStore
from volfit.replay_report import replay

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _published_state(tmp_path, n_nodes: int = 2) -> tuple[AppState, str]:
    state = AppState(REF_DATE, store_path=tmp_path / "vol.db")
    isos = [e.isoformat() for e in sorted(state.forwards(TICKER))][:n_nodes]
    for iso in isos:
        service.calibrate_node(state, TICKER, iso, "mid")
    return state, isos[0]


def test_settings_and_edits_append_audit_events(tmp_path):
    state, iso = _published_state(tmp_path, n_nodes=1)
    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"regLambda": fs.regLambda * 2}))
    state.set_forward_policy(TICKER, iso, type(state.forward_policy(TICKER, iso))(
        mode="manual", manualForward=123.0))

    from volfit.api import edits
    from volfit.api.schemas import QuoteEditRequest

    edits.apply_quote_edit(state, TICKER, iso, "mid",
                           QuoteEditRequest(action="exclude", index=6))

    actions = [e["action"] for e in state.event_tail()]
    assert "fit_settings" in actions
    assert "forward_policy" in actions
    assert "quote_edit" in actions
    with VolStore(state.store_path) as store:
        rows = governance.list_events(store)
        assert [r["action"] for r in rows][:1] == ["quote_edit"]  # newest first
        assert rows[-1]["actor"] == "desk"
        diff = next(r for r in rows if r["action"] == "fit_settings")["payload"]
        assert "regLambda" in diff and len(diff["regLambda"]) == 2  # [old, new]
        # Append-only: the persistence module exposes no update/delete for events.
        assert not any(n.startswith(("update_event", "delete_event"))
                       for n in dir(governance))


def test_publish_chains_supersedes_and_recalls(tmp_path):
    state, _ = _published_state(tmp_path)
    first = build_surface_export(state, tickers=[TICKER])
    assert first.manifest.manifestId is not None
    assert first.manifest.parentId is None  # genesis publish

    fs = state.fit_settings()  # a real change => a different second manifest
    state.set_fit_settings(fs.model_copy(update={"regLambda": fs.regLambda * 3}))
    isos = [e.isoformat() for e in sorted(state.forwards(TICKER))][:2]
    for iso in isos:
        service.calibrate_node(state, TICKER, iso, "mid")
    second = build_surface_export(state, tickers=[TICKER])
    assert second.manifest.parentId == first.manifest.manifestId
    assert second.manifest.manifestId != first.manifest.manifestId

    with VolStore(state.store_path) as store:
        rows = {m["id"]: m for m in governance.list_manifests(store)}
        assert rows[first.manifest.manifestId]["state"] == "superseded"
        assert rows[second.manifest.manifestId]["state"] == "published"
        assert governance.set_manifest_state(
            store, second.manifest.manifestId, "recalled")
        loaded = governance.load_manifest(store, second.manifest.manifestId)
        assert loaded["state"] == "recalled"
        assert loaded["artifact"] is not None  # recall never deletes
    assert any(e["action"] == "publish" for e in state.event_tail())


def test_export_without_store_carries_no_lineage():
    state = AppState(REF_DATE)
    iso = sorted(state.forwards(TICKER))[0].isoformat()
    service.calibrate_node(state, TICKER, iso, "mid")
    out = build_surface_export(state, tickers=[TICKER])
    assert out.manifest.manifestId is None and out.manifest.parentId is None


def test_replay_reproduces_the_published_surface(tmp_path):
    """THE acceptance criterion (roadmap 3.5): rebuild every published curve
    point from stored inputs in a FRESH state and match to tolerance."""
    state, _ = _published_state(tmp_path)
    published = build_surface_export(state, tickers=[TICKER])
    assert published.manifest.manifestId is not None

    report = replay(state.store_path, "latest", tol=1e-9)
    assert report["manifestId"] == published.manifest.manifestId
    assert report["ok"], report
    assert report["worstIvDiff"] <= 1e-9
    assert len(report["nodes"]) == published.manifest.fittedNodes
    assert report["fidelityNotes"] == []  # no edits / priors on this publish

"""P6 hardening — migration / round-trip locks for the graph message config.

Gaps closed HERE (spec Phase 6 item 2, API round-trip + blob persistence):

* Envelope + policy SQLite reboot round-trip: staged rows AND a
  GraphDynamicPolicy activate, then an AppState rebuild on the same store
  restores BOTH slots byte-equal (active rows + policy solve-visible, the
  staged draft intact).
* Workspace-doc round-trip with an ACTIVE config present: restore_doc replays
  the doc's rows into the workspace AND reconciles the envelope's active slot
  WITHOUT a version bump; the reconcile persists across a further reboot; the
  solve-visible policy is untouched.
* Downgrade safety: the legacy ``graph_message_edges`` app_settings blob keeps
  mirroring the ACTIVE rows through the envelope lifecycle, so an older build
  reading only the legacy key sees exactly what runs.
* Corrupt/partial ``graph_message_config`` blobs never crash boot: junk JSON
  degrades to the legacy-migration path (and self-heals the blob), an
  unreadable SLOT degrades to None while the readable slot survives,
  wrong-typed slots fall back to a fresh lifecycle, malformed legacy rows are
  dropped row-by-row at migration.

Complementary coverage (NOT duplicated here):

* tests/test_graph_message_config.py — draft/active staging semantics,
  activate/revert, the one-time legacy-blob migration
  (test_legacy_blob_migrates_once), HTTP endpoint round-trip.
* tests/test_graph_message_production.py — policy lifecycle over HTTP
  (test_dynamic_policy_lifecycle), solve-time precedence
  (test_resolve_dynamic_policy_precedence), plain rows riding the workspace
  (test_message_edges_persist_and_ride_the_workspace).
* tests/test_graph_dynamic_production.py::test_residual_store_survives_restart
  — dynamic-residual store persistence + corrupt-record tolerance (which is
  why no residual-store test lives in this file).
* tests/test_graph_temporal_state.py::test_migrate_atm_floor_history — legacy
  ATM-floor history migration.
"""

from datetime import date

import pytest

from volfit.api.schemas import GraphDynamicPolicy, GraphMessageEdge
from volfit.api.settings_persist import (
    GRAPH_MESSAGE_CONFIG_KEY,
    load_graph_message_config,
    load_graph_message_edges,
    save_graph_message_config,
    save_graph_message_edges,
)
from volfit.api.state import AppState
from volfit.api.workspace import build_doc, restore_doc
from volfit.data.store import VolStore

REF_DATE = date(2026, 6, 10)


def _row(tk, src, tgt, beta=2.0, p=1e5) -> GraphMessageEdge:
    return GraphMessageEdge(
        sourceTicker=tk, sourceExpiry=src, targetTicker=tk, targetExpiry=tgt,
        messagePrecision=p, betaAtmVol=beta, betaSkew=beta, betaCurv=beta,
        relationClass="calendar",
    )


def _policy() -> GraphDynamicPolicy:
    """Non-default dials on every field so a round-trip can't pass by luck."""
    return GraphDynamicPolicy(
        clampMaxAgeDays=2.5,
        residualHalfLifeDays=5.0,
        semanticsDefaults={"custom": "directed_state"},
    )


def _write_raw_setting(store_path: str, key: str, text: str) -> None:
    """Inject raw text into app_settings, bypassing json.dumps — the only way
    to plant genuinely malformed JSON for the corrupt-blob boot tests."""
    with VolStore(store_path) as store:
        store.conn.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
            (key, text),
        )
        store.conn.commit()


# ------------------------------------------------- (a) envelope+policy reboot
def test_envelope_and_policy_survive_reboot(tmp_path):
    """Stage rows AND a policy, activate, stage a NEW draft, reboot: both
    lifecycle slots come back byte-equal (model_dump), the solve-visible reads
    (active rows, active policy, draft policy) are identical, and the staged
    draft is intact — nothing re-migrates or re-stamps."""
    store = str(tmp_path / "volfit.sqlite")
    rows_a = [_row("SPY", "2026-12-18", "2026-09-18", beta=1.5)]
    rows_b = [_row("SPY", "2027-06-18", "2026-12-18", beta=0.5)]
    policy = _policy()

    state1 = AppState(REF_DATE, store_path=store)
    state1.set_graph_message_draft(rows_a)
    state1.set_graph_message_draft_policy(policy)  # rows staged above survive
    state1.activate_message_config(notes="p6 reboot lock")
    state1.set_graph_message_draft(rows_b)  # staged for v2, NOT activated

    d1, a1 = state1.graph_message_config()
    # Preconditions so the round-trip assertions below are meaningful.
    assert a1 is not None and (a1.version, a1.notes) == (1, "p6 reboot lock")
    assert a1.policy is not None and a1.rows == rows_a
    assert d1 is not None and (d1.version, d1.parentVersion) == (2, 1)
    assert d1.rows == rows_b and d1.policy is not None  # policy rode along

    state2 = AppState(REF_DATE, store_path=store)
    d2, a2 = state2.graph_message_config()
    assert a2 is not None and a2.model_dump() == a1.model_dump()
    assert d2 is not None and d2.model_dump() == d1.model_dump()
    # Solve-visible reads after the reboot.
    assert state2.graph_message_edges() == rows_a
    assert state2.graph_message_policy() == policy
    assert state2.graph_message_policy(use_draft=True) == policy


# --------------------------------------- (b) workspace doc round-trip w/ config
def test_workspace_doc_reconciles_active_rows_without_version_bump(tmp_path):
    """A workspace doc built while v1 (rows_a + policy) was active restores
    into a state whose live config moved on to v2 (rows_b): the workspace rows
    replay byte-identically, the envelope's ACTIVE slot reconciles to the
    doc's rows WITHOUT a version bump (a restore replays state, it does not
    activate), the policy stays solve-visible, and the reconcile persists."""
    store = str(tmp_path / "volfit.sqlite")
    rows_a = [_row("SPY", "2026-12-18", "2026-09-18", beta=1.5)]
    rows_b = [_row("SPY", "2027-06-18", "2026-12-18", beta=0.5)]
    policy = _policy()

    state1 = AppState(REF_DATE, store_path=store)
    state1.set_graph_message_draft(rows_a)
    state1.set_graph_message_draft_policy(policy)
    state1.activate_message_config(notes="doc snapshot")  # active v1 = rows_a
    doc = build_doc(state1)
    assert doc["graphMessageEdges"] == [e.model_dump() for e in rows_a]

    # The live config moves PAST the doc: v2 activates different rows.
    state1.set_graph_message_draft(rows_b)
    state1.activate_message_config()

    state2 = AppState(REF_DATE, store_path=store)
    assert state2.graph_message_edges() == rows_b  # boots on v2
    restore_doc(state2, doc)

    # Workspace replay is byte-identical on the message-config field.
    assert state2.graph_message_edges() == rows_a
    assert build_doc(state2)["graphMessageEdges"] == doc["graphMessageEdges"]
    # The envelope reconciled: active ROWS follow the doc, lifecycle metadata
    # (version chain) carries on unchanged — and no activation was audited.
    _, active = state2.graph_message_config()
    assert active is not None and active.version == 2
    assert [e.model_dump() for e in active.rows] == doc["graphMessageEdges"]
    assert all(
        e["action"] != "graph_message_config_activate" for e in state2.event_tail()
    )
    # The restore's policy is untouched and still resolves for the solve.
    assert state2.graph_message_policy() == policy
    # The reconcile persisted: a fresh boot serves the restored rows.
    state3 = AppState(REF_DATE, store_path=store)
    assert state3.graph_message_edges() == rows_a
    _, active3 = state3.graph_message_config()
    assert active3 is not None and active3.version == 2


# ------------------------------------------------ (c) downgrade-safety mirror
def test_legacy_blob_mirrors_active_rows_through_lifecycle(tmp_path):
    """The legacy graph_message_edges blob mirrors the ACTIVE rows at every
    activation — and ONLY at activation (staging never leaks a draft to a
    downgraded reader) — including the empty-wipe config."""
    store = str(tmp_path / "volfit.sqlite")
    rows_a = [_row("SPY", "2026-12-18", "2026-09-18", beta=1.5)]
    rows_b = [_row("SPY", "2027-06-18", "2026-12-18", beta=0.5)]

    state = AppState(REF_DATE, store_path=store)
    state.set_graph_message_draft(rows_a)
    # Nothing active yet: an older build reading the legacy key sees nothing.
    assert load_graph_message_edges(store) == []

    state.activate_message_config()
    assert load_graph_message_edges(store) == [e.model_dump() for e in rows_a]

    # A staged (unactivated) edit leaves the mirror on the ACTIVE rows.
    state.set_graph_message_draft(rows_b)
    assert load_graph_message_edges(store) == [e.model_dump() for e in rows_a]

    state.activate_message_config()
    assert load_graph_message_edges(store) == [e.model_dump() for e in rows_b]

    # Activating a wipe mirrors the auto-relations config (empty list).
    state.set_graph_message_draft([])
    state.activate_message_config()
    assert load_graph_message_edges(store) == []


# --------------------------------------------- (d) corrupt/partial blob boots
def test_junk_json_config_blob_falls_back_to_legacy_migration(tmp_path):
    """Genuinely malformed JSON under the config key: boot warns, degrades to
    'never persisted', and the legacy blob migrates exactly as if the config
    key were absent. The migration REWRITES the blob, so the next boot reads a
    healthy v1 envelope (self-heal, no re-migration)."""
    store = str(tmp_path / "volfit.sqlite")
    legacy = _row("SPY", "2026-12-18", "2026-09-18").model_dump()
    save_graph_message_edges(store, [legacy])
    _write_raw_setting(store, GRAPH_MESSAGE_CONFIG_KEY, "{this is not json !!")

    with pytest.warns(UserWarning, match="graph-message-config load failed"):
        state = AppState(REF_DATE, store_path=store)
    draft, active = state.graph_message_config()
    assert active is not None
    assert (active.version, active.notes) == (1, "migrated from graph_message_edges")
    assert [e.model_dump() for e in state.graph_message_edges()] == [legacy]
    assert draft is not None and draft.rows == active.rows

    # Self-heal: the blob is readable again and the reboot stays on v1.
    assert load_graph_message_config(store) is not None
    state2 = AppState(REF_DATE, store_path=store)
    _, active2 = state2.graph_message_config()
    assert active2 is not None and active2.version == 1


def test_partial_config_blob_keeps_the_readable_slot(tmp_path):
    """Per-slot degrade contract (_coerce_message_config): an unreadable DRAFT
    slot becomes None while the valid ACTIVE slot survives intact, the solve
    keeps its rows, and the lifecycle still version-chains off the survivor."""
    store = str(tmp_path / "volfit.sqlite")
    rows = [_row("SPY", "2026-12-18", "2026-09-18")]
    state1 = AppState(REF_DATE, store_path=store)
    state1.set_graph_message_draft(rows)
    state1.activate_message_config(notes="keep me")

    blob = load_graph_message_config(store)
    assert blob is not None and blob["active"] is not None  # precondition
    blob["draft"] = {"version": "NaN", "rows": 17}  # fails envelope validation
    save_graph_message_config(store, blob)

    state2 = AppState(REF_DATE, store_path=store)
    draft, active = state2.graph_message_config()
    assert draft is None  # the unreadable slot degraded, boot survived
    assert active is not None and active.notes == "keep me"
    assert state2.graph_message_edges() == rows
    # Staging still works: a fresh draft chains off the surviving active.
    state2.set_graph_message_draft([])
    d2, a2 = state2.graph_message_config()
    assert d2 is not None and a2 is not None
    assert (d2.version, d2.parentVersion) == (a2.version + 1, a2.version)


def test_wrong_typed_config_slots_degrade_to_fresh_lifecycle(tmp_path):
    """Valid JSON of the wrong SHAPE in both slots (int / list instead of
    envelope dicts): boot degrades to a never-persisted config — no legacy
    rows, so no migration — and a from-scratch lifecycle works and persists."""
    store = str(tmp_path / "volfit.sqlite")
    save_graph_message_config(store, {"draft": 42, "active": ["not", "an", "env"]})

    state = AppState(REF_DATE, store_path=store)
    assert state.graph_message_config() == (None, None)
    assert state.graph_message_edges() == []

    rows = [_row("SPY", "2026-12-18", "2026-09-18")]
    state.set_graph_message_draft(rows)
    state.activate_message_config()
    _, active = AppState(REF_DATE, store_path=store).graph_message_config()
    assert active is not None and active.version == 1
    assert [e.model_dump() for e in active.rows] == [e.model_dump() for e in rows]


def test_malformed_legacy_rows_dropped_at_migration(tmp_path):
    """Row-level tolerance (_coerce_message_edges): unreadable legacy rows are
    skipped, the readable one migrates — a partial blob degrades to fewer
    edges, never a startup crash."""
    store = str(tmp_path / "volfit.sqlite")
    good = _row("SPY", "2026-12-18", "2026-09-18").model_dump()
    save_graph_message_edges(store, [good, {"garbage": True}, 42])

    state = AppState(REF_DATE, store_path=store)
    assert [e.model_dump() for e in state.graph_message_edges()] == [good]
    _, active = state.graph_message_config()
    assert active is not None and active.version == 1  # migrated the survivor

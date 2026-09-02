"""Workspace serialization (R1 item 9): AppState's user-authored state is one
serializable, scoped object.

Contracts: (1) the workspace doc JSON round-trips exactly (serialize ->
restore into a fresh state -> serialize gives the same doc); (2) a restored
workspace produces BYTE-IDENTICAL fits (quote edits, var-swap quotes, active
prior anchor, settings all survive); (3) restore is a state reset — version
counters advance and every warm cache drops; (4) observation-filter node
states round-trip (the durable-filter-state prerequisite for R2/R4); (5) the
publish manifest captures session edits + active-prior CONTENT and
volfit.replay_report restores them, so an edited/anchored publish replays to
1e-9 with NO fidelity caveats (the two v0 gaps, closed); legacy count-only
manifests keep their stated-tolerance notes.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np

from volfit.api import edits, filter_history, observation_filter, priors, service
from volfit.api.export import build_surface_export
from volfit.api.schemas import (
    EventSpec,
    ForwardPolicy,
    MarketSettings,
    QuoteEditRequest,
)
from volfit.api.session import EditSession
from volfit.api.state import AppState
from volfit.api.varswap_session import VarSwapSession
from volfit.data import governance
from volfit.data.store import VolStore
from volfit.replay_report import _fidelity_notes, replay

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _calibrated_state(store_path=None, n_nodes: int = 2) -> tuple[AppState, list[str]]:
    state = AppState(REF_DATE, store_path=store_path)
    isos = [e.isoformat() for e in sorted(state.forwards(TICKER))][:n_nodes]
    for iso in isos:
        service.calibrate_node(state, TICKER, iso, "mid")
    return state, isos


def _worked_state() -> tuple[AppState, list[str]]:
    """A state with every kind of user-authored content the workspace scopes."""
    state, isos = _calibrated_state()
    edits.apply_quote_edit(
        state, TICKER, isos[0], "mid", QuoteEditRequest(action="exclude", index=6)
    )
    edits.apply_quote_edit(
        state, TICKER, isos[0], "mid",
        QuoteEditRequest(action="amend", index=3, mid=0.24),
    )
    state.varswap_session((TICKER, isos[0])).apply("set", 0.22)
    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"regLambda": fs.regLambda * 2}))
    state.set_market_settings(TICKER, MarketSettings(rate=0.031))
    state.set_forward_policy(
        TICKER, isos[1], ForwardPolicy(mode="manual", manualForward=105.0)
    )
    state.set_events(TICKER, [EventSpec(time=0.05, weight=1.5, label="earnings")])
    state.set_node_lit(TICKER, isos[1], False)
    state.set_spot_shift(TICKER, 0.01)
    state.set_spot_follow(TICKER, "scenario")
    snap = priors.capture_snapshot(state, TICKER, "mid", lv=False)
    assert snap is not None
    state.set_active_prior(TICKER, snap, "saved")
    return state, isos


def _fit_of(state: AppState, iso: str):
    ptr = state.get_calibrated_ptr(TICKER, iso, "mid")
    assert ptr is not None
    record = state.get_fit(ptr[0])
    assert record is not None
    return record


# ------------------------------------------------------------- round-trip
def test_workspace_doc_round_trips_exactly():
    state, _ = _worked_state()
    doc = state.workspace_doc()
    json.dumps(doc)  # JSON-safe by construction

    fresh = AppState(REF_DATE)
    fresh.restore_workspace(doc)
    assert fresh.workspace_doc() == doc


def test_session_and_varswap_docs_round_trip_history():
    s = EditSession()
    s.apply("exclude", 6, None, 20)
    s.apply("amend", 3, 0.21, 20)
    s.undo()
    s2 = EditSession()
    s2.load_doc(s.to_doc())
    assert s2.edits == s.edits and s2.version == s.version
    assert s2.can_undo == s.can_undo and s2.can_redo == s.can_redo
    s2.redo()
    assert s2.edits[3].amended_iv == 0.21
    assert "undo" not in s.to_doc(history=False)

    v = VarSwapSession()
    v.apply("set", 0.19)
    v.apply("exclude", None)
    v2 = VarSwapSession()
    v2.load_doc(v.to_doc())
    assert v2.state == v.state and v2.version == v.version
    v2.undo()
    assert v2.state.level == 0.19 and not v2.state.excluded


def test_restored_workspace_fits_byte_identical():
    """THE refactor invariant: a restored workspace reproduces every fit
    bit-for-bit — edits, var-swap quote, prior anchor and settings included."""
    state, isos = _worked_state()
    for iso in isos:
        service.calibrate_node(state, TICKER, iso, "mid")
    doc = state.workspace_doc()

    fresh = AppState(REF_DATE)
    fresh.restore_workspace(doc)
    for iso in isos:
        service.calibrate_node(fresh, TICKER, iso, "mid")

    for iso in isos:
        a, b = _fit_of(state, iso), _fit_of(fresh, iso)
        assert np.array_equal(
            a.result.params.to_vector(), b.result.params.to_vector()
        )
        curve_a = [(p.k, p.vol) for p in service.model_curve(a)]
        curve_b = [(p.k, p.vol) for p in service.model_curve(b)]
        assert curve_a == curve_b


def test_restore_is_a_reset_versions_advance_and_caches_drop():
    state, isos = _worked_state()
    assert state.get_calibrated_ptr(TICKER, isos[0], "mid") is not None
    assert state.loaded_snapshot(TICKER) is not None
    versions = (
        state.settings_version, state.options_version,
        state.spot_version, state.events_version(TICKER),
        state.forwards_version(TICKER), state.active_prior_version(TICKER),
    )

    state.restore_workspace(state.workspace_doc())  # restore into ITSELF

    after = (
        state.settings_version, state.options_version,
        state.spot_version, state.events_version(TICKER),
        state.forwards_version(TICKER), state.active_prior_version(TICKER),
    )
    assert all(n > o for n, o in zip(after, versions))
    assert state.get_calibrated_ptr(TICKER, isos[0], "mid") is None
    assert state.loaded_snapshot(TICKER) is None
    # content survived the reset
    assert state.spot_shift(TICKER) == 0.01
    assert state.spot_follow(TICKER) == "scenario"  # the follow selector rides along
    assert not state.node_lit(TICKER, isos[1])
    assert state.active_prior(TICKER) is not None
    assert state.session_if_exists((TICKER, isos[0])).edits


def test_filter_states_round_trip():
    """Durable filter state (the R2/R4 prerequisite): overlay Kalman states
    serialize and restore with exact arrays."""
    state = AppState(REF_DATE)
    state.set_options(
        state.options().model_copy(update={"observationFilterMode": "overlay"})
    )
    iso = sorted(state.forwards(TICKER))[0].isoformat()
    service.calibrate_node(state, TICKER, iso, "mid")
    holder = state.filter_node((TICKER, iso, "mid"))
    assert holder is not None

    doc = state.workspace_doc()
    assert doc["filterStates"], "overlay commit should have produced a state"
    fresh = AppState(REF_DATE)
    fresh.restore_workspace(doc)
    restored = fresh.filter_node((TICKER, iso, "mid"))
    assert restored is not None
    assert np.array_equal(holder.state.mean, restored.state.mean)
    assert np.array_equal(holder.state.cov, restored.state.cov)
    assert holder.state.provenance == restored.state.provenance
    if holder.update is not None:
        assert np.array_equal(holder.update.innovation, restored.update.innovation)
    assert fresh.workspace_doc()["filterStates"] == doc["filterStates"]


def _history_state(n_steps: int = 2) -> tuple[AppState, list[str]]:
    """Filter ON with ``n_steps`` committed ring steps on each of two nodes:
    the seed, then genuinely NEW observations (data-version bumps) through the
    real commit hook — the test_filter_history idempotence-lock recipe."""
    state = AppState(REF_DATE)
    state.set_options(
        state.options().model_copy(update={"observationFilterMode": "overlay"})
    )
    isos = [e.isoformat() for e in sorted(state.forwards(TICKER))][:2]
    records = {iso: service.displayed_base(state, TICKER, iso, "mid") for iso in isos}
    for _ in range(n_steps - 1):
        state.bump_data_version(TICKER)
        for iso in isos:
            observation_filter.on_fit_commit(
                state, TICKER, iso, "mid", records[iso], None
            )
    for iso in isos:
        assert len(state.filter_history((TICKER, iso, "mid"))) == n_steps
    return state, isos


def test_filter_history_round_trips():
    """V3.9 rider: the per-node history rings persist under the additive
    ``filterHistory`` key — build_doc -> restore into a FRESH state gives the
    identical /filter/history payload per node and an identical doc."""
    from fastapi.testclient import TestClient

    from volfit.api import create_app

    state, isos = _history_state(n_steps=3)
    doc = state.workspace_doc()
    json.dumps(doc)  # JSON-safe by construction
    assert [d["expiry"] for d in doc["filterHistory"]] == sorted(isos)
    assert all(len(d["steps"]) == 3 for d in doc["filterHistory"])
    assert all(d["mode"] == "mid" and d["ticker"] == TICKER for d in doc["filterHistory"])
    # the step docs ARE the wire dicts, and step_from_doc is their exact inverse
    for d in doc["filterHistory"]:
        for s in d["steps"]:
            assert filter_history.step_doc(filter_history.step_from_doc(s)) == s
    expected = {
        iso: filter_history.history_payload(state, TICKER, iso, "mid").model_dump()
        for iso in isos
    }
    assert all(p["active"] and len(p["steps"]) == 3 for p in expected.values())

    fresh = AppState(REF_DATE)
    fresh.restore_workspace(doc)
    for iso in isos:
        got = filter_history.history_payload(fresh, TICKER, iso, "mid").model_dump()
        assert got == expected[iso]
    assert fresh.workspace_doc() == doc
    assert fresh.workspace_doc()["filterHistory"] == doc["filterHistory"]

    # ... and through the endpoint of a restored app (the FilterTimeline feed)
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        c.app.state.volfit.restore_workspace(doc)
        for iso in isos:
            r = c.get(f"/smiles/{TICKER}/{iso}/filter/history")
            assert r.status_code == 200
            assert r.json() == expected[iso]


def test_workspace_without_filter_history_key_restores_empty_rings():
    """An older doc (no ``filterHistory`` key) restores cleanly: the filter
    STATES still restore, the rings are empty and the endpoint answers
    0 steps without error."""
    from fastapi.testclient import TestClient

    from volfit.api import create_app

    state, isos = _history_state()
    doc = state.workspace_doc()
    del doc["filterHistory"]
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        app_state = c.app.state.volfit
        app_state.restore_workspace(doc)
        assert app_state.filter_node((TICKER, isos[0], "mid")) is not None
        for iso in isos:
            assert app_state.filter_history((TICKER, iso, "mid")) is None
            r = c.get(f"/smiles/{TICKER}/{iso}/filter/history")
            assert r.status_code == 200
            assert r.json() == {"active": False, "steps": []}
        # re-serializing emits the key (empty), never a missing key
        assert app_state.workspace_doc()["filterHistory"] == []


def test_restore_replaces_stale_rings_and_builds_doc_without_rings():
    """Restore is a reset for the rings too: a state's own rings are replaced
    by the doc's (here: none), and a filter-off worked state emits an empty
    ``filterHistory`` list (its doc stays otherwise unchanged)."""
    state, _ = _worked_state()
    assert state.workspace_doc()["filterHistory"] == []
    hist_state, isos = _history_state()
    hist_state.restore_workspace(state.workspace_doc())
    for iso in isos:
        assert hist_state.filter_history((TICKER, iso, "mid")) is None


# --------------------------------------------------- replay fidelity (gaps)
def test_publish_with_edits_and_prior_replays_exactly(tmp_path):
    """The two v0 replay fidelity gaps, closed: a publish carrying session
    quote edits, a var-swap quote AND an active prior anchor replays from its
    manifest to 1e-9 with NO fidelity notes."""
    state, isos = _calibrated_state(store_path=tmp_path / "vol.db")
    edits.apply_quote_edit(
        state, TICKER, isos[0], "mid", QuoteEditRequest(action="exclude", index=6)
    )
    state.varswap_session((TICKER, isos[0])).apply("set", 0.22)
    snap = priors.capture_snapshot(state, TICKER, "mid", lv=False)
    assert snap is not None
    state.set_active_prior(TICKER, snap, "saved")  # anchors (default hybrid mode)
    # Recalibrate EVERY fitted node so nothing publishes stale: capture_snapshot
    # bootstrap-fits all lit expiries, and the prior bump moved their keys.
    all_isos = [e.isoformat() for e in sorted(state.forwards(TICKER))]
    for iso in all_isos:
        service.calibrate_node(state, TICKER, iso, "mid")

    published = build_surface_export(state, tickers=[TICKER])
    mid = published.manifest.manifestId
    assert mid is not None
    with VolStore(state.store_path) as store:
        doc = governance.load_manifest(store, mid)["doc"]
    assert doc["editedNodes"] == 1
    assert doc["sessionEdits"][TICKER][isos[0]]["edits"]  # content, not a count
    assert doc["varSwapQuotes"][TICKER][isos[0]]["state"]["level"] == 0.22
    assert doc["activePriorContent"][TICKER]["ticker"] == TICKER
    assert doc["activePriorSources"][TICKER] == "saved"

    assert doc["staleNodes"] == 0

    report = replay(state.store_path, "latest", tol=1e-9)
    assert report["ok"], report
    assert report["worstIvDiff"] <= 1e-9
    assert report["fidelityNotes"] == []


def test_stale_published_nodes_carry_a_fidelity_note(tmp_path):
    """A node published FROZEN at older inputs than the manifest captures
    cannot replay exactly — the manifest counts it and the report says so."""
    state, isos = _calibrated_state(store_path=tmp_path / "vol.db")
    snap = priors.capture_snapshot(state, TICKER, "mid", lv=False)
    state.set_active_prior(TICKER, snap, "saved")  # bumps every node's fit key
    service.calibrate_node(state, TICKER, isos[0], "mid")  # isos[1] stays stale

    build_surface_export(state, tickers=[TICKER])
    report = replay(state.store_path, "latest", tol=1e-9)
    assert any("STALE" in n for n in report["fidelityNotes"]), report


def test_fidelity_notes_legacy_vs_captured():
    legacy = {"editedNodes": 2, "activePriors": 1}
    notes = _fidelity_notes(legacy)
    assert len(notes) == 2 and all("legacy" in n for n in notes)

    captured = {
        "editedNodes": 2, "activePriors": 1,
        "sessionEdits": {}, "varSwapQuotes": {},
        "activePriorContent": {}, "activePriorSources": {},
    }
    assert _fidelity_notes(captured) == []

    active = dict(captured, options={"observationFilterMode": "active"})
    notes = _fidelity_notes(active)
    assert len(notes) == 1 and "ACTIVE observation filter" in notes[0]

    stale = dict(captured, staleNodes=3)
    notes = _fidelity_notes(stale)
    assert len(notes) == 1 and "STALE" in notes[0]

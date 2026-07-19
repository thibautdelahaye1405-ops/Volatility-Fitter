"""P5b U6 — the draft/active message-config lifecycle.

Locks: PUT stages the DRAFT and the solve keeps using the ACTIVE rows until
Activate (event-logged, version-bumped); useDraftConfig test-drives the staged
rows; Revert discards; the legacy graph_message_edges blob migrates into an
initial v1 active config exactly once; the endpoints round-trip.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_extrapolation import extrapolate
from volfit.api.schemas import (
    GraphExtrapolateRequest,
    GraphMessageEdge,
    SyntheticObservation,
)
from volfit.api.settings_persist import save_graph_message_edges
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def state() -> AppState:
    return AppState(REF_DATE)


@pytest.fixture()
def primed(state):
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    return state


def _isos(state, ticker):
    return [e.isoformat() for e in sorted(state.forwards(ticker))]


def _row(tk, src, tgt, beta=2.0, p=1e5) -> GraphMessageEdge:
    return GraphMessageEdge(
        sourceTicker=tk, sourceExpiry=src, targetTicker=tk, targetExpiry=tgt,
        messagePrecision=p, betaAtmVol=beta, betaSkew=beta, betaCurv=beta,
        relationClass="calendar",
    )


def test_draft_stages_and_activate_flips(state):
    tk = state.active_tickers()[0]
    isos = _isos(state, tk)
    rows = [_row(tk, isos[1], isos[0])]

    state.set_graph_message_draft(rows)
    # The solve's row set (active) is untouched by a draft save…
    assert state.graph_message_edges() == []
    assert state.graph_message_draft_edges() == rows
    draft, active = state.graph_message_config()
    assert active is None
    assert draft is not None and draft.version == 1 and draft.parentVersion is None

    state.activate_message_config(notes="first cut")
    assert state.graph_message_edges() == rows
    draft, active = state.graph_message_config()
    assert active is not None
    assert (active.version, active.notes) == (1, "first cut")
    # The draft continues as a CLEAN copy staged for v2.
    assert draft is not None
    assert (draft.version, draft.parentVersion, draft.rows) == (2, 1, rows)
    actions = [e["action"] for e in state.event_tail()]
    assert "graph_message_config_activate" in actions

    # Second cycle bumps the version chain.
    state.set_graph_message_draft([])
    state.activate_message_config()
    _, active2 = state.graph_message_config()
    assert active2 is not None and (active2.version, active2.parentVersion) == (2, 1)
    assert state.graph_message_edges() == []


def test_use_draft_config_test_drives_the_staged_rows(primed):
    """A staged draft leaves the default solve on auto relations; the
    run-draft toggle solves WITH the staged rows (β=2 exact transmission on a
    +1pt pulse — the U3 firm what-if through the U6 draft)."""
    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    primed.set_graph_message_draft([_row(tk, isos[1], isos[0], beta=2.0)])

    base = dict(
        propagationMode="precision_messages",
        flatAtm=True,
        syntheticObservations=[
            SyntheticObservation(ticker=tk, expiry=isos[1], dAtmVol=0.01)
        ],
    )
    def _shift(**extra):
        resp = extrapolate(primed, GraphExtrapolateRequest(**base, **extra))
        by = {(n.ticker, n.expiry): n for n in resp.nodes}
        return by[(tk, isos[0])].shiftBp

    # Draft run: the single staged factor transmits exactly β·z = +200 bp.
    assert _shift(useDraftConfig=True) == pytest.approx(200.0, rel=0.01)
    # Default run: auto relations (β = maturity ratio ≠ 2) — a different field.
    assert _shift() != pytest.approx(200.0, rel=0.01)


def test_revert_discards_the_draft(state):
    tk = state.active_tickers()[0]
    isos = _isos(state, tk)
    state.set_graph_message_draft([_row(tk, isos[1], isos[0])])
    state.activate_message_config()
    state.set_graph_message_draft([])  # stage a wipe…
    state.revert_message_config()  # …and discard it
    draft, active = state.graph_message_config()
    assert draft is not None and active is not None
    assert draft.rows == active.rows and draft.version == active.version + 1


def test_legacy_blob_migrates_once(tmp_path):
    store = str(tmp_path / "volfit.sqlite")
    legacy = _row("SPY", "2026-12-18", "2026-09-18").model_dump()
    save_graph_message_edges(store, [legacy])

    state = AppState(REF_DATE, store_path=store)
    draft, active = state.graph_message_config()
    assert active is not None
    assert (active.version, active.notes) == (1, "migrated from graph_message_edges")
    assert [e.model_dump() for e in state.graph_message_edges()] == [legacy]
    assert draft is not None and draft.rows == active.rows

    # Reboot: the config blob is now authoritative — still v1, no re-migration.
    state2 = AppState(REF_DATE, store_path=store)
    _, active2 = state2.graph_message_config()
    assert active2 is not None and active2.version == 1


def test_config_endpoints_roundtrip():
    with TestClient(create_app(reference_date=REF_DATE)) as client:
        cfg = client.get("/graph/config/messages").json()
        assert cfg == {"draft": None, "active": None}
        # Activating nothing is a 400 (no draft staged).
        assert client.post("/graph/config/messages/activate", json={}).status_code == 400

        tk = client.get("/universe").json()["tickers"][0]
        isos = [
            e["expiry"] for e in client.get("/universe").json()["expiries"][tk]
        ]
        row = _row(tk, isos[1], isos[0]).model_dump()
        client.put("/graph/edges/messages", json={"edges": [row]})
        cfg = client.get("/graph/config/messages").json()
        assert cfg["active"] is None and cfg["draft"]["version"] == 1
        # The editor GET reads the draft.
        assert client.get("/graph/edges/messages").json()["edges"][0]["betaAtmVol"] == 2.0

        cfg = client.post(
            "/graph/config/messages/activate", json={"notes": "go"}
        ).json()
        assert cfg["active"]["version"] == 1 and cfg["active"]["notes"] == "go"
        assert cfg["draft"]["version"] == 2

        assert client.post("/graph/config/messages/revert", json={}).status_code == 200

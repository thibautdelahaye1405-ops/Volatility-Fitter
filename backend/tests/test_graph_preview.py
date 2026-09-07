"""Live-preview graph solves (GRAPH ERGONOMICS ARC, 2026-09-07 ruling).

``GraphExtrapolateRequest.preview`` is the wire flag behind the Graph lens's
Live toggle: it re-solves on every dial / relation edit with the EXACT same
numbers a Run would produce, but writes NOTHING — no innovation history
(``AppState.record_graph_innovations``, the idio band-floor feed), no
layered-mode residual-store mutation or persistence
(``solve_dynamic_field``'s ``update_store`` / ``persist_graph_dynamic_
residuals``), and no graph-inferred LAST RUN cache (``api/graph_inferred``,
what every node view draws its inferred smile from). Only the explicit Run
(``preview=False``, the default) commits. The "graph output is never prior
input" invariant holds for both — this module locks the recording side only.

Fixture mirrors ``test_graph_inferred.py``: the synthetic universe with
every ticker's prior primed via ``priors.capture_snapshot`` +
``state.set_active_prior``, so the production solve has calibratable lit
nodes to turn into observations.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, graph_inferred, priors

REF_DATE = date(2026, 6, 10)


@pytest.fixture
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        state = c.app.state.volfit
        for tk in state.active_tickers():
            snap = priors.capture_snapshot(state, tk, "mid")
            if snap is not None:
                state.set_active_prior(tk, snap, "saved")
        yield c


def test_preview_solve_matches_run_numbers(client):
    """A preview solve and a real Run over the same (unchanged) state produce
    identical per-node numbers — ``preview`` only gates recording, never the
    computation."""
    preview = client.post("/graph/extrapolate", json={"preview": True})
    assert preview.status_code == 200
    run = client.post("/graph/extrapolate", json={})
    assert run.status_code == 200

    preview_nodes = preview.json()["nodes"]
    run_nodes = run.json()["nodes"]
    assert len(preview_nodes) == len(run_nodes) > 0
    for p, r in zip(preview_nodes, run_nodes):
        assert p["ticker"] == r["ticker"] and p["expiry"] == r["expiry"]
        assert p["postAtmVol"] == pytest.approx(r["postAtmVol"])
        assert p["postSkew"] == pytest.approx(r["postSkew"])
        assert p["postCurv"] == pytest.approx(r["postCurv"])
        assert p["shiftBp"] == pytest.approx(r["shiftBp"])
        assert p["sd"] == pytest.approx(r["sd"])


def test_preview_records_nothing(client, monkeypatch):
    """A preview solve leaves the graph-inferred LAST RUN untouched and never
    calls ``record_graph_innovations``; a subsequent real Run does both."""
    state = client.app.state.volfit
    graph_inferred.clear_run(state)

    original = state.record_graph_innovations
    calls: list = []

    def spy(items):
        calls.append(items)
        return original(items)

    monkeypatch.setattr(state, "record_graph_innovations", spy)

    preview = client.post("/graph/extrapolate", json={"preview": True})
    assert preview.status_code == 200
    assert graph_inferred.graph_run(state) is None
    assert calls == []

    run = client.post("/graph/extrapolate", json={})
    assert run.status_code == 200
    assert len(calls) == 1
    assert graph_inferred.graph_run(state) is not None


def test_preview_layered_never_writes_residual_store(client, monkeypatch):
    """A layered-mode preview neither mutates the in-memory residual store
    (``update_store`` follows ``preview``) nor persists it."""
    state = client.app.state.volfit
    before = dict(state.graph_dynamic_residuals)

    persisted: list = []
    monkeypatch.setattr(
        state, "persist_graph_dynamic_residuals", lambda: persisted.append(True)
    )

    resp = client.post(
        "/graph/extrapolate",
        json={"preview": True, "propagationMode": "layered_dynamic_harmonic"},
    )
    assert resp.status_code == 200
    assert dict(state.graph_dynamic_residuals) == before
    assert persisted == []

"""P5b U5 — POST /graph/preflight dry-run diagnostics.

The contract under test: NOTHING is fitted or recorded; counts are honest;
Run is blocked only on genuine blockers (empty universe); the message-mode
sweeps surface β extremes, σ outliers, inconsistent cycles, dominated
receivers, and stranded (no-lit-path) components as warnings/info.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_preflight import preflight
from volfit.api.schemas import (
    GraphExtrapolateRequest,
    GraphMessageEdge,
    SyntheticObservation,
)
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


def _codes(resp):
    return {i.code for i in resp.issues}


def test_preflight_counts_and_never_fits_or_records(primed, monkeypatch):
    """Dry-run contract: the report never triggers a slice fit (the bootstrap
    prior tier is bypassed) and never records innovations."""
    import volfit.api.graph_nodes as gn

    monkeypatch.setattr(
        gn, "fit_or_get", lambda *a, **k: pytest.fail("preflight must not fit")
    )
    monkeypatch.setattr(
        primed,
        "record_graph_innovations",
        lambda *a, **k: pytest.fail("preflight must not record"),
    )
    resp = preflight(primed, GraphExtrapolateRequest())
    assert resp.ok is True
    assert resp.universeNodes == resp.litCount + resp.darkCount
    assert resp.universeNodes > 0
    # Ungated: every lit node observes (lazy bootstrap at Run).
    assert resp.observationCount == resp.litCount
    # Primed state has active priors — no missing-prior warning.
    assert "missing_priors" not in _codes(resp)


def test_preflight_flags_missing_priors_without_fitting(state):
    """An unprimed state: the snapshot tiers resolve to 'none' — surfaced as
    a warning covering the whole universe, still without any fit."""
    resp = preflight(state, GraphExtrapolateRequest())
    codes = _codes(resp)
    assert "missing_priors" in codes
    weak = next(i for i in resp.issues if i.code == "missing_priors")
    assert weak.severity == "warning"
    assert weak.count == resp.universeNodes


def test_preflight_blocks_only_on_empty_universe(state, monkeypatch):
    """An empty selection is the ONE genuine blocker (a live universe cannot
    be emptied through the API — ValueError guard — so the degenerate
    universe is stubbed)."""
    import volfit.api.graph_preflight as gp
    from volfit.api.graph_universe import SelectedUniverse

    monkeypatch.setattr(
        gp,
        "build_selected_universe",
        lambda *a, **k: SelectedUniverse(nodes=(), graph=None),
    )
    resp = preflight(state, GraphExtrapolateRequest())
    assert resp.ok is False
    assert [i.code for i in resp.issues] == ["empty_universe"]
    assert resp.issues[0].severity == "blocker"


def test_preflight_message_relation_sweeps(primed):
    """β extremes, σ outliers, inconsistent cycles and dominated receivers —
    all via request-level rows (the same precedence Run uses)."""
    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    rows = [
        # |β| extreme + one leg of an inconsistent cycle.
        GraphMessageEdge(
            sourceTicker=tk, sourceExpiry=isos[1], targetTicker=tk, targetExpiry=isos[0],
            messagePrecision=1e4, betaAtmVol=5.0, relationClass="calendar",
        ),
        # The other leg: product 5·5 = 25 ≠ 1 → cycle flag; also dominates
        # isos[1]'s incoming (p·β² huge vs the tiny row below).
        GraphMessageEdge(
            sourceTicker=tk, sourceExpiry=isos[0], targetTicker=tk, targetExpiry=isos[1],
            messagePrecision=1e4, betaAtmVol=5.0, relationClass="calendar",
        ),
        # σ loose (p=50 → σ ≈ 14pt).
        GraphMessageEdge(
            sourceTicker=tk, sourceExpiry=isos[2], targetTicker=tk, targetExpiry=isos[1],
            messagePrecision=50.0, betaAtmVol=1.0, relationClass="calendar",
        ),
        # σ tight (p=1e7 → σ ≈ 0.03pt).
        GraphMessageEdge(
            sourceTicker=tk, sourceExpiry=isos[2], targetTicker=tk, targetExpiry=isos[3],
            messagePrecision=1e7, betaAtmVol=1.0, relationClass="calendar",
        ),
    ]
    resp = preflight(
        primed,
        GraphExtrapolateRequest(
            propagationMode="precision_messages", messageEdges=rows
        ),
    )
    codes = _codes(resp)
    assert {"beta_extreme", "sigma_loose", "sigma_tight", "beta_cycle",
            "dominated_receiver"} <= codes
    assert resp.ok is True  # warnings never block


def test_preflight_no_lit_path_and_dropped_pulses(primed):
    """A what-if pulse on one node of a two-node relation island strands the
    rest of the universe (§14.3 warning); pulses outside the selection are
    reported as dropped."""
    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    rows = [
        GraphMessageEdge(
            sourceTicker=tk, sourceExpiry=isos[1], targetTicker=tk, targetExpiry=isos[0],
            messagePrecision=1e4, betaAtmVol=1.0, relationClass="calendar",
        ),
    ]
    resp = preflight(
        primed,
        GraphExtrapolateRequest(
            propagationMode="precision_messages",
            messageEdges=rows,
            syntheticObservations=[
                SyntheticObservation(ticker=tk, expiry=isos[0], dAtmVol=0.01),
                SyntheticObservation(ticker="NOPE", expiry="2099-01-01", dAtmVol=0.01),
            ],
        ),
    )
    codes = _codes(resp)
    assert "pulses_outside_universe" in codes
    assert "no_lit_path" in codes
    stranded = next(i for i in resp.issues if i.code == "no_lit_path")
    assert stranded.count == resp.universeNodes - 2
    assert resp.observationCount == 1


def test_preflight_endpoint_and_calendar_off(primed):
    """The route round-trips, and the calendar-off policy is surfaced as info
    (never a blocker)."""
    with TestClient(create_app(reference_date=REF_DATE)) as client:
        resp = client.post(
            "/graph/preflight",
            json={"propagationMode": "precision_messages", "calendarEnabled": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "calendar_disabled" in {i["code"] for i in body["issues"]}
        assert all(i["severity"] != "blocker" for i in body["issues"])

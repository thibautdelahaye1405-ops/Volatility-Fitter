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


# ------------------------------------------------ P6 V3 layered-mode sweeps
def _layered(**over):
    return GraphExtrapolateRequest(
        propagationMode="layered_dynamic_harmonic", **over
    )


def test_layered_directed_cycle_blocks(primed):
    """A directed relation cycle is the one thing the layered solve REJECTS
    (§6.5) — preflight must block Run on it."""
    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    rows = [
        GraphMessageEdge(
            sourceTicker=tk, sourceExpiry=isos[0], targetTicker=tk, targetExpiry=isos[1],
            messagePrecision=1e4, betaAtmVol=1.0, relationClass="broad_index",
        ),
        GraphMessageEdge(
            sourceTicker=tk, sourceExpiry=isos[1], targetTicker=tk, targetExpiry=isos[0],
            messagePrecision=1e4, betaAtmVol=1.0, relationClass="broad_index",
        ),
    ]
    resp = preflight(primed, _layered(messageEdges=rows))
    assert resp.ok is False
    blocker = next(i for i in resp.issues if i.code == "directed_cycle")
    assert blocker.severity == "blocker"
    assert blocker.count == 2
    # The same pair as RECIPROCAL rows is fine (harmonic, not a DAG cycle).
    recip = [r.model_copy(update={"relationClass": "calendar"}) for r in rows]
    assert "directed_cycle" not in _codes(preflight(primed, _layered(messageEdges=recip)))


def test_layered_directed_support_is_one_way(primed):
    """§7.7 support replaces the undirected §14.3 sweep: a directed arc
    transmits source→target only, so support follows the arrow."""
    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    pulse = [SyntheticObservation(ticker=tk, expiry=isos[0], dAtmVol=0.01)]
    arrow = GraphMessageEdge(
        sourceTicker=tk, sourceExpiry=isos[0], targetTicker=tk, targetExpiry=isos[1],
        messagePrecision=1e4, betaAtmVol=1.0, relationClass="broad_index",
    )
    resp = preflight(
        primed, _layered(messageEdges=[arrow], syntheticObservations=pulse)
    )
    codes = _codes(resp)
    assert "no_lit_path" not in codes  # replaced in layered mode
    supported = next(i for i in resp.issues if i.code == "no_support")
    assert supported.count == resp.universeNodes - 2  # pulse + arrow target
    # Reverse the arrow: the observed node cannot support its INFORMER.
    back = GraphMessageEdge(
        sourceTicker=tk, sourceExpiry=isos[1], targetTicker=tk, targetExpiry=isos[0],
        messagePrecision=1e4, betaAtmVol=1.0, relationClass="broad_index",
    )
    resp = preflight(
        primed, _layered(messageEdges=[back], syntheticObservations=pulse)
    )
    stranded = next(i for i in resp.issues if i.code == "no_support")
    assert stranded.count == resp.universeNodes - 1


def test_layered_residual_store_sweeps(primed):
    """Stored residuals under a different config version warn (Run purges
    them, golden 15.13); random-walk memory older than 30d warns; with a
    half-life the same age is merely 'effectively decayed' info. The stored
    residual also counts as SUPPORT (the D7 ghost prediction)."""
    import numpy as np

    from volfit.graph.temporal_state import empty_residual

    tk = primed.active_tickers()[0]
    isos = _isos(primed, tk)
    old_day = float(primed.reference_date.toordinal()) - 40.0
    primed.graph_dynamic_residuals[(tk, isos[0])] = empty_residual(
        "some-old-version"
    ).updated_hard(
        np.array([0.01, 0.0, 0.0]), np.array([1e-4, 1.0, 1.0]), old_day, "cal:test"
    )
    pulse = [SyntheticObservation(ticker=tk, expiry=isos[1], dAtmVol=0.01)]
    arrow = GraphMessageEdge(
        sourceTicker=tk, sourceExpiry=isos[1], targetTicker=tk, targetExpiry=isos[2],
        messagePrecision=1e4, betaAtmVol=1.0, relationClass="broad_index",
    )
    resp = preflight(
        primed, _layered(messageEdges=[arrow], syntheticObservations=pulse)
    )
    codes = _codes(resp)
    assert "residual_config_mismatch" in codes
    rw = next(i for i in resp.issues if i.code == "stale_residual")
    assert rw.severity == "warning"  # random walk: never decays
    # The ghost seeds support: pulse + target + the residual-backed node.
    supported = next(i for i in resp.issues if i.code == "no_support")
    assert supported.count == resp.universeNodes - 3
    # With a half-life, 40d >> 3×2d is merely decayed — info, not warning.
    resp = preflight(
        primed,
        _layered(
            messageEdges=[arrow],
            syntheticObservations=pulse,
            residualHalfLifeDays=2.0,
        ),
    )
    decayed = next(i for i in resp.issues if i.code == "stale_residual")
    assert decayed.severity == "info"

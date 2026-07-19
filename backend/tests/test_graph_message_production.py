"""Phase-3 tests: precision-message production orchestration (arc P3).

Exit gate (spec §23 Phase 3): an end-to-end production request runs the
message operator through graph_extrapolation.solve — reusing transported
priors, lit innovations, reconstruction, bands, attribution — while the
legacy smooth_field path stays byte-identical. Controlled golden semantics
(full-amplitude / shrunk / averaged transfer) are locked through the REAL
production assembly (solve_message_field) with hand-built universes, and the
schema-v2 machinery (edge precedence, persistence, the test-locked legacy
direction inversion, cycle diagnostics) is exercised end to end."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_extrapolation import extrapolate, solve
from volfit.api.graph_message import (
    DISCONNECTED_Z_SD,
    message_edges_from_legacy,
    solve_message_field,
)
from volfit.api.graph_select import observation_plan
from volfit.api.graph_universe import SelectedNode, SelectedUniverse
from volfit.api.schemas import (
    GraphEdgeInput,
    GraphExtrapolateRequest,
    GraphMessageEdge,
    GraphObservationPlanRequest,
)
from volfit.api.state import AppState
from volfit.api.workspace import build_doc, restore_doc

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


# --------------------------------------------------- controlled fixtures
def _ladder_universe():
    """One ticker, three expiries: A(0.25y, dark), B(0.5y, LIT), C(1y, dark)."""
    nodes = (
        SelectedNode("TT", "A", False),
        SelectedNode("TT", "B", True),
        SelectedNode("TT", "C", False),
    )
    t_by = {("TT", "A"): 0.25, ("TT", "B"): 0.5, ("TT", "C"): 1.0}
    return SelectedUniverse(nodes=nodes, graph=None), t_by


def _cross_universe():
    """Three tickers, one shared expiry: X and Y lit, Z dark."""
    nodes = (
        SelectedNode("X", "E", True),
        SelectedNode("Y", "E", True),
        SelectedNode("Z", "E", False),
    )
    t_by = {("X", "E"): 0.5, ("Y", "E"): 0.5, ("Z", "E"): 0.5}
    return SelectedUniverse(nodes=nodes, graph=None), t_by


def _solve_ladder(request, obs_atm=0.21, p0=1e12, r_cal=1e12, **kw):
    universe, t_by = _ladder_universe()
    baseline = np.zeros((3, 3))
    baseline[:, 0] = 0.20
    return (
        solve_message_field(
            universe,
            t_by,
            request,
            baseline,
            np.full((3, 3), p0),
            np.array([1]),
            np.array([[obs_atm, 0.0, 0.0]]),
            np.full((1, 3), r_cal),
            **kw,
        ),
        universe,
    )


MSG = dict(propagationMode="precision_messages")


# ----------------------------------------------------- byte identity lock
def test_smooth_field_default_is_unchanged(primed):
    """§21.10: the default mode is the legacy path — explicit smooth_field and
    an untouched request produce identical payloads, with the new diagnostic
    fields inert."""
    a = extrapolate(primed, GraphExtrapolateRequest())
    b = extrapolate(primed, GraphExtrapolateRequest(propagationMode="smooth_field"))
    assert a.model_dump() == b.model_dump()
    assert a.propagationMode == "smooth_field"
    assert a.cycleDiagnostics == []
    assert all(n.qIncoming is None and n.noLitPath is None for n in a.nodes)


# ------------------------------------------- golden semantics, production path
def test_full_amplitude_calendar(primed_request=None):
    """§21.1 through the production assembly: +1 vol point at 6M propagates at
    FULL amplitude — +2 points to 3M, +0.5 to 1Y (alphaT=1, desk rho=1)."""
    (field, diag), _u = _solve_ladder(GraphExtrapolateRequest(**MSG))
    assert field.mean[0, 0] == pytest.approx(0.22, abs=1e-6)  # 3M: beta 2
    assert field.mean[2, 0] == pytest.approx(0.205, abs=1e-6)  # 1Y: beta 0.5
    assert field.mean[1, 0] == pytest.approx(0.21, abs=1e-6)  # lit pinned
    assert not diag.no_lit_path.any()
    assert diag.cycle_flags == ()
    assert np.all(diag.q_incoming > 0.0)
    # skew/curv saw zero innovation and stay at baseline exactly
    assert np.allclose(field.mean[:, 1:], 0.0, atol=1e-9)


def test_shrunk_amplitude_via_anchor():
    """§21.12 through production: calendarAmplitude=0.34 transfers exactly
    rho*beta*z on a single-source receiver."""
    (field, _diag), _u = _solve_ladder(
        GraphExtrapolateRequest(calendarAmplitude=0.34, **MSG)
    )
    assert field.mean[0, 0] == pytest.approx(0.20 + 0.34 * 0.02, abs=1e-6)
    assert field.mean[2, 0] == pytest.approx(0.20 + 0.34 * 0.005, abs=1e-6)


def test_anchor_override_wins():
    """§18.4: an explicit innovationAnchorPrecision overrides the derived
    anchor — zero forces desk full force even with a shrunk multiplier."""
    (field, _), _u = _solve_ladder(
        GraphExtrapolateRequest(
            calendarAmplitude=0.34, innovationAnchorPrecision=0.0, **MSG
        )
    )
    assert field.mean[0, 0] == pytest.approx(0.22, abs=1e-6)


def test_cross_asset_average():
    """§21.4 through production: a dark name hearing two equal-precision
    beta-one lit messages posts their average."""
    universe, t_by = _cross_universe()
    baseline = np.zeros((3, 3))
    baseline[:, 0] = 0.20
    req = GraphExtrapolateRequest(**MSG)
    field, diag = solve_message_field(
        universe,
        t_by,
        req,
        baseline,
        np.full((3, 3), 1e12),
        np.array([0, 1]),
        np.array([[0.21, 0.0, 0.0], [0.23, 0.0, 0.0]]),
        np.full((2, 3), 1e12),
    )
    assert field.mean[2, 0] == pytest.approx(0.22, abs=1e-6)
    assert not diag.no_lit_path.any()


def test_weak_baseline_weakens_the_innovation():
    """§15.2: r_d combines calibration AND baseline precision harmonically —
    an uncertain transported prior cannot yield a precise innovation. NB with
    a single source and zero anchor the transfer is r_d-invariant (Invariant
    2), so the effect is observed against a competing anchor (shrunk mode)."""
    req = GraphExtrapolateRequest(calendarAmplitude=0.5, **MSG)
    (strong, _), _u = _solve_ladder(req, p0=1e12)
    (weak, _), _u = _solve_ladder(req, p0=1e2)
    shift_strong = strong.mean[0, 0] - 0.20
    shift_weak = weak.mean[0, 0] - 0.20
    assert 0.0 < shift_weak < 0.5 * shift_strong


def test_no_lit_component_and_band_placement():
    """§14.3 + §15.3: a disconnected dark ticker stays at its prior with the
    explicitly broad disconnected variance PLUS its baseline variance; an
    observed node's band does NOT re-add the baseline term."""
    nodes = (
        SelectedNode("TT", "A", True),
        SelectedNode("TT", "B", True),
        SelectedNode("ZZ", "Q", False),  # different ticker, different expiry
    )
    t_by = {("TT", "A"): 0.25, ("TT", "B"): 0.5, ("ZZ", "Q"): 0.4}
    universe = SelectedUniverse(nodes=nodes, graph=None)
    baseline = np.zeros((3, 3))
    baseline[:, 0] = 0.20
    p0 = np.full((3, 3), 1e4)
    field, diag = solve_message_field(
        universe,
        t_by,
        GraphExtrapolateRequest(**MSG),
        baseline,
        p0,
        np.array([0, 1]),
        np.array([[0.21, 0.0, 0.0], [0.21, 0.0, 0.0]]),
        np.full((2, 3), 1e10),
    )
    assert diag.no_lit_path[2] and not diag.no_lit_path[0]
    assert field.mean[2, 0] == pytest.approx(0.20, abs=1e-12)  # stays at prior
    expected_var = DISCONNECTED_Z_SD[0] ** 2 + 1.0 / 1e4  # broad + baseline once
    assert field.sd[2, 0] == pytest.approx(np.sqrt(expected_var), rel=1e-9)
    # observed node: posterior variance only (baseline lives inside r_d)
    assert field.sd[0, 0] ** 2 < 1.0 / 1e4


# ------------------------------------------------- schema v2 edge machinery
def test_explicit_message_edges_replace_auto():
    """Request messageEdges define the whole topology: beta-one calendar rows
    make the 3M receiver copy the 6M innovation instead of doubling it."""
    rows = [
        GraphMessageEdge(
            sourceTicker="TT", sourceExpiry="B", targetTicker="TT", targetExpiry="A",
            messagePrecision=1e3, betaAtmVol=1.0, relationClass="calendar",
        ),
        GraphMessageEdge(
            sourceTicker="TT", sourceExpiry="B", targetTicker="TT", targetExpiry="C",
            messagePrecision=1e3, betaAtmVol=1.0, relationClass="calendar",
        ),
    ]
    (field, _), _u = _solve_ladder(
        GraphExtrapolateRequest(messageEdges=rows, **MSG)
    )
    assert field.mean[0, 0] == pytest.approx(0.21, abs=1e-6)
    assert field.mean[2, 0] == pytest.approx(0.21, abs=1e-6)


def test_persisted_message_edges_used_when_request_empty():
    rows = [
        GraphMessageEdge(
            sourceTicker="TT", sourceExpiry="B", targetTicker="TT", targetExpiry="A",
            messagePrecision=1e3, betaAtmVol=1.0,
        )
    ]
    (field, diag), _u = _solve_ladder(
        GraphExtrapolateRequest(**MSG), persisted_edges=rows
    )
    assert field.mean[0, 0] == pytest.approx(0.21, abs=1e-6)
    # C is not named by the persisted topology -> its own no-lit component
    assert diag.no_lit_path[2]


def test_calendar_distance_rule_derives_precision():
    """precisionRule='calendar_distance' ignores messagePrecision and applies
    the §9.2 family — visible through the receiver conditional q."""
    rows = [
        GraphMessageEdge(
            sourceTicker="TT", sourceExpiry="B", targetTicker="TT", targetExpiry="A",
            messagePrecision=1.0, precisionRule="calendar_distance",
            relationClass="calendar",
        )
    ]
    (_, diag), _u = _solve_ladder(GraphExtrapolateRequest(messageEdges=rows, **MSG))
    expected = 1.7e3 / (0.97 + np.sqrt(0.25))
    assert diag.q_incoming[0] == pytest.approx(expected, rel=1e-9)


def test_legacy_conversion_inverts_labels_not_economics():
    """§18.3 test-locked: engine truth is 'to informs from', so the v2 target
    (receiver) = legacy `from` and the v2 source (informer) = legacy `to`."""
    legacy = [
        GraphEdgeInput(
            fromTicker="NAME", fromExpiry="E", toTicker="INDEX", toExpiry="E",
            weight=2.0, betaAtmVol=0.7, betaSkew=0.6, betaCurv=0.5,
        )
    ]
    rows = message_edges_from_legacy(legacy, precision_per_weight=100.0)
    assert len(rows) == 1
    assert rows[0].targetTicker == "NAME" and rows[0].sourceTicker == "INDEX"
    assert rows[0].messagePrecision == pytest.approx(200.0)
    assert (rows[0].betaAtmVol, rows[0].betaSkew, rows[0].betaCurv) == (0.7, 0.6, 0.5)


def test_cycle_diagnostics_flag_non_reciprocal_pair():
    rows = [
        GraphMessageEdge(
            sourceTicker="TT", sourceExpiry="B", targetTicker="TT", targetExpiry="A",
            messagePrecision=1e3, betaAtmVol=2.0,
        ),
        GraphMessageEdge(
            sourceTicker="TT", sourceExpiry="A", targetTicker="TT", targetExpiry="B",
            messagePrecision=1e3, betaAtmVol=2.0,
        ),
    ]
    (_, diag), _u = _solve_ladder(GraphExtrapolateRequest(messageEdges=rows, **MSG))
    assert len(diag.cycle_flags) == 1
    assert diag.cycle_flags[0][2] == pytest.approx(4.0)


def test_message_edges_persist_and_ride_the_workspace(state):
    rows = [
        GraphMessageEdge(
            sourceTicker="SPY", sourceExpiry="2026-09-18",
            targetTicker="AAPL", targetExpiry="2026-09-18",
            messagePrecision=5e3, relationClass="broad_index",
        )
    ]
    state.set_graph_message_edges(rows)
    assert state.graph_message_edges() == rows
    doc = build_doc(state)
    assert doc["graphMessageEdges"][0]["targetTicker"] == "AAPL"
    restore_doc(state, doc)
    assert state.graph_message_edges() == rows


# --------------------------------------------------------- end-to-end + ports
def test_end_to_end_message_extrapolate(primed):
    """Exit gate: a full production request under precision_messages returns a
    coherent field with the wire diagnostics; near-zero innovations (prior ==
    today) keep every node at its prior."""
    resp = extrapolate(primed, GraphExtrapolateRequest(**MSG))
    assert resp.propagationMode == "precision_messages"
    assert len(resp.nodes) > 0
    for node in resp.nodes:
        assert node.qIncoming is not None and node.qIncoming >= 0.0
        assert node.noLitPath is False
        assert node.postAtmVol == pytest.approx(node.priorAtmVol, abs=2e-3)
        assert node.bandHi > node.bandLo


def test_end_to_end_reconstructed_smile_route():
    """Exit gate: the node-smile route reconstructs a smile + attribution from
    the message posterior (MessagePosterior.attribution feeding the panel),
    with mode parity on the payload shape."""
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        tk = "ALPHA"
        isos = [e["expiry"] for e in client.get("/universe").json()["expiries"][tk]]
        client.post(f"/calibrate/{tk}/{isos[0]}")
        client.post(f"/calibrate/{tk}/{isos[1]}")
        bodies = {}
        for mode in ("precision_messages", "smooth_field"):
            resp = client.get(
                f"/graph/extrapolate/nodes/{tk}/{isos[1]}",
                params={"propagationMode": mode},
            )
            assert resp.status_code == 200
            bodies[mode] = resp.json()
        msg = bodies["precision_messages"]
        assert len(msg["post"]) > 0  # reconstructed posterior smile points
        assert len(msg["postBandLo"]) == len(msg["post"])
        assert msg["attribution"] != []  # MessagePosterior.attribution feed
        assert len(msg["post"]) == len(bodies["smooth_field"]["post"])
        # A node with nothing to reconstruct from 200s with an empty curve in
        # BOTH modes (parity — not a message-mode regression).
        for mode in ("precision_messages", "smooth_field"):
            resp = client.get(
                f"/graph/extrapolate/nodes/{tk}/{isos[2]}",
                params={"propagationMode": mode},
            )
            assert resp.status_code == 200
            assert resp.json()["post"] == []


def test_hybrid_reduces_to_message_at_zero_smoothness(primed):
    """§15.4: hybrid = message + eta*L_dir^beta (+OT); with etaScale=0 and
    lambdaScale=0 the extra term vanishes and hybrid equals pure message."""
    msg = extrapolate(primed, GraphExtrapolateRequest(**MSG))
    hyb = extrapolate(
        primed,
        GraphExtrapolateRequest(
            propagationMode="hybrid", etaScale=0.0, lambdaScale=0.0
        ),
    )
    assert hyb.propagationMode == "hybrid"
    assert [n.model_dump() for n in hyb.nodes] == [n.model_dump() for n in msg.nodes]


def test_observation_plan_in_message_mode(primed):
    """The quote-next closed form ports to Σ⁺ columns (graph/select.py)."""
    tk = primed.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(primed.forwards(tk))]
    primed.set_node_lit(tk, isos[1], False)
    resp = observation_plan(
        primed, GraphObservationPlanRequest(topN=5, **MSG)
    )
    assert resp.nCandidates >= 1
    assert resp.candidates, "expected ranked candidates in message mode"
    for cand in resp.candidates:
        assert cand.selfSdAfterBp <= cand.selfSdBeforeBp + 1e-9
        assert cand.totalVarReductionPct >= 0.0
        assert cand.assumedPrecision > 0.0

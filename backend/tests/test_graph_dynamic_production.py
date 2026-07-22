"""Phase-4 tests: layered dynamic-harmonic production orchestration.

EXIT GATE (framework §17 Phase 4): the §5 asynchronous A/B replay runs
end-to-end THROUGH the production assembly (solve_dynamic_field — the same
seam graph_extrapolation.solve forks into) with persistent residual state
across snapshots, reproducing the Phase-0 fixture sequences. Also locks:
relation-semantics defaults (§9.2), auto relations staying reciprocal
(harmonic calendar transfer through the production path), directed-cycle
rejection, config-version residual invalidation (golden 15.13), the
holdout/what-if no-persistence rule, and legacy byte-identity (the untouched
smooth_field/message suites plus the inert-defaults check here)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from volfit.api.graph_dynamic import row_semantics, solve_dynamic_field
from volfit.api.graph_universe import SelectedNode, SelectedUniverse
from volfit.api.schemas import GraphExtrapolateRequest, GraphMessageEdge
from volfit.graph.directed_state import DirectedCycleError

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "graph_dynamic_golden.json").read_text()
)

BASE = 0.20    # flat transported-prior ATM baseline
SCALE = 1e-3   # fixture exposition units -> vol units

LAYERED = dict(propagationMode="layered_dynamic_harmonic")


def _pair_universe():
    nodes = (SelectedNode("TA", "E", True), SelectedNode("TB", "E", True))
    t_by = {("TA", "E"): 0.5, ("TB", "E"): 0.5}
    return SelectedUniverse(nodes=nodes, graph=None), t_by


def _arrow(beta=1.0, **kw):
    return GraphMessageEdge(
        sourceTicker="TA", sourceExpiry="E", targetTicker="TB", targetExpiry="E",
        messagePrecision=1e6, betaAtmVol=beta, relationClass="broad_index", **kw,
    )


def _solve_pair(request, obs, store, now_day):
    """One snapshot through the production assembly; obs = {node_idx: atm}."""
    universe, t_by = _pair_universe()
    baseline = np.zeros((2, 3))
    baseline[:, 0] = BASE
    idx = np.array(sorted(obs), dtype=int)
    values = np.zeros((idx.size, 3))
    values[:, 0] = [obs[i] for i in sorted(obs)]
    field, diagnostics = solve_dynamic_field(
        universe, t_by, request, baseline, np.full((2, 3), 1e12),
        idx, values, np.full((idx.size, 3), 1e12),
        residual_store=store, now_day=now_day,
    )
    return field, diagnostics


def _replay(request, store):
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    a_marks, b_marks = [], []
    last_a = None
    for t in fx["snapshots"]:
        if t in obs_a:
            last_a = BASE + obs_a[t] * SCALE
        obs = {0: last_a}
        if t in obs_b:
            obs[1] = BASE + obs_b[t] * SCALE
        field, _ = _solve_pair(request, obs, store, now_day=t)
        a_marks.append(field.mean[0, 0])
        b_marks.append(field.mean[1, 0])
    return a_marks, b_marks


# ------------------------------------------------------------------ exit gate
def test_exit_gate_async_ab_through_production():
    """§5 A/B end-to-end: B follows A dark, keeps its −3 dislocation after
    t=3.5, never reverses, and A never moves off its own calibration."""
    fx = FIXTURE["async_ab"]
    store: dict = {}
    request = GraphExtrapolateRequest(messageEdges=[_arrow()], **LAYERED)
    a, b = _replay(request, store)
    expected_a = [BASE + v * SCALE for v in fx["expected_a"]]
    expected_b = [BASE + v * SCALE for v in fx["expected_b"]]
    assert a == pytest.approx(expected_a, rel=1e-9)
    assert b == pytest.approx(expected_b, rel=1e-6)
    # the persistent dislocation is in the store, with provenance
    res = store[("TB", "E")]
    assert res.mean[0] == pytest.approx(
        fx["expected_u_after_3_5"] * SCALE, rel=1e-6
    )
    assert res.persistable()


def test_exit_gate_half_life_variant():
    fx = FIXTURE["async_ab"]
    hl = FIXTURE["residual_half_life"]
    request = GraphExtrapolateRequest(
        messageEdges=[_arrow()], residualHalfLifeDays=hl["half_life"], **LAYERED
    )
    _, b = _replay(request, {})
    expected = BASE + hl["expected_b_at_4_0"] * SCALE
    assert b[fx["snapshots"].index(4.0)] == pytest.approx(expected, rel=1e-6)


def test_zero_reverse_influence_through_production():
    """Golden 15.2 at the API seam: A's path is identical with and without
    B's t=3.5 print — the cut plus the clamped boundary, end to end."""
    request = GraphExtrapolateRequest(messageEdges=[_arrow()], **LAYERED)
    a_with, _ = _replay(request, {})
    fx = FIXTURE["async_ab"]
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    store: dict = {}
    a_without = []
    last_a = None
    for t in fx["snapshots"]:
        if t in obs_a:
            last_a = BASE + obs_a[t] * SCALE
        field, _ = _solve_pair(request, {0: last_a}, store, now_day=t)
        a_without.append(field.mean[0, 0])
    assert a_with == pytest.approx(a_without, rel=1e-12)


# ------------------------------------------------------- semantics + topology
def test_relation_semantics_defaults():
    assert row_semantics(_arrow()) == "directed_state"
    assert row_semantics(_arrow(relationSemantics="reciprocal_harmonic")) == (
        "reciprocal_harmonic"
    )
    calendar = GraphMessageEdge(
        sourceTicker="T", sourceExpiry="B", targetTicker="T", targetExpiry="A",
        relationClass="calendar",
    )
    assert row_semantics(calendar) == "reciprocal_harmonic"


def test_directed_cycle_rejected():
    back = GraphMessageEdge(
        sourceTicker="TB", sourceExpiry="E", targetTicker="TA", targetExpiry="E",
        messagePrecision=1e6, relationClass="broad_index",
    )
    request = GraphExtrapolateRequest(messageEdges=[_arrow(), back], **LAYERED)
    with pytest.raises(DirectedCycleError):
        _solve_pair(request, {0: BASE + 0.01}, {}, now_day=0.0)


def test_auto_relations_stay_reciprocal_calendar_transfer():
    """No explicit rows: auto ladders run reciprocal-harmonic — +1pt at the
    lit 6M transfers +2pt to 3M and +0.5pt to 1Y (§8 / §21.1 semantics)."""
    nodes = (
        SelectedNode("TT", "A", False),
        SelectedNode("TT", "B", True),
        SelectedNode("TT", "C", False),
    )
    t_by = {("TT", "A"): 0.25, ("TT", "B"): 0.5, ("TT", "C"): 1.0}
    universe = SelectedUniverse(nodes=nodes, graph=None)
    baseline = np.zeros((3, 3))
    baseline[:, 0] = BASE
    request = GraphExtrapolateRequest(**LAYERED)
    field, diagnostics = solve_dynamic_field(
        universe, t_by, request, baseline, np.full((3, 3), 1e12),
        np.array([1]), np.array([[BASE + 0.01, 0.0, 0.0]]),
        np.full((1, 3), 1e12),
    )
    assert field.mean[:, 0] == pytest.approx(
        [BASE + 0.02, BASE + 0.01, BASE + 0.005], rel=1e-6
    )
    assert not diagnostics.no_lit_path.any()


# ------------------------------------------------------ state discipline
def test_config_change_invalidates_residual():
    """Golden 15.13 through production: a beta change drops the stored
    dislocation — B reverts to the pure systematic prediction, flagged by
    the store simply no longer carrying it."""
    fx = FIXTURE["async_ab"]
    store: dict = {}
    request = GraphExtrapolateRequest(messageEdges=[_arrow()], **LAYERED)
    _replay(request, store)  # leaves u = −3·SCALE at t=5
    assert ("TB", "E") in store
    changed = GraphExtrapolateRequest(messageEdges=[_arrow(beta=1.5)], **LAYERED)
    field, _ = _solve_pair(
        changed, {0: BASE + fx["obs_a"]["5.0"] * SCALE}, store, now_day=6.0
    )
    assert ("TB", "E") not in store  # invalidated, never silently reused
    assert field.mean[1, 0] == pytest.approx(
        BASE + 1.5 * fx["obs_a"]["5.0"] * SCALE, rel=1e-6
    )


def test_explicit_config_version_survives_beta_drift():
    """The Phase-5 campaign-1 lesson: data-derived beta re-estimation must
    NOT wipe temporal memory when the caller pins residualConfigVersion —
    while the structural default still invalidates on explicit edits
    (locked by test_config_change_invalidates_residual)."""
    fx = FIXTURE["async_ab"]
    store: dict = {}
    pinned = dict(LAYERED, residualConfigVersion="v-stable")
    _replay(GraphExtrapolateRequest(messageEdges=[_arrow(beta=1.0)], **pinned), store)
    assert ("TB", "E") in store  # u = −3·SCALE under the pinned identity
    drifted = GraphExtrapolateRequest(messageEdges=[_arrow(beta=1.1)], **pinned)
    field, _ = _solve_pair(
        drifted, {0: BASE + fx["obs_a"]["5.0"] * SCALE}, store, now_day=6.0
    )
    assert ("TB", "E") in store  # memory SURVIVED the re-estimated beta
    expected = BASE + (1.1 * fx["obs_a"]["5.0"] - 3.0) * SCALE
    assert field.mean[1, 0] == pytest.approx(expected, rel=1e-6)


def test_stateless_and_firm_solves_never_persist():
    request = GraphExtrapolateRequest(messageEdges=[_arrow()], **LAYERED)
    universe, t_by = _pair_universe()
    baseline = np.zeros((2, 3))
    baseline[:, 0] = BASE
    store: dict = {}
    solve_dynamic_field(
        universe, t_by, request, baseline, np.full((2, 3), 1e12),
        np.array([0, 1]), np.array([[0.21, 0, 0], [0.21, 0, 0]]),
        np.full((2, 3), 1e12), firm_observations=True,
        residual_store=store, now_day=0.0,
    )
    assert store == {}  # what-if pulses are non-persisting (§10 Step 8)


def test_stale_observation_demotes_to_soft_anchor():
    """Clamp-requires-freshness: an observation older than clampMaxAgeDays is
    no longer a hard boundary — the mark can differ from the stale print."""
    request = GraphExtrapolateRequest(messageEdges=[_arrow()], **LAYERED)
    universe, t_by = _pair_universe()
    baseline = np.zeros((2, 3))
    baseline[:, 0] = BASE
    field, _ = _solve_pair(request, {0: BASE + 0.01, 1: BASE - 0.01}, {}, 0.0)
    assert field.mean[1, 0] == pytest.approx(BASE - 0.01, rel=1e-9)  # fresh: clamped
    field_stale, _ = solve_dynamic_field(
        universe, t_by, request, baseline, np.full((2, 3), 1e12),
        np.array([0, 1]), np.array([[BASE + 0.01, 0, 0], [BASE - 0.01, 0, 0]]),
        np.full((2, 3), 1e4),  # calibration precision, not firm
        obs_age_days=np.array([0.0, 30.0]),  # B a month old
        now_day=0.0,
    )
    # B's mark is now a compromise between its stale print and A's prediction
    assert BASE - 0.01 < field_stale.mean[1, 0] < BASE + 0.01


def test_readonly_store_reads_but_never_writes():
    """Phase-5 holdout contract: update_store=False solves USE the persisted
    residual for predictions but neither write, purge, nor invalidate the
    store — including under a changed config version."""
    fx = FIXTURE["async_ab"]
    store: dict = {}
    request = GraphExtrapolateRequest(messageEdges=[_arrow()], **LAYERED)
    _replay(request, store)  # leaves u = −3·SCALE
    frozen = dict(store)
    universe, t_by = _pair_universe()
    baseline = np.zeros((2, 3))
    baseline[:, 0] = BASE
    field, _ = solve_dynamic_field(
        universe, t_by, request, baseline, np.full((2, 3), 1e12),
        np.array([0]), np.array([[BASE + fx["obs_a"]["5.0"] * SCALE, 0, 0]]),
        np.full((1, 3), 1e12),
        residual_store=store, update_store=False, now_day=6.0,
    )
    # prediction USES the stored dislocation (B = A − 3, not B = A) ...
    assert field.mean[1, 0] == pytest.approx(
        BASE + (fx["obs_a"]["5.0"] - 3.0) * SCALE, rel=1e-6
    )
    # ... and the store is untouched, even though A was observed
    assert store == frozen
    # a changed config must not purge under read-only either
    changed = GraphExtrapolateRequest(messageEdges=[_arrow(beta=1.5)], **LAYERED)
    solve_dynamic_field(
        universe, t_by, changed, baseline, np.full((2, 3), 1e12),
        np.array([0]), np.array([[BASE + 0.015, 0, 0]]),
        np.full((1, 3), 1e12),
        residual_store=store, update_store=False, now_day=6.0,
    )
    assert store == frozen


def test_wire_decomposition_and_surprise():
    """Phase-6 V0 exit-gate contract: every ATM mark decomposes exactly as
    baseline + systematic + residual + harmonic, and B's t=3.5 dislocation
    fires a loud §12.2 residual surprise."""
    fx = FIXTURE["async_ab"]
    store: dict = {}
    request = GraphExtrapolateRequest(messageEdges=[_arrow()], **LAYERED)
    obs_a = {float(k): v for k, v in fx["obs_a"].items()}
    obs_b = {float(k): v for k, v in fx["obs_b"].items()}
    last_a, chi_35, decomp_checked = None, None, 0
    for t in fx["snapshots"]:
        if t in obs_a:
            last_a = BASE + obs_a[t] * SCALE
        obs = {0: last_a}
        if t in obs_b:
            obs[1] = BASE + obs_b[t] * SCALE
        field, diag = _solve_pair(request, obs, store, now_day=t)
        for i, name in enumerate([("TA", "E"), ("TB", "E")]):
            row = diag.per_node[name]
            total = (
                row["systematicAtmVol"]
                + row["residualAtmVol"]
                + row["harmonicAtmVol"]
            )
            assert BASE + total == pytest.approx(field.mean[i, 0], abs=1e-9)
            decomp_checked += 1
        if t == 3.5:
            chi_35 = diag.per_node[("TB", "E")]["residualSurpriseAtm"]
            assert diag.per_node[("TB", "E")]["boundaryClass"] == "fresh_certified"
        if t == 4.0:
            row = diag.per_node[("TB", "E")]
            assert row["boundaryClass"] == "unobserved"
            assert row["residualAtmVol"] == pytest.approx(-3 * SCALE, rel=1e-6)
            assert row["residualAgeDays"] == pytest.approx(0.5)
    assert decomp_checked == 22
    # -3 points against sqrt(2) x the 1-point relation noise (1/q = 1e-6 on
    # the ATM handle, prior residual variance equal): chi = -3/sqrt(2).
    assert chi_35 == pytest.approx(-3.0 / np.sqrt(2.0), rel=1e-3)


def test_prior_save_guard_graph_output_never_prior_input():
    """Framework §10 Step 8 / §29.4 invariant, certification-locked: a dark
    node's graph-extrapolated surface never enters a prior snapshot, even
    right after a solve produced values for it — only lit calibrated nodes
    are captured."""
    from datetime import date

    from volfit.api import priors
    from volfit.api.graph_extrapolation import extrapolate
    from volfit.api.state import AppState

    state = AppState(date(2026, 6, 10))
    tk = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.forwards(tk))]
    dark = isos[0]
    state.set_node_lit(tk, dark, False)
    extrapolate(state, GraphExtrapolateRequest())  # graph output now exists
    snap = priors.capture_snapshot(state, tk, "mid", lv=False)
    assert snap is not None
    captured = {n.expiry for n in snap.nodes}
    assert dark not in captured
    assert captured  # the lit calibrated nodes are still there


def test_legacy_defaults_inert():
    """The new schema fields exist but change nothing until the mode is
    selected — a default request still declares smooth_field (byte identity
    for the legacy paths is locked by the untouched existing suites)."""
    request = GraphExtrapolateRequest()
    assert request.propagationMode == "smooth_field"
    assert request.residualHalfLifeDays is None
    assert request.clampMaxAgeDays == 1.0
    assert GraphMessageEdge(
        sourceTicker="a", sourceExpiry="x", targetTicker="b", targetExpiry="x"
    ).relationSemantics is None

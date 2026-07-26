"""Intraday async replay locks (framework §16.1 machinery).

Three layers:

  * the harness's pure scheduling/labelling helpers (lit schedule, phase,
    persistence buckets, hub relabelling, fractional-day clock);
  * the two production seams the replay rides — ``solve(now_day=...)``
    threads a FRACTIONAL residual clock into the layered store, and
    ``solve(obs_ages_days=...)`` overrides the certification age (a stored
    instant's chains are fresh AS OF that instant; the live-mode wall-clock
    age would demote every anchor — the smoke-found wiring bug);
  * both seams default to the production path (None) byte-identically.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest

from volfit.api import create_app, priors
from volfit.api.graph_extrapolation import extrapolate, solve
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState

from backtest.graph_intraday import (
    elapsed_bucket,
    frac_day,
    hub_directed,
    phase_of,
    target_lit,
)

REF_DATE = date(2026, 6, 10)


# ------------------------------------------------------------- pure helpers
def test_lit_schedule_and_phase():
    assert target_lit("async_once", 3, 3) is True
    assert target_lit("async_once", 2, 3) is False
    assert target_lit("async_once", 4, 3) is False
    assert target_lit("async_dark", 3, 3) is False
    assert phase_of("async_once", 2, 3) == "pre"
    assert phase_of("async_once", 4, 3) == "post"
    assert phase_of("async_dark", 4, 3) == "dark"
    with pytest.raises(ValueError):
        target_lit("nope", 0, 0)


def test_elapsed_buckets():
    assert elapsed_bucket(0.2) == "0.0-0.75h"
    assert elapsed_bucket(1.0) == "0.75-1.75h"
    assert elapsed_bucket(2.5) == "1.75-3.25h"
    assert elapsed_bucket(5.0) == "3.25-24.0h"
    assert elapsed_bucket(-0.5) is None  # pre-lit rows carry no bucket
    assert elapsed_bucket(None) is None


def test_frac_day_clock():
    """Monotone within a session, exactly the ordinal at midnight, and the
    known 14:30 UTC fraction."""
    d = datetime(2026, 6, 30, 14, 30, 0)
    assert frac_day(d) == pytest.approx(float(d.toordinal()) + 14.5 / 24.0)
    assert frac_day(datetime(2026, 6, 30, 0, 0, 0)) == float(d.toordinal())
    assert frac_day(datetime(2026, 6, 30, 15, 0, 0)) > frac_day(d)


def test_hub_rows_become_directed():
    """The hub's informer rows are relabelled directed broad-market arcs; peer
    rows between non-hub tickers stay untouched (reciprocal by §9.2 default)."""
    from volfit.api.schemas import GraphMessageEdge

    def row(src, tgt):
        return GraphMessageEdge(
            sourceTicker=src, sourceExpiry="2026-07-17",
            targetTicker=tgt, targetExpiry="2026-07-17",
            messagePrecision=1e4, betaAtmVol=1.0, relationClass="sector_peer",
        )

    rows = hub_directed([row("SPY", "IWM"), row("QQQ", "IWM"), row("SPY", "SPY")], "SPY")
    by = {(r.sourceTicker, r.targetTicker): r for r in rows}
    assert by[("SPY", "IWM")].relationSemantics == "directed"
    assert by[("SPY", "IWM")].relationClass == "broad_index"
    assert by[("QQQ", "IWM")].relationSemantics is None  # peer stays class-default
    assert by[("QQQ", "IWM")].relationClass == "sector_peer"
    assert by[("SPY", "SPY")].relationSemantics is None  # self rows untouched


# ------------------------------------------------------- production seams
@pytest.fixture(scope="module")
def primed() -> AppState:
    state = AppState(REF_DATE)
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    return state


def _layered_req() -> GraphExtrapolateRequest:
    return GraphExtrapolateRequest(
        propagationMode="layered_dynamic_harmonic",
        residualHalfLifeDays=0.1,
        residualConfigVersion="test:intraday-seams",
    )


def test_now_day_threads_a_fractional_residual_clock(primed):
    """The layered store's observation stamps ARE the passed fractional clock —
    the §16.1 requirement that residual age and half-life decay act within a
    session (the production day-ordinal default cannot see sub-day time)."""
    now = float(REF_DATE.toordinal()) + 14.5 / 24.0
    primed.graph_dynamic_residuals = {}
    sol = solve(primed, _layered_req(), now_day=now, obs_ages_days={})
    assert sol is not None
    store = primed.graph_dynamic_residuals
    assert store  # certified lit calibrations recorded residuals
    assert all(res.observed_at == now for res in store.values())
    primed.graph_dynamic_residuals = {}


def test_obs_ages_override_gates_certification(primed):
    """Explicit ages gate the boundary clamp: fresh ({}) records residuals for
    every calibrated lit node; ages beyond clampMaxAgeDays demote every
    anchor and record NOTHING (the wall-clock trap a stored replay hits)."""
    req = _layered_req()
    primed.graph_dynamic_residuals = {}
    solve(primed, req, obs_ages_days={})
    n_fresh = len(primed.graph_dynamic_residuals)
    assert n_fresh > 0

    primed.graph_dynamic_residuals = {}
    stale = {tk: 30.0 for tk in primed.active_tickers()}  # >> clampMaxAgeDays
    solve(primed, req, obs_ages_days=stale)
    assert len(primed.graph_dynamic_residuals) == 0
    primed.graph_dynamic_residuals = {}


def test_default_seams_are_byte_identical():
    """now_day=None + obs_ages_days=None reproduce the production payload
    exactly (a fresh state per arm — the solve records innovations)."""
    with_defaults = extrapolate(AppState(REF_DATE), GraphExtrapolateRequest())
    state = AppState(REF_DATE)
    explicit = solve(state, GraphExtrapolateRequest(), now_day=None, obs_ages_days=None)
    assert explicit is not None
    by_name = {(n.ticker, n.expiry): n for n in with_defaults.nodes}
    for i, node in enumerate(explicit.universe.nodes):
        wire = by_name[(node.ticker, node.expiry)]
        assert float(explicit.field.mean[i, 0]) == pytest.approx(
            wire.postAtmVol, abs=1e-12
        )
        assert float(explicit.field.sd[i, 0]) == pytest.approx(wire.sd, abs=1e-12)


def test_replay_smoke_end_to_end_via_api_state():
    """A miniature async replay THROUGH the seams: prior frozen at t0, target
    lit once at t1 (fractional clock), dark at t2 — the t2 layered solve must
    read the carried residual (its mark differs from a store-less control)."""
    state = AppState(REF_DATE)
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    target = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.selected_expiries(target))]
    req = _layered_req()
    base = float(REF_DATE.toordinal())

    # t1: target lit -> residuals recorded on its nodes.
    cell: dict = {}
    state.graph_dynamic_residuals = cell
    solve(state, req, now_day=base + 0.45, obs_ages_days={})
    assert any(name[0] == target for name in cell)

    # t2: target dark; carried store vs empty store must move its marks.
    for iso in isos:
        state.set_node_lit(target, iso, False)
    state.graph_dynamic_residuals = dict(cell)
    with_mem = solve(state, req, now_day=base + 0.55, obs_ages_days={})
    state.graph_dynamic_residuals = {}
    without = solve(state, req, now_day=base + 0.55, obs_ages_days={})
    i = with_mem.universe.node_index((target, isos[0]))
    assert float(with_mem.field.mean[i, 0]) != pytest.approx(
        float(without.field.mean[i, 0]), abs=1e-9
    )
    # Cleanup for other module-scope users.
    for iso in isos:
        state.set_node_lit(target, iso, True)


def test_frac_day_differences_drive_the_decay(primed):
    """Half-life decay acts on FRACTIONAL day gaps: a residual advanced 0.1d
    (one half-life) decays its mean by exactly 1/2."""
    from volfit.graph.temporal_state import residual_dynamics

    dyn = residual_dynamics(half_life=0.1, v_inf=np.ones(3))
    phi = dyn.phi(0.1)
    assert np.allclose(phi, 0.5)

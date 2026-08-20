"""Observation-filter history ring + endpoint + replay evidence (V3.9 item 7).

Locks:
  * the ring is bounded at 64 and appends exactly ONE step per committed
    update — idempotent per (data_version, session_version) like the commit
    itself; seed steps carry their provenance and a charged dt of 0;
  * ζ is the PRE-inflation standardized innovation ν/√(diag(P⁻+R)) — numeric
    lock against hand-computed values, with and without the adaptive
    component — and chi2 = Σζ² on the diagnostics payload;
  * the history dict clears with the chain caches (source/as-of switch) and
    survives the transient as-of round-trip (_CHAIN_CACHE_ATTRS), mirroring
    the filter-state locks;
  * GET /smiles/{t}/{e}/filter/history is read-only and poll-safe: empty when
    off / unseeded, populated after commits, and a re-GET appends nothing;
  * backtest.filter_replay drives the PRODUCTION commit path over a tiny
    2-instant synthetic store: 2 ring steps (seed + update), finite ζ, JSON
    part + HTML page emitted. The real intraday.sqlite is never touched here.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from volfit.api import filter_history, observation_filter, service
from volfit.api.filter_history import FilterHistory, FilterStep, zeta_of
from volfit.api.observation_filter import NodeFilter
from volfit.api.state import AppState
from volfit.calib.observation_filter import (
    FilterMeasurement,
    FilterPrediction,
    FilterState,
    FilterUpdate,
)

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _node(state):
    return [e.isoformat() for e in sorted(state.forwards(TICKER))][1]


def _overlay_state():
    state = AppState(REF_DATE)
    state.set_options(
        state.options().model_copy(update={"observationFilterMode": "overlay"})
    )
    return state


def _dummy_step(i: int) -> FilterStep:
    v = (float(i), 0.0, 0.0)
    return FilterStep(
        ts=float(i), dt_days=0.0, prediction=v, prediction_std=v,
        observation=v, observation_std=v, innovation=v, zeta=v, gain=v,
        posterior=v, posterior_std=v, process_breakdown={}, transport_distance=0.0,
        provenance="update", reset_reason=None, contaminated=False,
    )


# ------------------------------------------------------------------ the ring
def test_ring_bounded_at_64_keeps_newest():
    ring = FilterHistory()
    for i in range(70):
        ring.append(_dummy_step(i))
    steps = ring.steps()
    assert len(ring) == len(steps) == 64
    assert steps[0].ts == 6.0 and steps[-1].ts == 69.0  # oldest dropped


def test_commit_appends_one_step_idempotent_per_versions():
    state = _overlay_state()
    iso = _node(state)
    key = (TICKER, iso, "mid")
    record = service.displayed_base(state, TICKER, iso, "mid")
    ring = state.filter_history(key)
    assert ring is not None and len(ring) == 1
    seed = ring.steps()[0]
    assert seed.provenance.startswith("seed:")
    assert seed.reset_reason == "first"
    assert seed.dt_days == 0.0  # a seed charges no process-noise time
    # same (data_version, session_version): NOT a new observation, no step
    observation_filter.on_fit_commit(state, TICKER, iso, "mid", record, None)
    assert len(state.filter_history(key)) == 1
    # a genuinely new observation appends exactly one update step
    state.bump_data_version(TICKER)
    observation_filter.on_fit_commit(state, TICKER, iso, "mid", record, None)
    steps = state.filter_history(key).steps()
    assert len(steps) == 2
    assert steps[1].provenance == "update" and steps[1].reset_reason is None
    assert steps[1].dt_days >= 0.0
    assert steps[1].zeta is not None and np.all(np.isfinite(steps[1].zeta))


# ---------------------------------------------------------------- zeta / chi2
def _holder(pred: FilterPrediction, meas: FilterMeasurement) -> NodeFilter:
    upd = FilterUpdate(
        innovation=meas.handles - pred.mean,
        innovation_cov=pred.cov + meas.cov,
        gain=np.eye(3),
        mean=meas.handles,
        cov=meas.cov,
    )
    st = FilterState(("T", "e", "mid"), ("ATM", "skew", "curvature"),
                     upd.mean, upd.cov, 0.0, "update")
    return NodeFilter(st, pred, meas, upd, 0, 0, 100.0)


def test_zeta_numeric_lock_vs_hand_computed():
    p = np.array([1e-6, 4e-4, 1e-2])
    r = np.array([4e-6, 1e-4, 3e-2])
    m = np.array([0.20, -0.30, 0.10])
    z = np.array([0.203, -0.28, 0.30])
    pred = FilterPrediction(mean=m, cov=np.diag(p), transport_distance=0.0)
    meas = FilterMeasurement(handles=z, cov=np.diag(r))
    zeta = zeta_of(_holder(pred, meas))
    assert zeta == pytest.approx((z - m) / np.sqrt(p + r))
    # adaptive inflation stored on the prediction: zeta stays PRE-inflation
    factors = np.array([4.0, 1.0, 1.0])
    scale = np.sqrt(factors)
    pred_infl = FilterPrediction(
        mean=m, cov=np.diag(p) * np.outer(scale, scale), transport_distance=0.0,
        q_breakdown={"adaptive": (factors - 1.0) * p},
    )
    zeta_infl = zeta_of(_holder(pred_infl, meas))
    assert zeta_infl == pytest.approx((z - m) / np.sqrt(p + r))


def test_diagnostics_payload_emits_zeta_and_chi2():
    state = _overlay_state()
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")
    holder = state.filter_node((TICKER, iso, "mid"))
    d = observation_filter.filter_diagnostics(state, TICKER, iso, "mid")
    assert d.active is True and d.zeta is not None and len(d.zeta) == 3
    expected = zeta_of(holder)
    assert d.zeta == pytest.approx(list(expected))
    assert d.chi2 == pytest.approx(float(np.dot(expected, expected)))
    # the ring step carries the SAME zeta
    step = state.filter_history((TICKER, iso, "mid")).steps()[-1]
    assert list(step.zeta) == pytest.approx(list(expected))


# ------------------------------------------------------------- clear/preserve
def test_history_wiped_on_clear_and_restored_on_roundtrip():
    state = _overlay_state()
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")
    key = (TICKER, iso, "mid")
    assert state.filter_history(key) is not None
    # the transient as-of round-trip must NOT destroy the history
    assert "_filter_history" in AppState._CHAIN_CACHE_ATTRS
    cap = state.capture_chain_state()
    with state._lock:
        state._clear_chain_caches()  # what a source/as-of switch does
    assert state.filter_history(key) is None  # the strict reset
    state.restore_chain_state(cap)
    ring = state.filter_history(key)
    assert ring is not None and len(ring) == 1  # round-trip transparent


# ------------------------------------------------------------------- endpoint
def test_history_endpoint_off_populated_and_poll_safe():
    from fastapi.testclient import TestClient

    from volfit.api import create_app

    with TestClient(create_app(reference_date=REF_DATE)) as c:
        iso = c.get(f"/forwards/{TICKER}").json()["entries"][1]["expiry"]
        # off (default): inactive, empty, 200
        r = c.get(f"/smiles/{TICKER}/{iso}/filter/history")
        assert r.status_code == 200
        assert r.json() == {"active": False, "steps": []}
        opts = c.get("/settings/options").json()
        opts["observationFilterMode"] = "overlay"
        assert c.put("/settings/options", json=opts).status_code == 200
        # bogus node: still 200, inactive (advisory endpoint)
        assert c.get("/smiles/NOPE/2099-01-01/filter/history").status_code == 200
        # enabled but nothing committed yet: still empty
        assert c.get(f"/smiles/{TICKER}/{iso}/filter/history").json()["steps"] == []
        # a viewed smile commits a fit -> one seed step appears
        c.get(f"/smiles/{TICKER}/{iso}")
        body = c.get(f"/smiles/{TICKER}/{iso}/filter/history").json()
        assert body["active"] is True and len(body["steps"]) == 1
        step = body["steps"][0]
        assert step["provenance"].startswith("seed:")
        assert step["resetReason"] == "first" and step["dtDays"] == 0.0
        assert len(step["zeta"]) == 3
        assert all(np.isfinite(v) for v in step["zeta"])
        # poll-safe: a re-GET fits nothing and appends nothing
        again = c.get(f"/smiles/{TICKER}/{iso}/filter/history").json()
        assert len(again["steps"]) == 1


# ----------------------------------------------------------- offline replay
T1 = datetime(2026, 6, 10, 14, 0)
T2 = datetime(2026, 6, 10, 15, 30)
EXPIRIES = (REF_DATE + timedelta(days=30), REF_DATE + timedelta(days=91))


def _mini_doc(ticker: str) -> dict:
    """The test_backtest_scenarios store-building pattern: the deterministic
    synthetic chain (belly only) snapshotted at two intraday instants."""
    from volfit.data.provider import SyntheticProvider

    prov = SyntheticProvider(reference_date=REF_DATE, tickers=(ticker,))
    ch = prov.fetch_chain(ticker, expiries=list(EXPIRIES))
    quotes = [
        {"expiry": q.expiry.isoformat(), "strike": float(q.strike), "cp": q.call_put,
         "bid": float(q.bid), "ask": float(q.ask), "size": int(q.open_interest)}
        for q in ch.quotes if 0.8 <= q.strike / ch.spot <= 1.2
    ]
    return {
        "asset": ticker, "day": REF_DATE.isoformat(), "exercise_style": "american",
        "expiries": [e.isoformat() for e in EXPIRIES],
        "snapshots": [
            {"ts": T1.isoformat(), "spot": float(ch.spot), "quotes": quotes},
            {"ts": T2.isoformat(), "spot": float(ch.spot), "quotes": quotes},
        ],
    }


def test_filter_replay_offline_mini_run(tmp_path):
    from backtest.capture_intraday import _persist_db
    from backtest.filter_replay import replay

    db = str(tmp_path / "mini.sqlite")
    assert _persist_db(db, "SPY", _mini_doc("SPY")) == 2
    out = str(tmp_path / "out")
    written = replay(db, ["SPY"], out_dir=out)
    part = os.path.join(out, f"SPY_{REF_DATE.isoformat()}.json")
    assert part in written and os.path.exists(part)
    with open(part, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["meta"]["ticker"] == "SPY" and doc["meta"]["nInstants"] == 2
    assert len(doc["nodes"]) == 1  # --max-expiries default: the front rung
    (steps,) = doc["nodes"].values()
    assert len(steps) == 2  # seed at 14:00, update at 15:30
    assert steps[0]["provenance"].startswith("seed:")
    assert steps[0]["resetReason"] == "first" and steps[0]["dtDays"] == 0.0
    assert steps[1]["provenance"] == "update"
    # the charged clock is the calendar default: 1.5h between the instants
    assert steps[1]["dtDays"] == pytest.approx(1.5 / 24.0)
    assert steps[1]["zeta"] is not None
    assert all(np.isfinite(v) for v in steps[1]["zeta"])
    html = os.path.join(out, "filter_replay.html")
    assert html in written and os.path.exists(html)
    text = open(html, encoding="utf-8").read()
    assert "SPY" in text and "overlay" in text
    # resumable: a re-run skips the existing part (only the page is rewritten)
    again = replay(db, ["SPY"], out_dir=out)
    assert again == [html]

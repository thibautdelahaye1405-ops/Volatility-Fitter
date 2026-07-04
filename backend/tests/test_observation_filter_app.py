"""Observation-filter app layer (Phase 3 of Docs/observation_filter_roadmap.md).

Locks the wiring semantics of Note 15 §7.2 on the synthetic provider:
  * off = dormant (no state stored, endpoint inactive, fits untouched);
  * a committed fit in overlay mode seeds from the prior hierarchy, then
    predicts/updates on genuinely NEW observations only (idempotent per
    data/session version);
  * the reset matrix: quote edits and stale gaps reseed, source/as-of changes
    wipe the store (and the transient as-of round-trip restores it);
  * the Jacobian measurement route is live end-to-end (route=1 in the
    breakdown) with gains in [0, 1];
  * the advisory endpoint never 500s.
"""

from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from volfit.api import observation_filter, service
from volfit.api.state import AppState
from volfit.calib.observation_filter import transport_handles

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


# ------------------------------------------------------------------- off mode
def test_off_mode_stores_nothing():
    state = AppState(REF_DATE)
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")
    assert state.filter_node((TICKER, iso, "mid")) is None
    d = observation_filter.filter_diagnostics(state, TICKER, iso, "mid")
    assert d.active is False and d.mode == "off"


# ------------------------------------------------------- seed on first commit
def test_first_commit_seeds_and_updates():
    state = _overlay_state()
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")
    holder = state.filter_node((TICKER, iso, "mid"))
    assert holder is not None
    # no saved prior in a fresh state: the hierarchy seeds from today's mid fit
    assert holder.state.provenance.startswith("seed:")
    assert holder.state.reset_reason == "first"
    assert holder.update is not None and holder.measurement is not None
    gains = np.diag(holder.update.gain)
    assert np.all(gains >= 0.0) and np.all(gains <= 1.0 + 1e-9)
    # the Jacobian route was live (solver_diag retained through _compute_fit)
    assert holder.measurement.breakdown["route"] == 1.0
    assert holder.measurement.contaminated is False  # no active prior => pure z


def test_diagnostics_payload_complete():
    state = _overlay_state()
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")
    d = observation_filter.filter_diagnostics(state, TICKER, iso, "mid")
    assert d.active is True and d.mode == "overlay"
    assert d.handleNames == ["ATM", "skew", "curvature"]
    for field in (
        d.prediction, d.predictionStd, d.observation, d.observationStd,
        d.innovation, d.gain, d.posterior, d.posteriorStd,
    ):
        assert len(field) == 3
    assert set(d.processBreakdown) == {"clock", "spot", "event", "source", "model"}
    assert d.measurementBreakdown["route"] == 1.0
    # drawable overlay: posterior curve + level band + prediction curve, with
    # the band ordered around the posterior at ATM
    assert len(d.post) > 0 and len(d.predCurve) > 0
    assert len(d.postBandLo) == len(d.post) == len(d.postBandHi)
    mid = len(d.post) // 2
    assert d.postBandLo[mid].vol <= d.post[mid].vol <= d.postBandHi[mid].vol


# ------------------------------------------------------------- idempotency
def test_same_snapshot_is_one_observation():
    state = _overlay_state()
    iso = _node(state)
    record = service.displayed_base(state, TICKER, iso, "mid")
    holder1 = state.filter_node((TICKER, iso, "mid"))
    again = observation_filter.on_fit_commit(state, TICKER, iso, "mid", record, None)
    assert again is holder1  # same data/session version: stored state returned


def test_new_data_version_predicts_and_updates():
    state = _overlay_state()
    iso = _node(state)
    record = service.displayed_base(state, TICKER, iso, "mid")
    seeded = state.filter_node((TICKER, iso, "mid"))
    state.bump_data_version(TICKER)
    updated = observation_filter.on_fit_commit(state, TICKER, iso, "mid", record, None)
    assert updated is not seeded
    assert updated.state.provenance == "update"
    assert updated.state.reset_reason is None
    # solver_diag=None on this manual commit: the factors fallback carried R
    assert updated.measurement.breakdown["route"] == 0.0
    # posterior variance never exceeds the prediction variance (an update
    # with a valid R can only add information)
    assert np.all(
        np.diag(updated.update.cov) <= np.diag(updated.prediction.cov) + 1e-15
    )


# --------------------------------------------------------------- reset matrix
def test_quote_edit_resets():
    state = _overlay_state()
    iso = _node(state)
    record = service.displayed_base(state, TICKER, iso, "mid")
    observation_filter.reset_node(state, TICKER, iso, "mid")  # session mark moved
    state.bump_data_version(TICKER)
    holder = observation_filter.on_fit_commit(state, TICKER, iso, "mid", record, None)
    assert holder.state.reset_reason == "quotes_edited"
    assert holder.state.provenance.startswith("seed:")


def test_stale_gap_resets():
    state = _overlay_state()
    iso = _node(state)
    record = service.displayed_base(state, TICKER, iso, "mid")
    holder = state.filter_node((TICKER, iso, "mid"))
    aged = replace(
        holder,
        state=replace(holder.state, timestamp=holder.state.timestamp - 200 * 3600.0),
        data_version=holder.data_version - 1,  # so the commit is "new"
    )
    state.set_filter_node((TICKER, iso, "mid"), aged)
    fresh = observation_filter.on_fit_commit(state, TICKER, iso, "mid", record, None)
    assert fresh.state.reset_reason == "stale"


def test_source_switch_wipes_and_roundtrip_restores():
    state = _overlay_state()
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")
    key = (TICKER, iso, "mid")
    assert state.filter_node(key) is not None
    # the transient as-of round-trip must NOT destroy the filter
    assert "_filter_states" in AppState._CHAIN_CACHE_ATTRS
    cap = state.capture_chain_state()
    with state._lock:
        state._clear_chain_caches()  # what a source/as-of switch does
    assert state.filter_node(key) is None  # the strict reset
    state.restore_chain_state(cap)
    assert state.filter_node(key) is not None  # round-trip transparent


# ------------------------------------------------------- short-dated noise
def test_maturity_noise_multiplier():
    """FINDINGS F3: stated noise scales sqrt(30/DTE) below 30 DTE, never
    below 1 — a 7-DTE chain's R roughly doubles, a 1-year chain is untouched."""
    from volfit.api.observation_filter import _maturity_noise_mult

    assert _maturity_noise_mult(1.0) == 1.0
    assert _maturity_noise_mult(30.0 / 365.0) == pytest.approx(1.0)
    assert _maturity_noise_mult(7.0 / 365.0) == pytest.approx(np.sqrt(30 / 7), rel=1e-6)
    assert _maturity_noise_mult(15.0 / 365.0) > _maturity_noise_mult(20.0 / 365.0)


# ------------------------------------------------------------------ transport
def test_transport_handles_first_order():
    """ATM moves by SSR*skew*h, skew by curvature*h, curvature unchanged
    (Note 12 eq. shift to first order)."""
    x = np.array([0.20, -0.35, 0.10])
    out = transport_handles(x, h=0.02, ssr=2.0)
    assert out[0] == pytest.approx(0.20 + 2.0 * (-0.35) * 0.02)
    assert out[1] == pytest.approx(-0.35 + 0.10 * 0.02)
    assert out[2] == 0.10
    assert transport_handles(x, 0.0, 2.0) == pytest.approx(x)


# ------------------------------------------------------------------- endpoint
def test_endpoint_never_500s():
    from fastapi.testclient import TestClient

    from volfit.api import create_app

    with TestClient(create_app(reference_date=REF_DATE)) as c:
        iso = c.get(f"/forwards/{TICKER}").json()["entries"][1]["expiry"]
        # off (default): inactive, 200
        r = c.get(f"/smiles/{TICKER}/{iso}/filter")
        assert r.status_code == 200 and r.json()["active"] is False
        # bogus node: still 200, inactive (advisory endpoint)
        opts = c.get("/settings/options").json()
        opts["observationFilterMode"] = "overlay"
        assert c.put("/settings/options", json=opts).status_code == 200
        assert c.get("/smiles/NOPE/2099-01-01/filter").status_code == 200
        # a viewed smile commits a fit; the filter endpoint then reports a step
        c.get(f"/smiles/{TICKER}/{iso}")
        r = c.get(f"/smiles/{TICKER}/{iso}/filter")
        assert r.status_code == 200
        body = r.json()
        assert body["active"] is True
        assert len(body["gain"]) == 3

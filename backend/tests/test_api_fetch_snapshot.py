"""V3.7 item 15 — POST /fetch/snapshot: the unified fetch (quotes + spot) with
an optional CHEAP prior auto-roll before calibration.

Locks:
  * flag OFF (the default): the verb is exactly the legacy fetch_options +
    fetch_spots sequence — chains refreshed (data version bumps, nodes stale,
    calibrated pointers preserved), spot shift set (pure transport), NO prior
    roll, NOTHING calibrated while autoCalibrate is off;
  * flag ON + a saved snapshot: the active prior rolls to it via the O(1)
    saved branch (active-prior version bumps, exactly ONE ``prior_selection``
    governance event, the as-of stays live — never the prev-close
    recalibration ladder); a second snapshot fetch is a no-op (no second
    event, no version bump);
  * flag ON + no saved snapshot: no roll, no event, no error;
  * flag ON + snapshot already active: skipped (no governance-event flood).

The legacy endpoint locks (test_gated_workflow, test_api_workflow's
test_fetch_spots_transports_without_recal) stay green untouched.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _put_options(client, **overrides) -> None:
    opts = client.get("/settings/options").json()
    opts.update(overrides)
    assert client.put("/settings/options", json=opts).status_code == 200


def _iso(client) -> str:
    return client.get("/universe").json()["expiries"][TICKER][1]["expiry"]


def _prior_events(state) -> list[dict]:
    """All in-memory ``prior_selection`` audit events (newest first)."""
    return [e for e in state.event_tail(500) if e["action"] == "prior_selection"]


def _saved_snapshot(client, state):
    """Create ALPHA's saved prior snapshot (calibrates its lit nodes first)."""
    client.post("/fetch/options", json={"tickers": [TICKER]})
    snap = priors.capture_snapshot(state, TICKER, "mid", lv=False)
    assert snap is not None
    state.save_prior_snapshot(snap)
    return snap


# ------------------------------------------------------------ flag OFF (default)
def test_flag_off_is_the_legacy_sequence(client):
    """Default OFF: chains refreshed + shift set + NO roll + NOTHING calibrated."""
    _put_options(client, autoCalibrate=False)  # flag off is already the default
    state = client.app.state.volfit
    iso = _iso(client)
    base = client.get(f"/smiles/{TICKER}/{iso}").json()  # bootstrap a fit
    dv0 = state.data_version(TICKER)
    ver0 = state.active_prior_version(TICKER)
    ev0 = len(_prior_events(state))

    res = client.post("/fetch/snapshot", json={"tickers": [TICKER]})
    assert res.status_code == 200
    body = res.json()
    # Same shape + semantics as fetch_options' result.
    assert set(body) == {"tickers", "spots", "calibrationStarted"}
    assert body["tickers"] == [TICKER]
    assert TICKER in body["spots"]
    assert body["calibrationStarted"] is False  # autoCalibrate off => nothing fits

    # (i) chains refreshed: data version bumped, the node marked stale (the
    # calibrated pointer preserved — frozen until Calibrate).
    assert state.data_version(TICKER) > dv0
    moved = client.get(f"/smiles/{TICKER}/{iso}").json()
    assert moved["hasFit"] is True
    assert moved["stale"] is True
    # (ii) spot shift set as pure transport (synthetic spot static => return ~0,
    # forward unchanged — the test_fetch_spots_transports_without_recal contract).
    assert state.spot_shift(TICKER) == pytest.approx(0.0, abs=1e-12)
    assert moved["forward"] == pytest.approx(base["forward"], rel=1e-12)
    # (iii) NO prior roll: nothing activated, no version bump, no audit event.
    assert state.active_prior(TICKER) is None
    assert state.active_prior_version(TICKER) == ver0
    assert len(_prior_events(state)) == ev0
    # (iv) nothing calibrated: no background job ran.
    assert client.get("/calibration/status").json()["running"] is False


def test_flag_off_auto_calibrate_still_kicks(client):
    """The autoCalibrate tail keeps fetch_options semantics (default auto ON)."""
    iso = _iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")  # bootstrap
    res = client.post("/fetch/snapshot", json={"tickers": [TICKER]}).json()
    assert res["calibrationStarted"] is True
    import time

    for _ in range(200):
        if not client.get("/calibration/status").json()["running"]:
            break
        time.sleep(0.1)
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is False


# ---------------------------------------------------------------- flag ON: roll
def test_flag_on_rolls_saved_prior_once(client):
    """A saved snapshot becomes the active prior: version bump + exactly ONE
    prior_selection event; the second snapshot fetch is a no-op."""
    _put_options(client, autoCalibrate=False, autoRollPriorOnFetch=True)
    state = client.app.state.volfit
    snap = _saved_snapshot(client, state)
    asof0 = state.as_of
    ver0 = state.active_prior_version(TICKER)
    ev0 = len(_prior_events(state))
    assert state.active_prior(TICKER) is None  # saving does not activate

    assert client.post("/fetch/snapshot", json={"tickers": [TICKER]}).status_code == 200
    active = state.active_prior(TICKER)
    assert active is not None
    assert (active.savedTs, active.dataTs) == (snap.savedTs, snap.dataTs)
    assert state.active_prior_source(TICKER) == "saved"
    assert state.active_prior_version(TICKER) == ver0 + 1
    events = _prior_events(state)
    assert len(events) == ev0 + 1  # exactly one governance event
    assert events[0]["scope"] == TICKER
    assert events[0]["payload"]["source"] == "saved"
    # The CHEAP branch only: no as-of flip (the prev-close ladder never ran).
    assert state.as_of == asof0

    # Second call: the saved snapshot is already active — a full no-op.
    assert client.post("/fetch/snapshot", json={"tickers": [TICKER]}).status_code == 200
    assert state.active_prior_version(TICKER) == ver0 + 1
    assert len(_prior_events(state)) == ev0 + 1


def test_flag_on_without_saved_snapshot_noops(client):
    """No saved snapshot: the roll is skipped silently (never the ladder)."""
    _put_options(client, autoCalibrate=False, autoRollPriorOnFetch=True)
    state = client.app.state.volfit
    ver0 = state.active_prior_version(TICKER)
    ev0 = len(_prior_events(state))

    res = client.post("/fetch/snapshot", json={"tickers": [TICKER]})
    assert res.status_code == 200
    assert res.json()["tickers"] == [TICKER]  # the fetch itself still ran
    assert state.active_prior(TICKER) is None
    assert state.active_prior_version(TICKER) == ver0
    assert len(_prior_events(state)) == ev0


def test_flag_on_already_active_logs_no_event(client):
    """The saved snapshot is already the active prior: no event, no bump."""
    _put_options(client, autoCalibrate=False, autoRollPriorOnFetch=True)
    state = client.app.state.volfit
    snap = _saved_snapshot(client, state)
    state.set_active_prior(TICKER, snap, "saved")  # activated out-of-band
    ver0 = state.active_prior_version(TICKER)
    ev0 = len(_prior_events(state))

    assert client.post("/fetch/snapshot", json={"tickers": [TICKER]}).status_code == 200
    assert state.active_prior_version(TICKER) == ver0
    assert len(_prior_events(state)) == ev0

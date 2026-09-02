"""API tests for the fast spot-move endpoints (/spot/{ticker}).

A spot shift transports the smile/term/LV-grid (GET /smiles reflects it) with no
recalibration; Re-anchor clears it, refetches the chain and calibrates the
ticker's lit nodes as the background job — the previous fit staying on screen
meanwhile (never a blank chart); the state carries the market-spot readout and
who set the shift (the dial vs the real-time poll); the live probe reports the
implied return.
"""

import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _iso(client) -> str:
    # The universe lists each ticker's expiry ladder; pick the second rung (~3M).
    universe = client.get("/universe").json()
    return universe["expiries"][TICKER][1]["expiry"]


def test_spot_state_defaults(client):
    state = client.get(f"/spot/{TICKER}").json()
    assert state["ticker"] == TICKER
    assert state["spotReturn"] == 0.0
    assert state["anchorSpot"] > 0.0
    assert state["shiftedSpot"] == pytest.approx(state["anchorSpot"])
    assert state["regime"] == "sticky_strike"
    assert state["regimeSsr"] == 1.0


def test_put_shift_moves_forward_and_smile(client):
    iso = _iso(client)
    base = client.get(f"/smiles/{TICKER}/{iso}").json()
    f0 = base["forward"]

    st = client.put(f"/spot/{TICKER}", json={"spotReturn": 0.02}).json()
    assert st["spotReturn"] == pytest.approx(0.02)
    assert st["shiftedSpot"] == pytest.approx(st["anchorSpot"] * 1.02)

    moved = client.get(f"/smiles/{TICKER}/{iso}").json()
    assert moved["forward"] == pytest.approx(f0 * 1.02, rel=1e-9)
    # Sticky-strike, equity skew, spot up => ATM vol drops.
    assert moved["diagnostics"]["atmVol"] < base["diagnostics"]["atmVol"]


def _drain(client) -> None:
    """Wait for the background calibration job to go idle."""
    for _ in range(300):
        if not client.get("/calibration/status").json()["running"]:
            return
        time.sleep(0.05)
    raise AssertionError("calibration job did not drain")


def test_calibrate_reanchors(client):
    iso = _iso(client)
    f0 = client.get(f"/smiles/{TICKER}/{iso}").json()["forward"]
    client.put(f"/spot/{TICKER}", json={"spotReturn": 0.05})
    st = client.post(f"/spot/{TICKER}/calibrate").json()
    assert st["spotReturn"] == 0.0 and st["shiftSource"] is None
    # The chain was refetched and the ticker's lit nodes went to the background job.
    assert st["refetched"] is True and st["calibrationStarted"] is True and st["busy"] is False
    assert st["litNodes"] >= 1
    _drain(client)
    smile = client.get(f"/smiles/{TICKER}/{iso}").json()
    assert smile["forward"] == pytest.approx(f0, rel=1e-9)
    assert smile["hasFit"] is True and smile["stale"] is False


def test_reanchor_keeps_the_previous_fit_on_screen_in_the_gated_workflow():
    """The gated live server (nothing calibrates on a read): Re-anchor must
    never blank the chart — the historical cache drop left the ticker with no
    fit at all. The previous fit stays displayed while the background job
    recalibrates every lit node of the ticker at the refetched chain's spot."""
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        iso = _iso(client)
        client.post("/calibrate")  # the explicit first calibration
        _drain(client)
        base = client.get(f"/smiles/{TICKER}/{iso}").json()
        assert base["hasFit"] is True and base["model"]
        client.put(f"/spot/{TICKER}", json={"spotReturn": 0.03})
        moved = client.get(f"/smiles/{TICKER}/{iso}").json()
        assert moved["forward"] == pytest.approx(base["forward"] * 1.03, rel=1e-9)
        st = client.post(f"/spot/{TICKER}/calibrate").json()
        assert st["calibrationStarted"] is True and st["spotReturn"] == 0.0
        # Straight after: the shift is cleared and a fit is STILL displayed.
        mid = client.get(f"/smiles/{TICKER}/{iso}").json()
        assert mid["hasFit"] is True and mid["model"]
        assert mid["forward"] == pytest.approx(base["forward"], rel=1e-9)
        _drain(client)
        done = client.get(f"/smiles/{TICKER}/{iso}").json()
        assert done["hasFit"] is True and done["stale"] is False
        assert client.get(f"/spot/{TICKER}").json()["spotReturn"] == 0.0


def test_reanchor_reports_busy_when_the_job_is_taken(client, monkeypatch):
    """One background job at a time: with it taken, Re-anchor still clears the
    dial and refetches, but reports ``busy`` (nothing started) for the panel."""
    state = client.app.state.volfit
    monkeypatch.setattr(state.calibration_jobs, "start_stages", lambda *a, **k: False)
    client.put(f"/spot/{TICKER}", json={"spotReturn": 0.02})
    st = client.post(f"/spot/{TICKER}/calibrate").json()
    assert st["busy"] is True and st["calibrationStarted"] is False
    assert st["spotReturn"] == 0.0 and st["refetched"] is True


def test_spot_state_market_readout(client):
    """The panel's readouts: the calibration anchor, the latest known market
    spot (the fetched chain's own until something is probed, then the probe
    with its stamp), the source label and the Re-anchor scope."""
    st = client.get(f"/spot/{TICKER}").json()
    assert st["liveSource"] == "chain" and st["liveSpot"] == pytest.approx(st["anchorSpot"])
    assert st["liveReturn"] == pytest.approx(0.0, abs=1e-12)
    assert st["streaming"] is False and st["sourceLabel"]
    assert st["litNodes"] >= 1 and st["shiftSource"] is None
    client.get(f"/spot/{TICKER}/live")  # a probe is remembered
    st = client.get(f"/spot/{TICKER}").json()
    assert st["liveSource"] == "probe" and st["liveAt"]
    assert st["liveSpot"] == pytest.approx(st["anchorSpot"])


def test_shift_source_dial_versus_live_poll(client, monkeypatch):
    """The dial's shift is "manual" (the tick stream lives at it); the real-time
    poll's is "live" (the stream keeps its own fresher book spot); 0 has none."""
    from volfit.api import workflow

    state = client.app.state.volfit
    assert client.put(f"/spot/{TICKER}", json={"spotReturn": 0.02}).json()["shiftSource"] == "manual"
    assert state.manual_spot_shift(TICKER) == pytest.approx(0.02)
    # The scheduler's poll (a moved provider spot) marks the shift "live".
    monkeypatch.setattr(state, "live_spot", lambda t: state.anchor_spot(t) * 1.01)
    workflow.fetch_spots(state, [TICKER])
    st = client.get(f"/spot/{TICKER}").json()
    assert st["shiftSource"] == "live" and st["spotReturn"] == pytest.approx(0.01)
    assert state.manual_spot_shift(TICKER) == 0.0
    client.put(f"/spot/{TICKER}", json={"spotReturn": 0.0})
    assert client.get(f"/spot/{TICKER}").json()["shiftSource"] is None


def test_live_spot_probe(client):
    live = client.get(f"/spot/{TICKER}/live").json()
    # Synthetic spot is static, so the live probe equals the anchor (return 0).
    assert live["liveSpot"] == pytest.approx(live["anchorSpot"])
    assert live["spotReturn"] == pytest.approx(0.0, abs=1e-12)


def test_unknown_ticker_404(client):
    assert client.get("/spot/NOPE").status_code == 404
    assert client.put("/spot/NOPE", json={"spotReturn": 0.01}).status_code == 404

"""API tests for the fast spot-move endpoints (/spot/{ticker}).

A spot shift transports the smile/term/LV-grid (GET /smiles reflects it) with no
recalibration; Recalibrate = the top-bar Calibrate for ONE ticker (same scope,
same snapshot rule: the streaming book, else the last fetched chain with no
request) as the background job — the previous fit staying on screen meanwhile
(never a blank chart); the state carries the prevailing market spot and what
the spot FOLLOWS (market vs scenario); the live probe reports the implied return.
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
    v0 = client.app.state.volfit.data_version(TICKER)
    st = client.post(f"/spot/{TICKER}/calibrate").json()
    assert st["spotReturn"] == 0.0
    # No stream: the LAST FETCHED chain is used (no refetch), and the ticker's
    # lit nodes went to the background job with the top bar's default scope.
    assert st["snapshotted"] is False and client.app.state.volfit.data_version(TICKER) == v0
    assert st["calibrationStarted"] is True and st["busy"] is False and st["scope"] == "both"
    assert st["litNodes"] >= 1
    _drain(client)
    smile = client.get(f"/smiles/{TICKER}/{iso}").json()
    assert smile["forward"] == pytest.approx(f0, rel=1e-9)
    assert smile["hasFit"] is True and smile["stale"] is False


def test_recalibrate_keeps_the_previous_fit_on_screen_in_the_gated_workflow():
    """The gated live server (nothing calibrates on a read): Recalibrate must
    never blank the chart — the historical cache drop left the ticker with no
    fit at all. The previous fit stays displayed while the background job
    recalibrates every lit node of the ticker at the snapshot's spot."""
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


def test_recalibrate_reports_busy_when_the_job_is_taken(client, monkeypatch):
    """One background job at a time: with it taken, Recalibrate still clears
    the dial but reports ``busy`` (nothing started) for the panel."""
    state = client.app.state.volfit
    monkeypatch.setattr(state.calibration_jobs, "start_stages", lambda *a, **k: False)
    client.put(f"/spot/{TICKER}", json={"spotReturn": 0.02})
    st = client.post(f"/spot/{TICKER}/calibrate").json()
    assert st["busy"] is True and st["calibrationStarted"] is False
    assert st["spotReturn"] == 0.0


def test_recalibrate_scopes_mirror_the_top_bar(client, monkeypatch):
    """The scope names are the top bar's: "parametric" runs the parametric
    groups only, "lv" the LV item only (regardless of the Options toggle),
    "both" parametric then LV when Local-Vol is enabled — the SAME stage
    builders as the global verbs, on one ticker."""
    state = client.app.state.volfit
    seen: list[list[str]] = []

    def capture(stages, workers=1):
        seen.append([phase for groups in stages for _t, items in groups for _l, phase, _f in items])
        return True

    monkeypatch.setattr(state.calibration_jobs, "start_stages", capture)
    client.post(f"/spot/{TICKER}/calibrate", params={"scope": "parametric"})
    client.post(f"/spot/{TICKER}/calibrate", params={"scope": "lv"})
    client.post(f"/spot/{TICKER}/calibrate", params={"scope": "both"})
    assert set(seen[0]) == {"Parametric"}
    assert seen[1] == ["LV"]
    assert set(seen[2]) == {"Parametric", "LV"} and seen[2][-1] == "LV"
    assert client.post(f"/spot/{TICKER}/calibrate", params={"scope": "nope"}).status_code == 422


def test_recalibrate_snapshots_the_book_while_streaming():
    """The calibration snapshot rule, per ticker AND global: while the source
    streams, a fresh synchronous quotes + spot snapshot is taken off the book
    (the data version bumps — every node re-anchors on it); with no stream the
    last fetched chain is used, no refetch."""
    from volfit.api import workflow
    from volfit.data.provider import SyntheticProvider

    class Streaming(SyntheticProvider):
        streaming = False

        def is_streaming(self):
            return self.streaming

    prov = Streaming(reference_date=REF_DATE, tickers=(TICKER,))
    with TestClient(create_app(reference_date=REF_DATE, providers={"fake": prov}, active_source="fake")) as client:
        state = client.app.state.volfit
        iso = _iso(client)
        client.get(f"/smiles/{TICKER}/{iso}")
        v0 = state.data_version(TICKER)
        assert client.post(f"/spot/{TICKER}/calibrate").json()["snapshotted"] is False
        _drain(client)
        assert state.data_version(TICKER) == v0  # no stream: the last fetched chain
        prov.streaming = True
        assert client.post(f"/spot/{TICKER}/calibrate").json()["snapshotted"] is True
        _drain(client)
        assert state.data_version(TICKER) == v0 + 1  # a fresh book snapshot
        # The global verb takes the same snapshot.
        assert workflow.calibration_chains(state, [TICKER]) is True
        assert state.data_version(TICKER) == v0 + 2
        prov.streaming = False
        assert workflow.calibration_chains(state, [TICKER]) is False
        assert state.data_version(TICKER) == v0 + 2


def test_spot_state_market_readout(client):
    """The panel's readouts: the calibration anchor, the latest known market
    spot (the fetched chain's own until something is probed, then the probe
    with its stamp), the source label and the Re-anchor scope."""
    st = client.get(f"/spot/{TICKER}").json()
    assert st["liveSource"] == "chain" and st["liveSpot"] == pytest.approx(st["anchorSpot"])
    assert st["liveReturn"] == pytest.approx(0.0, abs=1e-12)
    assert st["streaming"] is False and st["sourceLabel"]
    assert st["litNodes"] >= 1 and st["follow"] == "market" and st["followForced"] is False
    client.get(f"/spot/{TICKER}/live")  # a probe is remembered
    st = client.get(f"/spot/{TICKER}").json()
    assert st["liveSource"] == "probe" and st["liveAt"]
    assert st["liveSpot"] == pytest.approx(st["anchorSpot"])


def test_follow_market_versus_scenario(client, monkeypatch):
    """The selector: following the MARKET syncs the shift to the prevailing spot
    (now, and on every spot poll / fetch); the SCENARIO is the dial — a manual
    shift switches to it and the market poll leaves it alone."""
    from volfit.api import workflow

    state = client.app.state.volfit
    # The dial => scenario.
    st = client.put(f"/spot/{TICKER}", json={"spotReturn": 0.02}).json()
    assert st["follow"] == "scenario" and st["spotReturn"] == pytest.approx(0.02)
    # The market moved 1 % (a probe); a scenario ticker keeps its dial...
    moved = state.anchor_spot(TICKER) * 1.01
    monkeypatch.setattr(state.provider, "spot", lambda t, e=None: moved)
    workflow.fetch_spots(state, [TICKER])
    st = client.get(f"/spot/{TICKER}").json()
    assert st["spotReturn"] == pytest.approx(0.02) and st["liveReturn"] == pytest.approx(0.01)
    # ...until it follows the market: the shift syncs to the prevailing spot.
    st = client.put(f"/spot/{TICKER}/follow", json={"follow": "market"}).json()
    assert st["follow"] == "market" and st["spotReturn"] == pytest.approx(0.01)
    assert workflow.sync_market_shifts(state, [TICKER]) == []  # already in sync
    # Back to the scenario: the current spot is the scenario's starting point.
    st = client.put(f"/spot/{TICKER}/follow", json={"follow": "scenario"}).json()
    assert st["follow"] == "scenario" and st["spotReturn"] == pytest.approx(0.01)
    assert client.put(f"/spot/{TICKER}/follow", json={"follow": "nope"}).status_code == 422


def test_realtime_spot_mode_forces_market_follow(client):
    state = client.app.state.volfit
    client.put(f"/spot/{TICKER}", json={"spotReturn": 0.02})  # scenario
    state.set_options(state.options().model_copy(update={"spotMode": "realtime"}))
    st = client.get(f"/spot/{TICKER}").json()
    assert st["follow"] == "market" and st["followForced"] is True
    state.set_options(state.options().model_copy(update={"spotMode": "static"}))
    assert client.get(f"/spot/{TICKER}").json()["follow"] == "scenario"


def test_live_spot_probe(client):
    live = client.get(f"/spot/{TICKER}/live").json()
    # Synthetic spot is static, so the live probe equals the anchor (return 0).
    assert live["liveSpot"] == pytest.approx(live["anchorSpot"])
    assert live["spotReturn"] == pytest.approx(0.0, abs=1e-12)


def test_unknown_ticker_404(client):
    assert client.get("/spot/NOPE").status_code == 404
    assert client.put("/spot/NOPE", json={"spotReturn": 0.01}).status_code == 404

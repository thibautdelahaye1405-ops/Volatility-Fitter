"""Quote table on the two-frame grammar (volfit.api.table + the SSE rows).

* ``rows`` = the calibration frame (now carrying the fit's own target band);
* ``marketRows`` = the prevailing frame: pure market (no edits), target of the
  fit mode, Model IV = the fit ROLLED to the prevailing spot at the market
  moneyness, ``index`` = the calibration row at the same strike;
* no spot move: market rows == calibration rows (same strikes, same IVs, same
  Model IV); a spot move re-expresses k and, under sticky strike, keeps the
  Model IV at a fixed strike;
* CSV ``frame=market``; live tick rows carry ``modelIv``.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.smile_layers import strike_key
from volfit.api.table_stream import table_events

REF = date(2026, 6, 10)
T = "BETA"


@pytest.fixture()
def rig():
    app = create_app(reference_date=REF)
    client = TestClient(app)
    state = app.state.volfit
    expiry = state.provider.available_expiries(T)[1].isoformat()
    table = client.get(f"/smiles/{T}/{expiry}/table").json()
    assert table["rows"] and table["marketRows"]
    return state, client, expiry, table


def _by_strike(rows):
    return {strike_key(r["strike"]): r for r in rows}


def test_market_rows_match_calibration_rows_without_a_move(rig):
    state, client, expiry, t = rig
    assert t["marketForward"] == pytest.approx(t["forward"], rel=1e-12)
    assert t["marketSpot"] > 0 and t["marketTimestamp"] and t["marketLive"] is False
    calib, market = _by_strike(t["rows"]), _by_strike(t["marketRows"])
    assert set(calib) == set(market)
    for key, m in market.items():
        c = calib[key]
        assert m["index"] == c["index"] and m["excluded"] is False and m["amended"] is False
        assert m["k"] == pytest.approx(c["k"], abs=1e-12)
        assert m["midIv"] == pytest.approx(c["midIv"]) and m["modelIv"] == pytest.approx(c["modelIv"], abs=1e-9)
        assert m["midPrice"] == pytest.approx(c["midPrice"], abs=1e-9)
        assert m["targetLo"] is None and c["targetLo"] is None  # mid mode: no band


def test_targets_follow_the_fit_mode_on_both_frames(rig):
    state, client, expiry, _ = rig
    t = client.get(f"/smiles/{T}/{expiry}/table", params={"fit_mode": "haircut"}).json()
    for r in t["rows"] + t["marketRows"]:
        assert r["bidIv"] <= r["targetLo"] <= r["midIv"] <= r["targetHi"] <= r["askIv"]
    t2 = client.get(f"/smiles/{T}/{expiry}/table", params={"fit_mode": "bidask"}).json()
    for r in t2["marketRows"]:
        assert r["targetLo"] == pytest.approx(r["bidIv"]) and r["targetHi"] == pytest.approx(r["askIv"])


def test_spot_move_rolls_the_market_frame_only(rig):
    state, client, expiry, base = rig
    shift = 0.02
    state.set_spot_shift(T, shift)
    t = client.get(f"/smiles/{T}/{expiry}/table").json()
    state.set_spot_shift(T, 0.0)
    assert t["marketForward"] == pytest.approx(base["marketForward"] * (1.0 + shift), rel=1e-12)
    assert t["marketSpot"] == pytest.approx(base["marketSpot"] * (1.0 + shift), rel=1e-12)
    market, base_market = _by_strike(t["marketRows"]), _by_strike(base["marketRows"])
    for key, m in market.items():
        assert m["k"] == pytest.approx(math.log(m["strike"] / t["marketForward"]), abs=1e-12)
        # sticky strike (default regime): the rolled fit keeps the vol at a fixed strike
        assert m["modelIv"] == pytest.approx(base_market[key]["modelIv"], abs=2e-4)
        assert m["midIv"] == pytest.approx(base_market[key]["midIv"])  # quotes unchanged (same chain)


def test_edits_stay_on_the_calibration_rows(rig):
    state, client, expiry, base = rig
    idx = base["rows"][1]["index"]
    assert client.post(f"/smiles/{T}/{expiry}/edits", json={"action": "exclude", "index": idx}).status_code == 200
    t = client.get(f"/smiles/{T}/{expiry}/table").json()
    assert any(r["excluded"] for r in t["rows"]) and not any(r["excluded"] for r in t["marketRows"])
    client.post(f"/smiles/{T}/{expiry}/edits", json={"action": "reset"})


def test_csv_frame_market(rig):
    state, client, expiry, t = rig
    calib = client.get(f"/smiles/{T}/{expiry}/table.csv").text.splitlines()
    market = client.get(f"/smiles/{T}/{expiry}/table.csv", params={"frame": "market"}).text.splitlines()
    assert calib[0] == market[0]  # same frozen header
    assert len(market) == len(t["marketRows"]) + 1 and len(calib) == len(t["rows"]) + 1


def test_live_rows_carry_the_rolled_model_iv():
    from tests.test_table_stream import StreamingSynthetic

    prov = StreamingSynthetic(reference_date=REF, tickers=(T,))
    app = create_app(reference_date=REF, providers={"fake": prov}, active_source="fake")
    client = TestClient(app)
    state = app.state.volfit
    expiry = prov.available_expiries(T)[0].isoformat()
    base = client.get(f"/smiles/{T}/{expiry}/table").json()
    prov.streaming = True
    prov.spot_scale = 1.01

    async def first():
        n = {"c": 0}

        async def dc():
            n["c"] += 1
            return n["c"] > 1

        async for chunk in table_events(state, T, expiry, dc, tick=0.0):
            return json.loads(chunk[len("data:"):].strip())

    f = asyncio.run(first())
    calib = _by_strike(base["rows"])
    assert f["rows"] and all(r["modelIv"] is not None for r in f["rows"])
    for r in f["rows"]:  # sticky strike: the rolled fit keeps the vol at a fixed strike
        c = calib.get(strike_key(r["strike"]))
        if c is not None:
            assert r["modelIv"] == pytest.approx(c["modelIv"], abs=2e-4)
            assert r["index"] == c["index"]

"""The Smile Viewer's two comparable frames (volfit.api.smile_layers) on the
SmileData payload, and the rolled fit + live target on the SSE tick stream.

Offline on the synthetic provider (+ the streaming fake of test_table_stream):
* every quote band carries its strike; the market frame's quotes are PURE
  market (no edits, target of the viewed fit mode, click-through index);
* no spot move: market.model == model (the fit) and calib.model == model;
* an active spot shift: market.forward = F0 (1 + shift) (proportional — the
  synthetic chain has no cash dividends), market.model is the transported
  curve (reused), calib.model stays the un-transported fit;
* an edit (exclude) shows on the calibration quotes only;
* the no-fit payload has a market frame (quotes, no curve) and no calib frame;
* the SSE first frame carries the rolled model + per-row target/index.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, service, smile_layers
from volfit.api.table_stream import table_events

REF = date(2026, 6, 10)
TICKER = "ALPHA"


@pytest.fixture()
def rig():
    app = create_app(reference_date=REF)
    client = TestClient(app)
    state = app.state.volfit
    expiry = state.provider.available_expiries(TICKER)[1].isoformat()
    payload = client.get(f"/smiles/{TICKER}/{expiry}").json()
    assert payload["hasFit"] is not False and payload["model"], "fixture must have a fit"
    return state, client, expiry, payload


def _vol_at(curve, k):
    ks = np.array([p["k"] for p in curve])
    vs = np.array([p["vol"] for p in curve])
    return float(np.interp(k, ks, vs))


def test_payload_carries_both_frames_with_strikes(rig):
    state, client, expiry, p = rig
    assert p["market"] is not None and p["calib"] is not None
    # every calibration quote has a strike consistent with its k and the forward
    for q in p["quotes"]:
        assert q["strike"] == pytest.approx(p["forward"] * math.exp(q["k"]), rel=1e-12)
    m = p["market"]
    assert m["forward"] == pytest.approx(p["forward"], rel=1e-12)  # no spot move
    assert m["live"] is False and m["spot"] > 0 and m["timestamp"]
    # market quotes: same strikes as the calibration quotes, pure market, click-through index
    calib_by_strike = {smile_layers.strike_key(q["strike"]): q for q in p["quotes"]}
    assert {smile_layers.strike_key(q["strike"]) for q in m["quotes"]} == set(calib_by_strike)
    for q in m["quotes"]:
        c = calib_by_strike[smile_layers.strike_key(q["strike"])]
        assert q["index"] == c["index"] and q["excluded"] is False and q["amended"] is False
        assert q["k"] == pytest.approx(math.log(q["strike"] / m["forward"]), abs=1e-12)
        assert q["bid"] == pytest.approx(c["bid"]) and q["targetLo"] is None  # mid mode
    # no move: rolled == displayed == calibration curve
    assert m["model"] == p["model"] and p["calib"]["model"] == p["model"]
    assert p["calib"]["forward"] == pytest.approx(p["forward"], rel=1e-12)


def test_market_target_follows_the_fit_mode_without_edits(rig):
    state, client, expiry, _ = rig
    p = client.get(f"/smiles/{TICKER}/{expiry}", params={"fit_mode": "haircut"}).json()
    for q in p["market"]["quotes"]:
        assert q["targetLo"] is not None and q["bid"] <= q["targetLo"] <= q["mid"]
        assert q["mid"] <= q["targetHi"] <= q["ask"]
    p2 = client.get(f"/smiles/{TICKER}/{expiry}", params={"fit_mode": "bidask"}).json()
    for q in p2["market"]["quotes"]:
        assert q["targetLo"] == pytest.approx(q["bid"]) and q["targetHi"] == pytest.approx(q["ask"])


def test_spot_move_rolls_the_market_frame_and_keeps_the_calibration_frame(rig):
    state, client, expiry, base = rig
    shift = 0.02
    state.set_spot_shift(TICKER, shift)
    moved = client.get(f"/smiles/{TICKER}/{expiry}").json()
    m, c = moved["market"], moved["calib"]
    assert m["forward"] == pytest.approx(base["forward"] * (1.0 + shift), rel=1e-12)
    assert m["spot"] == pytest.approx(float(state.anchor_spot(TICKER)) * (1.0 + shift), rel=1e-12)
    assert m["model"] == moved["model"]  # the active-shift curve is reused
    assert c["forward"] == pytest.approx(base["forward"], rel=1e-12)
    assert c["model"] == base["model"]  # the fit on its calibration spot, untouched
    # sticky strike (the default regime): rolled(k0 - h) == calibration(k0)
    h = math.log(1.0 + shift)
    for k0 in (-0.05, 0.0, 0.05):
        assert _vol_at(m["model"], k0 - h) == pytest.approx(_vol_at(c["model"], k0), abs=2e-4)
    # strikes are invariant; market k re-expressed against the moved forward
    for q in m["quotes"]:
        assert q["k"] == pytest.approx(math.log(q["strike"] / m["forward"]), abs=1e-12)
    state.set_spot_shift(TICKER, 0.0)


def test_edits_stay_on_the_calibration_frame(rig):
    state, client, expiry, base = rig
    target = base["quotes"][2]
    r = client.post(f"/smiles/{TICKER}/{expiry}/edits", json={"action": "exclude", "index": target["index"]})
    assert r.status_code == 200
    p = client.get(f"/smiles/{TICKER}/{expiry}").json()
    assert any(q["excluded"] for q in p["quotes"])
    assert not any(q["excluded"] for q in p["market"]["quotes"])  # pure market


def test_no_fit_payload_has_a_market_frame_only():
    app = create_app(reference_date=REF, gated=True)
    client = TestClient(app)
    state = app.state.volfit
    expiry = state.provider.available_expiries(TICKER)[0].isoformat()
    state.ensure_chain(TICKER)
    p = client.get(f"/smiles/{TICKER}/{expiry}").json()
    assert p["hasFit"] is False and p["model"] == []
    assert p["calib"] is None
    assert p["market"] is not None and p["market"]["model"] == [] and p["market"]["quotes"]
    assert all(q["index"] >= 0 for q in p["market"]["quotes"])  # joins the (unfit) quote list


def test_sse_frame_carries_the_rolled_fit_and_live_target():
    from tests.test_table_stream import StreamingSynthetic

    prov = StreamingSynthetic(reference_date=REF, tickers=(TICKER,))
    app = create_app(reference_date=REF, providers={"fake": prov}, active_source="fake")
    client = TestClient(app)
    state = app.state.volfit
    expiry = prov.available_expiries(TICKER)[0].isoformat()
    base = client.get(f"/smiles/{TICKER}/{expiry}", params={"fit_mode": "bidask"}).json()
    prov.streaming = True
    prov.spot_scale = 1.01

    async def first():
        n = {"c": 0}

        async def dc():
            n["c"] += 1
            return n["c"] > 1

        async for chunk in table_events(state, TICKER, expiry, dc, tick=0.0, fit_mode="bidask"):
            return json.loads(chunk[len("data:"):].strip())

    f = asyncio.run(first())
    assert f["type"] == "ticks" and f["full"] is True
    assert f["model"] and f["forward"] == pytest.approx(base["forward"] * 1.01, rel=1e-9)
    # the rolled fit (sticky strike): model(k0 - h) == calibration(k0)
    h = math.log(1.01)
    for k0 in (-0.05, 0.0, 0.05):
        assert _vol_at(f["model"], k0 - h) == pytest.approx(_vol_at(base["calib"]["model"], k0), abs=2e-4)
    calib_idx = {smile_layers.strike_key(q["strike"]): q["index"] for q in base["quotes"]}
    for r in f["rows"]:
        assert r["targetLo"] == pytest.approx(r["bidIv"]) and r["targetHi"] == pytest.approx(r["askIv"])
        assert r["index"] == calib_idx.get(smile_layers.strike_key(r["strike"]), -1)
    assert any(r["index"] >= 0 for r in f["rows"])

"""Live quote-table tick stream (volfit.api.table_stream + the SSE route).

Offline: a SyntheticProvider subclass plays a streaming source — ``is_streaming``
/ ``live_chain`` (book-only reader) return a perturbed copy of its own chain —
so the live slice can be checked against the table built from the SAME chain
(identical keys and IVs at zero perturbation, shifted IVs otherwise), and the
delta tracker / SSE generator are driven deterministically. The generator is
exercised directly with a fake disconnect probe (TestClient.stream teardown can
hang on an infinite generator — see test_sse_status.py).
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import replace
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api import table_stream
from volfit.api.table_stream import LiveTableTracker, live_slice, row_key, table_events
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 10)


class StreamingSynthetic(SyntheticProvider):
    """Synthetic source with a fake live book: the live chain is the synthetic
    chain with every quote scaled by ``shift`` (+ per-quote ``bumps``), and the
    ``drop`` set made one-sided (bid withdrawn)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.streaming = False
        self.ready = True
        self.shift = 0.0
        self.bumps: dict[tuple[float, str], float] = {}
        self.drop: set[tuple[float, str]] = set()
        self.spot_scale = 1.0  # live spot / snapshot spot (the forward moves with it)
        self.live_reads = 0

    def is_streaming(self):
        return self.streaming

    def live_chain(self, ticker, expiries):
        self.live_reads += 1
        if not self.streaming or not self.ready:
            return None
        snap = self.fetch_chain(ticker, expiries)
        quotes = []
        for q in snap.quotes:
            ident = (q.strike, q.call_put)
            if ident in self.drop:
                quotes.append(replace(q, bid=None))
                continue
            f = (1.0 + self.shift) * self.bumps.get(ident, 1.0)
            quotes.append(replace(q, bid=q.bid * f, ask=q.ask * f))
        stamp = snap.timestamp + timedelta(seconds=len(self.bumps) + len(self.drop))
        return replace(snap, quotes=quotes, timestamp=stamp, spot=snap.spot * self.spot_scale)


@pytest.fixture()
def rig():
    prov = StreamingSynthetic(reference_date=REF, tickers=("ALPHA",))
    app = create_app(reference_date=REF, providers={"fake": prov}, active_source="fake")
    client = TestClient(app)
    expiry = prov.available_expiries("ALPHA")[0].isoformat()
    table = client.get(f"/smiles/ALPHA/{expiry}/table").json()
    assert table["rows"], "the table fixture must have rows"
    return app.state.volfit, prov, expiry, table


def _keys(table) -> set[str]:
    return {row_key(r["strike"]) for r in table["rows"]}


# ------------------------------------------------------------------ slice
def test_live_slice_is_none_without_a_stream(rig):
    state, prov, expiry, _ = rig
    assert live_slice(state, "ALPHA", expiry) is None  # not streaming -> no live ticks
    prov.streaming, prov.ready = True, False
    assert live_slice(state, "ALPHA", expiry) is None  # streaming but book not ready


def test_live_slice_matches_table_keys_and_tracks_the_live_market(rig):
    state, prov, expiry, table = rig
    prov.streaming = True
    sl = live_slice(state, "ALPHA", expiry)
    assert sl is not None and {r.key for r in sl.rows} == _keys(table)
    by_key = {r.key: r for r in sl.rows}
    for r in table["rows"]:  # same chain, same pipeline -> same bands and prices
        live = by_key[row_key(r["strike"])]  # (wire rounding: 8 dp vols, 6 dp prices)
        assert live.midIv == pytest.approx(r["midIv"], abs=1e-8)
        assert live.bidPrice == pytest.approx(r["bidPrice"], abs=1e-6)
        assert live.type == r["type"] and live.k == pytest.approx(r["k"], abs=1e-8)
    fp0 = sl.fingerprint
    prov.shift = 0.02  # the market moves: every price +2% -> every IV up
    sl2 = live_slice(state, "ALPHA", expiry)
    assert sl2.fingerprint != fp0
    for r in table["rows"]:
        assert {x.key: x for x in sl2.rows}[row_key(r["strike"])].midIv > r["midIv"]


def test_live_slice_inverts_at_the_live_forward(rig):
    """A streamed spot move transports the node's forward (proportional here — the
    synthetic chain has no cash dividends) and the live IVs are inverted at it;
    rows stay keyed by strike so the table/chart join survives the move."""
    state, prov, expiry, table = rig
    prov.streaming = True
    base = live_slice(state, "ALPHA", expiry)
    prov.spot_scale = 1.01
    moved = live_slice(state, "ALPHA", expiry)
    assert moved.forward == pytest.approx(base.forward * 1.01, rel=1e-12)
    assert moved.spot == pytest.approx(base.spot * 1.01, rel=1e-12)
    assert {r.key for r in moved.rows} <= _keys(table) | {r.key for r in base.rows}
    by_key = {r.key: r for r in moved.rows}
    # same strikes, re-expressed moneyness: k shifts by -log(1.01) at fixed strike
    for r in base.rows:
        if r.key in by_key:
            assert by_key[r.key].k == pytest.approx(r.k - math.log(1.01), abs=1e-6)
            assert by_key[r.key].strike == pytest.approx(r.strike, abs=1e-6)


def test_scenario_dial_frames_the_live_slice_and_market_follow_does_not(rig):
    """In the SCENARIO follow mode the dial is the frame the stream lives in —
    forward, spot, row moneyness and the rolled shift — while the book's own
    spot rides along as ``live_spot``; the live IVs stay inverted at the live
    forward (the prices are the market's). Following the MARKET, the frame is
    the book itself whatever shift the spot poll synced (the book is fresher)."""
    from volfit.api.schemas import SpotShiftRequest
    from volfit.api.spot import set_shift

    state, prov, expiry, _table = rig
    prov.streaming = True
    base = live_slice(state, "ALPHA", expiry)
    set_shift(state, "ALPHA", SpotShiftRequest(spotReturn=0.02))  # the dial => scenario
    dial = live_slice(state, "ALPHA", expiry)
    assert dial.shift == pytest.approx(0.02)
    assert dial.forward == pytest.approx(base.forward * 1.02, rel=1e-12)
    assert dial.spot == pytest.approx(base.spot * 1.02, rel=1e-12)
    assert dial.live_spot == pytest.approx(base.spot, rel=1e-12)  # the book did not move
    by_key = {r.key: r for r in dial.rows}
    for r in base.rows:  # fixed strikes re-expressed against the dial's forward; IVs untouched
        assert by_key[r.key].k == pytest.approx(r.k - math.log(1.02), abs=1e-6)
        assert by_key[r.key].midIv == pytest.approx(r.midIv, abs=1e-8)
        assert by_key[r.key].strike == pytest.approx(r.strike, abs=1e-6)
    # A scenario at 0 is the ANCHOR frame, not the book.
    set_shift(state, "ALPHA", SpotShiftRequest(spotReturn=0.0))
    prov.spot_scale = 1.01
    zero = live_slice(state, "ALPHA", expiry)
    assert zero.forward == pytest.approx(base.forward, rel=1e-12) and zero.shift == 0.0
    assert zero.live_spot == pytest.approx(base.spot * 1.01, rel=1e-12)
    # Following the market (the poll synced a stale 5 %): the frame is the live
    # book again (its own spot move).
    state.set_spot_follow("ALPHA", "market")
    state.set_spot_shift("ALPHA", 0.05)
    poll = live_slice(state, "ALPHA", expiry)
    assert poll.forward == pytest.approx(base.forward * 1.01, rel=1e-12)
    assert poll.shift == pytest.approx(0.01, abs=1e-12)
    assert poll.spot == pytest.approx(base.spot * 1.01, rel=1e-12)
    assert poll.live_spot == pytest.approx(poll.spot, rel=1e-12)


# ---------------------------------------------------------------- tracker
def test_tracker_resends_every_row_when_the_dial_moves(rig):
    """A dial move with no tick re-frames every row (new moneyness, new forward
    and spot, the fit rolled to the dial's spot) as a delta — NOT a full reset,
    so the table's flash logic keeps flagging only material IV moves."""
    from volfit.api.schemas import SpotShiftRequest
    from volfit.api.spot import set_shift

    state, prov, expiry, table = rig
    prov.streaming = True
    tracker = LiveTableTracker()
    first = tracker.frame(state, "ALPHA", expiry)
    assert first.full and first.liveSpot == pytest.approx(first.spot)
    assert tracker.frame(state, "ALPHA", expiry) is None
    set_shift(state, "ALPHA", SpotShiftRequest(spotReturn=0.02))  # no tick, just the dial
    moved = tracker.frame(state, "ALPHA", expiry)
    assert moved is not None and not moved.full
    assert {r.key for r in moved.rows} == _keys(table) and moved.gone == []
    assert moved.forward == pytest.approx(first.forward * 1.02, rel=1e-12)
    assert moved.spot == pytest.approx(first.spot * 1.02, rel=1e-12)
    assert moved.liveSpot == pytest.approx(first.liveSpot)  # the book's spot is unchanged
    assert moved.model is not None  # the fit rolled to the dial's spot
    assert tracker.frame(state, "ALPHA", expiry) is None  # steady again


def test_tracker_full_then_deltas_then_gone_then_off(rig):
    state, prov, expiry, table = rig
    prov.streaming = True
    tracker = LiveTableTracker()
    first = tracker.frame(state, "ALPHA", expiry)
    assert first.type == "ticks" and first.full and first.ready and first.streaming
    assert {r.key for r in first.rows} == _keys(table) and first.nLive == len(table["rows"])
    assert first.spot == pytest.approx(table["forward"], rel=1e-9) or first.spot > 0
    assert tracker.frame(state, "ALPHA", expiry) is None  # nothing ticked
    reads = prov.live_reads
    # one quote ticks -> a delta frame with exactly that row
    target = table["rows"][3]
    prov.bumps[(target["strike"], target["type"])] = 1.05
    delta = tracker.frame(state, "ALPHA", expiry)
    assert delta is not None and not delta.full
    assert [r.key for r in delta.rows] == [row_key(target["strike"])]
    assert delta.rows[0].midIv > target["midIv"] and delta.gone == []
    assert prov.live_reads == reads + 1
    # a quote goes one-sided -> reported gone (the table falls back to its row)
    victim = table["rows"][0]
    prov.drop.add((victim["strike"], victim["type"]))
    gone = tracker.frame(state, "ALPHA", expiry)
    assert gone is not None and gone.gone == [row_key(victim["strike"])]
    assert gone.rows == [] and gone.nLive == len(table["rows"]) - 1
    # the stream stops -> one status frame (overlay dropped), then silence
    prov.streaming = False
    off = tracker.frame(state, "ALPHA", expiry)
    assert off.type == "status" and off.streaming is False and off.ready is False
    assert tracker.frame(state, "ALPHA", expiry) is None
    # back on -> a full repaint
    prov.streaming = True
    again = tracker.frame(state, "ALPHA", expiry)
    assert again.type == "ticks" and again.full


def test_tracker_announces_warming_once(rig):
    state, prov, expiry, _ = rig
    prov.streaming, prov.ready = True, False
    tracker = LiveTableTracker()
    warm = tracker.frame(state, "ALPHA", expiry)
    assert warm.type == "status" and warm.streaming is True and warm.ready is False
    assert tracker.frame(state, "ALPHA", expiry) is None
    prov.ready = True
    assert tracker.frame(state, "ALPHA", expiry).type == "ticks"


# -------------------------------------------------------------------- SSE
async def _chunks(state, ticker, expiry, n: int) -> list[str]:
    checks = {"n": 0}

    async def is_disconnected() -> bool:
        checks["n"] += 1
        return checks["n"] > n

    out = []
    async for chunk in table_events(state, ticker, expiry, is_disconnected, tick=0.0):
        out.append(chunk)
    return out


def test_sse_first_event_is_a_full_ticks_frame(rig):
    state, prov, expiry, table = rig
    prov.streaming = True
    chunks = asyncio.run(_chunks(state, "ALPHA", expiry, 2))
    assert chunks and chunks[0].startswith("data:")
    frame = json.loads(chunks[0][len("data:"):].strip())
    assert frame["type"] == "ticks" and frame["full"] is True
    assert {r["key"] for r in frame["rows"]} == _keys(table)
    assert len(chunks) == 1  # second pass: nothing ticked -> no event (no heartbeat yet)


def test_sse_without_a_stream_says_so_and_never_reads_the_book(rig):
    state, prov, expiry, _ = rig
    chunks = asyncio.run(_chunks(state, "ALPHA", expiry, 2))
    assert len(chunks) == 1
    frame = json.loads(chunks[0][len("data:"):].strip())
    assert frame == {
        "type": "status", "streaming": False, "ready": False, "full": False, "ts": None,
        "spot": None, "forward": None, "liveSpot": None, "rows": [], "gone": [], "nLive": 0,
            "model": None,
    }
    assert prov.live_reads == 0


def test_sse_unknown_node_ends_with_error_event(rig):
    state, prov, _, _ = rig
    prov.streaming = True
    chunks = asyncio.run(_chunks(state, "ALPHA", "2099-01-01", 3))
    assert len(chunks) == 1 and chunks[0].startswith("event: error")


def test_stream_route_is_registered(rig):
    state, *_ = rig
    app = create_app(reference_date=REF)
    assert "/smiles/{ticker}/{expiry}/table/stream" in {getattr(r, "path", "") for r in app.routes}
    assert table_stream.TICK_SECONDS == 1.0

"""Locks for the BUCKET ROTATION of the Bloomberg live book
(volfit.data.bloomberg_rotation + the hooks in bloomberg_plan / bloomberg_live
/ bloomberg_health), offline over the FakeSession / FakeBlp of
tests/test_bloomberg_stream.py — the fake paints every subscribed security
from its table the way the service INITPAINTs (churn check 2026-09-24: thirty
buckets of 40, every one painted in 0.8–3.0 s, 0 failures).

The contracts, in the design's order:

1. ENGAGES ONLY OVER THE CAP — under it the plan is byte-identical with the
   rotation on or off and no worker runs; over it R slots are reserved, the
   live set is the allocation's answer on the remainder and the pool is the
   rest, nearest the money first.
2. THE WORKER cycles the pool in buckets of ≤ R on the live session, the
   paint memory fills with stamps + spots, every bucket is unsubscribed, a
   failed security is skipped and retried next cycle.
3. THE CHAIN carries the rotated paints with their own ``timestamp`` and
   ``spot``; only a never-painted contract stays unquoted.
4. RE-PLAN SAFETY — a re-plan while a bucket is subscribed leaves the bucket
   alone and the worker finishes its cycle; a bucket security the new plan
   wants live is handed over, never dropped.
5. HEALTH — ``stream_stats()`` (validates as the API's ``StreamHealth``) and
   the light's "rotating N over cap · cycle X s".
6. QUOTE SYNC — the synchronisation step brings a rotated paint quoted at an
   older spot back onto the smile (within 1 bp) where the naive read is off
   by tens of bp.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import numpy as np

from tests.test_bloomberg_stream import (
    NEAR,
    SPOT,
    FakeBlp,
    FakeSession,
    _near_expiry,
    _opt_chain_frame,
    _paint,
    _wait,
)
from volfit.api.quote_sync import SyncContext
from volfit.api.quotes import prepare_quotes
from volfit.core.black import black_call
from volfit.data.bloomberg import BloombergProvider
from volfit.data.bloomberg_rotation import Paint, PaintMemory, rotation_order

STRIKES = list(range(90, 111))  # 21 strikes, $1 apart
LADDER = [f"SPY US {NEAR} {cp}{k} Equity" for k in STRIKES for cp in ("C", "P")]  # 42 contracts
UNDER = "SPY US Equity"
T = 30.0 / 365.0


def _session(spot: float = SPOT, skip: set[str] | None = None, **kwargs) -> FakeSession:
    """Paints the underlying at ``spot`` and every ladder contract (bid 1.0 /
    ask 1.2) except ``skip`` (left un-painted: the bucket waits them out)."""
    paint = {UNDER: {"LAST_PRICE": str(spot)}}
    for d in LADDER:
        if not skip or d not in skip:
            paint[d] = {"BID": "1.0", "ASK": "1.2", "LAST_PRICE": "1.1", "VOLUME": "3"}
    return FakeSession(paint=paint, **kwargs)


def _provider(session, cap: int = 9, slots: int | None = 2, poll: float = 0.01, wait: float = 0.5, **kwargs):
    """A one-ticker provider over the 42-contract ladder; ``cap`` 9 with R = 2
    leaves 6 live contracts (+ the underlying) and a 36-contract pool."""
    bdp_values = {UNDER: {"PX_LAST": SPOT}}
    blp = FakeBlp(_opt_chain_frame(LADDER), bdp_values)
    kwargs.setdefault("strike_window", (0.5, 1.5))
    kwargs.setdefault("book_first_wait", 0.3)
    prov = BloombergProvider(
        ["SPY"], blp_module=blp, stream_session_factory=lambda: session,
        max_subscriptions=cap, rotation_slots=slots, **kwargs,
    )
    prov._rotation_poll, prov._rotation_wait = poll, wait
    return prov, blp


def _strike(sec: str) -> float:
    return float(sec.split()[3][1:])


def _batches(session) -> list[list[str]]:
    return [[s for s, _f, _o in batch] for batch in session.subscribed]


# ------------------------------------------------------ 1. only over the cap

def test_rotation_engages_only_over_the_cap_and_is_byte_identical_under_it():
    session = _session()
    prov_on, _ = _provider(session, cap=60, slots=5)  # 42 + 1 < 60: under the cap
    prov_off, _ = _provider(session, cap=60, slots=0)
    plan = prov_on.option_tickers("SPY", [_near_expiry()])
    assert len(plan) == 42 and prov_off.option_tickers("SPY", [_near_expiry()]) == plan
    assert prov_on._plan_subscriptions(plan) == prov_off._plan_subscriptions(plan) == [UNDER] + plan
    assert prov_on._rotation_active == 0 and prov_on._rotation_pool == [] and prov_on._stream_dropped == set()
    prov_on.start_streaming(plan)
    try:
        assert _wait(lambda: prov_on._book is not None and prov_on._book.started() == 43)
        assert prov_on._rotation is None  # no worker under the cap
        assert prov_on.stream_stats()["rotation"] is None
        assert "over cap" not in prov_on._stream_status()[1]
    finally:
        prov_on.stop_streaming()
    # Over the cap: R = min(2, 9 // 4) = 2 reserved, 6 live (the nearest), the rest pooled nearest first.
    prov, _ = _provider(_session(), cap=9, slots=2)
    live = prov._plan_subscriptions(prov.option_tickers("SPY", [_near_expiry()]))
    assert prov._rotation_active == 2 and live[0] == UNDER and len(live) == 7
    assert all(abs(_strike(s) - SPOT) <= 1.0 for s in live[1:])
    pool = prov._rotation_pool
    assert len(pool) == 36 and set(pool) == prov._stream_dropped and set(pool).isdisjoint(live)
    dist = [abs(_strike(s) - SPOT) for s in pool]
    assert dist == sorted(dist)  # nearest the money first
    assert prov.streaming_contracts() == set()  # not streaming yet


def test_rotation_order_interleaves_tickers_by_rank():
    dropped = ["A1", "A2", "A3", "B1", "B2"]  # grouped per ticker, each in rank order
    assert rotation_order(dropped, lambda s: s[0]) == ["A1", "B1", "A2", "B2", "A3"]
    assert rotation_order([], lambda s: s) == []


# ------------------------------------------------------------ 2. the worker

def test_worker_cycles_buckets_fills_the_memory_and_unsubscribes_every_bucket():
    session = _session()
    prov, blp = _provider(session)
    plan = prov.option_tickers("SPY", [_near_expiry()])
    n_bdp = len(blp.bdp_calls)
    t0 = time.monotonic()
    prov.start_streaming(plan)
    try:
        worker = prov._rotation
        assert worker is not None and worker.is_running()
        peak = 0
        while worker.stats()["cycles"] < 2 and time.monotonic() - t0 < 10.0:
            peak = max(peak, len(prov._sub.securities))
            time.sleep(0.005)
        stats = worker.stats()
        assert stats["cycles"] >= 2, stats
        assert stats["pool"] == 36 and stats["slots"] == 2 and stats["painted"] == 36 and stats["failed"] == 0
        assert stats["cycleSeconds"] > 0.0 and stats["bucketSeconds"] is not None
        assert peak <= 7 + 2  # never more than the live set + one bucket subscribed
        assert worker.memory.size() == 36
        pool = worker.pool()
        for sec in pool:
            p = worker.memory.get(sec)
            assert isinstance(p, Paint) and (p.bid, p.ask, p.last, p.volume) == (1.0, 1.2, 1.1, 3)
            assert isinstance(p.stamp, datetime) and p.ts is None and p.spot == SPOT
        # every bucket (<= 2 securities, in pool order) was subscribed then unsubscribed
        buckets = _batches(session)[1:]
        assert all(len(b) <= 2 for b in buckets) and buckets[0] == pool[:2]
        unsubscribed = [s for b in session.unsubscribed for s in b]
        assert set(unsubscribed) == set(pool) and unsubscribed[:2] == pool[:2]
        assert prov._book.quote(pool[0]) is None or pool[0] in worker.owned()  # forgotten by the book
        assert len(blp.bdp_calls) == n_bdp  # not one metered hit
    finally:
        prov.stop_streaming()
    assert not worker.is_running() and prov._rotation is None


def test_failed_securities_are_skipped_and_retried_next_cycle():
    prov, _ = _provider(_session(fail={f"SPY US {NEAR} C90 Equity": "BAD_SEC"}))
    bad = f"SPY US {NEAR} C90 Equity"
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        worker = prov._rotation
        assert _wait(lambda: worker.stats()["cycles"] >= 2, timeout=10.0)
        stats = worker.stats()
        assert stats["painted"] == 35 and stats["failed"] == 1 and stats["memory"] == 35
        assert worker.memory.get(bad) is None
        session = prov._stream_factory()  # the one FakeSession the factory hands out
        assert sum(bad in b for b in _batches(session)) >= 2  # retried on the next cycle
        assert prov.stream_stats()["refused"] <= 1
    finally:
        prov.stop_streaming()


def test_paint_memory_retains_only_the_pool():
    mem = PaintMemory()
    now = datetime.utcnow()
    for s in ("A", "B", "C"):
        mem.put(s, Paint(1.0, 1.2, None, None, None, now, 100.0))
    mem.retain(["B", "Z"])
    assert mem.size() == 1 and mem.get("B") is not None and mem.get("A") is None


# ------------------------------------------------------------- 3. the chain

def test_chain_carries_rotated_paints_with_their_own_stamp_and_spot():
    session = _session()
    prov, blp = _provider(session)
    near = _near_expiry()
    prov.start_streaming(prov.option_tickers("SPY", [near]))
    try:
        worker = prov._rotation
        assert _wait(lambda: worker.stats()["cycles"] >= 1, timeout=10.0)
        worker.stop()  # freeze the memory: the paints keep the spot they were taken at
        n_bdp = len(blp.bdp_calls)
        snap = prov.live_chain("SPY", [near])
        assert snap is not None and len(snap.quotes) == 42 and len(blp.bdp_calls) == n_bdp
        rotated = [q for q in snap.quotes if abs(q.strike - SPOT) > 1.0]
        live = [q for q in snap.quotes if abs(q.strike - SPOT) <= 1.0]
        assert len(rotated) == 36 and len(live) == 6
        assert all(q.bid == 1.0 and q.ask == 1.2 and q.last == 1.1 and q.volume == 3 for q in snap.quotes)
        assert {q.spot for q in snap.quotes} == {SPOT}
        # the underlying moves + a stamped live tick: live quotes follow, paints keep their own
        stamp = datetime(2026, 9, 24, 15, 30, 0)
        prov._book.apply([_paint(UNDER, LAST_PRICE="101.0"),
                          {"kind": "data", "sec": f"SPY US {NEAR} C100 Equity",
                           "fields": {"BID": "1.01"}, "ts": stamp}])
        snap = prov.live_chain("SPY", [near])
        assert snap.spot == 101.0 and snap.timestamp == stamp
        by_strike = {(q.strike, q.call_put): q for q in snap.quotes}
        assert by_strike[(100.0, "C")].spot == 101.0 and by_strike[(100.0, "C")].bid == 1.01
        assert all(q.spot == 101.0 and q.timestamp == stamp for q in snap.quotes if abs(q.strike - SPOT) <= 1.0)
        for q in snap.quotes:
            if abs(q.strike - SPOT) > 1.0:
                sec = f"SPY US {NEAR} {q.call_put}{int(q.strike)} Equity"
                p = worker.memory.get(sec)
                assert q.spot == p.spot == SPOT  # quoted against the spot of its paint
                # dated by its age: the chain's newest stamp minus the wall time since the paint
                age = (stamp - q.timestamp).total_seconds()
                assert 0.0 <= age < 5.0 and abs(age - (datetime.utcnow() - p.stamp).total_seconds()) < 1.0
        # a paint with a provider stamp of its own is dated by it (like a live tick)
        old = datetime(2026, 9, 24, 14, 0, 0)
        sec = f"SPY US {NEAR} C95 Equity"
        p = worker.memory.get(sec)
        worker.memory.put(sec, Paint(p.bid, p.ask, p.last, p.volume, old, p.stamp, p.spot))
        snap = prov.live_chain("SPY", [near])
        assert {q.timestamp for q in snap.quotes if q.strike == 95.0 and q.call_put == "C"} == {old}
        # a contract never painted is the only one carried unquoted
        worker.memory.retain([s for s in worker.pool() if "C90" not in s])
        snap = prov.live_chain("SPY", [near])
        blank = [q for q in snap.quotes if q.bid is None]
        assert [(q.strike, q.call_put) for q in blank] == [(90.0, "C")]
        assert blank[0].spot == 101.0 and blank[0].timestamp == stamp
    finally:
        prov.stop_streaming()


# ------------------------------------------------------- 4. re-plan safety

def test_a_replan_leaves_the_bucket_in_flight_alone_and_the_cycle_completes():
    """The first bucket's securities are NOT painted by the fake: the worker
    holds that bucket for the full wait, during which a re-plan runs."""
    prov0, _ = _provider(_session())
    prov0._plan_subscriptions(prov0.option_tickers("SPY", [_near_expiry()]))
    pool = prov0._rotation_pool
    first = pool[:2]
    session = _session(skip=set(first))
    prov, _ = _provider(session, wait=0.6)
    near = _near_expiry()
    plan = prov.option_tickers("SPY", [near])
    prov.start_streaming(plan)
    try:
        worker = prov._rotation
        assert _wait(lambda: worker.owned() == set(first))
        n_unsub = len(session.unsubscribed)
        added, removed = prov.update_streaming(plan)  # the same universe: a no-op re-plan
        assert (added, removed) == ([], [])
        assert worker.owned() == set(first) and set(first) <= set(prov._sub.securities)
        assert len(session.unsubscribed) == n_unsub  # the bucket was not touched
        assert prov._rotation is worker and worker.pool() == pool  # same pool: the cycle goes on
        assert _wait(lambda: worker.stats()["cycles"] >= 1, timeout=10.0)
        assert worker.stats()["painted"] == 34  # the two un-painted ones timed out, the rest painted
        assert [s for b in session.unsubscribed for s in b][:2] == first  # released by the worker itself
    finally:
        prov.stop_streaming()


def test_a_bucket_security_promoted_to_the_live_set_is_handed_over_not_dropped():
    prov0, _ = _provider(_session())
    prov0._plan_subscriptions(prov0.option_tickers("SPY", [_near_expiry()]))
    first = prov0._rotation_pool[:2]
    session = _session(skip=set(first))
    prov, _ = _provider(session, wait=0.6)
    near = _near_expiry()
    plan = prov.option_tickers("SPY", [near])
    prov.start_streaming(plan)
    try:
        worker = prov._rotation
        assert _wait(lambda: worker.owned() == set(first))
        prov._max_subscriptions = 21  # a wider budget: R stays 2, the live set grows to 18
        added, removed = prov.update_streaming(plan)
        assert set(first) <= set(added) and removed == []
        assert worker.owned() == set() and set(first) <= set(prov._sub.securities)
        assert set(first).isdisjoint(prov._stream_dropped) and set(first).isdisjoint(worker.pool())
        assert len(worker.pool()) == 42 - 18
        # ... and the worker, moving on, never unsubscribes them
        assert _wait(lambda: worker.stats()["cycles"] >= 1, timeout=10.0)
        assert all(s not in first for b in session.unsubscribed for s in b)
        assert set(first) <= set(prov._sub.securities)
        # the memory forgot what left the pool
        assert all(worker.memory.get(s) is None for s in first)
    finally:
        prov.stop_streaming()


# ---------------------------------------------------------------- 5. health

def test_stream_stats_and_the_light_report_the_rotation():
    from volfit.api.routers.datasource import StreamHealth

    prov, _ = _provider(_session())
    assert prov.stream_stats() is None
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        worker = prov._rotation
        assert _wait(lambda: prov._book is not None and prov._book.started() >= 7)
        level, detail = prov._stream_status()
        assert level == "amber" and "rotating 36 over cap · " in detail and "painted so far" in detail, detail
        assert _wait(lambda: worker.stats()["cycles"] >= 1, timeout=10.0)
        detail = prov._stream_status()[1]
        assert "rotating 36 over cap · cycle " in detail and detail.endswith(" s"), detail
        stats = prov.stream_stats()
        health = StreamHealth(**stats)
        assert health.overCap == 36 and health.requested == 42 and health.cap == 9
        assert health.acknowledged >= 7 and 7 <= health.subscribed <= 9 and health.refused == 0
        assert health.tickers == {"SPY": True} and health.connected and health.running
        assert health.allocation == {"SPY": {"requested": 42, "live": 6, "focus": 0}}
        assert health.rate >= 0.0 and stats["messages"] > 36 and stats["lastMessageAge"] is not None
        rot = health.rotation
        assert rot["pool"] == 36 and rot["slots"] == 2 and rot["cycles"] >= 1 and rot["painted"] == 36
        assert rot["bucketWait"] == 0.5 and rot["cycleSeconds"] > 0 and rot["memory"] == 36
        assert 0 <= rot["paintedNow"] <= 36 and 0 <= rot["bucketsNow"] <= 18
        assert health.detail == detail and health.level == "amber"
    finally:
        prov.stop_streaming()
    assert prov.stream_stats() is None


# ------------------------------------------------------------ 6. quote sync

def sigma_ref(k):
    """The known (skewed) smile: sigma(k) = 0.20 - 0.25 k + 0.5 k^2."""
    k = np.asarray(k, dtype=float)
    return 0.20 - 0.25 * k + 0.5 * k * k


def _priced_session(spot: float) -> FakeSession:
    """Every ladder contract priced at ``spot`` (zero carry, F = S) with the
    vol its STRIKE has on the reference smile at F = 100 (sticky-strike
    truth), 1 % relative half-spread."""
    paint = {UNDER: {"LAST_PRICE": str(spot)}}
    for sec in LADDER:
        strike = _strike(sec)
        sigma = float(sigma_ref(np.log(strike / SPOT)))
        call = spot * float(black_call(np.log(strike / spot), sigma * sigma * T))
        mid = call if sec.split()[3][0] == "C" else call - (spot - strike)
        paint[sec] = {"BID": f"{mid * 0.99:.6f}", "ASK": f"{mid * 1.01:.6f}"}
    return FakeSession(paint=paint)


def test_quote_sync_brings_a_rotated_paint_quoted_at_an_older_spot_onto_the_smile():
    """The pool is painted while the underlying stands 0.1 % below the chain's
    spot; the live set then re-ticks at the chain's spot. Read naively the
    paints mis-read the smile by tens of bp; synchronised they sit on it."""
    from volfit.data.forwards import ImpliedForward

    s_old = SPOT * (1.0 - 1e-3)
    session = _priced_session(s_old)
    prov, _ = _provider(session)
    near = _near_expiry()
    prov._style_cache["SPY"] = "european"  # the fake ladder is priced European
    prov.start_streaming(prov.option_tickers("SPY", [near]))
    try:
        worker = prov._rotation
        assert _wait(lambda: worker.stats()["cycles"] >= 1, timeout=10.0)
        worker.stop()  # the memory holds paints taken at s_old ...
        for sec in worker.pool():  # ... two minutes ago
            p = worker.memory.get(sec)
            worker.memory.put(sec, Paint(p.bid, p.ask, p.last, p.volume, p.ts, p.stamp - timedelta(minutes=2), p.spot))
        # now the live set re-ticks at SPOT (priced there) and the underlying moves to SPOT
        fresh = _priced_session(SPOT).paint
        stamp = datetime.utcnow().replace(microsecond=0)
        records = [{"kind": "data", "sec": UNDER, "fields": {"LAST_PRICE": str(SPOT)}, "ts": stamp}]
        for sec in prov._sub.securities:
            if sec != UNDER:
                records.append({"kind": "data", "sec": sec, "fields": fresh[sec], "ts": stamp})
        prov._book.apply(records)
        snap = prov.live_chain("SPY", [near])
        assert snap.spot == SPOT and snap.timestamp == stamp
        rotated = {(q.strike, q.call_put) for q in snap.quotes if q.spot == s_old}
        assert len(rotated) == 36 and all(q.timestamp < stamp for q in snap.quotes if q.spot == s_old)
    finally:
        prov.stop_streaming()
    fwd = ImpliedForward(expiry=near, forward=SPOT, discount=1.0, n_strikes=21, residual_rms=0.0)
    ctx = SyncContext(
        forward_at=lambda s: SPOT * s / SPOT, regime="sticky_strike",
        reference_w=lambda k: sigma_ref(k) ** 2 * T, reference_forward=SPOT, sigma_atm=0.20,
    )
    naive = prepare_quotes(snap, near, fwd, T)
    synced = prepare_quotes(snap, near, fwd, T, sync=ctx)
    err_naive = np.abs(naive.iv_mid - sigma_ref(naive.k)) * 1e4
    err_sync = np.abs(synced.iv_mid - sigma_ref(synced.k)) * 1e4
    # the prep keeps the OTM side per strike: 21 rows, the 3 live strikes' and 18 rotated
    assert synced.sync_reference == "fit" and synced.n_synced == int(np.count_nonzero(synced.age_min > 0.0)) >= 15
    assert err_naive.max() > 20.0, f"naive max error {err_naive.max():.1f} bp"
    assert err_sync.max() < 1.0, f"synchronised max error {err_sync.max():.3f} bp"
    assert 1.9 < synced.age_min.max() <= 2.1 and synced.age_min.min() == 0.0  # the paints are 2 min older
    ladder_k = {round(float(k), 6) for k in np.log(np.array(STRIKES, dtype=float) / SPOT)}
    assert {round(float(k), 6) for k in synced.k} <= ladder_k  # relabelled at F_now: the ladder's strikes


def test_no_metered_hit_while_rotating_a_selection_wider_than_the_cap():
    """The whole point: a universe over the cap is read off the book."""
    session = _session()
    prov, blp = _provider(session)
    near = _near_expiry()
    prov.start_streaming(prov.option_tickers("SPY", [near]))
    try:
        n = len(blp.bdp_calls)
        assert _wait(lambda: prov._rotation.stats()["cycles"] >= 1, timeout=10.0)
        snap = prov.fetch_chain("SPY", [near])
        assert len(snap.quotes) == 42 and all(q.bid is not None for q in snap.quotes)
        assert len(blp.bdp_calls) == n
    finally:
        prov.stop_streaming()

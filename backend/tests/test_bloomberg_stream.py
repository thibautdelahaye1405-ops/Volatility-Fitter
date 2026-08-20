"""Offline tests for the Bloomberg ``//blp/mktdata`` streaming path.

No Terminal / no blpapi: ``FakeMessage`` stands in for a blpapi subscription
message (the duck-typed surface volfit.data.bloomberg_decode reads) and
``FakeSession`` for the session the subscription thread drives — it acknowledges
every subscription with ``SubscriptionStarted`` and paints each security from a
scripted ``paint`` table, the way the live service INITPAINTs (confirmed against
an open Terminal 2026-08-20). The provider tests reuse the FakeBlp reference-data
stub of test_bloomberg and assert the book path issues NO ``bdp``.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta

import pandas as pd

from volfit.data.bloomberg import BloombergProvider
from volfit.data.bloomberg_decode import (
    decode_data_message,
    decode_event,
    decode_status_message,
    parse_stamp,
)
from volfit.data.bloomberg_live import RECENTER_PCT
from volfit.data.bloomberg_stream import SUBSCRIBE_BATCH, BbgBook, BloombergSubscription

TODAY = date.today()


# ------------------------------------------------------------------ fakes
class FakeElement:
    def __init__(self, value=None, null=False, children=None):
        self._value, self._null, self._children = value, null, children or {}

    def isNull(self):  # noqa: N802 — blpapi naming
        return self._null

    def getValueAsString(self):  # noqa: N802
        return str(self._value)

    def hasElement(self, key):  # noqa: N802
        return key in self._children

    def getElementAsString(self, key):  # noqa: N802
        return str(self._children[key])


class _Cid:
    def __init__(self, v):
        self._v = v

    def value(self):
        return self._v


class FakeMessage:
    """``fields``: {name: value | None (NULL element)}; ``reason``: status block."""

    def __init__(self, name, sec, fields=None, reason=None):
        self._name, self._sec = name, sec
        self._fields = dict(fields or {})
        self._reason = reason

    def messageType(self):  # noqa: N802
        return self._name

    def correlationIds(self):  # noqa: N802
        return [_Cid(self._sec)] if self._sec is not None else []

    def hasElement(self, name, *_):  # noqa: N802
        return name in self._fields or (name == "reason" and self._reason is not None)

    def getElement(self, name):  # noqa: N802
        if name == "reason":
            return FakeElement(children=self._reason)
        v = self._fields[name]
        return FakeElement(v, null=v is None)


def _paint(sec, **fields):
    return {"kind": "data", "sec": sec, "fields": fields, "ts": None}


class FakeSession:
    """Scripted mktdata session: acknowledges + paints every subscribed security."""

    def __init__(self, paint=None, fail_open=False, fail=None, delayed=False):
        self.paint = dict(paint or {})
        self.fail = dict(fail or {})  # sec -> reason
        self.delayed = delayed
        self.fail_open = fail_open
        self.subscribed: list[list[tuple[str, str, str]]] = []
        self.queue: list[list[dict]] = []
        self.stopped = False

    def openService(self, name):  # noqa: N802
        return not self.fail_open

    def subscription_list(self, items):
        return list(items)

    def subscribe(self, subs):
        self.subscribed.append(list(subs))
        batch = []
        for sec, _fields, _opts in subs:
            if sec in self.fail:
                batch.append({"kind": "failure", "sec": sec, "reason": self.fail[sec]})
                continue
            batch.append({"kind": "started", "sec": sec})
            fields = dict(self.paint.get(sec, {}))
            if fields:
                fields.setdefault("IS_DELAYED_STREAM", "true" if self.delayed else "false")
                batch.append({"kind": "data", "sec": sec, "fields": fields, "ts": None})
        self.queue.append(batch)

    def push(self, records):
        self.queue.append(list(records))

    def nextEvent(self, timeout_ms):  # noqa: N802
        if self.queue:
            return self.queue.pop(0)
        time.sleep(0.005)
        return None

    def stop(self):
        self.stopped = True


def _wait(pred, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


# ------------------------------------------------------------------- book
def test_book_merges_deltas_and_clears_nulled_sides():
    book = BbgBook()
    t1 = datetime(2026, 8, 20, 18, 0, 0)
    book.apply([{"kind": "data", "sec": "S", "fields": {"BID": "1.0", "ASK": "1.2", "LAST_PRICE": "1.1", "VOLUME": "12.0", "IS_DELAYED_STREAM": "true"}, "ts": t1}])
    tick = book.quote("S")
    assert (tick.bid, tick.ask, tick.last, tick.volume, tick.ts, tick.delayed) == (1.0, 1.2, 1.1, 12, t1, True)
    # delta: only the bid moves; an older stamp never rewinds the tick stamp
    book.apply([{"kind": "data", "sec": "S", "fields": {"BID": "1.05"}, "ts": t1 - timedelta(seconds=5)}])
    tick = book.quote("S")
    assert (tick.bid, tick.ask, tick.ts) == (1.05, 1.2, t1)
    # NULL ask = side withdrawn -> None; zero bid = no quote -> None
    book.apply([{"kind": "data", "sec": "S", "fields": {"ASK": None, "BID": "0"}, "ts": t1 + timedelta(seconds=1)}])
    tick = book.quote("S")
    assert tick.ask is None and tick.bid is None and tick.ts == t1 + timedelta(seconds=1)
    assert book.newest_ts() == t1 + timedelta(seconds=1) and book.delayed(["S"]) is True


def test_book_tracks_subscription_status():
    book = BbgBook()
    assert book.connected is False
    book.apply([{"kind": "started", "sec": "A"}, {"kind": "failure", "sec": "B", "reason": "Unknown/Invalid security"}])
    assert book.connected is True and book.started() == 1
    assert book.failures() == {"B": "Unknown/Invalid security"}
    book.apply([{"kind": "started", "sec": "B"}, {"kind": "terminated", "sec": "A", "reason": "x"}])
    assert book.failures() == {} and book.started() == 1
    book.apply([{"kind": "session_down"}])
    assert book.connected is False
    book.clear()
    assert book.started() == 0 and book.size() == 0


def test_book_wait_for_unblocks_on_paint_and_on_failure():
    book = BbgBook()
    threading.Timer(0.05, lambda: book.apply([_paint("U", LAST_PRICE="10")])).start()
    t0 = time.monotonic()
    assert book.wait_for("U", 2.0).last == 10.0
    assert time.monotonic() - t0 < 1.5
    threading.Timer(0.05, lambda: book.apply([{"kind": "failure", "sec": "F", "reason": "BAD_SEC"}])).start()
    t0 = time.monotonic()
    assert book.wait_for("F", 2.0) is None  # failed -> returns promptly, no tick
    assert time.monotonic() - t0 < 1.5
    assert book.wait_for("never", 0.05) is None


# ----------------------------------------------------------------- decode
def test_parse_stamp_normalizes_to_utc_naive():
    assert parse_stamp("2026-08-20T19:18:58.027+01:00") == datetime(2026, 8, 20, 18, 18, 58, 27000)
    assert parse_stamp("2026-08-20T18:18:58") == datetime(2026, 8, 20, 18, 18, 58)
    assert parse_stamp("garbage") is None and parse_stamp(None) is None


def test_decode_data_message_reports_present_fields_nulls_and_newest_stamp():
    msg = FakeMessage(
        "MarketDataEvents", "SPY US Equity",
        {"BID": "763.56", "ASK": None, "IS_DELAYED_STREAM": "true",
         "BID_UPDATE_STAMP_RT": "2026-08-20T19:18:58.967+01:00",
         "TRADE_UPDATE_STAMP_RT": "2026-08-20T19:18:59.016+01:00"},
    )
    rec = decode_data_message(msg)
    assert rec["kind"] == "data" and rec["sec"] == "SPY US Equity"
    assert rec["fields"] == {"BID": "763.56", "ASK": None, "IS_DELAYED_STREAM": "true"}
    assert rec["ts"] == datetime(2026, 8, 20, 18, 18, 59, 16000)  # newest, UTC
    assert decode_data_message(FakeMessage("MarketDataEvents", None, {"BID": "1"})) is None


def test_decode_status_messages():
    assert decode_status_message(FakeMessage("SubscriptionStarted", "A")) == {"kind": "started", "sec": "A"}
    bad = FakeMessage("SubscriptionFailure", "B", reason={"category": "BAD_SEC", "description": "Unknown/Invalid security"})
    assert decode_status_message(bad) == {"kind": "failure", "sec": "B", "reason": "Unknown/Invalid security"}
    gone = FakeMessage("SubscriptionTerminated", "C", reason={"category": "LIMIT"})
    assert decode_status_message(gone) == {"kind": "terminated", "sec": "C", "reason": "LIMIT"}
    assert decode_status_message(FakeMessage("SubscriptionStreamsActivated", "A")) == {}
    assert decode_event([{"kind": "started", "sec": "X"}]) == [{"kind": "started", "sec": "X"}]


# -------------------------------------------------------------- transport
def test_subscription_thread_batches_subscribes_and_books_ticks():
    secs = [f"S{i}" for i in range(SUBSCRIBE_BATCH * 2 + 10)]
    session = FakeSession(paint={"S0": {"BID": "1", "ASK": "2"}, "S5": {"LAST_PRICE": "3"}})
    book = BbgBook()
    sub = BloombergSubscription(secs, book, interval=1.0, session_factory=lambda: session)
    sub.start()
    try:
        assert _wait(lambda: book.started() == len(secs) and book.size() == 2)
        assert [len(b) for b in session.subscribed] == [SUBSCRIBE_BATCH, SUBSCRIBE_BATCH, 10]
        sec, fields, opts = session.subscribed[0][0]
        assert (sec, fields, opts) == ("S0", "BID,ASK,LAST_PRICE,VOLUME", "interval=1")
        assert book.quote("S0").bid == 1.0 and book.quote("S5").last == 3.0
        assert sub.is_running() and sub.securities == secs
    finally:
        sub.stop()
    assert _wait(lambda: not sub.is_running()) and session.stopped
    assert book.size() == 0  # stop() drops the book


def test_subscription_thread_survives_open_failure_and_retries():
    session = FakeSession(fail_open=True)
    sub = BloombergSubscription(["A"], BbgBook(), session_factory=lambda: session, max_backoff=0.05)
    sub.start()
    try:
        assert _wait(lambda: sub.last_error is not None and session.stopped)
        assert "could not open //blp/mktdata" in sub.last_error
        assert sub.is_running()  # still retrying with backoff, never crashed
    finally:
        sub.stop()
    assert _wait(lambda: not sub.is_running())


def test_subscription_reconnects_after_session_down():
    sessions: list[FakeSession] = []

    def factory():
        s = FakeSession(paint={"A": {"LAST_PRICE": "5"}})
        sessions.append(s)
        return s

    book = BbgBook()
    sub = BloombergSubscription(["A"], book, session_factory=factory, max_backoff=0.05)
    sub.start()
    try:
        assert _wait(lambda: len(sessions) == 1 and book.quote("A") is not None)
        sessions[0].push([{"kind": "session_down"}])
        assert _wait(lambda: len(sessions) == 2 and sessions[0].stopped)
        assert _wait(lambda: book.started() >= 1)  # resubscribed on the new session
    finally:
        sub.stop()


# --------------------------------------------------------------- provider
def _future(days: int) -> str:
    d = TODAY + timedelta(days=days)
    return f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}"


def _opt_chain_frame(descriptors):
    return pd.DataFrame({"ticker": ["SPY US Equity"] * len(descriptors), "field": ["OPT_CHAIN"] * len(descriptors), "Security Description": descriptors})


def _bdp_long(values):
    rows = [{"ticker": s, "field": f, "value": v} for s, fs in values.items() for f, v in fs.items()]
    return pd.DataFrame(rows, columns=["ticker", "field", "value"])


class FakeBlp:
    """xbbg.blp stand-in counting the metered reference requests."""

    def __init__(self, chain, bdp_values):
        self._chain, self._bdp_values = chain, bdp_values
        self.bdp_calls: list[list[str]] = []

    def is_connected(self):
        return True

    def bds(self, security, field, **_):
        assert field == "OPT_CHAIN"
        return self._chain

    def bdp(self, securities, fields, **_):
        secs = [securities] if isinstance(securities, str) else list(securities)
        self.bdp_calls.append(secs)
        return _bdp_long({s: {f: self._bdp_values.get(s, {}).get(f) for f in ([fields] if isinstance(fields, str) else fields)} for s in secs})


NEAR, FAR = _future(30), _future(120)
SPOT = 100.0
DESCRIPTORS = [f"SPY US {NEAR} C{k} Equity" for k in (90, 95, 100, 105, 110, 150)] + [
    f"SPY US {NEAR} P{k} Equity" for k in (90, 95, 100, 105, 110)
] + [f"SPY US {FAR} C100 Equity", f"SPY US {FAR} P100 Equity"]


def _make_provider(session, **kwargs):
    bdp_values = {"SPY US Equity": {"PX_LAST": SPOT}}
    for d in DESCRIPTORS:  # reference (metered) quotes, distinguishable from streamed ones
        bdp_values[d] = {"BID": "9.0", "ASK": "9.5", "LAST_PRICE": "9.2", "VOLUME": "1", "OPEN_INT": "77", "OPT_EXER_TYP": "American"}
    blp = FakeBlp(_opt_chain_frame(DESCRIPTORS), bdp_values)
    kwargs.setdefault("strike_window", (0.9, 1.1))
    prov = BloombergProvider(["SPY"], blp_module=blp, stream_session_factory=lambda: session, **kwargs)
    return prov, blp


def _near_expiry() -> date:
    return TODAY + timedelta(days=30)


def test_option_tickers_windows_around_a_cached_center():
    prov, blp = _make_provider(FakeSession())
    secs = prov.option_tickers("SPY", [_near_expiry()])
    assert all("C150" not in s for s in secs) and len(secs) == 10  # 90..110 C+P, 150 windowed out
    assert blp.bdp_calls == [["SPY US Equity"]]  # ONE metered PX_LAST to centre the window
    prov.option_tickers("SPY", [_near_expiry()])
    assert len(blp.bdp_calls) == 1  # cached centre: the per-tick call is free


def test_start_streaming_subscribes_underlying_and_caps_nearest_the_money():
    session = FakeSession()
    prov, _ = _make_provider(session, max_subscriptions=5)
    wanted = prov.option_tickers("SPY", [_near_expiry()])
    prov.start_streaming(wanted)
    try:
        assert _wait(lambda: session.subscribed)
        subscribed = [s for batch in session.subscribed for s, _, _ in batch]
        assert subscribed[0] == "SPY US Equity" and len(subscribed) == 5  # underlying + 4 nearest
        assert {s.split()[3] for s in subscribed[1:]} <= {"C100", "P100", "C95", "P95", "C105", "P105"}
        assert prov.streaming_contracts() == set(wanted)  # REQUESTED set (pre-cap) for the diff
        assert len(prov._stream_dropped) == 6
        assert prov.is_streaming()
    finally:
        prov.stop_streaming()
    assert not prov.is_streaming() and prov.streaming_contracts() == set()


def test_fetch_chain_and_spot_are_served_from_the_book_without_bdp():
    paint = {"SPY US Equity": {"BID": "101.0", "ASK": "101.2", "LAST_PRICE": "101.1"}}
    for d in DESCRIPTORS:
        paint[d] = {"BID": "1.0", "ASK": "1.2", "LAST_PRICE": "1.1", "VOLUME": "5"}
    session = FakeSession(paint=paint)
    prov, blp = _make_provider(session)
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        metered_before = len(blp.bdp_calls)
        snap = prov.fetch_chain("SPY", [_near_expiry()])
        assert len(blp.bdp_calls) == metered_before  # NO reference hit: the book served it
        assert snap.spot == 101.1 and len(snap.quotes) == 10
        assert {(q.bid, q.ask, q.last, q.volume) for q in snap.quotes} == {(1.0, 1.2, 1.1, 5)}
        assert snap.exercise_style == "american"
        assert prov.spot("SPY") == 101.1 and len(blp.bdp_calls) == metered_before
        assert prov.feed_status()[0] in ("green", "amber")
        # INITPAINTs carry no stamp: once ONE stamped tick exists, un-stamped quotes
        # are dated by the chain's newest provider stamp, not the wall clock
        # (honest on a 15-min delayed feed); the chain itself carries that stamp.
        stamp = datetime(2026, 8, 20, 18, 30, 58)
        prov._book.apply([{"kind": "data", "sec": DESCRIPTORS[2], "fields": {"BID": "1.01"}, "ts": stamp}])
        snap = prov.fetch_chain("SPY", [_near_expiry()])
        assert snap.timestamp == stamp and {q.timestamp for q in snap.quotes} == {stamp}
    finally:
        prov.stop_streaming()
    # back on the reference path: a fetch bdp's the contracts again
    prov.fetch_chain("SPY", [_near_expiry()])
    assert len(blp.bdp_calls) > metered_before


def test_fetch_chain_falls_back_to_reference_when_selection_not_subscribed():
    paint = {"SPY US Equity": {"LAST_PRICE": "100"}}
    session = FakeSession(paint=paint)
    prov, blp = _make_provider(session)
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        assert _wait(lambda: prov._book is not None and prov._book.started() > 0)
        n = len(blp.bdp_calls)
        far = TODAY + timedelta(days=120)
        snap = prov.fetch_chain("SPY", [_near_expiry(), far])  # far expiry not streamed yet
        assert len(blp.bdp_calls) == n + 1  # metered fallback, but a COMPLETE chain
        assert {q.expiry for q in snap.quotes} == {_near_expiry(), far}
        assert snap.quotes[0].open_interest == 77
        # the streamed chain afterwards carries the remembered OI + style
        snap2 = prov.fetch_chain("SPY", [_near_expiry()])
        assert snap2.quotes[0].open_interest == 77 and len(blp.bdp_calls) == n + 1
    finally:
        prov.stop_streaming()


def test_feed_status_reflects_stream_states():
    paint = {"SPY US Equity": {"LAST_PRICE": "100"}}
    session = FakeSession(paint=paint, delayed=True)
    prov, _ = _make_provider(session)
    assert prov.feed_status() == ("green", "real-time (Terminal)")  # reference path
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        assert _wait(lambda: prov._book is not None and prov._book.started() > 0)
        level, detail = prov.feed_status()
        assert level == "amber" and "warming" in detail  # no provider stamp yet
        ts = datetime.utcnow().replace(microsecond=0)
        prov._book.apply([{"kind": "data", "sec": "SPY US Equity", "fields": {"LAST_PRICE": "100.5"}, "ts": ts}])
        level, detail = prov.feed_status()
        assert level == "amber" and "delayed" in detail and "streaming" in detail
        prov._book.apply([{"kind": "data", "sec": "SPY US Equity", "fields": {"IS_DELAYED_STREAM": "false"}, "ts": ts}])
        level, detail = prov.feed_status()
        assert level == "green" and "real-time" in detail
        prov._book.apply([{"kind": "data", "sec": "SPY US Equity", "fields": {}, "ts": ts}])
        prov._book._ticks["SPY US Equity"] = prov._book._ticks["SPY US Equity"].__class__(
            last=100.5, ts=ts - timedelta(hours=1)
        )
        assert "idle since" in prov.feed_status()[1]
    finally:
        prov.stop_streaming()


def test_feed_status_red_when_underlying_refused_or_session_errors():
    session = FakeSession(fail={"SPY US Equity": "NOT_ENTITLED"})
    prov, _ = _make_provider(session)
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        assert _wait(lambda: prov._book is not None and "SPY US Equity" in prov._book.failures())
        assert prov.feed_status() == ("red", "stream: NOT_ENTITLED")
        assert prov.fetch_chain("SPY", [_near_expiry()]).spot == SPOT  # reference fallback still works
    finally:
        prov.stop_streaming()
    prov2, _ = _make_provider(FakeSession(fail_open=True))
    prov2.start_streaming(prov2.option_tickers("SPY", [_near_expiry()]))
    try:
        assert _wait(lambda: prov2._sub is not None and prov2._sub.last_error is not None)
        assert prov2.feed_status()[0] == "red"
    finally:
        prov2.stop_streaming()


def test_window_recentres_only_past_hysteresis():
    paint = {"SPY US Equity": {"LAST_PRICE": str(SPOT * (1.0 + 0.5 * RECENTER_PCT))}}
    session = FakeSession(paint=paint)
    prov, blp = _make_provider(session)
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        assert _wait(lambda: prov._book_spot("SPY", wait=0.0) is not None)
        prov.option_tickers("SPY", [_near_expiry()])
        assert prov._stream_center["SPY"] == SPOT  # within hysteresis: centre held
        prov._book.apply([_paint("SPY US Equity", LAST_PRICE=str(SPOT * (1.0 + 2 * RECENTER_PCT)))])
        prov.option_tickers("SPY", [_near_expiry()])
        assert prov._stream_center["SPY"] == SPOT * (1.0 + 2 * RECENTER_PCT)  # re-centred, no bdp
        assert blp.bdp_calls == [["SPY US Equity"]]
    finally:
        prov.stop_streaming()


def test_app_state_sync_streaming_drives_bloomberg():
    """AppState's provider-agnostic streaming hook opens the Bloomberg book for the
    active source (autoStream default ON) and tears it down when unwanted."""
    from volfit.api.state import AppState

    session = FakeSession(paint={"SPY US Equity": {"LAST_PRICE": "100"}})
    prov, _ = _make_provider(session)
    state = AppState(TODAY, providers={"bloomberg": prov}, active_source="bloomberg")
    state.sync_streaming()
    assert prov.is_streaming()
    assert _wait(lambda: session.subscribed) and session.subscribed[0][0][0] == "SPY US Equity"
    state.sync_streaming()  # unchanged universe -> no restart
    assert len(session.subscribed) == 1 or len(session.subscribed) == 2
    state.set_options(state.options().model_copy(update={"autoStream": False, "spotMode": "static"}))
    state.sync_streaming()
    assert not prov.is_streaming()

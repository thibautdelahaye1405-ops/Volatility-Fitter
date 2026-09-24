"""Book first (volfit.data.bloomberg_live ``_chain_from_book_first``): while
the ``//blp/mktdata`` book streams, a live fetch waits for the paint and the
selection's coverage before it even considers the metered fallback, never
falls back with ``book_only``, and a paint clears a stale refusal from the
light. Offline over the FakeSession / FakeBlp of tests/test_bloomberg_stream.py.
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest

from tests.test_bloomberg_stream import (
    DESCRIPTORS,
    TODAY,
    FakeBlp,
    FakeSession,
    _make_provider,
    _near_expiry,
    _opt_chain_frame,
    _wait,
)
from volfit.data.bloomberg import BloombergProvider


def _painted_session():
    paint = {"SPY US Equity": {"BID": "100.0", "ASK": "100.2", "LAST_PRICE": "100.1"}}
    for d in DESCRIPTORS:
        paint[d] = {"BID": "1.0", "ASK": "1.2"}
    return FakeSession(paint=paint)


def test_fetch_waits_for_the_selections_coverage_instead_of_a_metered_pull():
    """A selection edit is resubscribed by the scheduler within a tick: the fetch
    that arrives first waits for it (book first) and is served from the book."""
    session = _painted_session()
    prov, blp = _make_provider(session, book_first_wait=3.0)
    near, far = _near_expiry(), TODAY + timedelta(days=120)
    prov.start_streaming(prov.option_tickers("SPY", [near]))
    try:
        assert _wait(lambda: prov._book is not None and prov._book.started() == 11)
        n = len(blp.bdp_calls)
        threading.Timer(0.25, lambda: prov.update_streaming(prov.option_tickers("SPY", [near, far]))).start()
        t0 = time.monotonic()
        snap = prov.fetch_chain("SPY", [near, far])  # far is not covered yet
        elapsed = time.monotonic() - t0
        assert len(blp.bdp_calls) == n  # NO metered pull: the book served it once covered
        assert {q.expiry for q in snap.quotes} == {near, far}
        assert 0.2 <= elapsed < 3.0
        assert "hits today" in prov.feed_status()[1]  # the listing + centre hits ride on the light
    finally:
        prov.stop_streaming()


def test_the_wait_is_bounded_and_then_the_metered_pull_completes_the_chain():
    session = _painted_session()
    prov, blp = _make_provider(session, book_first_wait=0.3)
    near, far = _near_expiry(), TODAY + timedelta(days=120)
    prov.start_streaming(prov.option_tickers("SPY", [near]))
    try:
        assert _wait(lambda: prov._book is not None and prov._book.started() == 11)
        n = len(blp.bdp_calls)
        t0 = time.monotonic()
        snap = prov.fetch_chain("SPY", [near, far])
        assert 0.3 <= time.monotonic() - t0 < 2.0
        assert len(blp.bdp_calls) == n + 2 and {q.expiry for q in snap.quotes} == {near, far}
    finally:
        prov.stop_streaming()


def test_book_only_never_falls_back_to_a_metered_pull():
    session = _painted_session()
    prov, blp = _make_provider(session, book_only=True, book_first_wait=0.2)
    near, far = _near_expiry(), TODAY + timedelta(days=120)
    prov.start_streaming(prov.option_tickers("SPY", [near]))
    try:
        assert _wait(lambda: prov._book is not None and prov._book.started() == 11)
        n = len(blp.bdp_calls)
        assert len(prov.fetch_chain("SPY", [near]).quotes) == 10  # covered: served from the book
        with pytest.raises(ValueError, match="book_only"):
            prov.fetch_chain("SPY", [near, far])  # uncovered: refused, never a bdp
        assert len(blp.bdp_calls) == n
        assert prov.feed_status()[0] != "red"  # not a feed refusal
    finally:
        prov.stop_streaming()
    prov.fetch_chain("SPY", [near])  # off stream the reference path is the only path
    assert len(blp.bdp_calls) > n


def test_a_refused_underlying_does_not_hold_the_fetch_for_the_whole_wait():
    session = FakeSession(fail={"SPY US Equity": "NOT_ENTITLED"})
    prov, _ = _make_provider(session, book_first_wait=5.0)
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        assert _wait(lambda: prov._book is not None and "SPY US Equity" in prov._book.failures())
        t0 = time.monotonic()
        assert prov.fetch_chain("SPY", [_near_expiry()]).spot == 100.0  # reference fallback at once
        assert time.monotonic() - t0 < 2.0
    finally:
        prov.stop_streaming()


def test_a_subscription_paint_clears_a_stale_reference_refusal():
    """The light showed 'workflow review needed' all morning while the book
    streamed: any answered request — a paint included — clears the refusal."""
    session = _painted_session()
    prov, _ = _make_provider(session)
    prov._last_error = "workflow review needed"
    prov.start_streaming(prov.option_tickers("SPY", [_near_expiry()]))
    try:
        assert prov.spot("SPY") == 100.1  # off the book
        assert prov._last_error is None
    finally:
        prov.stop_streaming()
    assert prov.feed_status()[0] == "green"


def test_stream_plan_uses_the_per_expiry_window():
    """The streaming plan shrinks with the shared rule: a 2-day rung subscribes
    ~+-30 % of the ladder (the cap ranking stays nearest-the-money)."""
    two_days = TODAY + timedelta(days=2)
    mmddyy = f"{two_days.month:02d}/{two_days.day:02d}/{two_days.year % 100:02d}"
    strikes = list(range(60, 155, 5))
    descriptors = [f"SPY US {mmddyy} {cp}{k} Equity" for k in strikes for cp in ("C", "P")]
    plans = {}
    for window in ("auto", None):
        blp = FakeBlp(_opt_chain_frame(descriptors), {"SPY US Equity": {"PX_LAST": 100.0}})
        prov = BloombergProvider(["SPY"], blp_module=blp, stream_session_factory=FakeSession,
                                 strike_window=window, exchange_day=lambda: TODAY)
        plans[window] = prov.option_tickers("SPY", [two_days])
    assert len(plans[None]) == 2 * len(strikes)
    kept = sorted({float(s.split()[3][1:]) for s in plans["auto"]})
    assert kept == [k for k in strikes if 74.4 <= k <= 134.4] and len(plans["auto"]) == 24

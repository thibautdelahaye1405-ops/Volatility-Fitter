"""The metered reference path of the Bloomberg provider (volfit.data.
bloomberg_fields + the per-expiry window of volfit.data.bloomberg).

Locks, offline over the FakeBlp of tests/test_bloomberg.py:

* a live fetch requests exactly two fields (BID, ASK); the exercise style is
  ONE OPT_EXER_TYP hit per ticker per exchange day; LAST / VOLUME / OI arrive
  only with the explicit ``enrich_reference``;
* ``call_stats`` counts hits = securities x fields (a bds = one), the unique
  securities and the last fetch; the status light carries the hits;
* the "auto" strike window is the shared per-expiry rule: a 2-day rung keeps
  ~+-30 % of the ladder, a 1-year rung the wide band — and the PREPARED quotes
  (volfit.api.quotes.prepare_quotes) are byte-identical with the window on
  and off, the containment the rule was sized for.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from tests.test_bloomberg import FakeBlp, _make_provider, _opt_chain_frame
from volfit.api.quotes import prepare_quotes
from volfit.core.black import black_call
from volfit.data.bloomberg import BloombergProvider
from volfit.data.bloomberg_fields import LIVE_FIELDS, REFERENCE_FIELDS, STYLE_FIELD, MeteredBlp
from volfit.data.bloomberg_parse import session_connected
from volfit.data.forwards import ResolvedForward

TODAY = date.today()


class RecordingBlp(FakeBlp):
    """FakeBlp that keeps EVERY bdp call as (securities, fields)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls: list[tuple[list[str], list[str]]] = []

    def bdp(self, securities, fields, **kw):
        secs = [securities] if isinstance(securities, str) else list(securities)
        flds = [fields] if isinstance(fields, str) else list(fields)
        self.calls.append((secs, flds))
        return super().bdp(securities, fields, **kw)


def _recording_provider(**kwargs):
    provider, blp = _make_provider(**kwargs)
    rec = RecordingBlp(blp._chain, blp._bdp_values)
    provider._blp = rec  # swap the fake before the first request (the meter wraps it lazily)
    return provider, rec


# --------------------------------------------------------- fields + style

def test_live_fetch_requests_bid_ask_only_and_probes_the_style_once_a_day():
    day = [date(2026, 9, 24)]
    provider, blp = _recording_provider(exchange_day=lambda: day[0])
    provider.fetch_chain("SPY")
    quote_pulls = [c for c in blp.calls if len(c[0]) > 1]
    assert len(quote_pulls) == 1 and quote_pulls[0][1] == list(LIVE_FIELDS) == ["BID", "ASK"]
    style_probes = [c for c in blp.calls if c[1] == [STYLE_FIELD]]
    assert len(style_probes) == 1 and len(style_probes[0][0]) == 1  # one representative contract
    provider.fetch_chain("SPY")  # same day: the style is remembered, no second probe
    assert len([c for c in blp.calls if c[1] == [STYLE_FIELD]]) == 1
    day[0] += timedelta(days=1)  # a new exchange day re-probes once
    provider.fetch_chain("SPY")
    assert len([c for c in blp.calls if c[1] == [STYLE_FIELD]]) == 2
    assert not any(set(REFERENCE_FIELDS) & set(c[1]) for c in blp.calls)  # never LAST/VOLUME/OI


def test_style_falls_back_to_the_index_rule_when_the_probe_answers_nothing():
    provider, blp = _recording_provider()
    for sec in list(blp._bdp_values):
        blp._bdp_values[sec].pop("OPT_EXER_TYP", None)
    assert provider.fetch_chain("SPY").exercise_style == "american"  # SPY US Equity: not an index
    assert "SPY" not in provider._style_cache  # a non-answer is not cached for the day


def test_enrich_reference_fills_oi_and_volume_for_later_chains():
    provider, blp = _recording_provider()
    before = len(blp.calls)
    out = provider.enrich_reference("SPY")
    enrich = blp.calls[-1]
    assert enrich[1] == list(REFERENCE_FIELDS) and len(enrich[0]) == 3
    assert out["securities"] == 3 and out["hits"] == 9 and out["openInterest"] == 3
    assert len(blp.calls) == before + 2  # one PX_LAST (the window centre) + ONE reference pull
    near = provider.available_expiries("SPY")[0]
    by_strike = {(q.strike, q.call_put): q for q in provider.fetch_chain("SPY", [near]).quotes}
    assert by_strike[(500.0, "C")].open_interest == 340 and by_strike[(500.0, "C")].volume == 12
    assert by_strike[(500.0, "C")].last == 247.0 and by_strike[(500.0, "P")].open_interest == 5


# ------------------------------------------------------------------ meter

def test_call_stats_count_hits_unique_securities_and_the_last_fetch():
    day = [date(2026, 9, 24)]
    provider, _blp = _recording_provider(exchange_day=lambda: day[0])
    assert provider.call_stats()["hitsToday"] == 0
    assert provider.feed_status() == ("green", "real-time (Terminal)")  # no suffix before any hit
    provider.fetch_chain("SPY")
    stats = provider.call_stats()
    # listing 3 bds (OPT_CHAIN + W + Q, one security x one field each) + PX_LAST
    # + the style probe + 3 contracts x 2 fields
    assert stats["hitsToday"] == 3 + 1 + 1 + 6 and stats["callsToday"] == 6
    assert stats["uniqueSecuritiesToday"] == 4  # the underlying + 3 contracts
    assert stats["lastFetchSecurities"] == 3 and stats["lastFetchHits"] == 6
    assert stats["lastFetchWall"] is not None and stats["lastFetchWall"] >= 0.0
    assert provider.feed_status() == ("green", "real-time (Terminal) · 11 hits today")
    provider.enrich_reference("SPY")
    assert provider.call_stats()["hitsToday"] == 11 + 1 + 9
    day[0] += timedelta(days=1)  # the meter rolls with the exchange day
    assert provider.call_stats()["hitsToday"] == 0


def test_the_meter_wraps_the_module_transparently():
    provider, blp = _recording_provider()
    wrapped = provider._blp_module()
    assert isinstance(wrapped, MeteredBlp) and wrapped.is_connected() is True
    assert session_connected(wrapped) is True  # the status probe sees through the wrapper
    assert provider._blp_module() is wrapped  # wrapped once
    provider._last_error = "daily request limit reached"  # a stale refusal on the light
    assert provider.spot("SPY") == 741.75  # an answered PX_LAST clears it
    assert provider.feed_status()[0] == "green" and blp.calls[-1][1] == ["PX_LAST"]


# ------------------------------------------------- the per-expiry window

SPOT = 100.0
#: A wide listed ladder (0.1 .. 10 x spot) so BOTH rungs get windowed.
STRIKES = [float(k) for k in range(10, 1005, 5)]
TWO_DAYS = TODAY + timedelta(days=2)
ONE_YEAR = TODAY + timedelta(days=365)
#: Flat vols per rung — both under the rule's containment condition (an 80 %
#: name at 2 days, a 30 % name at a year: 4 sigma sqrt(T) <= half-width).
SIGMA = {TWO_DAYS: 0.8, ONE_YEAR: 0.3}


def _mmddyy(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}"


def _flat_smile_chain() -> tuple[list[str], dict]:
    """A European chain priced at a flat vol per rung around a zero-carry
    forward, both sides at every strike, +-1 % spread — the values a Terminal
    would answer (far strikes price at zero and read as no quote)."""
    descriptors, values = [], {"SPY US Equity": {"PX_LAST": SPOT}}
    for expiry in (TWO_DAYS, ONE_YEAR):
        t = (expiry - TODAY).days / 365.0
        for k in STRIKES:
            w = SIGMA[expiry] ** 2 * t
            call = SPOT * float(black_call(math.log(k / SPOT), w))
            put = call - (SPOT - k)
            for cp, mid in (("C", call), ("P", put)):
                desc = f"SPY US {_mmddyy(expiry)} {cp}{k:g} Equity"
                descriptors.append(desc)
                values[desc] = {"BID": f"{mid * 0.99:.6f}", "ASK": f"{mid * 1.01:.6f}", "OPT_EXER_TYP": "European"}
    return descriptors, values


def _windowed_provider(window):
    descriptors, values = _flat_smile_chain()
    blp = RecordingBlp(_opt_chain_frame(descriptors), values)
    provider = BloombergProvider(["SPY"], blp_module=blp, strike_window=window, exchange_day=lambda: TODAY)
    return provider, blp


def test_auto_window_is_per_expiry_short_rung_tight_long_rung_wide():
    provider, blp = _windowed_provider("auto")
    provider.fetch_chain("SPY", [TWO_DAYS, ONE_YEAR])
    pulled = [c for c in blp.calls if c[1] == ["BID", "ASK"]][0][0]
    strikes_2d = sorted({float(s.split()[3][1:]) for s in pulled if _mmddyy(TWO_DAYS) in s})
    strikes_1y = sorted({float(s.split()[3][1:]) for s in pulled if _mmddyy(ONE_YEAR) in s})
    # 2 days: |ln K/S| <= 4 sqrt(2/365) = 0.296 -> 74.4 .. 134.4 of a 10 .. 1000 ladder
    assert strikes_2d == [k for k in STRIKES if 74.4 <= k <= 134.4] and strikes_2d[0] == 75.0 and strikes_2d[-1] == 130.0
    assert len(strikes_2d) / len(STRIKES) < 0.1  # a few percent of spot, not 0.5-1.5 x spot
    # 1 year: 4 sqrt(1) = 4 hits the 3.0 cap (S/20 .. 20 S) — a sanity bound the
    # 10 .. 1000 ladder never reaches, so the long rung keeps EVERY strike
    assert strikes_1y == list(STRIKES) and strikes_1y[0] == 10.0 and strikes_1y[-1] == 1000.0
    # the legacy tuple and None still mean what they did
    legacy, blp2 = _windowed_provider((0.5, 1.5))
    legacy.fetch_chain("SPY", [TWO_DAYS, ONE_YEAR])
    pulled2 = [c for c in blp2.calls if c[1] == ["BID", "ASK"]][0][0]
    assert {float(s.split()[3][1:]) for s in pulled2} == {k for k in STRIKES if 50.0 <= k <= 150.0}
    whole, blp3 = _windowed_provider(None)
    whole.fetch_chain("SPY", [TWO_DAYS, ONE_YEAR])
    assert len([c for c in blp3.calls if c[1] == ["BID", "ASK"]][0][0]) == 2 * 2 * len(STRIKES)


def test_prepared_quotes_are_byte_identical_with_the_window_on_and_off():
    """The window contains the prep's Z_MAX band (volfit.data.strike_window):
    every quote a fit reads survives it, so the prepared arrays are equal."""
    on, _ = _windowed_provider("auto")
    off, _ = _windowed_provider(None)
    snap_on = on.fetch_chain("SPY", [TWO_DAYS, ONE_YEAR])
    snap_off = off.fetch_chain("SPY", [TWO_DAYS, ONE_YEAR])
    assert len(snap_on.quotes) < len(snap_off.quotes)  # the window did cut securities
    for expiry in (TWO_DAYS, ONE_YEAR):
        t = (expiry - TODAY).days / 365.0
        fwd = ResolvedForward(expiry=expiry, forward=SPOT, discount=1.0, source="manual")
        a = prepare_quotes(snap_on, expiry, fwd, t)
        b = prepare_quotes(snap_off, expiry, fwd, t)
        assert len(a.k) >= 5  # a real slice, not an empty one (5-wide strikes, tick floor)
        assert np.array_equal(a.k, b.k) and np.array_equal(a.w_mid, b.w_mid)
        assert np.array_equal(a.iv_bid, b.iv_bid) and np.array_equal(a.iv_ask, b.iv_ask)
        assert np.array_equal(a.iv_mid, b.iv_mid)


def test_window_never_windows_down_to_nothing_and_ignores_a_bad_spot():
    provider, _ = _windowed_provider("auto")
    contracts = provider._select_contracts("SPY", [TWO_DAYS])
    assert provider._window_contracts(contracts, None) == contracts
    assert provider._window_contracts(contracts, 0.0) == contracts
    assert provider._window_contracts(contracts, 1e-9) == contracts  # nothing inside -> the full set
    assert len(provider._window_contracts(contracts, SPOT)) == 24

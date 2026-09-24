"""Offline tests for the Massive provider (volfit.data.massive).

No network: an injected ``http_get`` returns canned JSON in the *exact shapes*
captured from the live Massive API (2026-06-13) — the reference-contracts list,
the option-chain snapshot (greeks/IV/day, with and without entitled
``last_quote``/spot), and the NOT_AUTHORIZED gate. The fake also exercises
``next_url`` pagination.
"""

from __future__ import annotations

from datetime import date

import pytest

from volfit.data.massive import MassiveProvider

TODAY = date.today()


def _exp(days: int) -> str:
    return date.fromordinal(TODAY.toordinal() + days).isoformat()


class FakeHttp:
    """Maps a (url, params) call to a canned JSON body; supports next_url."""

    def __init__(self, pages: dict[str, dict]):
        self.pages = pages
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url: str, params: dict | None) -> dict:
        self.calls.append((url, params))
        # Page lookup: the cursor key on next_url, else the bare path of url.
        if "cursor=" in url:
            key = url.split("cursor=")[1]
        else:
            key = url.split("massive.com")[-1].split("?")[0]
        return self.pages[key]


def _contract(strike: float, expiry_days: int, cp: str = "call") -> dict:
    return {
        "contract_type": cp,
        "exercise_style": "american",
        "expiration_date": _exp(expiry_days),
        "strike_price": strike,
        "ticker": f"O:SPY{strike:.0f}{cp[0].upper()}",
        "underlying_ticker": "SPY",
    }


# --------------------------------------------------------------- expiries

def test_available_expiries_paginates_and_filters():
    pages = {
        "/v3/reference/options/contracts": {
            "results": [_contract(500, 30), _contract(505, 30), _contract(520, 120)],
            "status": "OK",
            "next_url": "https://api.massive.com/v3/reference/options/contracts?cursor=PAGE2",
        },
        "PAGE2": {
            "results": [_contract(530, 900)],  # beyond max_days -> filtered
            "status": "OK",
        },
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    expiries = provider.available_expiries("SPY")
    assert expiries == sorted({date.fromisoformat(_exp(30)), date.fromisoformat(_exp(120))})


def test_available_expiries_cached_per_ticker():
    """The expiry ladder is static intra-session: a second call reuses the cache and
    does not re-paginate the contracts reference; refresh_contracts forces a fresh pull."""
    pages = {
        "/v3/reference/options/contracts": {
            "results": [_contract(500, 30), _contract(520, 120)],
            "status": "OK",
        }
    }
    fake = FakeHttp(pages)
    provider = MassiveProvider(["SPY"], api_key="k", http_get=fake)
    a = provider.available_expiries("SPY")
    assert a and provider.available_expiries("SPY") == a
    assert _ref_calls(fake) == 1  # second call served from cache
    provider.refresh_contracts()
    provider.available_expiries("SPY")
    assert _ref_calls(fake) == 2  # cleared -> fresh pull


# ------------------------------------------------- contract-listing cache

def _ref_calls(fake: "FakeHttp") -> int:
    return sum(1 for url, _ in fake.calls if "reference/options/contracts" in url)


def test_option_tickers_caches_contract_listing():
    """``option_tickers`` / ``_chain_from_book`` must not re-paginate the contracts
    reference on every call (the WS read + per-tick resubscribe diff hammer it).
    Since 2026-09-24 EVERY derived view — a different expiry set, the expiry
    ladder — comes off ONE listing per (underlying, exchange day): a second key
    is no second pagination; only ``refresh_contracts`` re-pulls."""
    pages = {
        "/v3/reference/options/contracts": {
            "results": [_contract(500, 30, "call"), _contract(500, 30, "put")],
            "status": "OK",
        }
    }
    fake = FakeHttp(pages)
    provider = MassiveProvider(["SPY"], api_key="k", http_get=fake)
    provider._note_spot("SPY", 500.0)  # the plan is windowed around a centre (2026-09-24)
    exps = [date.fromisoformat(_exp(30))]

    a = provider.option_tickers("SPY", exps)
    b = provider.option_tickers("SPY", exps)
    assert a == b == ["O:SPY500C", "O:SPY500P"]
    assert _ref_calls(fake) == 1  # second call served from cache

    provider.option_tickers("SPY", None)  # a different (ticker, expiry set) key
    provider.available_expiries("SPY")  # and the ladder
    assert _ref_calls(fake) == 1  # derived from the same day's listing

    provider.refresh_contracts()  # explicit invalidation re-pulls
    provider.option_tickers("SPY", exps)
    assert _ref_calls(fake) == 2


# --------------------------------------------------------------- chain

def _snap_result(strike, days, cp, *, quote=True, spot=True):
    out = {
        "details": {
            "contract_type": cp,
            "exercise_style": "american",
            "expiration_date": _exp(days),
            "strike_price": strike,
        },
        "day": {"close": 12.5, "volume": 66},
        "greeks": {"delta": 0.5, "gamma": 0.01, "theta": -0.2, "vega": 0.1},
        "implied_volatility": 0.1834,
        "open_interest": 8,
    }
    if quote:
        out["last_quote"] = {"bid": 12.3, "ask": 12.7, "midpoint": 12.5}
    if spot:
        out["underlying_asset"] = {"ticker": "SPY", "price": 741.75}
    else:
        out["underlying_asset"] = {"ticker": "SPY"}
    return out


def test_fetch_chain_full_entitlement():
    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [
                _snap_result(500, 30, "call"),
                _snap_result(500, 30, "put"),
            ],
            "status": "OK",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(30))])
    assert snap.spot == 741.75
    assert snap.exercise_style == "american"
    call = next(q for q in snap.quotes if q.call_put == "C")
    assert call.bid == 12.3 and call.ask == 12.7
    assert call.last == 12.5 and call.volume == 66 and call.open_interest == 8


def test_prev_close_chain_is_stamped_at_the_session_close():
    """A prev-close chain IS the latest completed session's close, so its stamp
    is that session's close instant — not the fetch time (which made every
    prev-close node read "≠ as-of" in the nodes pane, 2026-08-27d finding).
    Live chains keep the fetch-time stamp."""
    from datetime import datetime, timezone

    from volfit.data.expiry_time import latest_completed_session, session_close_utc
    from volfit.data.provider import AsOf

    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [_snap_result(500, 30, "call"), _snap_result(500, 30, "put")],
            "status": "OK",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    exp = [date.fromisoformat(_exp(30))]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    prev = provider.fetch_chain("SPY", exp, as_of=AsOf(mode="prev_close"))
    expected = session_close_utc(latest_completed_session(now))
    assert prev.timestamp == expected
    assert all(q.timestamp == expected for q in prev.quotes)
    assert prev.timestamp <= now  # a completed session, never the future
    live = provider.fetch_chain("SPY", exp)
    assert abs((live.timestamp - now).total_seconds()) < 60  # fetch-time stamp


def test_latest_completed_session_rolls_at_the_close():
    from datetime import datetime

    from volfit.data.expiry_time import latest_completed_session, session_close_utc

    wed = date(2026, 6, 10)  # a regular Wednesday
    close = session_close_utc(wed)  # 20:00 UTC (EDT)
    assert close.hour == 20 and close.date() == wed
    assert latest_completed_session(close) == wed  # at the close: today counts
    assert latest_completed_session(close.replace(hour=15)) == date(2026, 6, 9)  # mid-session: yesterday
    # Saturday 12:00 UTC -> Friday's session.
    assert latest_completed_session(datetime(2026, 6, 13, 12, 0)) == date(2026, 6, 12)
    # Monday pre-market (08:00 UTC = 04:00 ET) -> the previous Friday.
    assert latest_completed_session(datetime(2026, 6, 15, 8, 0)) == date(2026, 6, 12)


def test_spot_reads_underlying_without_full_chain():
    """spot() must not pull the whole chain (the base default does, ~20-30 s on a big
    name): with expiries given it hits ONLY the nearest expiry's snapshot, reads
    underlying_asset.price, and never enumerates the contracts reference."""
    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [_snap_result(500, 30, "call"), _snap_result(500, 30, "put")],
            "status": "OK",
        }
    }
    fake = FakeHttp(pages)
    provider = MassiveProvider(["SPY"], api_key="k", http_get=fake)
    s = provider.spot("SPY", [date.fromisoformat(_exp(30)), date.fromisoformat(_exp(60))])
    assert s == 741.75
    assert _ref_calls(fake) == 0  # expiries supplied -> no contracts-reference pull
    snap_calls = [u for u, _ in fake.calls if "snapshot/options" in u]
    assert len(snap_calls) == 1  # nearest expiry only, not every expiry


def test_snapshot_results_concurrent_multi_expiry_preserves_order():
    """Multiple selected expiries paginate CONCURRENTLY; the results come back complete
    and concatenated in sorted-expiry order regardless of which thread finishes first."""
    e1, e2 = _exp(30), _exp(60)

    def http_get(url, params):  # param-aware: each expiry returns its own contract
        exp = (params or {}).get("expiration_date")
        days = {e1: 30, e2: 60}.get(exp)
        if days is None:
            return {"results": [], "status": "OK"}
        return {"results": [_snap_result(500 + days, days, "call")], "status": "OK"}

    provider = MassiveProvider(["SPY"], api_key="k", http_get=http_get)
    # pass the expiries UNSORTED; the output must still be sorted-expiry order
    results = provider._snapshot_results(
        "SPY", [date.fromisoformat(e2), date.fromisoformat(e1)]
    )
    assert [r["details"]["expiration_date"] for r in results] == [e1, e2]


def test_fetch_chain_without_spot_raises_upgrade():
    # Snapshot lacks last_quote + underlying price (the current key's tier);
    # the stock-snapshot fallback answers NOT_AUTHORIZED.
    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [_snap_result(500, 30, "call", quote=False, spot=False)],
            "status": "OK",
        },
        "/v2/snapshot/locale/us/markets/stocks/tickers/SPY": {
            "status": "NOT_AUTHORIZED",
            "message": "You are not entitled to this data. Please upgrade your plan.",
        },
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    with pytest.raises(RuntimeError, match="upgrade"):
        provider.fetch_chain("SPY", [date.fromisoformat(_exp(30))])


def test_iv_fallback_synthesizes_fittable_chain():
    """NBBO gated but the snapshot still carries IV + underlying price: the chain
    is synthesized from the IVs as zero-spread European quotes that re-invert to
    exactly Massive's reported IV (the base-tier 'fit from IVs' path)."""
    import math

    from volfit.core.black import implied_vol

    iv = 0.1834
    days = 30
    call = _snap_result(800, days, "call", quote=False, spot=True)  # OTM -> clean inversion
    put = _snap_result(700, days, "put", quote=False, spot=True)
    call["implied_volatility"] = put["implied_volatility"] = iv
    pages = {"/v3/snapshot/options/SPY": {"results": [call, put], "status": "OK"}}
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))

    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(days))])
    assert snap.spot == 741.75
    assert snap.exercise_style == "european"  # priced from Black, no de-Am
    assert snap.zero_carry  # parity carries no information: F = spot, D = 1
    c = next(q for q in snap.quotes if q.call_put == "C")
    assert c.bid == c.ask and c.bid > 0  # zero-spread synthetic quote
    # Re-invert the OTM call price -> recovers Massive's IV.
    t = days / 365.0
    k = math.log(800 / 741.75)
    recovered = float(implied_vol(k, c.bid / 741.75, t))
    assert recovered == pytest.approx(iv, abs=1e-4)


def test_iv_fallback_off_keeps_empty_quotes():
    """With iv_fallback disabled, a gated chain returns untwo-sided quotes (the
    old behaviour) rather than synthesizing from IV."""
    res = _snap_result(800, 30, "call", quote=False, spot=True)
    pages = {"/v3/snapshot/options/SPY": {"results": [res], "status": "OK"}}
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages), iv_fallback=False)
    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(30))])
    assert snap.exercise_style == "american"
    assert snap.quotes[0].bid is None and snap.quotes[0].ask is None


def test_spot_from_parity_without_underlying_price():
    """NBBO entitled but the option snapshot carries no underlying price (an
    options-only plan): spot is derived from put-call parity on the chain, NOT the
    separate stocks-snapshot endpoint (so 'Options Advanced' works without it)."""
    days = 30
    # forward = 100 (zero carry): C − P = F − K at each strike. Zero-spread quotes.
    book = {95: (7.0, 2.0), 100: (4.0, 4.0), 105: (2.0, 7.0)}
    results = []
    for strike, (c, p) in book.items():
        for cp, mid in (("call", c), ("put", p)):
            results.append({
                "details": {"contract_type": cp, "exercise_style": "american",
                            "expiration_date": _exp(days), "strike_price": strike},
                "day": {"close": mid}, "open_interest": 1,
                "last_quote": {"bid": mid, "ask": mid},
                "underlying_asset": {"ticker": "SPY"},  # NO price
            })
    pages = {"/v3/snapshot/options/SPY": {"results": results, "status": "OK"}}
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(days))])
    assert snap.spot == pytest.approx(100.0, abs=1e-6)  # parity forward, no stocks call
    assert all(q.bid is not None for q in snap.quotes)


def test_fetch_chain_live_serves_from_ws_book():
    """When a live book is attached, fetch_chain(live) builds the chain from the
    streamed NBBO (no REST snapshot) and implies spot from parity."""
    from volfit.data.massive_ws import LiveBook

    days = 30
    book_prices = {95: (7.0, 2.0), 100: (4.0, 4.0), 105: (2.0, 7.0)}  # forward 100
    contracts = []
    for strike in book_prices:
        for cp in ("call", "put"):
            contracts.append({
                "ticker": f"O:SPY{strike}{cp[0].upper()}", "contract_type": cp,
                "exercise_style": "american", "expiration_date": _exp(days),
                "strike_price": strike, "underlying_ticker": "SPY",
            })
    pages = {"/v3/reference/options/contracts": {"results": contracts, "status": "OK"}}
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))

    book = LiveBook()
    for strike, (c, p) in book_prices.items():
        book.apply([
            {"ev": "Q", "sym": f"O:SPY{strike}C", "bp": c, "ap": c + 0.2, "t": 1},
            {"ev": "Q", "sym": f"O:SPY{strike}P", "bp": p, "ap": p + 0.2, "t": 1},
        ])
    provider._live_book = book  # what start_streaming() installs

    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(days))])
    assert snap.spot == pytest.approx(100.0, abs=0.2)  # parity forward from the book
    call100 = next(q for q in snap.quotes if q.strike == 100 and q.call_put == "C")
    assert call100.bid == 4.0 and call100.ask == 4.2  # straight from the streamed book


def test_real_chains_carry_tick_size_but_iv_synthesized_do_not():
    """Real-price chains are stamped with the $0.01 venue tick (quote prep's
    tick-noise screen keys off it); the IV-synthesized fallback is exact Black
    prices — no price quantum, no screen."""
    days = 30
    res = _snap_result(500, days, "call", quote=True, spot=True)
    put = _snap_result(400, days, "put", quote=True, spot=True)
    pages = {"/v3/snapshot/options/SPY": {"results": [res, put], "status": "OK"}}
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(days))])
    assert snap.tick_size == 0.01

    call = _snap_result(800, days, "call", quote=False, spot=True)
    put2 = _snap_result(700, days, "put", quote=False, spot=True)
    call["implied_volatility"] = put2["implied_volatility"] = 0.19
    pages_iv = {"/v3/snapshot/options/SPY": {"results": [call, put2], "status": "OK"}}
    provider_iv = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages_iv))
    synth = provider_iv.fetch_chain("SPY", [date.fromisoformat(_exp(days))])
    assert synth.zero_carry and synth.tick_size is None


def test_book_chain_stamped_with_provider_tick_times():
    """A chain built from the WS book carries the NEWEST provider tick time,
    not the wall clock — the book retains yesterday's closing ticks across
    quiet periods, and relabelling them 'now' would hide the staleness."""
    from datetime import datetime, timezone

    from volfit.data.massive_ws import LiveBook

    days = 30
    old = datetime(2026, 7, 9, 20, 14, 0, tzinfo=timezone.utc)
    older = datetime(2026, 7, 9, 20, 13, 30, tzinfo=timezone.utc)
    book_prices = {95: (7.0, 2.0), 100: (4.0, 4.0), 105: (2.0, 7.0)}
    contracts = []
    for strike in book_prices:
        for cp in ("call", "put"):
            contracts.append({
                "ticker": f"O:SPY{strike}{cp[0].upper()}", "contract_type": cp,
                "exercise_style": "american", "expiration_date": _exp(days),
                "strike_price": strike, "underlying_ticker": "SPY",
            })
    pages = {"/v3/reference/options/contracts": {"results": contracts, "status": "OK"}}
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))

    book = LiveBook()
    for i, (strike, (c, p)) in enumerate(book_prices.items()):
        ts = old if i == 0 else older
        ns = int(ts.timestamp() * 1e9)
        book.apply([
            {"ev": "Q", "sym": f"O:SPY{strike}C", "bp": c, "ap": c + 0.2, "t": ns},
            {"ev": "Q", "sym": f"O:SPY{strike}P", "bp": p, "ap": p + 0.2, "t": ns},
        ])
    provider._live_book = book

    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(days))])
    assert snap.timestamp == old.replace(tzinfo=None)  # newest tick, UTC-naive
    assert snap.tick_size == 0.01
    stamped = [q.timestamp for q in snap.quotes if q.bid is not None]
    assert set(stamped) <= {old.replace(tzinfo=None), older.replace(tzinfo=None)}


def test_ws_url_derives_from_host():
    p = MassiveProvider(["SPY"], api_key="k")
    assert p._ws_url() == "wss://socket.massive.com/options"
    p2 = MassiveProvider(["SPY"], api_key="k", base_url="https://api.polygon.io")
    assert p2._ws_url() == "wss://socket.polygon.io/options"


def test_ws_urls_candidate_list_and_override():
    # Default: derived real-time cluster, with the delayed cluster auto-appended.
    p = MassiveProvider(["SPY"], api_key="k")
    assert p._ws_urls() == [
        "wss://socket.massive.com/options",
        "wss://delayed.polygon.io/options",
    ]
    # Explicit override becomes the primary; the delayed fallback still follows.
    p2 = MassiveProvider(["SPY"], api_key="k", ws_url="wss://delayed.polygon.io/options")
    assert p2._ws_urls() == ["wss://delayed.polygon.io/options"]  # dedup, no dup fallback


# ---------------------------------------- flat-file history (Tier 2) wiring

def _flat_store_fixture(tmp_path):
    """A FlatFileStore over a local gzip CSV fixture (no S3) — SPY front-expiry
    closes implying spot 500 by parity."""
    import gzip

    pytest.importorskip("duckdb")  # the store reads via duckdb (optional dep)
    from volfit.data.flatfiles import FlatFileStore, _to_ns

    ts = date(2026, 6, 12)
    ns = _to_ns(__import__("datetime").datetime(2026, 6, 12, 19, 55))
    rows = [
        ("O:SPY260616C00490000", 15, ns), ("O:SPY260616P00490000", 5, ns),
        ("O:SPY260616C00500000", 8, ns), ("O:SPY260616P00500000", 8, ns),
        ("O:SPY260616C00510000", 4, ns), ("O:SPY260616P00510000", 14, ns),
    ]
    path = tmp_path / f"{ts:%Y-%m-%d}.csv.gz"
    with gzip.open(path, "wt", newline="") as fh:
        fh.write("ticker,volume,open,close,high,low,window_start,transactions\n")
        for tk, close, w in rows:
            fh.write(f"{tk},10,{close},{close},{close},{close},{w},3\n")
    return FlatFileStore(source_uri=lambda day, freq: str(path))


def test_flat_store_adds_eod_and_history(tmp_path):
    p = MassiveProvider(["SPY"], api_key="k", flat_store=_flat_store_fixture(tmp_path))
    assert "eod" in p.historical_modes()  # flat store advertises per-day closes
    hist = p.available_history("SPY")
    assert len(hist) == 20 and all(d.weekday() < 5 for d in hist)  # weekdays, newest last
    assert hist == sorted(hist)
    # Without a store OR a key (the NBBO / aggregate history), eod is not offered.
    assert "eod" not in MassiveProvider(["SPY"], api_key="").historical_modes()


def test_fetch_chain_eod_uses_flat_day_aggs(tmp_path):
    """The flat-file MARKS path, pinned by the off switch (with the switch on the
    per-contract NBBO history is tried first — tests/test_massive_nbbo_history.py)."""
    from volfit.data.provider import AsOf

    p = MassiveProvider(["SPY"], api_key="k", flat_store=_flat_store_fixture(tmp_path), hist_nbbo=False)
    chain = p.fetch_chain("SPY", [date(2026, 6, 16)], as_of=AsOf(mode="eod", on=date(2026, 6, 12)))
    assert chain.spot == pytest.approx(500.0, abs=1e-6)
    assert len(chain.quotes) == 6 and chain.exercise_style == "american"
    c500 = next(q for q in chain.quotes if q.strike == 500.0 and q.call_put == "C")
    assert c500.bid == c500.ask == 8.0  # zero-spread close


def test_fetch_chain_past_intraday_uses_flat_minute_aggs(tmp_path):
    from datetime import datetime

    from volfit.data.provider import AsOf

    p = MassiveProvider(["SPY"], api_key="k", flat_store=_flat_store_fixture(tmp_path), hist_nbbo=False)
    # A past instant routes to the flat store (no REST /v3/quotes needed).
    chain = p.fetch_chain("SPY", None, as_of=AsOf(mode="intraday", ts=datetime(2026, 6, 12, 19, 55)))
    assert chain.spot == pytest.approx(500.0, abs=1e-6) and len(chain.quotes) == 6


def test_intraday_full_chain_is_served_by_the_concurrent_nbbo_history():
    """A past-instant chain of 100+ contracts used to fast-fail toward the
    flat-file store (one sequential REST per contract hung the app); it is now
    the concurrent per-contract NBBO history (volfit.data.massive_history —
    the full contract is in tests/test_massive_nbbo_history.py)."""
    from datetime import datetime

    from volfit.data.provider import AsOf

    quote_calls = {"n": 0}

    def http_get(url, params):
        if "/reference/options/contracts" in url:
            results = [
                {"ticker": f"O:SPY260918C{i * 1000:08d}", "expiration_date": "2026-09-18",
                 "strike_price": float(i), "contract_type": "call",
                 "exercise_style": "american"}
                for i in range(450, 550)  # 100 contracts, more than the old cap of 40
            ]
            return {"results": results, "status": "OK"}
        if "/v3/quotes/O:" in url:
            quote_calls["n"] += 1
            return {"results": [{"bid_price": 1.0, "ask_price": 1.2}], "status": "OK"}
        if url.endswith("/v3/quotes/SPY"):
            return {"results": [{"bid_price": 499.5, "ask_price": 500.5}], "status": "OK"}
        raise AssertionError(f"unexpected url {url}")

    p = MassiveProvider(["SPY"], api_key="k", http_get=http_get)  # no flat_store
    chain = p.fetch_chain("SPY", [date(2026, 9, 18)],
                          as_of=AsOf(mode="intraday", ts=datetime(2026, 6, 12, 19, 45)))
    assert quote_calls["n"] == 100 and len(chain.quotes) == 100
    assert chain.quote_kind == "quotes" and chain.spot == 500.0


# ------------------------------------------- Tier 3: aggregate reconstruction

def _aggs_http(target_ms):
    """http_get over the contracts reference + /v2/aggs minute bars. Each contract
    has a stale prior bar (close 99) and the real bar AT target_ms, so at-or-before
    selection is exercised. SPY stock aggs give the historical spot (500)."""
    closes = {  # SPY 490/500/510 C/P -> parity spot 500 (C-P = 500-K)
        "O:SPY260616C00490000": 15.0, "O:SPY260616P00490000": 5.0,
        "O:SPY260616C00500000": 8.0, "O:SPY260616P00500000": 8.0,
        "O:SPY260616C00510000": 4.0, "O:SPY260616P00510000": 14.0,
    }

    def http_get(url, params):
        if "/reference/options/contracts" in url:
            results = [
                {"ticker": tk, "expiration_date": "2026-06-16",
                 "strike_price": float(tk[-8:]) / 1000.0,
                 "contract_type": "call" if tk[-9] == "C" else "put",
                 "exercise_style": "american"}
                for tk in closes
            ]
            return {"status": "OK", "results": results}
        if "/v2/aggs/ticker/" in url:
            sym = url.split("/v2/aggs/ticker/")[1].split("/range")[0]
            if sym == "SPY":
                return {"status": "OK", "results": [
                    {"t": target_ms - 60000, "c": 499.0, "v": 1},
                    {"t": target_ms, "c": 500.0, "v": 2}]}
            c = closes.get(sym)
            if c is None:
                return {"status": "OK", "results": []}
            return {"status": "OK", "results": [
                {"t": target_ms - 60000, "c": 99.0, "v": 1},  # stale prior bar
                {"t": target_ms, "c": c, "v": 5}]}
        raise AssertionError(f"unexpected url {url}")

    return http_get


def test_fetch_agg_chain_reconstructs_from_minute_aggregates():
    from datetime import datetime

    ts = datetime(2026, 6, 15, 19, 55)
    target_ms = int(ts.replace(tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000)
    p = MassiveProvider(["SPY"], api_key="k", http_get=_aggs_http(target_ms))
    chain = p._fetch_agg_chain("SPY", [date(2026, 6, 16)], ts)
    assert chain.spot == pytest.approx(500.0)  # underlying minute-agg close
    assert len(chain.quotes) == 6 and chain.exercise_style == "american"
    c500 = next(q for q in chain.quotes if q.strike == 500.0 and q.call_put == "C")
    assert c500.bid == c500.ask == 8.0  # the target-minute close, not the stale 99


def test_today_intraday_serves_live_snapshot():
    """TODAY's intraday isn't bulk-reconstructable via REST, so it serves the live
    snapshot (the 'now / pre-connect' chain), NOT a per-contract aggregate crawl."""
    from datetime import datetime, time

    from volfit.data.provider import AsOf

    def http_get(url, params):
        if "/v3/snapshot/options/" in url:
            return {"status": "OK", "results": [
                _snap_result(740, 30, "call"), _snap_result(740, 30, "put"),
                _snap_result(745, 30, "call"), _snap_result(745, 30, "put")]}
        if "/v2/aggs/ticker/" in url:
            raise AssertionError("today-intraday must not crawl per-contract aggregates")
        return {"status": "OK", "results": []}

    p = MassiveProvider(["SPY"], api_key="k", http_get=http_get)
    ts = datetime.combine(date.today(), time(15, 0))  # TODAY
    chain = p.fetch_chain("SPY", None, as_of=AsOf(mode="intraday", ts=ts))
    assert chain.spot == 741.75 and chain.quotes  # from the live snapshot


def test_historical_aggregate_single_contract():
    from datetime import datetime, timezone

    ts = datetime(2026, 6, 15, 19, 55)
    target_ms = int(ts.replace(tzinfo=timezone.utc).timestamp() * 1000)
    p = MassiveProvider(["SPY"], api_key="k", http_get=_aggs_http(target_ms))
    bar = p.historical_aggregate("O:SPY260616C00500000", ts)
    assert bar is not None and bar["c"] == 8.0  # at-or-before target


def test_paginate_raises_on_not_authorized():
    pages = {
        "/v3/snapshot/options/SPY": {
            "status": "NOT_AUTHORIZED",
            "message": "You are not entitled to this data.",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    with pytest.raises(RuntimeError, match="Massive"):
        provider.fetch_chain("SPY", [date.fromisoformat(_exp(30))])


# --------------------------------------------------------------- IV overlay

def test_iv_surface():
    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [_snap_result(500, 30, "call", quote=False, spot=False)],
            "status": "OK",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    rows = provider.iv_surface("SPY", [date.fromisoformat(_exp(30))])
    assert len(rows) == 1
    row = rows[0]
    assert row["iv"] == pytest.approx(0.1834)
    assert row["callPut"] == "C" and row["strike"] == 500.0
    assert row["delta"] == 0.5 and row["openInterest"] == 8


# --------------------------------------------------------------- search

def test_search_symbols_uses_reference_tickers():
    pages = {
        "/v3/reference/tickers": {
            "results": [
                {"ticker": "SPY", "name": "SPDR S&P 500", "type": "ETF",
                 "primary_exchange": "ARCX"},
            ],
            "status": "OK",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    matches = provider.search_symbols("spdr")
    assert matches[0].symbol == "SPY"
    assert matches[0].name == "SPDR S&P 500" and matches[0].type == "ETF"


def test_search_symbols_falls_back_on_failure():
    def boom(url, params):
        raise RuntimeError("network down")

    provider = MassiveProvider(["SPY"], api_key="k", http_get=boom)
    # Base echo search still resolves a plausible bare symbol.
    assert any(m.symbol == "SPY" for m in provider.search_symbols("SPY"))


# ------------------------------------------------------ index roots (SPX)

def test_index_root_lists_contracts_by_bare_root_and_snapshots_by_i_prefix():
    """SPX on Massive (live-verified 2026-09-23): the contracts reference keys
    an index by its BARE root (``underlying_ticker=I:SPX`` answers 0 rows, so
    the old spelling left ``available_expiries`` empty and Add/stream/history
    all failed), while the snapshot and aggregate endpoints take the ``I:``
    spelling. Both the listing and the status probe must use the bare root on
    the reference and keep ``I:SPX`` on the snapshot."""
    spx_contract = dict(_contract(5000, 30), ticker="O:SPX5000C", underlying_ticker="SPX")
    pages = {
        "/v3/reference/options/contracts": {"results": [spx_contract], "status": "OK"},
        "/v3/snapshot/options/I:SPX": {
            "results": [_snap_result(500, 30, "call"), _snap_result(500, 30, "put")],
            "status": "OK",
        },
    }
    fake = FakeHttp(pages)
    provider = MassiveProvider(["SPX"], api_key="k", http_get=fake)

    assert provider.available_expiries("SPX") == [date.fromisoformat(_exp(30))]
    ref_calls = [p for u, p in fake.calls if "reference/options/contracts" in u]
    assert ref_calls and all(p["underlying_ticker"] == "SPX" for p in ref_calls)

    snap = provider.fetch_chain("SPX", [date.fromisoformat(_exp(30))])
    assert len(snap.quotes) == 2
    assert any(u.endswith("/v3/snapshot/options/I:SPX") for u, _ in fake.calls)
    assert not any("/v3/snapshot/options/SPX" in u for u, _ in fake.calls)

    fake.calls.clear()
    colour, _detail = provider.feed_status()
    assert colour != "red"
    ref_probe = [p for u, p in fake.calls if "reference/options/contracts" in u]
    assert ref_probe and ref_probe[0]["underlying_ticker"] == "SPX"
    assert any(u.endswith("/v3/snapshot/options/I:SPX") for u, _ in fake.calls)


# ------------------------------------- the snapshot request plan (2026-09-24)

class _WindowApi:
    """A snapshot API honouring ``expiration_date`` / ``.gte`` / ``.lte`` and
    ``strike_price.gte/.lte``, 250 rows a page via ``next_url`` cursors,
    thread-safe (two streams run at once). Records every request's params."""

    def __init__(self, rows, page: int = 250):
        import threading

        self.rows, self.page = rows, page
        self.calls: list[tuple[str, dict]] = []
        self._cursors: dict[str, tuple[list, int]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _match(r: dict, p: dict) -> bool:
        exp, k = r["details"]["expiration_date"], r["details"]["strike_price"]
        if "expiration_date" in p and exp != p["expiration_date"]:
            return False
        if "expiration_date.gte" in p and exp < p["expiration_date.gte"]:
            return False
        if "expiration_date.lte" in p and exp > p["expiration_date.lte"]:
            return False
        if "strike_price.gte" in p and k < p["strike_price.gte"]:
            return False
        if "strike_price.lte" in p and k > p["strike_price.lte"]:
            return False
        return True

    def __call__(self, url, params):
        p = dict(params or {})
        with self._lock:
            self.calls.append((url, p))
            if "cursor=" in url:
                rows, offset = self._cursors[url.split("cursor=")[1]]
            else:
                assert "/v3/snapshot/options/SPY" in url, url
                rows, offset = [r for r in self.rows if self._match(r, p)], 0
            body = {"results": rows[offset:offset + self.page], "status": "OK"}
            if offset + self.page < len(rows):
                cid = f"C{len(self._cursors)}"
                self._cursors[cid] = (rows, offset + self.page)
                body["next_url"] = f"https://api.massive.com/v3/snapshot/options/SPY?cursor={cid}"
            return body


def _window_rows(spot: float = 500.0, vol: float = 0.25, days=(7, 30, 200)) -> list[dict]:
    """A European chain priced flat at ``vol`` with F = spot, D = 1 (exact
    parity), 441 strikes from S*e^-2.2 to S*e^2.2 (882 rows an expiry: 4
    pages of 250) -- far past any window."""
    import math

    import numpy as np

    from volfit.core.black import black_call

    rows = []
    for d in days:
        t = d / 365.0
        for k in np.arange(-2.2, 2.2001, 0.01):
            strike = round(spot * math.exp(float(k)), 2)
            call = spot * float(black_call(math.log(strike / spot), vol * vol * t))
            for cp, px in (("call", call), ("put", call - (spot - strike))):
                rows.append({
                    "details": {"contract_type": cp, "exercise_style": "european",
                                "expiration_date": _exp(d), "strike_price": strike},
                    "last_quote": {"bid": px * 0.99, "ask": px * 1.01},
                    "day": {"close": px, "volume": 1}, "open_interest": 1,
                    "underlying_asset": {"ticker": "SPY", "price": spot},
                })
    return rows


def test_strike_window_leaves_the_prepared_quotes_byte_identical_and_cuts_the_pages():
    """The plan (volfit.data.massive_snapshot): the nearest selected expiry is
    fetched FIRST and unwindowed (it yields the spot); the rest carry
    ``strike_price.gte/lte`` from the shared window rule -- a window that
    contains the prep's Z_MAX band, so the PREPARED quotes are byte-identical
    with the window on or off while the pages (and the raw quotes) shrink.
    ``window_vol=None`` sends no strike filter at all."""
    import numpy as np

    from volfit.api.quotes import prepare_quotes
    from volfit.data.forwards import ImpliedForward, implied_forward
    from volfit.data.strike_window import strike_bounds

    rows = _window_rows()
    exps = [date.fromisoformat(_exp(d)) for d in (7, 30, 200)]
    api_u, api_w = _WindowApi(rows), _WindowApi(rows)
    plain = MassiveProvider(["SPY"], api_key="k", http_get=api_u, window_vol=None)
    windowed = MassiveProvider(["SPY"], api_key="k", http_get=api_w)
    cu, cw = plain.fetch_chain("SPY", exps), windowed.fetch_chain("SPY", exps)
    assert cu.spot == cw.spot == 500.0 and windowed.last_spot("SPY") == 500.0
    assert len(cw.quotes) < len(cu.quotes)  # the wings past the window were never requested
    assert len(api_w.calls) < len(api_u.calls)  # fewer pages
    for e in exps:
        t = (e - TODAY).days / 365.0
        fwd = ImpliedForward(expiry=e, forward=500.0, discount=1.0, n_strikes=0, residual_rms=0.0)
        pu, pw = prepare_quotes(cu, e, fwd, t), prepare_quotes(cw, e, fwd, t)
        assert pu.k.size > 10
        for name in ("k", "w_mid", "iv_bid", "iv_mid", "iv_ask"):
            assert np.array_equal(getattr(pu, name), getattr(pw, name)), (e, name)
        assert (pu.forward, pu.discount, pu.t, pu.tick_size) == (pw.forward, pw.discount, pw.t, pw.tick_size)
        fu, fw = implied_forward(cu, e), implied_forward(cw, e)  # the parity regressions agree too
        assert abs(fu.forward - fw.forward) < 1e-6 and abs(fu.discount - fw.discount) < 1e-9
    firsts = {p["expiration_date"]: p for u, p in api_w.calls if "cursor=" not in u}
    assert api_w.calls[0][1]["expiration_date"] == exps[0].isoformat()  # the nearest expiry FIRST
    assert "strike_price.gte" not in firsts[exps[0].isoformat()]  # and unwindowed
    for e in exps[1:]:
        lo, hi = strike_bounds(500.0, e, TODAY)
        p = firsts[e.isoformat()]
        assert p["strike_price.gte"] == pytest.approx(lo, abs=1e-4) and p["strike_price.gte"] <= lo
        assert p["strike_price.lte"] == pytest.approx(hi, abs=1e-4) and p["strike_price.lte"] >= hi
    assert not any("strike_price.gte" in p or "strike_price.lte" in p for _, p in api_u.calls)


def test_whole_horizon_is_two_date_shards_windowed_once_a_spot_is_known():
    """No selection: two ``expiration_date.gte/lte`` shards (the horizon split
    at its midpoint), unwindowed until a spot is known, then windowed at each
    shard's last expiry; ``horizon_shards=1`` + ``window_vol=None`` = the one
    pre-2026-09-24 request."""
    from datetime import timedelta

    rows = _window_rows(days=(7, 30, 200, 700))
    end, mid = TODAY + timedelta(days=730), TODAY + timedelta(days=365)
    api = _WindowApi(rows)
    p = MassiveProvider(["SPY"], api_key="k", http_get=api, max_days=730)
    chain = p.fetch_chain("SPY", None)
    firsts = [q for u, q in api.calls if "cursor=" not in u]
    assert firsts == [
        {"expiration_date.lte": mid.isoformat(), "limit": 250},
        {"expiration_date.gte": (mid + timedelta(days=1)).isoformat(),
         "expiration_date.lte": end.isoformat(), "limit": 250},
    ]
    keys = {(q.expiry, q.strike, q.call_put) for q in chain.quotes}
    assert len(keys) == len(rows) and chain.spot == 500.0
    legacy_api = _WindowApi(rows)
    legacy = MassiveProvider(["SPY"], api_key="k", http_get=legacy_api, max_days=730,
                             window_vol=None, horizon_shards=1)
    legacy_chain = legacy.fetch_chain("SPY", None)
    assert [q for u, q in legacy_api.calls if "cursor=" not in u] == [{"expiration_date.lte": end.isoformat(), "limit": 250}]
    assert {(q.expiry, q.strike, q.call_put) for q in legacy_chain.quotes} == keys
    api.calls.clear()
    again = p.fetch_chain("SPY", None)  # the spot is known now: the shards are windowed
    firsts = [q for u, q in api.calls if "cursor=" not in u]
    assert len(firsts) == 2 and all("strike_price.gte" in q and "strike_price.lte" in q for q in firsts)
    # At the reference vol the window sits at / near the 3.0 cap on both shards
    # (S/20 .. 20 S) — wider than this ±2.2 ladder, so nothing is dropped: the
    # filters ride the request, the chain is byte-identical.
    assert all(q["strike_price.gte"] < 30 and q["strike_price.lte"] > 9000 for q in firsts)
    assert {(q.expiry, q.strike, q.call_put) for q in again.quotes} == keys
    tight_api = _WindowApi(rows)  # a tight reference vol shows the window biting
    tight = MassiveProvider(["SPY"], api_key="k", http_get=tight_api, max_days=730, window_vol=0.3)
    tight.fetch_chain("SPY", None)
    tight_api.calls.clear()
    narrowed = tight.fetch_chain("SPY", None)
    assert len(narrowed.quotes) < len(chain.quotes)


def test_whole_horizon_shards_cut_at_the_contract_median_when_a_listing_is_at_hand():
    """The listing is front-loaded (dailies), so the date midpoint pages one
    shard four times the other (SPY live 2026-09-24: 38 + 10). With the day's
    listing in memory / on disk the cut sits at the contract-count median —
    never at the price of a pull."""
    from datetime import timedelta

    from volfit.data.massive_snapshot import horizon_shards

    rows = _window_rows(days=(7, 30, 200, 700))  # 882 rows an expiry: the median lands after the 2nd
    listing = [dict(_contract(500, d, "call"), ticker=f"O:SPY{d}") for d in (7, 30, 200, 700) for _ in range(10)]
    snapshot = _WindowApi(rows)

    def http_get(url, params):
        if "/v3/reference/options/contracts" in url:
            return {"results": listing, "status": "OK"}
        return snapshot(url, params)

    p = MassiveProvider(["SPY"], api_key="k", http_get=http_get, max_days=730)
    chain0 = p.fetch_chain("SPY", None)  # no listing yet: the date midpoint
    firsts = [q for u, q in snapshot.calls if "cursor=" not in u]
    assert firsts[0] == {"expiration_date.lte": (TODAY + timedelta(days=365)).isoformat(), "limit": 250}
    p.available_expiries("SPY")  # the listing is now in memory (one pull)
    snapshot.calls.clear()
    chain1 = p.fetch_chain("SPY", None)
    firsts = [q for u, q in snapshot.calls if "cursor=" not in u]
    assert firsts[0]["expiration_date.lte"] == _exp(30)  # 20 of 40 listed contracts by the 30-day expiry
    assert firsts[1]["expiration_date.gte"] == (TODAY + timedelta(days=31)).isoformat()
    assert {(q.expiry, q.strike) for q in chain1.quotes} <= {(q.expiry, q.strike) for q in chain0.quotes}
    # the pure function: quantile cuts, a degenerate cut at the horizon's end, no weights -> midpoints
    w = {TODAY + timedelta(days=d): n for d, n in ((7, 50), (30, 30), (200, 15), (700, 5))}
    assert horizon_shards(TODAY, 730, 2, w) == [(None, TODAY + timedelta(days=7)),
                                                 (TODAY + timedelta(days=8), TODAY + timedelta(days=730))]
    three = horizon_shards(TODAY, 730, 3, w)
    assert [s[1] for s in three] == [TODAY + timedelta(days=7), TODAY + timedelta(days=30), TODAY + timedelta(days=730)]
    assert horizon_shards(TODAY, 730, 2, {TODAY + timedelta(days=730): 100}) == [(None, TODAY + timedelta(days=365)), (TODAY + timedelta(days=366), TODAY + timedelta(days=730))]
    assert horizon_shards(TODAY, 730, 2, None) == horizon_shards(TODAY, 730, 2, {})

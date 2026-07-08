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
    reference on every call (the WS read + per-tick resubscribe diff hammer it)."""
    pages = {
        "/v3/reference/options/contracts": {
            "results": [_contract(500, 30, "call"), _contract(500, 30, "put")],
            "status": "OK",
        }
    }
    fake = FakeHttp(pages)
    provider = MassiveProvider(["SPY"], api_key="k", http_get=fake)
    exps = [date.fromisoformat(_exp(30))]

    a = provider.option_tickers("SPY", exps)
    b = provider.option_tickers("SPY", exps)
    assert a == b == ["O:SPY500C", "O:SPY500P"]
    assert _ref_calls(fake) == 1  # second call served from cache

    provider.option_tickers("SPY", None)  # a different (ticker, expiry set) key
    assert _ref_calls(fake) == 2

    provider.refresh_contracts()  # explicit invalidation re-pulls
    provider.option_tickers("SPY", exps)
    assert _ref_calls(fake) == 3


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
    # Without a store, eod is not offered.
    assert "eod" not in MassiveProvider(["SPY"], api_key="k").historical_modes()


def test_fetch_chain_eod_uses_flat_day_aggs(tmp_path):
    from volfit.data.provider import AsOf

    p = MassiveProvider(["SPY"], api_key="k", flat_store=_flat_store_fixture(tmp_path))
    chain = p.fetch_chain("SPY", [date(2026, 6, 16)], as_of=AsOf(mode="eod", on=date(2026, 6, 12)))
    assert chain.spot == pytest.approx(500.0, abs=1e-6)
    assert len(chain.quotes) == 6 and chain.exercise_style == "american"
    c500 = next(q for q in chain.quotes if q.strike == 500.0 and q.call_put == "C")
    assert c500.bid == c500.ask == 8.0  # zero-spread close


def test_fetch_chain_past_intraday_uses_flat_minute_aggs(tmp_path):
    from datetime import datetime

    from volfit.data.provider import AsOf

    p = MassiveProvider(["SPY"], api_key="k", flat_store=_flat_store_fixture(tmp_path))
    # A past instant routes to the flat store (no REST /v3/quotes needed).
    chain = p.fetch_chain("SPY", None, as_of=AsOf(mode="intraday", ts=datetime(2026, 6, 12, 19, 55)))
    assert chain.spot == pytest.approx(500.0, abs=1e-6) and len(chain.quotes) == 6


def test_intraday_full_chain_fast_fails_without_flat_store():
    """A past-instant reconstruction of a whole chain via per-contract REST must
    NOT crawl hundreds of requests (the hang) — it fast-fails toward the flat-file
    store. A small selection still uses the per-contract path (test_asof covers it)."""
    from datetime import datetime

    from volfit.data.provider import AsOf

    quote_calls = {"n": 0}

    def http_get(url, params):
        if "/reference/options/contracts" in url:
            results = [
                {"ticker": f"O:SPY260918C{i:08d}", "expiration_date": "2026-09-18",
                 "strike_price": float(i), "contract_type": "call",
                 "exercise_style": "american"}
                for i in range(100)  # 100 contracts > _INTRADAY_REST_MAX
            ]
            return {"results": results, "status": "OK"}
        if "/v3/quotes/" in url:
            quote_calls["n"] += 1
            return {"results": [{"bid_price": 1.0, "ask_price": 1.2}], "status": "OK"}
        raise AssertionError(f"unexpected url {url}")

    p = MassiveProvider(["SPY"], api_key="k", http_get=http_get)  # no flat_store
    with pytest.raises(RuntimeError, match="flat-file"):
        p.fetch_chain("SPY", [date(2026, 9, 18)],
                      as_of=AsOf(mode="intraday", ts=datetime(2026, 6, 12, 19, 45)))
    assert quote_calls["n"] == 0  # fast-failed before crawling any per-contract quote


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

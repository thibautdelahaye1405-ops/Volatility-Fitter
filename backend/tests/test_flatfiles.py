"""Flat-file history store (volfit.data.flatfiles) — offline via a local CSV.gz.

No S3: ``source_uri`` points DuckDB at a gzipped CSV fixture in the exact
flat-file shape (``ticker,...,close,...,window_start,...``), so the real duckdb
read + as-of window query + OCC reconstruction run offline.
"""

from __future__ import annotations

import gzip
from datetime import date, datetime

import pytest

from volfit.data.flatfiles import FlatFileStore, _to_ns

duckdb = pytest.importorskip("duckdb")

DAY = date(2026, 6, 12)
T2 = datetime(2026, 6, 12, 19, 55)  # 15:55 ET bar
T2_NS = _to_ns(T2)
T1_NS = T2_NS - 60_000_000_000  # the prior minute

# Front-expiry SPY closes chosen so put-call parity implies spot 500 (D=1, F=500):
#   C-P = 500-K  ->  K=490:+10  K=500:0  K=510:-10
_ROWS = [
    # ticker, volume, open, close, high, low, window_start, transactions
    ("O:SPY260616C00490000", 10, 15, 15, 16, 14, T2_NS, 3),
    ("O:SPY260616P00490000", 10, 5, 5, 6, 4, T2_NS, 3),
    ("O:SPY260616C00500000", 99, 9, 8, 9, 7, T2_NS, 3),
    ("O:SPY260616C00500000", 99, 99, 99, 99, 99, T1_NS, 1),  # stale prior bar
    ("O:SPY260616P00500000", 10, 8, 8, 9, 7, T2_NS, 3),
    ("O:SPY260616C00510000", 10, 4, 4, 5, 3, T2_NS, 3),
    ("O:SPY260616P00510000", 10, 14, 14, 15, 13, T2_NS, 3),
    ("O:QQQ260616C00400000", 10, 7, 7, 8, 6, T2_NS, 3),  # off-watchlist: excluded
    ("garbage-row", 0, 0, 0, 0, 0, T2_NS, 0),  # unparseable: skipped
]
_HEADER = "ticker,volume,open,close,high,low,window_start,transactions\n"


@pytest.fixture()
def store(tmp_path):
    path = tmp_path / "2026-06-12.csv.gz"
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(_HEADER)
        for r in _ROWS:
            fh.write(",".join(str(x) for x in r) + "\n")
    return FlatFileStore(source_uri=lambda day, freq: str(path))


def test_reconstructs_chain_at_instant(store):
    chain = store.chain_at("SPY", None, T2, underlyings=["SPY", "QQQ"])
    assert chain is not None
    assert chain.ticker == "SPY" and chain.exercise_style == "american"
    assert chain.spot == pytest.approx(500.0, abs=1e-6)  # parity forward
    # 6 SPY contracts; QQQ + garbage excluded.
    assert len(chain.quotes) == 6
    assert {q.expiry for q in chain.quotes} == {date(2026, 6, 16)}
    # The 500-strike call uses the t2 bar (close 8), not the stale t1 bar (99).
    c500 = next(q for q in chain.quotes if q.strike == 500.0 and q.call_put == "C")
    assert c500.bid == 8.0 and c500.ask == 8.0  # zero-spread close


def test_expiry_filter(store):
    none = store.chain_at("SPY", [date(2099, 1, 1)], T2, underlyings=["SPY"])
    assert none is None  # no contracts on that expiry


def test_no_bars_before_target_returns_none(store):
    early = datetime(2026, 6, 12, 0, 0)  # before any bar that day
    assert store.chain_at("SPY", None, early, underlyings=["SPY"]) is None


def test_local_parquet_cache_roundtrip(tmp_path):
    src = tmp_path / "2026-06-12.csv.gz"
    with gzip.open(src, "wt", newline="") as fh:
        fh.write(_HEADER)
        for r in _ROWS:
            fh.write(",".join(str(x) for x in r) + "\n")
    cache = tmp_path / "cache"
    store = FlatFileStore(
        cache_dir=str(cache), source_uri=lambda day, freq: str(src)
    )
    chain = store.chain_at("SPY", None, T2, underlyings=["SPY", "QQQ"])
    assert chain is not None and chain.spot == pytest.approx(500.0, abs=1e-6)
    # The day's watchlist-filtered bars were materialized to Parquet.
    cached = list(cache.glob("*.parquet"))
    assert len(cached) == 1
    # Second call serves from the Parquet cache (still correct).
    again = store.chain_at("SPY", None, T2, underlyings=["SPY", "QQQ"])
    assert again is not None and len(again.quotes) == 6


def test_available_requires_creds_or_source():
    assert FlatFileStore().available() is False
    assert FlatFileStore(access_key="k", secret="s").available() is True
    assert FlatFileStore(source_uri=lambda d, f: "x").available() is True

"""Columnar Parquet/DuckDB snapshot history (ROADMAP perf #6).

Offline: write a few snapshots to Parquet, then exercise the analytical reads
(snapshot_at / latest / list), the multi-snapshot columnar scan, idempotency,
and the SQLite -> Parquet exporter.
"""

from __future__ import annotations

from datetime import date, datetime

from volfit.data.columnar import ColumnarHistory, export_from_sqlite
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot, OptionQuote

EXPIRY = date(2024, 8, 16)


def _snap(ticker: str, ts: datetime, spot: float) -> ChainSnapshot:
    quotes = []
    for strike, cmid, pmid in [(540, 8.0, 3.0), (545, 5.0, 5.0), (550, 3.0, 8.0)]:
        quotes.append(OptionQuote(ticker, EXPIRY, strike, "C", bid=cmid - 0.1,
                                  ask=cmid + 0.1, last=None, volume=10, open_interest=5,
                                  timestamp=ts))
        quotes.append(OptionQuote(ticker, EXPIRY, strike, "P", bid=pmid - 0.1,
                                  ask=pmid + 0.1, last=None, volume=7, open_interest=3,
                                  timestamp=ts))
    return ChainSnapshot(ticker, spot, ts, quotes, "american")


T1 = datetime(2024, 8, 5, 19, 40)
T2 = datetime(2024, 8, 5, 19, 45)


def test_write_then_analytical_reads(tmp_path):
    hist = ColumnarHistory(tmp_path)
    hist.write_snapshots([_snap("SPY", T1, 545.0), _snap("SPY", T2, 546.0),
                          _snap("AAPL", T2, 207.0)])

    # list (as-of index), newest first
    assert hist.list_snapshots(["SPY"]) == [("SPY", T2), ("SPY", T1)]
    assert len(hist.list_snapshots()) == 3

    # snapshot_at: nearest at-or-before
    assert hist.snapshot_at("SPY", datetime(2024, 8, 5, 19, 42)).timestamp == T1
    assert hist.snapshot_at("SPY", datetime(2024, 8, 5, 19, 50)).timestamp == T2
    assert hist.snapshot_at("SPY", datetime(2024, 8, 5, 19, 30)) is None
    assert hist.latest_snapshot("SPY").timestamp == T2

    # round-trip fidelity
    snap = hist.snapshot_at("SPY", datetime(2024, 8, 5, 19, 42))
    assert snap.spot == 545.0
    assert snap.exercise_style == "american"
    assert len(snap.quotes) == 6
    atm_c = next(q for q in snap.quotes if q.call_put == "C" and q.strike == 545.0)
    assert atm_c.bid == 4.9 and atm_c.ask == 5.1 and atm_c.last is None
    assert atm_c.open_interest == 5


def test_columnar_scan_and_idempotency(tmp_path):
    hist = ColumnarHistory(tmp_path)
    snaps = [_snap("SPY", T1, 545.0), _snap("SPY", T2, 546.0)]
    hist.write_snapshots(snaps)
    df = hist.scan_quotes(["SPY"], datetime(2024, 8, 5, 0, 0), datetime(2024, 8, 5, 23, 0))
    assert len(df) == 12  # 2 snapshots x 6 quotes

    # Re-writing the same snapshots is idempotent (de-dup), not doubled.
    hist.write_snapshots(snaps)
    assert len(hist.list_snapshots(["SPY"])) == 2
    df2 = hist.scan_quotes(["SPY"], datetime(2024, 8, 5, 0, 0), datetime(2024, 8, 5, 23, 0))
    assert len(df2) == 12


def test_empty_history_reads(tmp_path):
    hist = ColumnarHistory(tmp_path)
    assert not hist.available()
    assert hist.list_snapshots() == []
    assert hist.snapshot_at("SPY", T2) is None
    assert hist.latest_snapshot("SPY") is None
    assert len(hist.scan_quotes(None, T1, T2)) == 0


def test_export_from_sqlite(tmp_path):
    db = tmp_path / "vol.sqlite"
    with VolStore(db) as store:
        store.save_snapshot(_snap("SPY", T1, 545.0))
        store.save_snapshot(_snap("SPY", T2, 546.0))
    root = tmp_path / "history"
    n = export_from_sqlite(db, root)
    assert n == 2
    hist = ColumnarHistory(root)
    assert hist.available()
    assert hist.latest_snapshot("SPY").spot == 546.0
    assert len(hist.list_snapshots(["SPY"])) == 2

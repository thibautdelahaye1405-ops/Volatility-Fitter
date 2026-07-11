"""Intraday 0DTE capture (R2 item 10): multi-instant flat-file reduction +
the capture_intraday campaign module — fully offline via the source_uri hook.

Contracts: (1) ``chains_at`` reconstructs per-instant NBBOs from ONE scan and
matches ``chain_at`` per instant; (2) the session time grid is ET-correct and
half-day-clipped; (3) the expiry ladder keeps dailies + capped monthlies;
(4) ``capture_day`` fixtures carry every usable instant; ``run`` is resumable;
(5) the optional VolStore path persists snapshots WITH the settlement map, so
the app's captured replay + intraday clock price them exactly.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time

import pytest

from backtest.capture_intraday import (
    DEFAULT_TIMES,
    capture_day,
    run,
    select_expiries,
    session_instants,
)
from backtest.quotes_store import QuotesFlatFileStore, _to_ns

DAY = date(2024, 8, 16)  # a regular trading Friday
DAILY = date(2024, 8, 16)  # the 0DTE expiry itself
MONTHLY = date(2024, 9, 20)  # 3rd Friday
T1 = datetime(2024, 8, 16, 14, 0, 0)  # 10:00 ET in UTC-naive (EDT = UTC-4)
T2 = datetime(2024, 8, 16, 19, 45, 0)  # 15:45 ET

HEADER = (
    "ticker,ask_exchange,ask_price,ask_size,bid_exchange,bid_price,bid_size,"
    "sequence_number,sip_timestamp"
)


def _row(sym: str, bid: float, ask: float, ns: int) -> str:
    return f"{sym},1,{ask},10,1,{bid},10,0,{ns}"


def _sym(expiry: date, cp: str, strike: float) -> str:
    return f"O:SPY{expiry:%y%m%d}{cp}{int(strike * 1000):08d}"


def _write_fixture(path) -> None:
    """Two expiries (0DTE + monthly), paired strikes, DIFFERENT books at the
    two instants: mid drops 0.50 between T1 and T2 for every contract."""
    rows = [HEADER]
    book = [(540, 8.0, 3.0), (545, 5.0, 5.0), (550, 3.0, 8.0)]
    for expiry in (DAILY, MONTHLY):
        for strike, cmid, pmid in book:
            for cp, mid in (("C", cmid), ("P", pmid)):
                sym = _sym(expiry, cp, strike)
                rows.append(_row(sym, mid - 0.1, mid + 0.1, _to_ns(T1) - 1_000_000))
                lo = max(mid - 0.5, 0.2)
                rows.append(_row(sym, lo - 0.1, lo + 0.1, _to_ns(T2) - 1_000_000))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


@pytest.fixture()
def store(tmp_path):
    csv = tmp_path / "quotes.csv"
    _write_fixture(csv)
    return QuotesFlatFileStore(source_uri=lambda _day: str(csv))


def test_chains_at_matches_chain_at_per_instant(store):
    multi = store.chains_at("SPY", None, [T1, T2])
    assert set(multi) == {T1, T2}
    for ts in (T1, T2):
        single = store.chain_at("SPY", None, ts)
        got = multi[ts]
        assert got is not None and single is not None
        assert got.spot == pytest.approx(single.spot)
        key = lambda q: (q.expiry, q.call_put, q.strike)  # noqa: E731
        assert sorted(map(key, got.quotes)) == sorted(map(key, single.quotes))
        # the T1 book is the tight pre-drop one; T2 reflects the later NBBO
    atm_t1 = next(q for q in multi[T1].quotes
                  if q.expiry == DAILY and q.call_put == "C" and q.strike == 545.0)
    atm_t2 = next(q for q in multi[T2].quotes
                  if q.expiry == DAILY and q.call_put == "C" and q.strike == 545.0)
    assert atm_t1.mid == pytest.approx(5.0)
    assert atm_t2.mid == pytest.approx(4.5)  # the book moved between instants


def test_chains_at_rejects_multi_day():
    store = QuotesFlatFileStore(source_uri=lambda _d: "unused")
    with pytest.raises(ValueError):
        store.chains_at("SPY", None, [T1, datetime(2024, 8, 19, 14, 0)])


def test_session_instants_et_and_half_day_clipping():
    instants = session_instants(DAY)
    assert len(instants) == len(DEFAULT_TIMES)
    assert instants[0] == T1  # 10:00 ET == 14:00 UTC in August (EDT)
    assert instants[-1] == T2
    # Black Friday half-day (13:00 close): only instants at or before it survive
    half = session_instants(date(2024, 11, 29))
    assert all(t.hour * 60 + t.minute <= 18 * 60 for t in half)  # 13:00 EST = 18:00 UTC
    assert len(half) < len(DEFAULT_TIMES)


def test_select_expiries_keeps_dailies_and_capped_monthlies():
    board = {
        DAY,  # 0DTE
        date(2024, 8, 19), date(2024, 8, 21), date(2024, 8, 23),  # dailies
        date(2024, 9, 20), date(2024, 10, 18), date(2024, 11, 15),  # monthlies
        date(2025, 6, 20),  # far LEAP-ish monthly: outside the anchor window
    }
    kept = select_expiries(board, DAY)
    assert DAY in kept and date(2024, 8, 23) in kept
    assert date(2024, 9, 20) in kept and date(2024, 10, 18) in kept  # 2 anchors
    assert date(2024, 11, 15) not in kept  # anchor cap = 2
    assert date(2025, 6, 20) not in kept


def test_capture_day_fixture_shape(store):
    doc = capture_day(store, "SPY", DAY, times=(time(10, 0), time(15, 45)))
    assert doc is not None
    assert doc["asset"] == "SPY" and doc["day"] == DAY.isoformat()
    assert doc["expiries"] == [DAILY.isoformat(), MONTHLY.isoformat()]
    assert len(doc["snapshots"]) == 2
    for snap in doc["snapshots"]:
        assert snap["spot"] > 0
        assert len(snap["quotes"]) == 12  # 2 expiries x 3 strikes x {C, P}


def test_run_is_resumable_and_persists_settlement(store, tmp_path, monkeypatch):
    import backtest.capture_intraday as ci

    monkeypatch.setattr(ci, "FIXTURE_DIR", str(tmp_path / "fx"))
    db = tmp_path / "intraday.sqlite"
    written = run(DAY, DAY, tickers=("SPY",), times=(time(10, 0), time(15, 45)),
                  db_path=str(db), store=store)
    assert len(written) == 1
    doc = json.loads(open(written[0], encoding="utf-8").read())
    assert len(doc["snapshots"]) == 2
    # resumable: second run skips the existing fixture
    again = run(DAY, DAY, tickers=("SPY",), times=(time(10, 0), time(15, 45)),
                store=store)
    assert again == []
    # the VolStore replay path carries the settlement map (intraday clock input)
    from volfit.data.store import VolStore

    with VolStore(db) as vs:
        snap = vs.snapshot_at("SPY", T2)
    assert snap is not None
    assert snap.settlement is not None and DAILY in snap.settlement
    assert snap.settlement[DAILY].style == "pm"
    assert snap.timestamp == T2

"""Captured snapshots belong to the SOURCE that made them (store schema v10).

The as-of picker used to list every capture in the store under whichever
source was active — a Cboe / Yahoo auto-capture, a synthetic run's, an
export's — and offer "latest" / "n min before close" on a past day a
live-only source cannot fetch at all. Now every capture is tagged with the
producing data-source id: the picker lists a source's own captures only
(legacy untagged rows are never offered), while a replay of an explicit
captured selection stays lenient so saved workspaces keep working.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.asof import asof_payload
from volfit.api.state import AppState, AsOfSelection
from volfit.data.provider import SyntheticProvider
from volfit.data.store import SCHEMA_VERSION, VolStore

REF = date(2026, 6, 13)


def _state(db, source: str) -> AppState:
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return AppState(REF, providers={source: prov}, active_source=source, store_path=str(db))


def _app(db, source: str):
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return create_app(
        reference_date=REF, providers={source: prov}, active_source=source, store_path=str(db)
    )


def _captured_days(payload: dict) -> list[dict]:
    return [d for d in payload["days"] if d["hasCaptures"]]


# ------------------------------------------------------------ source tagging

def test_capture_is_tagged_with_its_source_and_listed_under_it_only(tmp_path):
    """A live fetch under 'cboe' is captured AS cboe's: listed for cboe, not
    for yahoo on the same store, and never by an unfiltered-source picker."""
    db = tmp_path / "cap.sqlite"
    cboe = _state(db, "cboe")
    chain = cboe.snapshot("ALPHA")  # live fetch -> auto-captured under "cboe"
    with VolStore(db) as store:
        assert len(store.list_snapshots(["ALPHA"], source="cboe")) == 1
        assert store.list_snapshots(["ALPHA"], source="yahoo") == []
        assert len(store.list_snapshots(["ALPHA"])) == 1  # unfiltered: everything
        assert store.snapshot_at("ALPHA", chain.timestamp, source="cboe") is not None
        assert store.snapshot_at("ALPHA", chain.timestamp, source="yahoo") is None

    # The picker under cboe offers the day (with its captured instant listed);
    # a second app on the SAME store under yahoo offers nothing captured.
    days = _captured_days(asof_payload(cboe))
    assert len(days) == 1 and days[0]["captures"] == [chain.timestamp.isoformat()]
    yahoo = _state(db, "yahoo")
    assert _captured_days(asof_payload(yahoo)) == []


def test_api_payload_carries_the_captures_of_the_active_source_only(tmp_path):
    db = tmp_path / "api.sqlite"
    with TestClient(_app(db, "cboe")) as c:
        iso = c.get("/universe").json()["expiries"]["ALPHA"][1]["expiry"]
        c.get(f"/smiles/ALPHA/{iso}")  # live fetch -> capture under cboe
        days = _captured_days(c.get("/asof").json())
        assert len(days) == 1 and len(days[0]["captures"]) == 1
        ts = days[0]["captures"][0]
        # The explicit captured pick (the picker's "Captured · HH:MM" row).
        r = c.post("/asof", json={"mode": "captured", "ts": ts})
        assert r.status_code == 200 and r.json()["mode"] == "captured" and r.json()["ts"] == ts
    with TestClient(_app(db, "yahoo")) as c:
        c.get("/universe")
        assert _captured_days(c.get("/asof").json()) == []


def test_capture_cap_per_day_is_newest_first(tmp_path):
    """Many captures on one day: the payload lists the newest first, capped."""
    from volfit.api.asof import MAX_CAPTURES_PER_DAY

    db = tmp_path / "many.sqlite"
    state = _state(db, "cboe")
    base = state.provider.fetch_chain("ALPHA")
    with VolStore(db) as store:
        for k in range(MAX_CAPTURES_PER_DAY + 3):
            snap = base.__class__(
                ticker=base.ticker, spot=base.spot,
                timestamp=datetime(2026, 6, 12, 14, 0) .replace(minute=k * 5 % 60, hour=14 + k * 5 // 60),
                quotes=base.quotes, exercise_style=base.exercise_style,
            )
            store.save_snapshot(snap, source="cboe")
    day = next(d for d in asof_payload(state)["days"] if d["date"] == "2026-06-12")
    caps = day["captures"]
    assert len(caps) == MAX_CAPTURES_PER_DAY
    assert caps == sorted(caps, reverse=True)
    assert caps[0] == datetime(2026, 6, 12, 14, 50).isoformat()


# ------------------------------------------------------------- legacy rows

def test_legacy_untagged_capture_replays_but_is_never_offered(tmp_path):
    """A pre-v10 row (no source) is not listed for any source, but an explicit
    captured selection (a saved workspace) still replays it."""
    db = tmp_path / "legacy.sqlite"
    state = _state(db, "cboe")
    chain = state.provider.fetch_chain("ALPHA")  # straight off the provider: not captured
    with VolStore(db) as store:
        store.save_snapshot(chain)  # source=None: a legacy row
        assert store.list_snapshots(["ALPHA"], source="cboe") == []
        assert len(store.list_snapshots(["ALPHA"])) == 1
        assert store.snapshot_at("ALPHA", chain.timestamp, source="cboe") is not None
    assert _captured_days(asof_payload(state)) == []
    state.set_as_of(AsOfSelection(mode="captured", ts=chain.timestamp))
    replay = state.snapshot("ALPHA")
    assert replay.spot == chain.spot and len(replay.quotes) == len(chain.quotes)


# ---------------------------------------------------------------- schema

def test_store_schema_v10_has_source_and_migrates_a_v9_file(tmp_path):
    assert SCHEMA_VERSION == 10
    fresh = tmp_path / "fresh.sqlite"
    with VolStore(fresh) as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 10
        cols = {r[1] for r in store.conn.execute("PRAGMA table_info(snapshots)")}
        assert "source" in cols

    # A v9 file: the snapshots table WITHOUT the column, one legacy row.
    old = tmp_path / "v9.sqlite"
    conn = sqlite3.connect(old)
    conn.executescript(
        """
        CREATE TABLE snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            spot            REAL NOT NULL,
            ts              TEXT NOT NULL,
            exercise_style  TEXT NOT NULL DEFAULT 'european',
            zero_carry      INTEGER NOT NULL DEFAULT 0,
            tick_size       REAL,
            settlement_json TEXT
        );
        INSERT INTO snapshots (ticker, spot, ts) VALUES ('ALPHA', 100.0, '2026-06-12T15:00:00');
        PRAGMA user_version = 9;
        """
    )
    conn.commit()
    conn.close()
    with VolStore(old) as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 10
        cols = {r[1] for r in store.conn.execute("PRAGMA table_info(snapshots)")}
        assert "source" in cols
        assert store.list_snapshots(["ALPHA"], source="cboe") == []  # untagged: never offered
        assert len(store.list_snapshots(["ALPHA"])) == 1
        assert store.snapshot_at("ALPHA", datetime(2026, 6, 12, 16), source="cboe") is not None

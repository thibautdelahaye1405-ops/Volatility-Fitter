"""SERIES ARC S0 — store schema v11 (Docs/series_replay_roadmap.md §5).

Locks: a fresh store is v11 with the four series tables and
``snapshots.series_id``; a v10 file migrates (column added, tables created,
rows kept); a snapshot saved as a series FRAME is skipped by the capture
listings (``list_snapshots`` / ``snapshot_at``) unless asked for, so the
as-of picker's payload never lists a frame; the frame table cascades with
its series.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import date, timedelta

from volfit.api.asof import asof_payload
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider
from volfit.data.store import SCHEMA_VERSION, VolStore
from volfit.data.store_series import SERIES_TABLES, has_series_tables

REF = date(2026, 6, 13)


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


# ------------------------------------------------------------------ schema

def test_fresh_store_is_v11_with_the_series_tables(tmp_path):
    assert SCHEMA_VERSION == 11
    with VolStore(tmp_path / "fresh.sqlite") as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 11
        assert set(SERIES_TABLES) <= _tables(store.conn)
        assert has_series_tables(store.conn)
        assert "series_id" in _cols(store.conn, "snapshots")
        assert {"series_id", "lane_id", "idx", "expiry"} <= _cols(store.conn, "series_fits")
        assert {"series_id", "idx", "snapshot_id", "quote_kind"} <= _cols(store.conn, "series_frames")


def test_a_v10_file_migrates_to_v11_keeping_its_rows(tmp_path):
    old = tmp_path / "v10.sqlite"
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
            settlement_json TEXT,
            source          TEXT
        );
        INSERT INTO snapshots (ticker, spot, ts, source)
            VALUES ('ALPHA', 100.0, '2026-06-12T15:00:00', 'cboe');
        PRAGMA user_version = 10;
        """
    )
    conn.commit()
    conn.close()
    assert not has_series_tables(sqlite3.connect(old))
    with VolStore(old) as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 11
        assert "series_id" in _cols(store.conn, "snapshots")
        assert has_series_tables(store.conn)
        rows = store.list_snapshots(["ALPHA"], source="cboe")
        assert len(rows) == 1  # the capture survives, still a capture (series_id NULL)
        assert store.conn.execute("SELECT series_id FROM snapshots").fetchone()[0] is None
    # Re-opening an up-to-date file takes the fast path (no DDL) and stays v11.
    with VolStore(old) as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 11


# ------------------------------------------------------- frame exclusion

def _chain(ts_offset_minutes: int = 0):
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    chain = prov.fetch_chain("ALPHA")
    if ts_offset_minutes:
        chain = dataclasses.replace(
            chain, timestamp=chain.timestamp + timedelta(minutes=ts_offset_minutes)
        )
    return chain


def test_series_frames_are_skipped_by_the_capture_listings(tmp_path):
    db = tmp_path / "frames.sqlite"
    with VolStore(db) as store:
        cap_id = store.save_snapshot(_chain(0), source="cboe")
        frame_id = store.save_snapshot(_chain(1), source="cboe", series_id="s1")
        later = _chain(1).timestamp

        listed = store.list_snapshots(["ALPHA"], source="cboe")
        assert [sid for _t, sid, _ts in listed] == [cap_id]
        listed_all = store.list_snapshots(["ALPHA"], source="cboe", include_series=True)
        assert {sid for _t, sid, _ts in listed_all} == {cap_id, frame_id}
        assert [sid for _t, sid, _ts in store.list_snapshots()] == [cap_id]  # unfiltered too

        # at-or-before the frame's instant lands on the CAPTURE, not the frame
        at = store.snapshot_at("ALPHA", later, source="cboe")
        assert at is not None and at.timestamp == _chain(0).timestamp
        at_frame = store.snapshot_at("ALPHA", later, source="cboe", include_series=True)
        assert at_frame is not None and at_frame.timestamp == later
        # the frame is still loadable by id (the series layer's address)
        assert store.load_snapshot(frame_id).timestamp == later
        assert store.conn.execute(
            "SELECT series_id FROM snapshots WHERE id = ?", (frame_id,)
        ).fetchone()[0] == "s1"


def test_asof_picker_payload_never_lists_a_series_frame(tmp_path):
    db = tmp_path / "picker.sqlite"
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    state = AppState(REF, providers={"cboe": prov}, active_source="cboe", store_path=str(db))
    chain = state.snapshot("ALPHA")  # live fetch -> one capture under cboe
    with VolStore(db) as store:
        for m in (1, 2, 3):  # three frames a minute apart on the same day
            store.save_snapshot(_chain(m), source="cboe", series_id="s1")
    days = [d for d in asof_payload(state)["days"] if d["hasCaptures"]]
    assert len(days) == 1
    assert days[0]["captures"] == [chain.timestamp.isoformat()]


def test_deleting_a_series_cascades_its_frames_and_fits(tmp_path):
    with VolStore(tmp_path / "cascade.sqlite") as store:
        c = store.conn
        c.execute(
            "INSERT INTO series (id, name, ticker, mode, created_ts, updated_ts, spec_json, "
            "base_fit_json, base_options_json) VALUES ('s1', 'n', 'ALPHA', 'import', "
            "'t', 't', '{}', '{}', '{}')"
        )
        c.execute("INSERT INTO series_lanes (series_id, lane_id, ord, name, family, spec_json) "
                  "VALUES ('s1', 'free', 0, 'free', 'lqd', '{}')")
        c.execute("INSERT INTO series_frames (series_id, idx, ts) VALUES ('s1', 0, 't0')")
        c.execute("INSERT INTO series_fits (series_id, lane_id, idx, expiry, model, params_json) "
                  "VALUES ('s1', 'free', 0, '2026-07-17', 'lqd', '{}')")
        c.execute("INSERT INTO series_fits (series_id, lane_id, idx, model, params_json) "
                  "VALUES ('s1', 'free', 0, 'affine', '{}')")  # the LV row: expiry ''
        c.commit()
        assert c.execute("SELECT COUNT(*) FROM series_fits").fetchone()[0] == 2
        c.execute("DELETE FROM series WHERE id = 's1'")
        c.commit()
        for t in ("series_lanes", "series_frames", "series_fits"):
            assert c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t

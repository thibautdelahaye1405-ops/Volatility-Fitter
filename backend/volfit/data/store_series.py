"""Series tables of the VolStore (schema v11, the SERIES ARC S0 contract).

A *Series* is one ticker's ordered set of instants, harvested and calibrated
under several model *lanes* and replayed (Docs/series_replay_roadmap.md §5).
The chains themselves stay where every chain lives — ``snapshots`` +
``quotes`` — and a frame points at its snapshot row; what this module adds is
the grouping: the series document, its lanes, its frame index and the fits
made per (lane, frame, expiry).

Why the frames carry a ``series_id`` on the ``snapshots`` row rather than a
table of their own: the harvest path and the import path both reuse
``VolStore.save_snapshot`` (dedupe, settlement, tick size) and the as-of
picker's listing must SKIP series frames — a one-minute series would flood
its eight-captures-per-day listing (``asof._captures_by_date``). The
``list_snapshots`` / ``snapshot_at`` filters default to captures only; the
series layer addresses its frames by snapshot id.

This module owns the DDL only. The CRUD (``api/series_store.py``, S1) and the
runner (S2/S3) come in their own modules under the 400-line policy.
"""

from __future__ import annotations

import sqlite3

#: Tables the series layer owns (in dependency order; ``series`` first).
SERIES_TABLES: tuple[str, ...] = ("series", "series_lanes", "series_frames", "series_fits")

#: The v11 DDL — every statement ``IF NOT EXISTS`` so re-running it on an
#: up-to-date file is a no-op (the store's own convention). ``expiry`` is
#: '' (empty) rather than NULL on the LV surface row so the primary key
#: stays total — SQLite treats NULLs as distinct in a PRIMARY KEY.
SERIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS series (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    source            TEXT,
    mode              TEXT NOT NULL,
    created_ts        TEXT NOT NULL,
    updated_ts        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'draft',
    fit_mode          TEXT NOT NULL DEFAULT 'mid',
    spec_json         TEXT NOT NULL,
    base_fit_json     TEXT NOT NULL,
    base_options_json TEXT NOT NULL,
    progress_json     TEXT,
    note              TEXT NOT NULL DEFAULT '',
    error             TEXT
);
CREATE TABLE IF NOT EXISTS series_lanes (
    series_id          TEXT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    lane_id            TEXT NOT NULL,
    ord                INTEGER NOT NULL,
    name               TEXT NOT NULL,
    colour             TEXT,
    family             TEXT NOT NULL,
    production         INTEGER NOT NULL DEFAULT 0,
    spec_json          TEXT NOT NULL,
    filter_json        TEXT,
    PRIMARY KEY (series_id, lane_id)
);
CREATE TABLE IF NOT EXISTS series_frames (
    series_id     TEXT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    ts            TEXT NOT NULL,
    snapshot_id   INTEGER REFERENCES snapshots(id),
    spot          REAL,
    quote_kind    TEXT,
    n_quotes      INTEGER NOT NULL DEFAULT 0,
    expiries_json TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'pending',
    error         TEXT,
    harvested_ts  TEXT,
    PRIMARY KEY (series_id, idx)
);
CREATE TABLE IF NOT EXISTS series_fits (
    series_id        TEXT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    lane_id          TEXT NOT NULL,
    idx              INTEGER NOT NULL,
    expiry           TEXT NOT NULL DEFAULT '',
    model            TEXT NOT NULL,
    params_json      TEXT NOT NULL,
    display_json     TEXT,
    diagnostics_json TEXT,
    metrics_json     TEXT,
    fit_ms           REAL,
    status           TEXT NOT NULL DEFAULT 'done',
    error            TEXT,
    PRIMARY KEY (series_id, lane_id, idx, expiry)
);
CREATE INDEX IF NOT EXISTS idx_series_ticker ON series (ticker, created_ts);
CREATE INDEX IF NOT EXISTS idx_series_frames_snapshot ON series_frames (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_series ON snapshots (series_id);
"""


def ensure_series_schema(conn: sqlite3.Connection) -> None:
    """Create the series tables + indexes (idempotent). Called by
    ``VolStore._ensure_schema`` AFTER the ``snapshots.series_id`` column
    exists — the index on it needs the column."""
    conn.executescript(SERIES_SCHEMA)


def has_series_tables(conn: sqlite3.Connection) -> bool:
    """True when every series table exists (a diagnostic for the migration
    lock; the store never branches on it)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?, ?)",
        SERIES_TABLES,
    ).fetchall()
    return len(rows) == len(SERIES_TABLES)

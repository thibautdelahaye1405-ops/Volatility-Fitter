"""SQLite persistence for snapshots, fits, priors and universes.

Design intent (ROADMAP Phase 3): SQLite is the transactional app store
(quotes for the current session, fitted parameters, saved priors, universe
configs); bulk chain *history* moves to Parquet/DuckDB later.  The schema is
versioned with `PRAGMA user_version` so future migrations can detect and
upgrade old files; WAL mode keeps reads non-blocking during writes.

Storage conventions
-------------------
- Dates are ISO strings ('YYYY-MM-DD'), timestamps ISO datetime strings —
  both round-trip exactly through `date/datetime.fromisoformat`.
- Model parameters and diagnostics are stored as JSON text columns, keeping
  the schema model-agnostic (LQD, SVI-JW, ... all share the `fits` table).
- Quote timestamps are normalized to the snapshot timestamp on save (the
  snapshot is the unit of observation; per-quote timestamps from providers
  are a fetch artifact).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from volfit.data.types import ChainSnapshot, Instrument, OptionQuote

#: v2 ([REQ 2026-06-12]): snapshots carry the contracts' exercise style so
#: reloaded chains keep de-Americanizing exactly like freshly fetched ones.
#: v3 ([REQ 2026-06-15]): an `app_settings` key/value table persists the global
#: Fit + Options defaults (the Options "Save as default" button), so a backend
#: restart restores them instead of the code defaults.
SCHEMA_VERSION = 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    ticker   TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    currency TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker         TEXT NOT NULL,
    spot           REAL NOT NULL,
    ts             TEXT NOT NULL,
    exercise_style TEXT NOT NULL DEFAULT 'european'
);
CREATE TABLE IF NOT EXISTS quotes (
    snapshot_id   INTEGER NOT NULL REFERENCES snapshots(id),
    expiry        TEXT NOT NULL,
    strike        REAL NOT NULL,
    call_put      TEXT NOT NULL CHECK (call_put IN ('C', 'P')),
    bid           REAL,
    ask           REAL,
    last          REAL,
    volume        INTEGER,
    open_interest INTEGER
);
CREATE TABLE IF NOT EXISTS fits (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    expiry           TEXT NOT NULL,
    model            TEXT NOT NULL,
    params_json      TEXT NOT NULL,
    created_ts       TEXT NOT NULL,
    diagnostics_json TEXT
);
CREATE TABLE IF NOT EXISTS priors (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    expiry           TEXT NOT NULL,
    model            TEXT NOT NULL,
    params_json      TEXT NOT NULL,
    created_ts       TEXT NOT NULL,
    diagnostics_json TEXT,
    label            TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prior_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker    TEXT NOT NULL,
    data_ts   TEXT NOT NULL,
    saved_ts  TEXT NOT NULL,
    doc_json  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS universes (
    name        TEXT PRIMARY KEY,
    config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_ts ON snapshots (ticker, ts);
CREATE INDEX IF NOT EXISTS idx_quotes_snapshot      ON quotes (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_fits_ticker_expiry   ON fits (ticker, expiry);
CREATE INDEX IF NOT EXISTS idx_priors_ticker_expiry ON priors (ticker, expiry);
CREATE INDEX IF NOT EXISTS idx_prior_snapshots_ticker
    ON prior_snapshots (ticker, data_ts);
"""


@dataclass(frozen=True)
class FitRecord:
    """One stored fit (or prior, when `label` is set)."""

    id: int
    ticker: str
    expiry: date
    model: str
    params: dict
    created_ts: datetime
    diagnostics: dict | None = None
    label: str | None = None


class VolStore:
    """Context-managed SQLite store for the vol-fitter app state.

    Usage::

        with VolStore(path) as store:
            sid = store.save_snapshot(chain)
            chain2 = store.load_snapshot(sid)
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    # -- lifecycle ---------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Create/migrate tables on open; refuse files from a newer schema.

        v1 -> v2: the `snapshots` table gains `exercise_style` (defaulting
        old rows to 'european' — the only style v1 ever stored).
        v2 -> v3: the `app_settings` key/value table is added — no migration
        beyond the `CREATE TABLE IF NOT EXISTS` in `_SCHEMA` (a brand-new table
        carries no old rows to backfill).
        v3 -> v4: the `prior_snapshots` table is added (full calibration
        snapshots for the prior framework) — again a brand-new table, so the
        `CREATE TABLE IF NOT EXISTS` is the whole migration.

        Fast path: a store is opened on *every* capture/persist/load, so once the
        file is already at `SCHEMA_VERSION` we return immediately — skipping the
        DDL `executescript` and the `PRAGMA user_version` write that otherwise ran
        (and committed) on the request thread at every open.
        """
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"{self.path} has schema version {version}, "
                f"newer than supported {SCHEMA_VERSION}"
            )
        if version == SCHEMA_VERSION:
            return  # already current — no DDL / no write on this open
        self.conn.executescript(_SCHEMA)
        if version == 1:  # existing v1 file: CREATE IF NOT EXISTS didn't touch it
            self.conn.execute(
                "ALTER TABLE snapshots ADD COLUMN "
                "exercise_style TEXT NOT NULL DEFAULT 'european'"
            )
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def __enter__(self) -> "VolStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- instruments -------------------------------------------------------

    def upsert_instrument(self, instrument: Instrument) -> None:
        self.conn.execute(
            "INSERT INTO instruments (ticker, name, currency) VALUES (?, ?, ?) "
            "ON CONFLICT(ticker) DO UPDATE SET name = excluded.name, "
            "currency = excluded.currency",
            (instrument.ticker, instrument.name, instrument.currency),
        )
        self.conn.commit()

    def load_instrument(self, ticker: str) -> Instrument | None:
        row = self.conn.execute(
            "SELECT ticker, name, currency FROM instruments WHERE ticker = ?", (ticker,)
        ).fetchone()
        return Instrument(*row) if row else None

    # -- snapshots ---------------------------------------------------------

    def save_snapshot(self, snapshot: ChainSnapshot) -> int:
        """Persist one chain snapshot; returns the new snapshot id."""
        cur = self.conn.execute(
            "INSERT INTO snapshots (ticker, spot, ts, exercise_style) "
            "VALUES (?, ?, ?, ?)",
            (
                snapshot.ticker,
                snapshot.spot,
                snapshot.timestamp.isoformat(),
                snapshot.exercise_style,
            ),
        )
        snapshot_id = int(cur.lastrowid)
        self.conn.executemany(
            "INSERT INTO quotes (snapshot_id, expiry, strike, call_put, bid, ask, "
            "last, volume, open_interest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    snapshot_id,
                    q.expiry.isoformat(),
                    q.strike,
                    q.call_put,
                    q.bid,
                    q.ask,
                    q.last,
                    q.volume,
                    q.open_interest,
                )
                for q in snapshot.quotes
            ],
        )
        self.conn.commit()
        return snapshot_id

    def load_snapshot(self, snapshot_id: int) -> ChainSnapshot:
        """Reload a snapshot; raises KeyError if the id is unknown."""
        row = self.conn.execute(
            "SELECT ticker, spot, ts, exercise_style FROM snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"no snapshot with id {snapshot_id}")
        ticker, spot, ts, exercise_style = row
        timestamp = datetime.fromisoformat(ts)
        quotes = [
            OptionQuote(
                ticker=ticker,
                expiry=date.fromisoformat(expiry),
                strike=strike,
                call_put=call_put,
                bid=bid,
                ask=ask,
                last=last,
                volume=volume,
                open_interest=open_interest,
                timestamp=timestamp,
            )
            for expiry, strike, call_put, bid, ask, last, volume, open_interest
            in self.conn.execute(
                "SELECT expiry, strike, call_put, bid, ask, last, volume, open_interest "
                "FROM quotes WHERE snapshot_id = ? ORDER BY expiry, strike, call_put",
                (snapshot_id,),
            )
        ]
        return ChainSnapshot(
            ticker=ticker,
            spot=spot,
            timestamp=timestamp,
            quotes=quotes,
            exercise_style=exercise_style,
        )

    def latest_snapshot(self, ticker: str) -> ChainSnapshot | None:
        """Most recent snapshot for a ticker (by timestamp, then id), or None."""
        row = self.conn.execute(
            "SELECT id FROM snapshots WHERE ticker = ? ORDER BY ts DESC, id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return self.load_snapshot(int(row[0])) if row else None

    def list_snapshots(
        self, tickers: list[str] | None = None
    ) -> list[tuple[str, int, datetime]]:
        """(ticker, id, timestamp) for stored snapshots, newest first.

        Restricted to ``tickers`` when given (the active universe). Backs the
        as-of picker's 'captured intraday' list.
        """
        sql = "SELECT ticker, id, ts FROM snapshots"
        args: list = []
        if tickers:
            placeholders = ", ".join("?" * len(tickers))
            sql += f" WHERE ticker IN ({placeholders})"
            args = list(tickers)
        sql += " ORDER BY ts DESC, id DESC"
        return [
            (ticker, int(sid), datetime.fromisoformat(ts))
            for ticker, sid, ts in self.conn.execute(sql, args)
        ]

    def snapshot_at(self, ticker: str, ts: datetime) -> ChainSnapshot | None:
        """The ticker's snapshot nearest at-or-before ``ts`` (None if none)."""
        row = self.conn.execute(
            "SELECT id FROM snapshots WHERE ticker = ? AND ts <= ? "
            "ORDER BY ts DESC, id DESC LIMIT 1",
            (ticker, ts.isoformat()),
        ).fetchone()
        return self.load_snapshot(int(row[0])) if row else None

    def last_snapshot_ts(self, ticker: str) -> datetime | None:
        """Timestamp of the ticker's most recent snapshot, or None (for capture
        dedup without loading the whole chain)."""
        row = self.conn.execute(
            "SELECT ts FROM snapshots WHERE ticker = ? ORDER BY ts DESC, id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    # -- fits and priors ---------------------------------------------------

    def save_fit(
        self,
        ticker: str,
        expiry: date,
        model: str,
        params: dict,
        diagnostics: dict | None = None,
        created_ts: datetime | None = None,
    ) -> int:
        """Store one fitted slice (parameters as JSON); returns the fit id."""
        return self._save_record("fits", ticker, expiry, model, params, diagnostics,
                                 created_ts, label=None)

    def load_fits(self, ticker: str, expiry: date | None = None) -> list[FitRecord]:
        return self._load_records("fits", ticker, expiry, label=None)

    def save_prior(
        self,
        ticker: str,
        expiry: date,
        model: str,
        params: dict,
        label: str,
        diagnostics: dict | None = None,
        created_ts: datetime | None = None,
    ) -> int:
        """Store a labelled prior (a fit promoted by the user); returns its id."""
        return self._save_record("priors", ticker, expiry, model, params, diagnostics,
                                 created_ts, label=label)

    def load_priors(
        self, ticker: str, expiry: date | None = None, label: str | None = None
    ) -> list[FitRecord]:
        return self._load_records("priors", ticker, expiry, label=label)

    # -- prior snapshots (full calibration snapshots for the prior framework) --

    def save_prior_snapshot(
        self, ticker: str, data_ts: datetime, saved_ts: datetime, doc: dict
    ) -> int:
        """Persist one full prior surface snapshot (JSON document); returns its id.

        ``data_ts`` is the market moment the calibration reflects (what the fetch
        freshness ladder compares against the previous close); ``saved_ts`` is the
        wall-clock save time. History is kept — each save is a new row."""
        cur = self.conn.execute(
            "INSERT INTO prior_snapshots (ticker, data_ts, saved_ts, doc_json) "
            "VALUES (?, ?, ?, ?)",
            [ticker, data_ts.isoformat(), saved_ts.isoformat(), json.dumps(doc)],
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def latest_prior_snapshot(self, ticker: str) -> dict | None:
        """The most recently SAVED prior snapshot document for a ticker, or None."""
        row = self.conn.execute(
            "SELECT doc_json FROM prior_snapshots WHERE ticker = ? "
            "ORDER BY saved_ts DESC, id DESC LIMIT 1",
            [ticker],
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_prior_snapshots(self, ticker: str) -> list[tuple[int, datetime, datetime]]:
        """(id, data_ts, saved_ts) of a ticker's snapshots, newest save first."""
        rows = self.conn.execute(
            "SELECT id, data_ts, saved_ts FROM prior_snapshots WHERE ticker = ? "
            "ORDER BY saved_ts DESC, id DESC",
            [ticker],
        ).fetchall()
        return [
            (int(i), datetime.fromisoformat(d), datetime.fromisoformat(s))
            for i, d, s in rows
        ]

    def _save_record(
        self,
        table: str,
        ticker: str,
        expiry: date,
        model: str,
        params: dict,
        diagnostics: dict | None,
        created_ts: datetime | None,
        label: str | None,
    ) -> int:
        ts = (created_ts or datetime.now()).isoformat()
        diag = json.dumps(diagnostics) if diagnostics is not None else None
        columns = "ticker, expiry, model, params_json, created_ts, diagnostics_json"
        values = [ticker, expiry.isoformat(), model, json.dumps(params), ts, diag]
        if table == "priors":
            columns += ", label"
            values.append(label)
        placeholders = ", ".join("?" * len(values))
        cur = self.conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def _load_records(
        self, table: str, ticker: str, expiry: date | None, label: str | None
    ) -> list[FitRecord]:
        has_label = table == "priors"
        columns = "id, ticker, expiry, model, params_json, created_ts, diagnostics_json"
        if has_label:
            columns += ", label"
        sql = f"SELECT {columns} FROM {table} WHERE ticker = ?"
        args: list = [ticker]
        if expiry is not None:
            sql += " AND expiry = ?"
            args.append(expiry.isoformat())
        if has_label and label is not None:
            sql += " AND label = ?"
            args.append(label)
        sql += " ORDER BY created_ts, id"
        records = []
        for row in self.conn.execute(sql, args):
            rec_id, tkr, exp, model, params_json, created_ts, diag_json = row[:7]
            records.append(
                FitRecord(
                    id=rec_id,
                    ticker=tkr,
                    expiry=date.fromisoformat(exp),
                    model=model,
                    params=json.loads(params_json),
                    created_ts=datetime.fromisoformat(created_ts),
                    diagnostics=json.loads(diag_json) if diag_json is not None else None,
                    label=row[7] if has_label else None,
                )
            )
        return records

    # -- app settings (key/value) -----------------------------------------

    def save_setting(self, key: str, value: dict) -> None:
        """Upsert one JSON-encoded setting (e.g. the saved Fit/Options defaults)."""
        self.conn.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
            (key, json.dumps(value)),
        )
        self.conn.commit()

    def load_setting(self, key: str) -> dict | None:
        """Return the parsed setting for ``key``, or None if it was never saved."""
        row = self.conn.execute(
            "SELECT value_json FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def delete_setting(self, key: str) -> None:
        """Remove a saved setting (no-op if absent)."""
        self.conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        self.conn.commit()

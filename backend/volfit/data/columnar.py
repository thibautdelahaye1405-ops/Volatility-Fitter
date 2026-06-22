"""Columnar snapshot/quote history on Parquet, queried via DuckDB (ROADMAP perf #6).

The transactional ``VolStore`` (SQLite) stays the source of truth for the live
session (current chains, fits, priors, universes). Its single-snapshot reads
(``snapshot_at`` / ``load_snapshot``) are indexed and fast — but the row-per-quote
table is poor for **multi-snapshot historical scans** (as-of replay over a window,
the prior ladder, and the backtest / neural-operator dataset of Phase 7), which
touch many snapshots but few columns. That access pattern is exactly what columnar
storage + predicate pushdown are built for.

``ColumnarHistory`` is an **additive** layer: bulk-export the SQLite history (or
write snapshots directly), then run the analytical reads over Parquet. It is NOT
wired into the live capture/read path here — that dual-write + read-through
integration is a deliberate, separately-reviewable follow-up; SQLite remains the
live store unchanged.

Layout: one Parquet file per ``(ticker, calendar-date)`` under
``{root}/{ticker}/{YYYY-MM-DD}.parquet`` — few, scan-friendly files (vs a file per
snapshot). Columns: ``ticker, ts, spot, exercise_style, expiry, strike, call_put,
bid, ask, last, volume, open_interest`` (``ts`` a TIMESTAMP identifying the
snapshot; ``expiry`` an ISO string). DuckDB globs the files with column pruning +
``ts`` predicate pushdown.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from volfit.data.types import ChainSnapshot, OptionQuote

_COLUMNS = [
    "ticker", "ts", "spot", "exercise_style", "expiry", "strike", "call_put",
    "bid", "ask", "last", "volume", "open_interest",
]


class ColumnarHistory:
    """Parquet + DuckDB columnar history (see module docstring)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ----------------------------------------------------------------- write
    def write_snapshots(self, snapshots: list[ChainSnapshot]) -> int:
        """Write snapshots to Parquet, one file per (ticker, date). A day-file is
        read-merged + de-duplicated on ``(ts, expiry, strike, call_put)`` so a
        re-export or an overlapping batch is idempotent. Returns rows written."""
        import pandas as pd

        groups: dict[tuple[str, date], list[ChainSnapshot]] = defaultdict(list)
        for s in snapshots:
            groups[(s.ticker, s.timestamp.date())].append(s)
        written = 0
        for (ticker, day), snaps in groups.items():
            path = self._day_path(ticker, day)
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = [r for s in snaps for r in _rows(s)]
            df = pd.DataFrame(rows, columns=_COLUMNS)
            if path.exists():  # merge with the existing day-file, then de-dup
                prev = pd.read_parquet(path)
                df = pd.concat([prev, df], ignore_index=True)
            df = df.drop_duplicates(
                subset=["ts", "expiry", "strike", "call_put"], keep="last"
            )
            df.to_parquet(path, index=False)
            written += len(rows)
        return written

    # ------------------------------------------------------------------ read
    def list_snapshots(
        self, tickers: list[str] | None = None
    ) -> list[tuple[str, datetime]]:
        """(ticker, ts) for every stored snapshot, newest first (the as-of index)."""
        globs = self._globs(tickers)
        if not globs:
            return []
        rows = self._con().execute(
            f"SELECT DISTINCT ticker, ts FROM read_parquet({globs}) ORDER BY ts DESC",
        ).fetchall()
        return [(str(t), _as_dt(ts)) for t, ts in rows]

    def snapshot_at(self, ticker: str, ts: datetime) -> ChainSnapshot | None:
        """The ticker's snapshot nearest at-or-before ``ts`` (None if none)."""
        globs = self._globs([ticker])
        if not globs:
            return None
        con = self._con()
        row = con.execute(
            f"SELECT max(ts) FROM read_parquet({globs}) WHERE ts <= ?", [ts]
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return self._load_at(con, globs, row[0])

    def latest_snapshot(self, ticker: str) -> ChainSnapshot | None:
        """The ticker's most recent snapshot, or None."""
        globs = self._globs([ticker])
        if not globs:
            return None
        con = self._con()
        row = con.execute(f"SELECT max(ts) FROM read_parquet({globs})").fetchone()
        if row is None or row[0] is None:
            return None
        return self._load_at(con, globs, row[0])

    def scan_quotes(
        self, tickers: list[str] | None, start: datetime, end: datetime
    ):
        """Columnar scan of every quote in ``[start, end]`` as a DataFrame — the
        capability SQLite is poor at (many snapshots, ts predicate pushdown). The
        primary feed for the Phase-7 neural-operator dataset / historical studies."""
        globs = self._globs(tickers)
        if not globs:
            import pandas as pd

            return pd.DataFrame(columns=_COLUMNS)
        return self._con().execute(
            f"SELECT * FROM read_parquet({globs}) WHERE ts >= ? AND ts <= ? "
            "ORDER BY ticker, ts, expiry, strike, call_put",
            [start, end],
        ).df()

    def available(self) -> bool:
        """Whether any Parquet history has been written under the root."""
        return self.root.exists() and any(self.root.glob("*/*.parquet"))

    # ------------------------------------------------------------- internals
    def _day_path(self, ticker: str, day: date) -> Path:
        return self.root / ticker / f"{day:%Y-%m-%d}.parquet"

    def _globs(self, tickers: list[str] | None) -> str | None:
        """A DuckDB ``read_parquet`` argument (a quoted glob list) for the tickers
        that actually have files — or None when nothing matches (so the caller
        skips the query rather than hit DuckDB's 'no files found' error)."""
        roots = (
            [self.root / t for t in tickers]
            if tickers
            else [p for p in self.root.glob("*") if p.is_dir()]
        )
        present = [r for r in roots if r.exists() and any(r.glob("*.parquet"))]
        if not present:
            return None
        globs = [f"{(r / '*.parquet').as_posix()}" for r in present]
        return "[" + ", ".join(f"'{g}'" for g in globs) + "]"

    def _load_at(self, con, globs: str, ts) -> ChainSnapshot:
        """Assemble the ChainSnapshot for one exact ``ts`` (all rows share it)."""
        rows = con.execute(
            f"SELECT ticker, ts, spot, exercise_style, expiry, strike, call_put, "
            f"bid, ask, last, volume, open_interest FROM read_parquet({globs}) "
            "WHERE ts = ? ORDER BY expiry, strike, call_put",
            [ts],
        ).fetchall()
        ticker = str(rows[0][0])
        timestamp = _as_dt(rows[0][1])
        quotes = [
            OptionQuote(
                ticker=ticker, expiry=date.fromisoformat(str(r[4])), strike=float(r[5]),
                call_put=str(r[6]), bid=_f(r[7]), ask=_f(r[8]), last=_f(r[9]),
                volume=_i(r[10]), open_interest=_i(r[11]), timestamp=timestamp,
            )
            for r in rows
        ]
        return ChainSnapshot(
            ticker=ticker, spot=float(rows[0][2]), timestamp=timestamp,
            quotes=quotes, exercise_style=str(rows[0][3]),
        )

    def _con(self):
        import duckdb

        return duckdb.connect()


def export_from_sqlite(volstore_path: str | Path, root: str | Path) -> int:
    """Bulk-migrate a SQLite ``VolStore``'s snapshot history to columnar Parquet.

    Reads every stored snapshot and writes it columnar (idempotent — re-export
    de-duplicates). Returns the number of snapshots exported. The fits / priors /
    universes / settings stay in SQLite (small, transactional)."""
    from volfit.data.store import VolStore

    hist = ColumnarHistory(root)
    with VolStore(volstore_path) as store:
        index = store.list_snapshots()
        snaps = [store.load_snapshot(sid) for _t, sid, _ts in index]
    if snaps:
        hist.write_snapshots(snaps)
    return len(snaps)


# --- row mapping + nullable coercions ---------------------------------------
def _rows(s: ChainSnapshot) -> list[tuple]:
    return [
        (
            s.ticker, s.timestamp, float(s.spot), s.exercise_style,
            q.expiry.isoformat(), float(q.strike), q.call_put,
            q.bid, q.ask, q.last, q.volume, q.open_interest,
        )
        for q in s.quotes
    ]


def _f(v) -> float | None:
    return None if v is None else float(v)


def _i(v) -> int | None:
    return None if v is None else int(v)


def _as_dt(v) -> datetime:
    """DuckDB returns a datetime for a TIMESTAMP column; tolerate an ISO string."""
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))

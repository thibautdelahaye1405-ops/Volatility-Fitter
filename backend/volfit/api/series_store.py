"""Series persistence — CRUD over the v11 series tables (SERIES ARC S1).

One :class:`SeriesStore` wraps an open :class:`VolStore` connection (the
store-per-request idiom of ``asof`` / ``history``: open, act, close). The
series document (``SeriesDoc``) is the unit: its ``spec`` — lanes included
— is stored as one JSON column and is the source of truth; ``series_lanes``
mirrors the lanes for querying and carries the per-lane filter ring;
``series_frames`` is the frame index (each frame points at a ``snapshots``
row); ``series_fits`` holds one row per (lane, frame, expiry) with the LV
surface row at ``expiry = ''`` (a NULL would break the primary key).

Ownership rule (§3.5 of the roadmap): a snapshot row whose ``series_id`` is
this series is series-OWNED and dies with it; a frame that references a
capture (``series_id`` NULL, an import from the app's own captures) leaves
the capture alone.
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from volfit.api.schemas_series import (
    FrameDoc,
    LaneFitDoc,
    LaneSpec,
    SeriesDoc,
    SeriesProgress,
    SeriesSpec,
    SeriesSummary,
)
from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot


def new_series_id() -> str:
    """A short opaque id (12 hex chars) — URL-safe, unique enough per desk."""
    return uuid4().hex[:12]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


class SeriesStore:
    """CRUD over the series tables of one open VolStore."""

    def __init__(self, store: VolStore) -> None:
        self.store = store
        self.conn = store.conn

    # ------------------------------------------------------------ series rows

    def create(self, doc: SeriesDoc) -> None:
        """Insert the series, its lane mirror rows and any frames it carries."""
        spec = doc.spec
        self.conn.execute(
            "INSERT INTO series (id, name, ticker, source, mode, created_ts, updated_ts, "
            "status, fit_mode, spec_json, base_fit_json, base_options_json, progress_json, "
            "note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc.id, spec.name, spec.ticker, spec.source, spec.mode, doc.createdTs,
                doc.updatedTs, doc.progress.status, spec.fitMode, spec.model_dump_json(),
                doc.baseFit.model_dump_json(), doc.baseOptions.model_dump_json(),
                doc.progress.model_dump_json(), spec.note,
            ),
        )
        for ord_, lane in enumerate(spec.lanes):
            self.conn.execute(
                "INSERT INTO series_lanes (series_id, lane_id, ord, name, colour, family, "
                "production, spec_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (doc.id, lane.id, ord_, lane.name, lane.colour, lane.family,
                 int(lane.production), lane.model_dump_json()),
            )
        for frame in doc.frames:
            self._write_frame(doc.id, frame)
        self.conn.commit()

    def list(self, ticker: str | None = None) -> list[SeriesSummary]:
        """Newest first; ``ticker`` filters case-insensitively."""
        sql = ("SELECT id, name, ticker, source, mode, status, created_ts, progress_json "
               "FROM series")
        args: list = []
        if ticker:
            sql += " WHERE UPPER(ticker) = ?"
            args.append(ticker.upper())
        sql += " ORDER BY created_ts DESC, id DESC"
        out = []
        for sid, name, tk, source, mode, status, created, progress_json in self.conn.execute(
            sql, args
        ):
            counts = self.conn.execute(
                "SELECT COUNT(*), SUM(status = 'ready') FROM series_frames WHERE series_id = ?",
                (sid,),
            ).fetchone()
            n_lanes = self.conn.execute(
                "SELECT COUNT(*) FROM series_lanes WHERE series_id = ?", (sid,)
            ).fetchone()[0]
            out.append(SeriesSummary(
                id=sid, name=name, ticker=tk, source=source, mode=mode, status=status,
                createdTs=created, nFrames=int(counts[0] or 0),
                nFramesReady=int(counts[1] or 0), nLanes=int(n_lanes),
            ))
        return out

    def get(self, series_id: str) -> SeriesDoc | None:
        row = self.conn.execute(
            "SELECT id, created_ts, updated_ts, spec_json, base_fit_json, base_options_json, "
            "progress_json FROM series WHERE id = ?",
            (series_id,),
        ).fetchone()
        if row is None:
            return None
        sid, created, updated, spec_json, fit_json, opt_json, progress_json = row
        return SeriesDoc(
            id=sid, createdTs=created, updatedTs=updated,
            spec=SeriesSpec.model_validate_json(spec_json),
            baseFit=FitSettings.model_validate_json(fit_json),
            baseOptions=OptionsSettings.model_validate_json(opt_json),
            progress=(SeriesProgress.model_validate_json(progress_json)
                      if progress_json else SeriesProgress()),
            frames=self.frames(sid),
        )

    def exists(self, series_id: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM series WHERE id = ?", (series_id,)
        ).fetchone() is not None

    def delete(self, series_id: str) -> bool:
        """Delete the series (lanes / frames / fits cascade) and the snapshot
        rows it OWNS (``snapshots.series_id``) with their quotes. False when
        the id is unknown."""
        if not self.exists(series_id):
            return False
        owned = [r[0] for r in self.conn.execute(
            "SELECT id FROM snapshots WHERE series_id = ?", (series_id,)
        )]
        self.conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
        for sid in owned:
            self.conn.execute("DELETE FROM quotes WHERE snapshot_id = ?", (sid,))
            self.conn.execute("DELETE FROM snapshots WHERE id = ?", (sid,))
        self.conn.commit()
        return True

    def set_progress(self, series_id: str, progress: SeriesProgress,
                     error: str | None = None) -> None:
        """Checkpoint the runner's counters + status (``updated_ts`` = now)."""
        progress = progress.model_copy(update={"updatedTs": now_iso()})
        self.conn.execute(
            "UPDATE series SET status = ?, progress_json = ?, updated_ts = ?, error = ? "
            "WHERE id = ?",
            (progress.status, progress.model_dump_json(), progress.updatedTs,
             error, series_id),
        )
        self.conn.commit()

    # ----------------------------------------------------------------- lanes

    def lanes(self, series_id: str) -> list[LaneSpec]:
        return [
            LaneSpec.model_validate_json(r[0]) for r in self.conn.execute(
                "SELECT spec_json FROM series_lanes WHERE series_id = ? ORDER BY ord",
                (series_id,),
            )
        ]

    def lane_filter(self, series_id: str, lane_id: str) -> dict | None:
        """The lane's persisted filter rings (``filter_history.step_doc``
        shape per node), or None."""
        row = self.conn.execute(
            "SELECT filter_json FROM series_lanes WHERE series_id = ? AND lane_id = ?",
            (series_id, lane_id),
        ).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def set_lane_filter(self, series_id: str, lane_id: str, doc: dict | None) -> None:
        self.conn.execute(
            "UPDATE series_lanes SET filter_json = ? WHERE series_id = ? AND lane_id = ?",
            (json.dumps(doc) if doc is not None else None, series_id, lane_id),
        )
        self.conn.commit()

    # ---------------------------------------------------------------- frames

    def _write_frame(self, series_id: str, frame: FrameDoc) -> None:
        self.conn.execute(
            "INSERT INTO series_frames (series_id, idx, ts, snapshot_id, spot, quote_kind, "
            "n_quotes, expiries_json, status, error, harvested_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(series_id, idx) DO UPDATE SET ts = excluded.ts, "
            "snapshot_id = excluded.snapshot_id, spot = excluded.spot, "
            "quote_kind = excluded.quote_kind, n_quotes = excluded.n_quotes, "
            "expiries_json = excluded.expiries_json, status = excluded.status, "
            "error = excluded.error, harvested_ts = excluded.harvested_ts",
            (
                series_id, frame.idx, frame.ts, frame.snapshotId, frame.spot,
                frame.quoteKind, frame.nQuotes,
                json.dumps({"expiries": frame.expiries, "warmup": frame.warmup}),
                frame.status, frame.error, frame.harvestedTs,
            ),
        )

    def put_frame(self, series_id: str, frame: FrameDoc) -> None:
        """Insert or update one frame (the harvest checkpoint)."""
        self._write_frame(series_id, frame)
        self.conn.commit()

    def frames(self, series_id: str) -> list[FrameDoc]:
        out = []
        for (idx, ts, snapshot_id, spot, quote_kind, n_quotes, expiries_json, status,
             error, harvested) in self.conn.execute(
            "SELECT idx, ts, snapshot_id, spot, quote_kind, n_quotes, expiries_json, "
            "status, error, harvested_ts FROM series_frames WHERE series_id = ? ORDER BY idx",
            (series_id,),
        ):
            ex = json.loads(expiries_json or "{}")
            if isinstance(ex, list):  # tolerate a bare list
                ex = {"expiries": ex, "warmup": False}
            out.append(FrameDoc(
                idx=idx, ts=ts, snapshotId=snapshot_id, spot=spot, quoteKind=quote_kind,
                nQuotes=int(n_quotes or 0), expiries=list(ex.get("expiries", [])),
                warmup=bool(ex.get("warmup", False)), status=status, error=error,
                harvestedTs=harvested,
            ))
        return out

    def frame(self, series_id: str, idx: int) -> FrameDoc | None:
        return next((f for f in self.frames(series_id) if f.idx == idx), None)

    def frame_chain(self, series_id: str, idx: int) -> ChainSnapshot | None:
        """The frame's stored chain (None when the frame has no snapshot yet)."""
        row = self.conn.execute(
            "SELECT snapshot_id FROM series_frames WHERE series_id = ? AND idx = ?",
            (series_id, idx),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return self.store.load_snapshot(int(row[0]))

    # ------------------------------------------------------------------ fits

    def save_fit(self, series_id: str, fit: LaneFitDoc) -> None:
        """Upsert one (lane, frame, expiry) fit; ``expiry`` None → '' (LV)."""
        self.conn.execute(
            "INSERT INTO series_fits (series_id, lane_id, idx, expiry, model, params_json, "
            "display_json, diagnostics_json, metrics_json, fit_ms, status, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(series_id, lane_id, idx, expiry) DO UPDATE SET model = excluded.model, "
            "params_json = excluded.params_json, display_json = excluded.display_json, "
            "diagnostics_json = excluded.diagnostics_json, metrics_json = excluded.metrics_json, "
            "fit_ms = excluded.fit_ms, status = excluded.status, error = excluded.error",
            (
                series_id, fit.laneId, fit.idx, fit.expiry or "", fit.model,
                json.dumps(fit.params), json.dumps(fit.display) if fit.display is not None
                else None, json.dumps(fit.diagnostics), json.dumps(fit.metrics), fit.fitMs,
                fit.status, fit.error,
            ),
        )
        self.conn.commit()

    def save_fits(self, series_id: str, fits) -> None:
        """Upsert several fits in ONE transaction (a lane's frame lands as one
        commit — the runner's checkpoint; a 390-frame fill in the rails)."""
        for fit in fits:
            self.conn.execute(
                "INSERT INTO series_fits (series_id, lane_id, idx, expiry, model, params_json, "
                "display_json, diagnostics_json, metrics_json, fit_ms, status, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(series_id, lane_id, idx, expiry) DO UPDATE SET model = excluded.model, "
                "params_json = excluded.params_json, display_json = excluded.display_json, "
                "diagnostics_json = excluded.diagnostics_json, metrics_json = excluded.metrics_json, "
                "fit_ms = excluded.fit_ms, status = excluded.status, error = excluded.error",
                (
                    series_id, fit.laneId, fit.idx, fit.expiry or "", fit.model,
                    json.dumps(fit.params),
                    json.dumps(fit.display) if fit.display is not None else None,
                    json.dumps(fit.diagnostics), json.dumps(fit.metrics), fit.fitMs,
                    fit.status, fit.error,
                ),
            )
        self.conn.commit()

    def fits(self, series_id: str, idx: int | None = None,
             lane_id: str | None = None) -> list[LaneFitDoc]:
        sql = ("SELECT lane_id, idx, expiry, model, params_json, display_json, "
               "diagnostics_json, metrics_json, fit_ms, status, error FROM series_fits "
               "WHERE series_id = ?")
        args: list = [series_id]
        if idx is not None:
            sql += " AND idx = ?"
            args.append(idx)
        if lane_id is not None:
            sql += " AND lane_id = ?"
            args.append(lane_id)
        sql += " ORDER BY idx, lane_id, expiry"
        return [
            LaneFitDoc(
                laneId=lane, idx=i, expiry=expiry or None, model=model,
                params=json.loads(params), display=json.loads(display) if display else None,
                diagnostics=json.loads(diag or "{}"), metrics=json.loads(metrics or "{}"),
                fitMs=fit_ms, status=status, error=error,
            )
            for lane, i, expiry, model, params, display, diag, metrics, fit_ms, status, error
            in self.conn.execute(sql, args)
        ]

    def reset_fits(self, series_id: str) -> int:
        """Drop every stored fit and every lane carry of a series and rewind
        its progress counters — a re-run then calibrates every frame again
        (the determinism check; a future "Recalibrate lanes" verb). Returns
        the number of fit rows dropped."""
        n = int(self.conn.execute(
            "SELECT COUNT(*) FROM series_fits WHERE series_id = ?", (series_id,)
        ).fetchone()[0])
        self.conn.execute("DELETE FROM series_fits WHERE series_id = ?", (series_id,))
        self.conn.execute("UPDATE series_lanes SET filter_json = NULL WHERE series_id = ?",
                          (series_id,))
        doc = self.get(series_id)
        if doc is not None:
            self.set_progress(series_id, doc.progress.model_copy(update={
                "status": "draft", "fitsDone": 0, "fitsTotal": 0, "current": None, "error": None,
            }))
        self.conn.commit()
        return n

    def count_fits(self, series_id: str, status: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM series_fits WHERE series_id = ?"
        args: list = [series_id]
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        return int(self.conn.execute(sql, args).fetchone()[0])

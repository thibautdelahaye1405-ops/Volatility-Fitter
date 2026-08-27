"""Filter-replay artifact routes (V3.9 rider): serve the OFFLINE replay.

``python -m backtest.filter_replay`` drives the production commit path over
stored intraday chains and writes, under :data:`FILTER_REPLAY_DIR`, one JSON
part per (ticker, day) plus a ``filter_replay.html`` evidence page. These
routes only serve those files so the Prior Evidence panel and the
FilterTimeline can link / render the latest replay — the
``/graph/benchmark/artifact`` precedent, nothing is computed here:

* ``GET /filter/replay/artifact``            — the newest ``*.html`` (404 + hint);
* ``GET /filter/replay/parts?ticker=``       — part metadata, newest first;
* ``GET /filter/replay/parts/{ticker}/{day}`` — one part document verbatim.

``FILTER_REPLAY_DIR`` is module-level so tests point it at a temp dir.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from volfit.api.schemas_filter_replay import (
    FilterReplayPartMeta,
    FilterReplayPartsResponse,
)

router = APIRouter(tags=["filter-replay"])

#: Where ``backtest.filter_replay`` writes its parts + page by default
#: (``backtest/results/filter_replay`` under backend/). Module-level so tests
#: can monkeypatch it (the BENCHMARK_ARTIFACT_DIR idiom).
FILTER_REPLAY_DIR = (
    Path(__file__).resolve().parents[3] / "backtest" / "results" / "filter_replay"
)

_RUN_HINT = "run python -m backtest.filter_replay (from backend/)"


# ------------------------------------------------------------------ helpers
def _read_part(path: Path) -> dict | None:
    """The part document, or None when the file is not a readable
    ``{"meta": ..., "nodes": ...}`` JSON object (skipped, never fatal)."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), dict):
        return None
    return doc


def _meta_of(path: Path, doc: dict) -> FilterReplayPartMeta | None:
    """Listing row from a part; the ``<TICKER>_<day>`` file stem backs any
    missing meta field. None when neither yields a ticker/day."""
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    stem_ticker, _, stem_day = path.stem.rpartition("_")
    ticker = str(meta.get("ticker") or stem_ticker or "")
    day = str(meta.get("day") or stem_day or "")
    if not ticker or not day:
        return None
    try:
        n_instants = int(meta.get("nInstants", 0))
    except (TypeError, ValueError):
        n_instants = 0
    return FilterReplayPartMeta(
        ticker=ticker,
        day=day,
        nInstants=n_instants,
        fitMode=str(meta.get("fitMode") or "mid"),
        filterMode=str(meta.get("filterMode") or "overlay"),
        expiries=sorted(str(k) for k in doc["nodes"]),
        mtime=float(path.stat().st_mtime),
    )


def _part_path(ticker: str, day: str) -> Path:
    """The part file for (ticker, day); rejects anything that is not a bare
    ticker + ISO date (no path components ever reach the filesystem)."""
    try:
        day_iso = date.fromisoformat(day).isoformat()
    except ValueError:
        raise HTTPException(status_code=404, detail=f"malformed day {day!r}") from None
    tk = ticker.strip().upper()
    if not tk or any(ch in tk for ch in "/\\") or ".." in tk:
        raise HTTPException(status_code=404, detail=f"malformed ticker {ticker!r}")
    return FILTER_REPLAY_DIR / f"{tk}_{day_iso}.json"


# ------------------------------------------------------------------- routes
@router.get("/filter/replay/artifact")
def filter_replay_artifact() -> FileResponse:
    """The newest offline filter-replay HTML page; 404 until a replay ran."""
    candidates = (
        sorted(FILTER_REPLAY_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime)
        if FILTER_REPLAY_DIR.is_dir()
        else []
    )
    if not candidates:
        raise HTTPException(
            status_code=404, detail=f"no filter-replay artifact — {_RUN_HINT}"
        )
    return FileResponse(candidates[-1], media_type="text/html")


@router.get("/filter/replay/parts", response_model=FilterReplayPartsResponse)
def filter_replay_parts(ticker: str | None = None) -> FilterReplayPartsResponse:
    """Replay parts NEWEST FIRST (replayed day desc, then mtime desc),
    optionally filtered to one ticker (case-insensitive). Unreadable or
    malformed files are skipped; no directory = an empty list."""
    if not FILTER_REPLAY_DIR.is_dir():
        return FilterReplayPartsResponse(parts=[])
    want = ticker.strip().upper() if ticker else None
    rows: list[FilterReplayPartMeta] = []
    for path in FILTER_REPLAY_DIR.glob("*.json"):
        doc = _read_part(path)
        if doc is None:
            continue
        row = _meta_of(path, doc)
        if row is None or (want is not None and row.ticker.upper() != want):
            continue
        rows.append(row)
    rows.sort(key=lambda r: (r.day, r.mtime), reverse=True)
    return FilterReplayPartsResponse(parts=rows)


@router.get("/filter/replay/parts/{ticker}/{day}")
def filter_replay_part(ticker: str, day: str) -> JSONResponse:
    """One part document VERBATIM (``meta`` + ``nodes`` of wire-shape steps);
    404 when absent or unreadable."""
    path = _part_path(ticker, day)
    doc = _read_part(path) if path.is_file() else None
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"no filter-replay part for {ticker.upper()} {day} — {_RUN_HINT}",
        )
    return JSONResponse(content=doc)

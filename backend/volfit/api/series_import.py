"""Import stored snapshots as a series (SERIES ARC S1, roadmap §3.1 "Import").

Three sources, ONE loader: the app's own captures of the ticker (the frames
REFERENCE the capture rows — nothing is copied and deleting the series
leaves the captures alone), another VolStore file (a backtest campaign
store such as the 0DTE ``intraday.sqlite`` or the V3.8 ``replay_day.sqlite``
— chains are copied in as series-owned frames), and a fixture file or
directory in either capture shape — the intraday one (``{asset, day,
exercise_style, expiries, snapshots: [{ts, spot, quotes}]}``) or the daily
one (``{asset, as_of, snapshot_ts_utc, exercise_style, spot, quotes}``).
Fixture quotes are stamped the way ``capture_intraday._persist_db`` stamps
them (US tick, per-expiry settlement, size → open interest) so the chains
price exactly as a captured replay would.

The clock of an imported series is DERIVED (the nearest step to the median
gap, the frame count) so the spec validates and the lens can label the
scrubber; the ladder follows D6 (pinned = the union of the frames'
expiries, or the caller's list, cropped nearest-first by ``maxExpiries``).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Iterator, Literal

from pydantic import BaseModel, Field

from volfit.api.schemas import FitMode
from volfit.api.schemas_series import (
    DEFAULT_FRAME_BUDGET_S,
    FrameDoc,
    LaneSpec,
    SeriesClock,
    SeriesDoc,
    SeriesLadder,
    SeriesProgress,
    SeriesSpec,
)
from volfit.api.series_presets import lane_preset
from volfit.api.series_store import SeriesStore, new_series_id, now_iso
from volfit.data.expiry_time import default_settlement
from volfit.data.store import VolStore
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote


class ImportSource(BaseModel):
    """Where the frames come from. ``path`` = the VolStore file (``store``)
    or a fixture file / directory (``fixtures``); ``start`` / ``end`` bound
    the instants; ``maxFrames`` keeps the first n in time."""

    kind: Literal["captures", "store", "fixtures"]
    path: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    maxFrames: int | None = Field(default=None, ge=1)


class SeriesImportRequest(BaseModel):
    """POST /series/import-store. Lanes come as explicit specs or as preset
    ids (``presets``); neither = the ``current`` preset (the live Options
    verbatim). ``fitMode`` None = the live Options' fit target."""

    name: str = Field(min_length=1, max_length=120)
    ticker: str = Field(min_length=1)
    source: ImportSource
    lanes: list[LaneSpec] | None = None
    presets: list[str] = []
    fitMode: FitMode | None = None
    ladder: SeriesLadder | None = None
    #: The (lane, frame) wall-clock cap (SeriesSpec.frameBudgetSeconds).
    frameBudgetSeconds: int | None = Field(default=DEFAULT_FRAME_BUDGET_S, ge=5, le=86_400)
    note: str = ""


class ImportError_(ValueError):
    """A source that cannot be read (bad path, unknown shape, no frames)."""


# ---------------------------------------------------------------- readers
#: A reader yields (timestamp, chain, snapshot_id) — the id is set only when
#: the chain is already a row of the APP store (captures), else None.
Instant = tuple[datetime, ChainSnapshot | None, int | None]


def _within(ts: datetime, src: ImportSource) -> bool:
    return (src.start is None or ts >= src.start) and (src.end is None or ts <= src.end)


def _read_captures(app_store: VolStore, ticker: str, source_id: str | None,
                   src: ImportSource) -> Iterator[Instant]:
    """The app's own captures of the ticker (this source's, newest first in
    the store → yielded oldest first). Legacy untagged rows are offered too
    when the ticker has no pinned source."""
    rows = app_store.list_snapshots([ticker], source=source_id)
    for _tk, sid, ts in sorted(rows, key=lambda r: r[2]):
        if _within(ts, src):
            yield ts, None, sid


def _read_store(ticker: str, src: ImportSource) -> Iterator[Instant]:
    if not src.path or not os.path.isfile(src.path):
        raise ImportError_(f"store file not found: {src.path!r}")
    with VolStore(src.path) as vs:
        rows = vs.list_snapshots([ticker], include_series=True)
        for _tk, sid, ts in sorted(rows, key=lambda r: r[2]):
            if _within(ts, src):
                yield ts, vs.load_snapshot(sid), None


def _fixture_files(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise ImportError_(f"fixture path not found: {path!r}")
    out = []
    for root, _dirs, files in os.walk(path):
        out += [os.path.join(root, f) for f in files if f.lower().endswith(".json")]
    return sorted(out)


def _settlement(doc: dict, ticker: str, expiries: set[date]) -> dict:
    """Per CONTRACT root when the fixture's ``meta.expiryRoots`` says which
    root listed each expiry, else the ticker's default (the capture rule)."""
    roots = (doc.get("meta") or {}).get("expiryRoots") or {}
    return {e: default_settlement(e, roots.get(e.isoformat(), ticker)) for e in sorted(expiries)}


def _quotes(doc: dict, ticker: str, ts: datetime, rows: list[dict]) -> list[OptionQuote]:
    return [
        OptionQuote(
            ticker=ticker, expiry=date.fromisoformat(q["expiry"]), strike=float(q["strike"]),
            call_put=q["cp"], bid=q.get("bid"), ask=q.get("ask"), last=None, volume=None,
            open_interest=q.get("size", q.get("ask_size")), timestamp=ts,
        )
        for q in rows
    ]


def _chain(doc: dict, ticker: str, ts: datetime, spot: float, rows: list[dict]) -> ChainSnapshot:
    quotes = _quotes(doc, ticker, ts, rows)
    return ChainSnapshot(
        ticker=ticker, spot=float(spot), timestamp=ts, quotes=quotes,
        exercise_style=doc.get("exercise_style", "american"), tick_size=US_OPTION_TICK,
        settlement=_settlement(doc, ticker, {q.expiry for q in quotes}),
    )


def _read_fixtures(ticker: str, src: ImportSource) -> Iterator[Instant]:
    """Both capture shapes; files of other tickers / unknown shapes are
    skipped (a directory may hold a whole campaign)."""
    if not src.path:
        raise ImportError_("fixtures need a path")
    for path in _fixture_files(src.path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or str(doc.get("asset", "")).upper() != ticker.upper():
            continue
        if isinstance(doc.get("snapshots"), list):  # intraday shape
            for snap in doc["snapshots"]:
                ts = datetime.fromisoformat(snap["ts"])
                if _within(ts, src):
                    yield ts, _chain(doc, ticker, ts, snap["spot"], snap["quotes"]), None
        elif "snapshot_ts_utc" in doc:  # daily shape
            ts = datetime.fromisoformat(doc["snapshot_ts_utc"])
            if _within(ts, src):
                yield ts, _chain(doc, ticker, ts, doc["spot"], doc["quotes"]), None


def read_instants(app_store: VolStore, ticker: str, source_id: str | None,
                  src: ImportSource) -> list[Instant]:
    """The source's instants of the ticker, oldest first, one per timestamp,
    bounded by ``start`` / ``end`` / ``maxFrames``."""
    if src.kind == "captures":
        it = _read_captures(app_store, ticker, source_id, src)
    elif src.kind == "store":
        it = _read_store(ticker, src)
    else:
        it = _read_fixtures(ticker, src)
    seen: set[datetime] = set()
    out: list[Instant] = []
    for ts, chain, sid in sorted(it, key=lambda r: r[0]):
        if ts in seen:
            continue
        seen.add(ts)
        out.append((ts, chain, sid))
        if src.maxFrames is not None and len(out) >= src.maxFrames:
            break
    return out


# ----------------------------------------------------------------- shaping

def quote_kind_of(chain: ChainSnapshot) -> str:
    """The chain's label, or ``marks`` when every two-sided quote is a
    single mark (the store keeps no label — a reloaded marks chain says
    ``quotes``)."""
    if chain.quote_kind != "quotes":
        return chain.quote_kind
    two_sided = [q for q in chain.quotes if q.bid is not None and q.ask is not None]
    if two_sided and all(q.bid == q.ask for q in two_sided):
        return "marks"
    return "quotes"


def frame_expiries(chain: ChainSnapshot, ladder: SeriesLadder) -> list[str]:
    """The frame's expiries under the ladder: alive at the instant, in the
    pinned list when one is given, cropped nearest-first by ``maxExpiries``."""
    day = chain.timestamp.date()
    alive = sorted(e for e in chain.expiries() if e >= day)
    if ladder.policy == "pinned" and ladder.expiries:
        want = {date.fromisoformat(e) for e in ladder.expiries}
        alive = [e for e in alive if e in want]
    if ladder.maxExpiries is not None:
        alive = alive[: ladder.maxExpiries]
    return [e.isoformat() for e in alive]


def derive_clock(instants: list[datetime]) -> SeriesClock:
    """The nearest step to the median gap (calendar steps past a day)."""
    gaps = sorted((b - a).total_seconds() for a, b in zip(instants, instants[1:]))
    median = gaps[len(gaps) // 2] if gaps else 900.0
    if median >= 5 * 86400:
        step = "weekly"
    elif median >= 0.5 * 86400:
        step = "daily"
    else:
        step = min(("1m", "5m", "15m", "30m", "1h"),
                   key=lambda s: abs({"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                                      "1h": 3600}[s] - median))
    return SeriesClock(start=instants[0], step=step, count=len(instants), sessionOnly=False)


def _resolve_lanes(req: SeriesImportRequest, base_fit) -> list[LaneSpec]:
    if req.lanes:
        return list(req.lanes)
    presets = req.presets or ["current"]
    try:
        return [lane_preset(p, base_fit) for p in presets]
    except KeyError as exc:
        raise ImportError_(f"unknown lane preset {exc.args[0]!r}") from None


# ------------------------------------------------------------------- import

def import_series(state, req: SeriesImportRequest) -> SeriesDoc:
    """Create a series from stored snapshots; returns the stored document.
    Raises ``ImportError_`` on an unreadable source or an empty selection
    and ``RuntimeError`` when the app has no store (VOLFIT_DB unset)."""
    if state.store_path is None:
        raise RuntimeError("series need a store: set VOLFIT_DB")
    ticker = req.ticker.upper()
    base_fit, base_options = state.fit_settings(), state.options()
    source_id = state.source_of(ticker) if req.source.kind == "captures" else None
    with VolStore(state.store_path) as app_store:
        instants = read_instants(app_store, ticker, source_id, req.source)
        if not instants:
            raise ImportError_(f"no stored snapshots of {ticker} match the selection")
        sid = new_series_id()
        # Resolve every chain first (captures load by id) so the ladder can
        # read the union of expiries before any frame is written.
        chains = [(ts, chain if chain is not None else app_store.load_snapshot(int(snap_id)),
                   snap_id) for ts, chain, snap_id in instants]
        ladder = req.ladder or SeriesLadder()
        if ladder.policy == "pinned" and not ladder.expiries:
            union = sorted({e for _ts, ch, _id in chains for e in ch.expiries()})
            ladder = ladder.model_copy(update={"expiries": [e.isoformat() for e in union]})
        spec = SeriesSpec(
            name=req.name, ticker=ticker, mode="import",
            source=(source_id if req.source.kind == "captures"
                    else f"import:{os.path.basename(req.source.path or '')}"),
            clock=derive_clock([ts for ts, _c, _i in chains]), ladder=ladder,
            fitMode=req.fitMode or base_options.fitMode,
            lanes=_resolve_lanes(req, base_fit), frameBudgetSeconds=req.frameBudgetSeconds,
            note=req.note,
        )
        stamp = now_iso()
        frames = []
        for idx, (ts, chain, snap_id) in enumerate(chains):
            if snap_id is None:  # a copied chain becomes a series-OWNED row
                snap_id = app_store.save_snapshot(chain, source=spec.source, series_id=sid)
            frames.append(FrameDoc(
                idx=idx, ts=ts.isoformat(), snapshotId=int(snap_id), spot=float(chain.spot),
                quoteKind=quote_kind_of(chain), nQuotes=len(chain.quotes),
                expiries=frame_expiries(chain, ladder), status="ready", harvestedTs=stamp,
            ))
        doc = SeriesDoc(
            id=sid, createdTs=stamp, updatedTs=stamp, spec=spec, baseFit=base_fit,
            baseOptions=base_options, frames=frames,
            progress=SeriesProgress(status="draft", framesTotal=len(frames),
                                    framesReady=len(frames), startedTs=stamp, updatedTs=stamp),
        )
        series = SeriesStore(app_store)
        series.create(doc)
        stored = series.get(sid)
    assert stored is not None
    return stored

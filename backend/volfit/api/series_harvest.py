"""Harvest one frame of a series (SERIES ARC S2, roadmap §3.2).

Historical: the ticker's provider is asked for the chain AS OF the frame's
instant through the same ``AsOf`` the as-of picker uses (``intraday`` on
Massive, ``eod`` on an EOD-only source), the download narrated into the
activity gauge; nothing of the live workspace moves. Live: the frame IS the
app's refreshed chain — ``state.refresh_chain`` reads quotes AND spot from
one snapshot (the book when the ticker streams, else a request), exactly
the unified fetch of the 2026-09-02g data model, so the desk sees the same
quotes the frame stores. Either way the chain is cropped to the ladder,
saved as a series-OWNED snapshot row and the frame checkpointed.
"""

from __future__ import annotations

from datetime import date, datetime

from volfit.api.schemas_series import FrameDoc, SeriesDoc
from volfit.api.series_import import quote_kind_of
from volfit.api.series_instants import frame_asof, ladder_expiries
from volfit.api.series_store import SeriesStore, now_iso
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot


def _crop(chain: ChainSnapshot, expiries) -> ChainSnapshot:
    want = set(expiries)
    kept = [q for q in chain.quotes if q.expiry in want]
    return ChainSnapshot(
        ticker=chain.ticker, spot=chain.spot, timestamp=chain.timestamp, quotes=kept,
        exercise_style=chain.exercise_style, zero_carry=chain.zero_carry,
        quote_kind=chain.quote_kind, tick_size=chain.tick_size,
        settlement=({e: s for e, s in chain.settlement.items() if e in want}
                    if chain.settlement else None),
    )


def fetch_frame_chain(state, doc: SeriesDoc, frame: FrameDoc, label: str = "") -> ChainSnapshot:
    """The chain of one frame from the source (historical) or the app's
    refreshed chain (live). Raises on a feed failure — the caller records
    the frame as failed."""
    spec = doc.spec
    ticker = spec.ticker
    ts = datetime.fromisoformat(frame.ts)
    if spec.mode == "live":
        state.refresh_chain(ticker)  # quotes + spot from ONE snapshot (book or request)
        chain = state.snapshot(ticker)
        # A live frame is stamped at the instant it was taken (the chain's own
        # timestamp), not the scheduled one — the scrubber shows the truth.
        return chain
    prov = state.provider_for(ticker)
    asof = frame_asof(prov, ts, spec.clock.step, spec.mode)
    if asof is None:
        raise RuntimeError(f"{state.source_of(ticker)!r} cannot serve {ticker} at {frame.ts}")
    pinned = None
    if spec.ladder.policy == "pinned" and spec.ladder.expiries:
        listed = [date.fromisoformat(e) for e in spec.ladder.expiries]
        pinned = ladder_expiries(listed, ts, spec.ladder) or None  # alive at the instant
    with state.activity.activity("series", label or f"Harvesting {ticker} · {frame.ts}"):
        return prov.fetch_chain(ticker, pinned, as_of=asof)


def harvest_frame(state, doc: SeriesDoc, frame: FrameDoc, label: str = "") -> FrameDoc:
    """Fetch, crop, persist and checkpoint one frame; a failure is recorded
    on the frame (status ``failed`` + error) and never raised."""
    spec = doc.spec
    try:
        chain = fetch_frame_chain(state, doc, frame, label)
        ts = chain.timestamp if spec.mode == "live" else datetime.fromisoformat(frame.ts)
        expiries = ladder_expiries(chain.expiries(), ts, spec.ladder)
        chain = _crop(chain, expiries)
        if not chain.quotes:
            raise RuntimeError("no quotes on the ladder at this instant")
        with VolStore(state.store_path) as store:
            snap_id = store.save_snapshot(chain, source=spec.source, series_id=doc.id)
            done = frame.model_copy(update={
                "ts": chain.timestamp.isoformat() if spec.mode == "live" else frame.ts,
                "snapshotId": snap_id, "spot": float(chain.spot),
                "quoteKind": quote_kind_of(chain), "nQuotes": len(chain.quotes),
                "expiries": [e.isoformat() for e in expiries], "status": "ready",
                "error": None, "harvestedTs": now_iso(),
            })
            SeriesStore(store).put_frame(doc.id, done)
        return done
    except Exception as exc:  # noqa: BLE001 — one bad frame never kills the harvest
        failed = frame.model_copy(update={"status": "failed", "error": str(exc)[:300],
                                          "harvestedTs": now_iso()})
        with VolStore(state.store_path) as store:
            SeriesStore(store).put_frame(doc.id, failed)
        return failed

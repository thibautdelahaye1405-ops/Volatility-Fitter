"""Create a series from a spec: resolve the instants, judge servability,
freeze the live settings, write the pending frames (SERIES ARC S2).

The estimate (``POST /series/estimate``) and the creation (``POST /series``)
share one resolution so what the dialog showed is what the job runs. The
pinned ladder is filled from the ticker's universe selection at creation
(D6); the base settings are the live Options / fit settings at that moment
(D3) — the lanes patch them, the live desk is never read again.
"""

from __future__ import annotations

from datetime import datetime, timezone

from volfit.api.schemas_series import (
    FrameDoc,
    SeriesCreateResponse,
    SeriesDoc,
    SeriesEstimate,
    SeriesProgress,
    SeriesSpec,
)
from volfit.api.series_instants import estimate as _estimate
from volfit.api.series_instants import resolve_instants, servable
from volfit.api.series_store import SeriesStore, new_series_id, now_iso
from volfit.data.store import VolStore


class SeriesSpecError(ValueError):
    """A spec the app cannot run (no instants, no servable frame, an unknown
    ticker, a source without history)."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _pinned(state, spec: SeriesSpec) -> SeriesSpec:
    """Fill a pinned ladder from the ticker's universe selection."""
    if spec.ladder.policy != "pinned" or spec.ladder.expiries:
        return spec
    chosen = state.selected_expiries(spec.ticker)
    ladder = spec.ladder.model_copy(update={"expiries": [e.isoformat() for e in chosen]})
    return spec.model_copy(update={"ladder": ladder})


def resolve(state, spec: SeriesSpec, now_utc: datetime | None = None):
    """(spec with the ladder filled, instants, servability flags, estimate)."""
    now_utc = now_utc or utcnow()
    ticker = spec.ticker.upper()
    if ticker not in state.active_tickers():
        raise SeriesSpecError(f"{ticker!r} is not in the universe — add it first")
    spec = spec.model_copy(update={"ticker": ticker, "tickers": [ticker]})
    if spec.source is None:
        spec = spec.model_copy(update={"source": state.source_of(ticker)})
    spec = _pinned(state, spec)
    prov = state.provider_for(ticker)
    instants = resolve_instants(spec.clock, spec.mode, now_utc)
    flags = [servable(prov, ticker, ts, spec.clock.step, spec.mode, now_utc)
             for ts, _w in instants]
    n_exp = len(spec.ladder.expiries) if spec.ladder.expiries else 6
    est = _estimate(spec, spec.source, instants, flags, n_exp, now_utc)
    est.warnings.extend(lane_warnings(state, spec))
    return spec, instants, flags, est


def lane_warnings(state, spec: SeriesSpec) -> list[str]:
    """What a lane combination is known to cost (recorded findings): the
    ACTIVE observation filter under the calendar-coupled solver on a sub-day
    series — its per-node predictions are not calendar-consistent across a
    dense ladder, so the symmetric repair grinds through its escalations
    (minutes per frame, 2026-09-10 on the 0DTE store)."""
    out: list[str] = []
    base = state.options()
    for lane in spec.lanes:
        opts = {**base.model_dump(), **lane.patchOptions}
        if (opts.get("observationFilterMode") == "active" and opts.get("enforceCalendar")
                and spec.clock.step_seconds is not None):
            out.append(f"lane {lane.name!r}: the active filter under the calendar-coupled "
                       "solver can take minutes per frame on a dense intraday ladder "
                       "(set enforceCalendar off on the lane, or use the overlay filter)")
    return out


def estimate(state, spec: SeriesSpec, now_utc: datetime | None = None) -> SeriesEstimate:
    return resolve(state, spec, now_utc)[3]


def create_series(state, spec: SeriesSpec, now_utc: datetime | None = None) -> SeriesCreateResponse:
    """Persist a new series with every frame pending (unservable instants are
    written as ``skipped`` so the index keeps the clock's shape)."""
    if state.store_path is None:
        raise RuntimeError("series need a store: set VOLFIT_DB")
    if spec.mode == "import":
        raise SeriesSpecError("an import series is created through /series/import-store")
    spec, instants, flags, est = resolve(state, spec, now_utc)
    if not instants:
        raise SeriesSpecError("the clock resolves to no instant")
    if not any(ok for ok, _r in flags):
        reasons = sorted({r for _ok, r in flags if r})
        raise SeriesSpecError("no instant can be served: " + "; ".join(reasons))
    stamp = now_iso()
    frames = [
        FrameDoc(idx=i, ts=ts.isoformat(), warmup=warm,
                 status="pending" if ok else "skipped", error=None if ok else reason)
        for i, ((ts, warm), (ok, reason)) in enumerate(zip(instants, flags))
    ]
    doc = SeriesDoc(
        id=new_series_id(), createdTs=stamp, updatedTs=stamp, spec=spec,
        baseFit=state.fit_settings(), baseOptions=state.options(), frames=frames,
        progress=SeriesProgress(status="draft", framesTotal=len(frames), updatedTs=stamp),
    )
    with VolStore(state.store_path) as store:
        SeriesStore(store).create(doc)
    state.log_event("series_create", scope=doc.id,
                    payload={"ticker": spec.ticker, "mode": spec.mode, "frames": len(frames),
                             "lanes": [lane.id for lane in spec.lanes]})
    return SeriesCreateResponse(id=doc.id, estimate=est)

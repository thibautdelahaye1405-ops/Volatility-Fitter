"""Series routes (SERIES ARC S1 + S2).

S1: list / get / delete / import-store. S2: estimate, create, the job
controls (start / pause / resume / cancel), the status and its SSE stream
(the ``/calibration/stream`` pattern: push on change, keep-alive comments).
Every route opens the app's VolStore for the request (the ``asof`` /
``history`` idiom) and answers 409 when the app runs without a store
(``VOLFIT_DB`` unset — series are persistent objects by definition). The
frame / strip payloads (S4) join in their phase; the roadmap §6 table is
the contract.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import monotonic

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from volfit.api import series_files
from volfit.api.series_adopt import AdoptError, AdoptPriorRequest, AdoptPriorResult, adopt_prior

from volfit.api.schemas_series import (
    FramePayload,
    LaneSpec,
    SeriesCreateResponse,
    SeriesDoc,
    SeriesEstimate,
    SeriesListResponse,
    SeriesSpec,
    StripPayload,
)
from volfit.api.series_create import SeriesSpecError, create_series, estimate
from volfit.api.series_evidence import (
    EvidencePayload,
    LaneFilterIndex,
    LaneFilterPayload,
    evidence_payload,
    lane_filter_index,
    lane_filter_ring,
)
from volfit.api.series_import import ImportError_, SeriesImportRequest, import_series
from volfit.api.series_jobs import SeriesJobStatus, series_jobs_of
from volfit.api.series_payload import UnknownSeriesError, frame_payload, strip_payload
from volfit.api.series_presets import LANE_PRESET_IDS, lane_preset
from volfit.api.series_store import SeriesStore
from volfit.data.store import VolStore

router = APIRouter(tags=["series"])

_NO_STORE = "series need a store: start the app with VOLFIT_DB set"
_SSE_TICK = 0.25
_SSE_HEARTBEAT = 15.0


def _state(request: Request):
    state = request.app.state.volfit
    if state.store_path is None:
        raise HTTPException(status_code=409, detail=_NO_STORE)
    return state


def _known(state, series_id: str) -> None:
    with VolStore(state.store_path) as store:
        if not SeriesStore(store).exists(series_id):
            raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}")


# ---------------------------------------------------------------- S1 reads

@router.get("/series", response_model=SeriesListResponse)
def list_series(request: Request, ticker: str | None = None) -> SeriesListResponse:
    state = _state(request)
    with VolStore(state.store_path) as store:
        return SeriesListResponse(series=SeriesStore(store).list(ticker))


@router.get("/series/presets", response_model=list[LaneSpec])
def series_presets(request: Request) -> list[LaneSpec]:
    """The eight dialog presets resolved against the LIVE fit settings (S4;
    declared before the id routes so "presets" is never read as an id)."""
    state = request.app.state.volfit
    base = state.fit_settings()
    return [lane_preset(p, base) for p in LANE_PRESET_IDS]


@router.get("/series/{series_id}", response_model=SeriesDoc)
def get_series(series_id: str, request: Request) -> SeriesDoc:
    state = _state(request)
    with VolStore(state.store_path) as store:
        doc = SeriesStore(store).get(series_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}")
    return doc


@router.delete("/series/{series_id}")
def delete_series(series_id: str, request: Request) -> dict:
    state = _state(request)
    jobs = series_jobs_of(state)
    jobs.cancel(series_id)  # a running / queued series is stopped first
    with VolStore(state.store_path) as store:
        ok = SeriesStore(store).delete(series_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}")
    state.log_event("series_delete", scope=series_id)
    return {"deleted": True, "id": series_id}


@router.post("/series/import-store", response_model=SeriesDoc)
def import_store(req: SeriesImportRequest, request: Request) -> SeriesDoc:
    state = _state(request)
    try:
        doc = import_series(state, req)
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    state.log_event("series_import", scope=doc.id,
                    payload={"ticker": doc.spec.ticker, "frames": len(doc.frames),
                             "kind": req.source.kind})
    return doc


# ------------------------------------------------------- S2 create + jobs

@router.post("/series/estimate", response_model=SeriesEstimate)
def estimate_series(spec: SeriesSpec, request: Request) -> SeriesEstimate:
    state = request.app.state.volfit  # an estimate needs no store
    try:
        return estimate(state, spec)
    except (SeriesSpecError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/series", response_model=SeriesCreateResponse)
def post_series(spec: SeriesSpec, request: Request) -> SeriesCreateResponse:
    state = _state(request)
    try:
        return create_series(state, spec)
    except (SeriesSpecError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/series/{series_id}/start", response_model=SeriesJobStatus)
@router.post("/series/{series_id}/resume", response_model=SeriesJobStatus)
def start_series(series_id: str, request: Request) -> SeriesJobStatus:
    state = _state(request)
    _known(state, series_id)
    outcome = series_jobs_of(state).start(series_id)
    if outcome == "busy":
        raise HTTPException(status_code=409, detail="the series is not in a startable state")
    state.log_event("series_start", scope=series_id, payload={"outcome": outcome})
    return series_jobs_of(state).status(series_id)


@router.post("/series/{series_id}/pause", response_model=SeriesJobStatus)
def pause_series(series_id: str, request: Request) -> SeriesJobStatus:
    state = _state(request)
    _known(state, series_id)
    series_jobs_of(state).pause(series_id)
    return series_jobs_of(state).status(series_id)


@router.post("/series/{series_id}/cancel", response_model=SeriesJobStatus)
def cancel_series(series_id: str, request: Request) -> SeriesJobStatus:
    state = _state(request)
    _known(state, series_id)
    series_jobs_of(state).cancel(series_id)
    return series_jobs_of(state).status(series_id)


@router.get("/series/{series_id}/status", response_model=SeriesJobStatus)
def series_status(series_id: str, request: Request) -> SeriesJobStatus:
    state = _state(request)
    _known(state, series_id)
    return series_jobs_of(state).status(series_id)


def _lane_ids(lanes: str | None) -> list[str] | None:
    if lanes is None or not lanes.strip():
        return None
    return [x.strip() for x in lanes.split(",") if x.strip()]


@router.get("/series/{series_id}/frame/{idx}", response_model=FramePayload)
def series_frame(series_id: str, idx: int, request: Request,
                 lanes: str | None = None) -> FramePayload:
    """One frame's market + every requested lane's curves, grid, term points
    and metrics (S4 §3.4; memoized per series / frame / lanes / stored fits)."""
    state = _state(request)
    try:
        return frame_payload(state, series_id, idx, _lane_ids(lanes))
    except UnknownSeriesError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}") from None
    except IndexError:
        raise HTTPException(status_code=404, detail=f"no frame {idx} in series {series_id!r}") from None


@router.get("/series/{series_id}/strip", response_model=StripPayload)
def series_strip(series_id: str, request: Request, lanes: str | None = None,
                 expiry: str | None = None) -> StripPayload:
    """The filmstrip: per frame scalars + per lane per metric one value per frame."""
    state = _state(request)
    try:
        return strip_payload(state, series_id, _lane_ids(lanes), expiry)
    except UnknownSeriesError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}") from None


@router.get("/series/{series_id}/evidence", response_model=EvidencePayload)
def series_evidence(series_id: str, request: Request, lanes: str | None = None,
                    expiry: str | None = None) -> EvidencePayload:
    """The Lanes stage's summary per lane over the ready frames (S5)."""
    state = _state(request)
    try:
        return evidence_payload(state, series_id, _lane_ids(lanes), expiry)
    except UnknownSeriesError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}") from None


@router.get("/series/{series_id}/lanes/{lane_id}/filter", response_model=LaneFilterIndex)
def series_lane_filter_index(series_id: str, lane_id: str, request: Request) -> LaneFilterIndex:
    state = _state(request)
    try:
        return lane_filter_index(state, series_id, lane_id)
    except UnknownSeriesError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}") from None
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown lane {lane_id!r}") from None


@router.get("/series/{series_id}/lanes/{lane_id}/filter/{expiry}",
            response_model=LaneFilterPayload)
def series_lane_filter_ring(series_id: str, lane_id: str, expiry: str,
                            request: Request) -> LaneFilterPayload:
    """The lane's observation-filter ring for one node, in the live wire shape."""
    state = _state(request)
    try:
        return lane_filter_ring(state, series_id, lane_id, expiry)
    except UnknownSeriesError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}") from None
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown lane {lane_id!r}") from None


@router.post("/series/{series_id}/export")
def export_series_file(series_id: str, request: Request) -> JSONResponse:
    """The ``volfit-series/1`` bundle (S6): spec + frames' chains + fits + carries."""
    state = _state(request)
    try:
        bundle = series_files.export_series(state, series_id)
    except series_files.UnknownSeriesError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}") from None
    name = bundle["series"]["spec"]["ticker"].lower()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return JSONResponse(content=bundle, headers={
        "Content-Disposition": f'attachment; filename="{name}_{stamp}.volfit-series.json"'})


@router.post("/series/import", response_model=SeriesDoc)
def import_series_file(request: Request, body: dict = Body(...)) -> SeriesDoc:
    """Recreate a ``volfit-series/1`` bundle's series (idempotent by id)."""
    state = _state(request)
    try:
        doc = series_files.import_series_file(state, body)
    except series_files.SeriesFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    state.log_event("series_import", scope=doc.id,
                    payload={"ticker": doc.spec.ticker, "frames": len(doc.frames), "kind": "file"})
    return doc


@router.post("/series/{series_id}/adopt-prior", response_model=AdoptPriorResult)
def adopt_series_prior(series_id: str, req: AdoptPriorRequest, request: Request) -> AdoptPriorResult:
    """One lane's fits at one frame become the ticker's live prior (save = activate)."""
    state = _state(request)
    try:
        return adopt_prior(state, series_id, req)
    except UnknownSeriesError:
        raise HTTPException(status_code=404, detail=f"unknown series {series_id!r}") from None
    except AdoptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/series/stream/{series_id}")
async def stream_series(series_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events of one series' job status: pushed on change, a
    keep-alive comment otherwise (the calibration stream's shape)."""
    state = _state(request)
    _known(state, series_id)
    jobs = series_jobs_of(state)

    async def gen():
        last: str | None = None
        last_beat = monotonic()
        while True:
            if await request.is_disconnected():
                break
            payload = jobs.status(series_id).model_dump_json()
            now = monotonic()
            if payload != last:
                last, last_beat = payload, now
                yield f"data: {payload}\n\n"
            elif now - last_beat >= _SSE_HEARTBEAT:
                last_beat = now
                yield ": keepalive\n\n"
            await asyncio.sleep(_SSE_TICK)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

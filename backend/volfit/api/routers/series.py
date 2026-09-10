"""Series routes (SERIES ARC S1: list / get / delete / import-store).

Every route opens the app's VolStore for the request (the ``asof`` /
``history`` idiom) and answers 409 when the app runs without a store
(``VOLFIT_DB`` unset — series are persistent objects by definition). The
harvest / job routes (S2) and the frame / strip payloads (S4) join this
router in their phases; the roadmap §6 table is the contract.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from volfit.api.schemas_series import SeriesDoc, SeriesListResponse
from volfit.api.series_import import ImportError_, SeriesImportRequest, import_series
from volfit.api.series_store import SeriesStore
from volfit.data.store import VolStore

router = APIRouter(tags=["series"])

_NO_STORE = "series need a store: start the app with VOLFIT_DB set"


def _state(request: Request):
    state = request.app.state.volfit
    if state.store_path is None:
        raise HTTPException(status_code=409, detail=_NO_STORE)
    return state


@router.get("/series", response_model=SeriesListResponse)
def list_series(request: Request, ticker: str | None = None) -> SeriesListResponse:
    state = _state(request)
    with VolStore(state.store_path) as store:
        return SeriesListResponse(series=SeriesStore(store).list(ticker))


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

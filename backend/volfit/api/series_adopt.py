"""Adopt a series frame as the live prior (SERIES ARC S6, roadmap §3.5).

The one place a series writes a prior — EXPLICIT, one lane at one frame:
the lane's stored fits of that frame are rebuilt into committed records on
a detached lane state (the payload's record rebuild + ``commit_record``),
``priors.capture_snapshot`` freezes that state's surface — the same
snapshot a per-node save produces — the LV surface row rides along as the
snapshot's ``lvSurface``, and the live state saves it through
``save_prior_snapshot``: save = activate (the 2026-09-07c ruling), the
+ Prior cell lights for the ticker's nodes, a governance event names the
series, the lane and the frame.
"""

from __future__ import annotations

from pydantic import BaseModel

from volfit.api import priors, service
from volfit.api.schemas_prior import LvSurfaceSnapshot
from volfit.api.series_lanes import LaneCarry, lane_state
from volfit.api.series_payload import UnknownSeriesError, record_from_doc
from volfit.api.series_store import SeriesStore
from volfit.data.store import VolStore


class AdoptPriorRequest(BaseModel):
    laneId: str | None = None  # None = the production lane
    idx: int


class AdoptPriorResult(BaseModel):
    ticker: str
    laneId: str
    idx: int
    dataTs: str
    nodes: int
    lvSurface: bool
    persisted: bool


class AdoptError(ValueError):
    pass


def adopt_prior(state, series_id: str, req: AdoptPriorRequest) -> AdoptPriorResult:
    if state.store_path is None:
        raise RuntimeError("series need a store: set VOLFIT_DB")
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(series_id)
        if doc is None:
            raise UnknownSeriesError(series_id)
        lane = (doc.spec.production_lane if req.laneId is None
                else next((ln for ln in doc.spec.lanes if ln.id == req.laneId), None))
        if lane is None:
            raise AdoptError(f"unknown lane {req.laneId!r}")
        frame = next((f for f in doc.frames if f.idx == req.idx), None)
        if frame is None or frame.status != "ready":
            raise AdoptError(f"frame {req.idx} is not a ready frame of the series")
        chain = series.frame_chain(series_id, req.idx)
        fits = [f for f in series.fits(series_id, idx=req.idx, lane_id=lane.id) if f.status == "done"]
    ticker = doc.spec.ticker
    if ticker not in state.active_tickers():
        raise AdoptError(f"{ticker!r} is not in the universe — add it first")
    if chain is None or not fits:
        raise AdoptError(f"lane {lane.id!r} has no fit at frame {req.idx}")
    fit_mode = lane.fitMode or doc.spec.fitMode
    st = lane_state(doc, lane, frame, chain, LaneCarry())
    surface = None
    for fit in fits:
        if fit.expiry is None:
            p = fit.params
            surface = LvSurfaceSnapshot(tNodes=list(p["tNodes"]), xNodes=list(p["xNodes"]),
                                        theta=[list(r) for r in p["theta"]])
            continue
        expiry = st.resolve_expiry(ticker, fit.expiry)
        prepared = service.prepared_quotes(st, ticker, expiry)
        service.commit_record(st, ticker, fit.expiry, fit_mode, record_from_doc(fit, prepared), None)
    snap = priors.capture_snapshot(st, ticker, fit_mode, lv=False)
    if snap is None:
        raise AdoptError("nothing to adopt: no calibrated node at this frame")
    # The prior's DATA instant is the frame's (the envelope stamps "now"):
    # the age the anchoring reads is the frame's age, not the click's.
    snap = snap.model_copy(update={"dataTs": frame.ts, "asOfLabel": f"series frame {req.idx}"})
    if surface is not None:
        snap = snap.model_copy(update={"lvSurface": surface})
    persisted = state.save_prior_snapshot(snap)
    state.log_event("series_adopt_prior", scope=ticker,
                    payload={"seriesId": series_id, "laneId": lane.id, "idx": req.idx,
                             "dataTs": snap.dataTs, "nodes": len(snap.nodes)})
    return AdoptPriorResult(ticker=ticker, laneId=lane.id, idx=req.idx, dataTs=snap.dataTs,
                            nodes=len(snap.nodes), lvSurface=surface is not None,
                            persisted=persisted)

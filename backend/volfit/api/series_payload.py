"""The replay payloads of a series (SERIES ARC S4, roadmap §3.4 / §6).

``frame_payload`` = everything the lens draws for ONE frame in one response:
the frame's market per expiry (the prepared quote bands in the frame
forward's moneyness — the shape the Smile chart's market frame consumes),
and per requested lane its slice curves (evaluated from the STORED
parameters through the snapshot-file record rebuild, never a refit), a
σ(k, τ) grid for the Surface stage, the term points and the metrics.
``strip_payload`` = the filmstrip: per frame scalars and per lane one value
per frame for each strip metric. Both read the store only; the frame
payload is memoized on the app state per (series, frame, lanes, number of
stored fits) so a scrubber never re-evaluates a frame it already drew.

The market is prepared on a detached lane state (``series_lanes.lane_state``
for the production lane, no calibration) so the quote screens and the fit
target band are the lane's own; every lane's curve is sampled by
``service.model_curve`` on a record rebuilt from the stored doc with that
prepared slice (the curve depends on the quotes' k range and τ alone).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from datetime import date

import numpy as np

from volfit.api import service
from volfit.api.displayed import displayed_slice
from volfit.api.schemas import QuoteBand
from volfit.api.schemas_series import (
    FramePayload,
    LaneFitDoc,
    LaneFrameDoc,
    SliceCurveDoc,
    StripPayload,
    SurfaceGridDoc,
)
from volfit.api.series_lanes import LaneCarry, lane_state
from volfit.api.series_store import SeriesStore
from volfit.api.snapshot_files import _display_from_doc
from volfit.api.state import FitRecord
from volfit.data.store import VolStore
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import CalibrationResult
from volfit.models.lqd.quadrature import build_slice

#: The filmstrip's per-lane metrics (frontend seriesTypes.STRIP_METRICS).
STRIP_METRICS = ("rmsBp", "maxIvBp", "pullAtmBp", "zetaAtm", "fitMs", "skew", "curvature")
#: The Surface stage's k grid (log-moneyness), shared by every expiry.
SURFACE_K = np.linspace(-0.6, 0.4, 61)
_CACHE_SIZE = 96


class UnknownSeriesError(KeyError):
    pass


# ---------------------------------------------------------------- records

def record_from_doc(fit: LaneFitDoc, prepared) -> FitRecord:
    """A read-only FitRecord from a stored slice doc + the frame's prepared
    quotes (the snapshot-file rebuild without the commit)."""
    lq = fit.params
    params = LQDParams(
        L=float(lq["L"]), R=float(lq["R"]), a=np.asarray(lq.get("a", []), dtype=float),
        alpha_left=float(lq.get("alphaL", 0.0)), alpha_right=float(lq.get("alphaR", 0.0)),
    )
    d = fit.diagnostics or {}
    result = CalibrationResult(
        params=params, slice=build_slice(params), cost=float(d.get("cost", 0.0)),
        n_evaluations=int(d.get("nEvaluations", 0)), success=bool(d.get("success", True)),
        max_iv_error=float(d.get("maxIvError", 0.0)),
    )
    return FitRecord(prepared=prepared, result=result, display=_display_from_doc(fit.display),
                     provenance="series")


def _bands(prepared, band) -> list[QuoteBand]:
    out = []
    for i, (k, b, a, m) in enumerate(zip(prepared.k, prepared.iv_bid, prepared.iv_ask,
                                         prepared.iv_mid)):
        out.append(QuoteBand(
            k=float(k), bid=float(b), ask=float(a), mid=float(m), index=i, excluded=False,
            amended=False, strike=float(prepared.forward) * math.exp(float(k)),
            targetLo=float(band.iv_lo[i]) if band is not None else None,
            targetHi=float(band.iv_hi[i]) if band is not None else None,
        ))
    return out


def _surface(records: dict[str, FitRecord]) -> SurfaceGridDoc | None:
    rows, taus, isos = [], [], []
    for iso in sorted(records):
        rec = records[iso]
        sl = displayed_slice(rec)
        w = np.maximum(sl.implied_w(SURFACE_K), 0.0)
        vols = service.fill_nonfinite(np.sqrt(w / rec.prepared.tau))
        rows.append([float(v) for v in vols])
        taus.append(float(rec.prepared.tau))
        isos.append(iso)
    if not rows:
        return None
    return SurfaceGridDoc(k=[float(k) for k in SURFACE_K], tau=taus, expiries=isos, sigma=rows)


# ------------------------------------------------------------------ frame

def _cache(state) -> OrderedDict:
    cache = getattr(state, "_series_frame_cache", None)
    if cache is None:
        cache = OrderedDict()
        state._series_frame_cache = cache
    return cache


def _load(state, series_id: str):
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(series_id)
        if doc is None:
            raise UnknownSeriesError(series_id)
        return doc


def frame_payload(state, series_id: str, idx: int, lane_ids: list[str] | None = None,
                  ) -> FramePayload:
    """GET /series/{id}/frame/{idx}?lanes= (raises UnknownSeriesError /
    IndexError for an unknown series / frame)."""
    doc = _load(state, series_id)
    frame = next((f for f in doc.frames if f.idx == idx), None)
    if frame is None:
        raise IndexError(idx)
    lanes = [lane for lane in doc.spec.lanes if lane_ids is None or lane.id in lane_ids]
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        n_fits = sum(1 for f in series.fits(series_id, idx=idx) if f.laneId in {ln.id for ln in lanes})
        key = (series_id, idx, tuple(lane.id for lane in lanes), n_fits)
        cache = _cache(state)
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        chain = series.frame_chain(series_id, idx)
        fits_by_lane = {lane.id: series.fits(series_id, idx=idx, lane_id=lane.id) for lane in lanes}
    if chain is None or frame.status != "ready":
        payload = FramePayload(seriesId=series_id, idx=idx, ts=frame.ts, quoteKind=frame.quoteKind,
                               spot=frame.spot, expiries=list(frame.expiries))
        return payload
    prod = doc.spec.production_lane
    fit_mode = prod.fitMode or doc.spec.fitMode
    st = lane_state(doc, prod, frame, chain, LaneCarry())
    ticker = doc.spec.ticker
    market: dict = {}
    prepared_by_iso: dict = {}
    forwards: dict[str, float] = {}
    for expiry in st.selected_expiries(ticker):
        iso = expiry.isoformat()
        try:
            prepared = service.prepared_quotes(st, ticker, expiry)
        except Exception:  # noqa: BLE001 — a rung the prep refuses is simply absent
            continue
        prepared_by_iso[iso] = prepared
        band = service.edited_band_full(st, ticker, iso, prepared, fit_mode)
        forwards[iso] = float(prepared.forward)
        market[iso] = {
            "expiry": iso, "t": float(prepared.t), "tau": float(prepared.tau),
            "forward": float(prepared.forward), "discount": float(prepared.discount),
            "spot": float(chain.spot),
            "quotes": [q.model_dump() for q in _bands(prepared, band)],
        }
    lane_docs: dict[str, LaneFrameDoc] = {}
    for lane in lanes:
        slices, records, term = [], {}, []
        status = "done"
        for fit in fits_by_lane.get(lane.id, []):
            if fit.expiry is None:
                continue
            prepared = prepared_by_iso.get(fit.expiry)
            if fit.status != "done" or prepared is None:
                status = "failed" if fit.status == "failed" else status
                continue
            rec = record_from_doc(fit, prepared)
            records[fit.expiry] = rec
            pts = service.model_curve(rec)
            slices.append(SliceCurveDoc(
                expiry=fit.expiry, t=float(prepared.t), forward=float(prepared.forward),
                k=[p.k for p in pts], iv=[p.vol for p in pts],
                atmVol=fit.metrics.get("atmVol"), skew=fit.metrics.get("skew"),
                curvature=fit.diagnostics.get("curvature"), metrics=dict(fit.metrics),
            ))
            term.append({"expiry": fit.expiry, "t": float(prepared.t),
                         "atmVol": fit.metrics.get("atmVol"),
                         "varSwapVol": fit.diagnostics.get("varSwapVol")})
        surface_row = next((f for f in fits_by_lane.get(lane.id, []) if f.expiry is None), None)
        rms = [s.metrics.get("rmsBp") for s in slices if s.metrics.get("rmsBp") is not None]
        metrics = {
            "rmsBp": round(float(np.mean(rms)), 3) if rms else None,
            "maxIvBp": max((s.metrics.get("maxIvBp") or 0.0) for s in slices) if slices else None,
            "nSlices": len(slices),
            "fitMs": next((f.fitMs for f in fits_by_lane.get(lane.id, []) if f.fitMs), None),
        }
        if surface_row is not None:
            metrics["surface"] = {"status": surface_row.status, **surface_row.metrics}
        lane_docs[lane.id] = LaneFrameDoc(
            laneId=lane.id, slices=sorted(slices, key=lambda s: s.expiry),
            surface=_surface(records), term=sorted(term, key=lambda r: r["expiry"]),
            metrics=metrics, status=status if slices else "failed",
        )
    payload = FramePayload(
        seriesId=series_id, idx=idx, ts=frame.ts, quoteKind=frame.quoteKind,
        spot=float(chain.spot), expiries=sorted(market), forwards=forwards, market=market,
        lanes=lane_docs,
    )
    cache = _cache(state)
    cache[key] = payload
    while len(cache) > _CACHE_SIZE:
        cache.popitem(last=False)
    return payload


# ------------------------------------------------------------------ strip

def strip_payload(state, series_id: str, lane_ids: list[str] | None = None,
                  expiry: str | None = None) -> StripPayload:
    """GET /series/{id}/strip?lanes=&expiry= — the filmstrip over the READY
    frames (warm-up frames included, flagged by the frame index)."""
    doc = _load(state, series_id)
    lanes = [lane for lane in doc.spec.lanes if lane_ids is None or lane.id in lane_ids]
    frames = [f for f in doc.frames if f.status == "ready"]
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        fits = {lane.id: series.fits(series_id, lane_id=lane.id) for lane in lanes}
    shown = expiry or (frames[0].expiries[0] if frames and frames[0].expiries else None)
    atm: dict[str, list] = {lane.id: [] for lane in lanes}
    metrics: dict[str, dict[str, list]] = {lane.id: {m: [] for m in STRIP_METRICS} for lane in lanes}
    for frame in frames:
        for lane in lanes:
            rows = [f for f in fits[lane.id] if f.idx == frame.idx and f.expiry and f.status == "done"]
            by_iso = {f.expiry: f for f in rows}
            pick = by_iso.get(shown) if shown else None
            if pick is None and rows:  # the nearest later expiry, else the last
                later = sorted(iso for iso in by_iso if shown is None or iso >= shown)
                pick = by_iso[later[0]] if later else by_iso[sorted(by_iso)[-1]]
            atm[lane.id].append(pick.metrics.get("atmVol") if pick else None)
            rms = [f.metrics.get("rmsBp") for f in rows if f.metrics.get("rmsBp") is not None]
            mx = [f.metrics.get("maxIvBp") for f in rows if f.metrics.get("maxIvBp") is not None]
            zeta = pick.metrics.get("zeta") if pick else None
            metrics[lane.id]["rmsBp"].append(round(float(np.mean(rms)), 3) if rms else None)
            metrics[lane.id]["maxIvBp"].append(max(mx) if mx else None)
            metrics[lane.id]["pullAtmBp"].append(pick.metrics.get("pullAtmBp") if pick else None)
            metrics[lane.id]["zetaAtm"].append(zeta[0] if isinstance(zeta, list) and zeta else None)
            metrics[lane.id]["fitMs"].append(pick.fitMs if pick else None)
            metrics[lane.id]["skew"].append(pick.metrics.get("skew") if pick else None)
            metrics[lane.id]["curvature"].append(
                pick.diagnostics.get("curvature") if pick else None)
    return StripPayload(
        seriesId=series_id, idx=[f.idx for f in frames], ts=[f.ts for f in frames],
        spot=[f.spot for f in frames], atmVol=atm, lanes=metrics,
    )


def frame_date(iso: str) -> date:
    return date.fromisoformat(iso)

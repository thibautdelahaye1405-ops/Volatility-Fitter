"""The Lanes stage's evidence (SERIES ARC S5, roadmap §3.4 "Lanes").

``evidence_payload`` summarizes every lane over the READY frames of the shown
expiry, derived from the same strip the filmstrip draws (one source, the
numbers agree): the mean rms / max error in vol bp, the worst frame, the
HANDLE-PATH ROUGHNESS — the mean frame-to-frame move of the ATM vol (bp)
and of the skew, i.e. what a prior or a filter damps, read beside the rms
it costs —, the mean (and mean absolute) pull against the free reference,
the fit time and the spread of the filter's ATM ζ. ``lane_filter_index`` /
``lane_filter_ring`` serve the lane's observation-filter rings from its
carry document (``series_lanes.filter_json``: the ``filterHistory`` entries
in the workspace-doc shape, each step already the ``/filter/history`` wire
dict), so the FilterTimeline draws a lane's ring as it draws the live one.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from volfit.api.series_payload import UnknownSeriesError, strip_payload
from volfit.api.series_store import SeriesStore
from volfit.data.store import VolStore


class WorstFrame(BaseModel):
    idx: int
    ts: str
    rmsBp: float


class LaneEvidence(BaseModel):
    nFrames: int = 0
    nFailed: int = 0
    meanRmsBp: float | None = None
    meanMaxIvBp: float | None = None
    worstFrame: WorstFrame | None = None
    roughnessAtmBp: float | None = None
    roughnessSkew: float | None = None
    meanPullAtmBp: float | None = None
    meanAbsPullAtmBp: float | None = None
    meanFitMs: float | None = None
    zetaAtmStd: float | None = None


class EvidencePayload(BaseModel):
    seriesId: str
    expiry: str | None = None
    lanes: dict[str, LaneEvidence] = {}


class LaneFilterIndex(BaseModel):
    laneId: str
    expiries: list[str] = []


class LaneFilterPayload(BaseModel):
    laneId: str
    expiry: str
    steps: list[dict] = []
    #: The series frame each step was committed on, by ORDER (the ring keeps
    #: the last 64 steps; a step's ``ts`` is the app's local-clock epoch of a
    #: naive timestamp, so the frame is matched by order, never by clock).
    frameIdx: list[int | None] = []


# --------------------------------------------------------------- evidence

def _mean(values) -> float | None:
    xs = [float(v) for v in values if v is not None and np.isfinite(v)]
    return round(float(np.mean(xs)), 4) if xs else None


def _roughness(values, scale: float = 1.0) -> float | None:
    """Mean |Δ| between CONSECUTIVE frames that both carry a value."""
    diffs = [abs(float(b) - float(a)) * scale for a, b in zip(values, values[1:])
             if a is not None and b is not None]
    return round(float(np.mean(diffs)), 4) if diffs else None


def _std(values) -> float | None:
    xs = [float(v) for v in values if v is not None and np.isfinite(v)]
    return round(float(np.std(xs)), 4) if len(xs) > 1 else None


def evidence_payload(state, series_id: str, lane_ids: list[str] | None = None,
                     expiry: str | None = None) -> EvidencePayload:
    """GET /series/{id}/evidence?lanes=&expiry= — per lane, over the strip."""
    strip = strip_payload(state, series_id, lane_ids, expiry)
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        doc = series.get(series_id)
        if doc is None:
            raise UnknownSeriesError(series_id)
        failed = {lane_id: {f.idx for f in series.fits(series_id, lane_id=lane_id)
                            if f.status == "failed"} for lane_id in strip.lanes}
    shown = expiry or (next((f.expiries[0] for f in doc.frames if f.expiries), None))
    lanes: dict[str, LaneEvidence] = {}
    for lane_id, metrics in strip.lanes.items():
        rms = metrics["rmsBp"]
        worst = None
        scored = [(v, i) for i, v in enumerate(rms) if v is not None]
        if scored:
            v, i = max(scored)
            worst = WorstFrame(idx=strip.idx[i], ts=strip.ts[i], rmsBp=float(v))
        lanes[lane_id] = LaneEvidence(
            nFrames=sum(1 for v in rms if v is not None),
            nFailed=len(failed.get(lane_id, ())),
            meanRmsBp=_mean(rms), meanMaxIvBp=_mean(metrics["maxIvBp"]), worstFrame=worst,
            roughnessAtmBp=_roughness(strip.atmVol.get(lane_id, []), 1e4),
            roughnessSkew=_roughness(metrics["skew"]),
            meanPullAtmBp=_mean(metrics["pullAtmBp"]),
            meanAbsPullAtmBp=_mean([abs(v) for v in metrics["pullAtmBp"] if v is not None]),
            meanFitMs=_mean(metrics["fitMs"]), zetaAtmStd=_std(metrics["zetaAtm"]),
        )
    return EvidencePayload(seriesId=series_id, expiry=shown, lanes=lanes)


# ------------------------------------------------------------ filter rings

def _rings(state, series_id: str, lane_id: str) -> list[dict]:
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        if not series.exists(series_id):
            raise UnknownSeriesError(series_id)
        if lane_id not in {lane.id for lane in series.lanes(series_id)}:
            raise KeyError(lane_id)
        carry = series.lane_filter(series_id, lane_id) or {}
    return list(carry.get("filterHistory") or [])


def lane_filter_index(state, series_id: str, lane_id: str) -> LaneFilterIndex:
    rings = _rings(state, series_id, lane_id)
    return LaneFilterIndex(laneId=lane_id, expiries=sorted({r["expiry"] for r in rings
                                                            if r.get("steps")}))


def lane_filter_ring(state, series_id: str, lane_id: str, expiry: str) -> LaneFilterPayload:
    """The lane's ring for one node (any fit mode; the lane runs one)."""
    rings = _rings(state, series_id, lane_id)
    steps = list(next((r.get("steps") or [] for r in rings if r.get("expiry") == expiry), []))
    with VolStore(state.store_path) as store:
        done = sorted({f.idx for f in SeriesStore(store).fits(series_id, lane_id=lane_id)
                       if f.expiry == expiry and f.status == "done"})
    frames: list[int | None] = list(done[-len(steps):]) if steps else []
    if len(frames) < len(steps):  # more steps than stored frames (never expected): pad left
        frames = [None] * (len(steps) - len(frames)) + frames
    return LaneFilterPayload(laneId=lane_id, expiry=expiry, steps=steps, frameIdx=frames)

"""Lane calibration over a series' frames (SERIES ARC S3, roadmap §3.3).

Every lane runs on its OWN detached ``AppState`` per frame — the
``backtest/filter_replay`` pattern: a fresh state over a stored-chains
provider holding that frame's chain, the lane's patches applied over the
series' frozen base settings, and the lane's TEMPORAL STATE carried from the
previous frame explicitly: the active prior (its own previous surface,
captured with ``priors.capture_snapshot``) and the observation-filter
holders + rings (``set_filter_node`` / ``set_filter_history``), the data
version bumped once per frame so each frame is a genuinely new observation.
The frame is then calibrated by ``workflow.calibrate_ticker`` — the SAME
work items the desk's per-ticker Calibrate runs (calendar coupling, warm
starts, the LV surface when the lane is an LV lane) — so a free lane's fit is
byte-identical to a live Calibrate on that chain under those settings (the
first S3 lock). The live workspace is never read after the series was
created (D5) except for the explicit ``live_prior`` seed (D4).

The carry is checkpointed per (lane, frame) into the lane row
(``series_lanes.filter_json``: the prior snapshot doc + the filter docs the
workspace file uses), so a pause / restart resumes at the next frame with
the exact chain state. Frames run frame-major (every lane on frame i before
frame i+1) so the pull against the free reference lane is computed as fits
land; lanes are sequential in the job thread (the shared fit pool stays the
live Calibrate's — a rider for the concurrency of free lanes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from time import perf_counter

from volfit.calib import deadline as deadline_clock
from volfit.calib.deadline import FitDeadlineExceeded

from volfit.api import affine_fit, priors, workflow
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.schemas_prior import PriorSurfaceSnapshot
from volfit.api.schemas_series import FrameDoc, LaneFitDoc, LaneSpec, SeriesDoc
from volfit.api.series_metrics import attach_filter, attach_pull, slice_fit_doc, surface_fit_doc
from volfit.api.series_feed import expected_fits
from volfit.api.series_store import SeriesStore
from volfit.api.state import AppState
from volfit.api.workspace_filter_doc import (
    filter_states_docs,
    filter_states_from,
    history_docs,
    history_from_docs,
)
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot
from volfit.replay_report import _StoredChains as SeriesChains

#: Options every lane state pins regardless of the base: nothing automatic
#: runs on a detached state, and the LV stage rides the lane family alone.
_PINNED_OPTIONS = {"autoCalibrate": False, "autoUpdate": "off", "autoStream": False}


# ------------------------------------------------------------------ carry


@dataclass
class LaneCarry:
    """What a lane hands from one frame to the next (D4)."""

    prior: PriorSurfaceSnapshot | None = None
    filter_states: dict = field(default_factory=dict)  # (ticker, iso, mode) -> NodeFilter
    filter_history: dict = field(default_factory=dict)  # (ticker, iso, mode) -> ring
    last_idx: int | None = None  # the frame this carry was captured on

    def to_doc(self) -> dict:
        return {
            "lastIdx": self.last_idx,
            "prior": self.prior.model_dump(mode="json") if self.prior is not None else None,
            "filterStates": filter_states_docs(self.filter_states),
            "filterHistory": history_docs(self.filter_history),
        }

    @classmethod
    def from_doc(cls, doc: dict | None) -> "LaneCarry":
        if not doc:
            return cls()
        prior = doc.get("prior")
        return cls(
            prior=PriorSurfaceSnapshot.model_validate(prior) if prior else None,
            filter_states=filter_states_from(doc.get("filterStates") or []),
            filter_history=history_from_docs(doc.get("filterHistory") or []),
            last_idx=doc.get("lastIdx"),
        )


# ------------------------------------------------------------ lane states


def lane_options(doc: SeriesDoc, lane: LaneSpec):
    """The lane's options: the frozen base, the lane's patch, the pinned
    switches, the LV stage by family — and the intraday clock ON for a
    sub-day series unless the patch says otherwise (a 15-minute series IS
    intraday: a same-day rung has calendar t = 0 without it)."""
    update = {}
    if doc.spec.clock.step_seconds is not None:
        update["intradayClock"] = True
    update.update(lane.patchOptions)
    update.update(_PINNED_OPTIONS)
    update["localVolEnabled"] = lane.family == "lv"
    return doc.baseOptions.model_copy(update=update)


def alive_expiries(chain: ChainSnapshot, expiries: list[str], intraday: bool) -> list[date]:
    """The frame's expiries still tradeable AT the instant: on the intraday
    clock an expiry lives until its settlement instant (the chain's
    per-expiry settlement, else the close of its day); on the calendar clock
    a same-day rung is degenerate (t = 0) and is dropped."""
    ts = chain.timestamp
    out = []
    for iso in expiries:
        e = date.fromisoformat(iso)
        if not intraday:
            if e > ts.date():
                out.append(e)
            continue
        settle = (chain.settlement or {}).get(e)
        if settle is not None:
            if settle.settle > ts:
                out.append(e)
        elif e >= ts.date():
            out.append(e)
    return out


def lane_state(doc: SeriesDoc, lane: LaneSpec, frame: FrameDoc, chain: ChainSnapshot,
               carry: LaneCarry) -> AppState:
    """A detached state for one (lane, frame): the frame's chain as the only
    provider, the lane's settings, the carried prior + filter state, the
    data version at the frame's ordinal. Raises ValueError when no expiry
    of the frame is alive at its instant."""
    ticker = doc.spec.ticker
    options = lane_options(doc, lane)
    st = AppState(chain.timestamp.date(), provider=SeriesChains({ticker: chain}))
    st.set_fit_settings(doc.baseFit.model_copy(update=lane.patchFit))
    st.set_options(options)
    st.set_expiries(ticker, alive_expiries(chain, frame.expiries, options.intradayClock))
    if carry.prior is not None:
        st.set_active_prior(ticker, carry.prior, "series")
    for key, holder in carry.filter_states.items():
        st.set_filter_node(key, holder)
    for key, ring in carry.filter_history.items():
        st.set_filter_history(key, ring)
    for _ in range(frame.idx):  # each frame is a NEW observation (the filter keys on it)
        st.bump_data_version(ticker)
    return st


def _carries_prior(st: AppState) -> bool:
    return st.options().priorPersistenceMode != "off"


def _carries_filter(st: AppState) -> bool:
    return st.options().observationFilterMode != "off"


def calibrate_frame(doc: SeriesDoc, lane: LaneSpec, frame: FrameDoc, chain: ChainSnapshot,
                    carry: LaneCarry, reference: dict[str, LaneFitDoc] | None = None,
                    ) -> tuple[list[LaneFitDoc], LaneCarry]:
    """Calibrate one lane on one frame; returns its fit docs (slices, then
    the LV surface for an LV lane) and the carry for the next frame.
    ``reference`` = the free reference lane's fits of this frame by expiry
    (the pull columns)."""
    ticker = doc.spec.ticker
    fit_mode = lane.fitMode or doc.spec.fitMode
    st = lane_state(doc, lane, frame, chain, carry)
    t0 = perf_counter()
    # The frame budget (SeriesSpec.frameBudgetSeconds): a deadline on the
    # detached state, checked between the desk's items and before every joint
    # refit of the calendar repair (volfit.calib.deadline). Past it the items
    # already committed stay, the rest raise — the same dying-repair path.
    budget = doc.spec.frameBudgetSeconds
    st.fit_deadline = deadline_clock.now() + budget if budget is not None else None
    # The desk's items: phase-A slice fits commit one by one, then the calendar
    # repair, then the LV surface. A repair that dies (the active filter's
    # calendar-inconsistent predictions on a dense intraday ladder — recorded
    # 2026-09-10) must not lose the committed phase-A fits: they are harvested
    # as they stand, tagged with the repair's failure.
    repair_error: str | None = None
    try:
        workflow.calibrate_ticker(st, ticker, fit_mode)
    except FitDeadlineExceeded as exc:
        repair_error = f"frame budget {budget} s exceeded: {exc}"
    except Exception as exc:  # noqa: BLE001
        repair_error = f"{type(exc).__name__}: {str(exc)[:200]}"
    fit_ms = (perf_counter() - t0) * 1000.0
    fits: list[LaneFitDoc] = []
    keys: list[tuple] = []
    for expiry in st.selected_expiries(ticker):
        iso = expiry.isoformat()
        ptr = st.get_calibrated_ptr(ticker, iso, fit_mode)
        record = st.get_fit(ptr[0]) if ptr is not None else None
        if record is None:
            fits.append(LaneFitDoc(laneId=lane.id, idx=frame.idx, expiry=iso, model="lqd",
                                   status="failed", error=repair_error or "no fit committed"))
            continue
        keys.append((ticker, iso, fit_mode))
        fit = slice_fit_doc(st, lane.id, frame.idx, ticker, iso, fit_mode, record, fit_ms)
        fit = attach_pull(fit, (reference or {}).get(iso))
        fit = attach_filter(fit, st.filter_history((ticker, iso, fit_mode)))
        if repair_error is not None:
            fit = fit.model_copy(update={"metrics": {**fit.metrics, "calendarRepair": repair_error}})
        fits.append(fit)
    if lane.family == "lv" and repair_error is not None:
        fits.append(LaneFitDoc(laneId=lane.id, idx=frame.idx, expiry=None, model="affine",
                               status="failed", error=repair_error))
    elif lane.family == "lv":
        try:
            resp = affine_fit.affine_payload(st, ticker, AffineFitRequest(fitMode=fit_mode))
            if resp.hasFit:
                fits.append(surface_fit_doc(lane.id, frame.idx, resp, fit_ms))
            else:
                fits.append(LaneFitDoc(laneId=lane.id, idx=frame.idx, expiry=None,
                                       model="affine", status="failed", error=resp.message))
        except Exception as exc:  # noqa: BLE001 — the surface's failure is a row
            fits.append(LaneFitDoc(laneId=lane.id, idx=frame.idx, expiry=None, model="affine",
                                   status="failed", error=str(exc)[:300]))
    nxt = LaneCarry(last_idx=frame.idx)
    if _carries_prior(st) and keys:
        nxt.prior = priors.capture_snapshot(st, ticker, fit_mode, lv=lane.family == "lv")
    if _carries_filter(st):
        nxt.filter_states = {k: st.filter_node(k) for k in keys if st.filter_node(k) is not None}
        nxt.filter_history = {k: st.filter_history(k) for k in keys
                              if st.filter_history(k) is not None}
    return fits, nxt


# -------------------------------------------------------------- the hook


def reference_lane(lanes: list[LaneSpec], lane: LaneSpec) -> LaneSpec | None:
    """The free lane of the same family a lane's pull is measured against
    (the first non-temporal lane of that family; a free lane reads zero)."""
    for cand in lanes:
        if cand.family == lane.family and not cand.temporal:
            return cand
    return None


def run_lanes(jobs, doc: SeriesDoc) -> None:
    """``SeriesJobs.calibrate_hook``: calibrate every lane over every frame
    as it lands (the run's feed hands frames over in index order while the
    harvest thread keeps fetching — 2026-09-11b), frame-major, checkpointing
    fits + carries as they land; returns early on a pause / cancel (the
    runner records the final status). Progress goes through the feed so the
    harvest thread's fields are never clobbered."""
    state = jobs._state
    series_id = doc.id
    feed = jobs.feed(doc)
    lanes = list(doc.spec.lanes)
    ticker = doc.spec.ticker
    n_frames = len(doc.frames)
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        carries = {lane.id: LaneCarry.from_doc(series.lane_filter(series_id, lane.id))
                   for lane in lanes}
        done_frames = {lane.id: {f.idx for f in series.fits(series_id, lane_id=lane.id)}
                       for lane in lanes}
        feed.advance(fitsTotal=expected_fits(doc, feed.landed()),
                     fitsDone=series.count_fits(series_id))
    for lane in lanes:  # the D4 seed: the live prior, once, before the first frame
        if lane.seed == "live_prior" and carries[lane.id].last_idx is None:
            carries[lane.id].prior = state.active_prior(ticker)
    for frame in feed.frames_as_ready(lambda: jobs._interrupted(series_id) is not None):
        frame_fits: dict[str, dict[str, LaneFitDoc]] = {}
        with VolStore(state.store_path) as store:
            series = SeriesStore(store)
            chain = series.frame_chain(series_id, frame.idx)
        if chain is None or not frame.expiries:
            continue
        for lane in lanes:
            ref = reference_lane(lanes, lane)
            ref_fits = frame_fits.get(ref.id) if ref is not None and ref.id != lane.id else None
            if frame.idx in done_frames[lane.id]:  # resumed: this (lane, frame) is stored
                with VolStore(state.store_path) as store:
                    stored = SeriesStore(store).fits(series_id, idx=frame.idx, lane_id=lane.id)
                frame_fits[lane.id] = {f.expiry: f for f in stored if f.expiry}
                continue
            if ref is not None and ref.id != lane.id and ref_fits is None:
                with VolStore(state.store_path) as store:
                    stored = SeriesStore(store).fits(series_id, idx=frame.idx, lane_id=ref.id)
                ref_fits = {f.expiry: f for f in stored if f.expiry} or None
            label = (f"Calibrating {ticker} frame {frame.idx + 1}/{n_frames} · {lane.name}"
                     f" · {frame.ts}")
            feed.advance(fit=label)
            try:
                with state.activity.activity("series", label):
                    fits, carry = calibrate_frame(doc, lane, frame, chain, carries[lane.id],
                                                  ref_fits)
            except Exception as exc:  # noqa: BLE001 — one bad (lane, frame) never kills the run
                fits = [LaneFitDoc(laneId=lane.id, idx=frame.idx, expiry=iso, model="lqd",
                                   status="failed", error=str(exc)[:300])
                        for iso in frame.expiries]
                carry = carries[lane.id]  # the chain state stays where it was
            carries[lane.id] = carry
            frame_fits[lane.id] = {f.expiry: f for f in fits if f.expiry}
            with VolStore(state.store_path) as store:
                series = SeriesStore(store)
                series.save_fits(series_id, fits)  # one commit per (lane, frame)
                series.set_lane_filter(series_id, lane.id, carry.to_doc())
                n_done = series.count_fits(series_id)
            failed = next((f.error for f in fits if f.status == "failed"), None)
            feed.advance(fitsDone=n_done, fitsTotal=expected_fits(doc, feed.landed()),
                         **({"error": failed} if failed is not None else {}))
            if jobs._interrupted(series_id):
                return
    feed.advance(fit=None, fitsTotal=expected_fits(doc, feed.landed()))

"""Prior framework — capture, save and status of full calibration snapshots.

``capture_snapshot`` freezes a ticker's currently-calibrated surface into a
``PriorSurfaceSnapshot`` (per-expiry model + LQD backbone + market state + the
affine LV grid). ``save_all`` snapshots every active ticker that has at least one
lit, calibrated node and persists it (VolStore history). ``prior_status`` reports
what is saved, for the Fetch button. Transport / on-the-fly fetch / the anchor
penalty are Phase B/C — this module only produces and stores the snapshots.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

import numpy as np

from volfit.api.displayed import displayed_atm_vol, displayed_skew
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.schemas_prior import (
    LvSurfaceSnapshot,
    PriorFetchResult,
    PriorFetchTicker,
    PriorNode,
    PriorSaveResult,
    PriorStatus,
    PriorSurfaceSnapshot,
    PriorTickerStatus,
)
from volfit.api.state import AppState


def _now() -> datetime:
    """UTC wall clock, second precision (snapshot save time)."""
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)


def _data_ts(state: AppState) -> datetime:
    """The market moment the current calibration reflects.

    The as-of selection's timestamp when historical; otherwise now (a live
    calibration). This is what the fetch freshness ladder compares against the
    previous close (Phase B)."""
    ts = getattr(state.as_of, "ts", None)
    return ts if ts is not None else _now()


def _jsonable(obj):
    """Recursively convert numpy scalars/arrays so a params dict is JSON-safe."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _dump_display(display) -> dict | None:
    """Serialize the displayed-model params (None for an LQD-only node).

    The displayed slice (RawSVI / MultiCoreSiv) is a (possibly nested) dataclass,
    so ``asdict`` + numpy coercion gives a faithful, JSON-safe param dict."""
    if display is None:
        return None
    slice_ = display.slice
    if dataclasses.is_dataclass(slice_):
        return _jsonable(dataclasses.asdict(slice_))
    return None


def _lv_surface_snapshot(state: AppState, ticker: str, fit_mode: str) -> LvSurfaceSnapshot | None:
    """The ticker's calibrated affine LV surface vertices + nodal variances, or
    None when it has none (too few expiries / LV disabled / not calibrated)."""
    from volfit.api import affine_fit

    try:
        resp = affine_fit.affine_payload(state, ticker, AffineFitRequest(fitMode=fit_mode))
    except Exception:  # noqa: BLE001 — no LV surface for this ticker
        return None
    # localVol is sqrt(nodal variance); store the variances theta = localVol^2.
    theta = [[float(v) * float(v) for v in row] for row in resp.localVol]
    return LvSurfaceSnapshot(tNodes=list(resp.tNodes), xNodes=list(resp.xNodes), theta=theta)


def capture_snapshot(
    state: AppState, ticker: str, fit_mode: str = "mid", lv: bool = True
) -> PriorSurfaceSnapshot | None:
    """Freeze the ticker's calibrated surface into a PriorSurfaceSnapshot.

    Captures every LIT expiry's displayed fit (the frozen calibrated slice +
    its LQD backbone), the market state (ref spot, per-expiry forward/discount,
    MarketSettings, event calendar) and the affine LV grid if present. Returns
    None when the ticker has no lit nodes to snapshot.

    ``lv=False`` skips the (expensive) Local-Vol surface capture for callers that
    only consume the parametric backbone (e.g. the temporal prior-mode backtest,
    whose transport reads the LQD nodes) — the default keeps it byte-identical.
    """
    from volfit.api import service

    isos = [
        e.isoformat()
        for e in sorted(state.forwards(ticker))
        if state.node_lit(ticker, e.isoformat())
    ]
    nodes: list[PriorNode] = []
    for iso in isos:
        try:
            record = service.displayed_base(state, ticker, iso, fit_mode)
        except Exception:  # noqa: BLE001 — a node that can't fit is skipped
            continue
        if record is None:
            continue  # uncalibrated node (gated, pre-Calibrate): not in the snapshot
        prepared = record.prepared
        nodes.append(
            PriorNode(
                expiry=iso,
                tCal=float(prepared.t),
                tau=float(prepared.tau),
                forward=float(prepared.forward),
                discount=float(prepared.discount),
                model=record.display.model if record.display is not None else "lqd",
                lqd=[float(v) for v in record.result.params.to_vector()],
                display=_dump_display(record.display),
                atmVol=float(displayed_atm_vol(record)),
                skew=float(displayed_skew(record)),
            )
        )
    if not nodes:
        return None
    return PriorSurfaceSnapshot(
        ticker=ticker,
        dataTs=_data_ts(state).isoformat(),
        savedTs=_now().isoformat(),
        asOfLabel=_asof_label(state),
        refSpot=float(state.anchor_spot(ticker)),
        market=state.market_settings(ticker).model_dump(),
        events=[e.model_dump() for e in state.events(ticker)],
        nodes=nodes,
        lvSurface=_lv_surface_snapshot(state, ticker, fit_mode) if lv else None,
    )


def _asof_label(state: AppState) -> str:
    """A short human label of the data moment the snapshot reflects."""
    sel = state.as_of
    if sel.mode == "live":
        return "live"
    day = sel.day or sel.on
    parts = [sel.mode] + ([day.isoformat()] if day else [])
    return " ".join(parts)


def save_all(state: AppState, fit_mode: str = "mid") -> PriorSaveResult:
    """Snapshot every active ticker that has lit, calibrated nodes; persist each.

    Returns the tickers captured, the total node count, and whether a store is
    configured (so the priors survive a restart)."""
    saved: list[str] = []
    total = 0
    persisted = state.store_path is not None
    for ticker in state.active_tickers():
        try:
            snap = capture_snapshot(state, ticker, fit_mode)
        except Exception:  # noqa: BLE001 — one bad ticker never fails the batch
            continue
        if snap is None:
            continue
        state.save_prior_snapshot(snap)
        saved.append(ticker)
        total += len(snap.nodes)
    return PriorSaveResult(tickers=saved, nodes=total, persisted=persisted and bool(saved))


def prior_status(state: AppState) -> PriorStatus:
    """Saved- and active-prior availability per active ticker (for the buttons)."""
    out: list[PriorTickerStatus] = []
    for ticker in state.active_tickers():
        snap = state.latest_prior_snapshot(ticker)
        active = state.active_prior(ticker)
        status = PriorTickerStatus(
            ticker=ticker,
            activeSource=state.active_prior_source(ticker),
            activeDataTs=active.dataTs if active is not None else None,
        )
        if snap is not None:
            status.dataTs = snap.dataTs
            status.savedTs = snap.savedTs
            status.asOfLabel = snap.asOfLabel
            status.nodeCount = len(snap.nodes)
            status.hasLvSurface = snap.lvSurface is not None
        out.append(status)
    return PriorStatus(tickers=out)


# --------------------------------------------------------------- fetch ladder
def _prev_close_instant(state: AppState) -> tuple[datetime, date]:
    """The previous-close instant (UTC-naive) + the session date it belongs to."""
    from volfit.api import asof as asof_mod

    history = asof_mod._history_dates(state)
    prev_session = asof_mod._prev_session(history, state.reference_date)
    return asof_mod.market_close_utc(prev_session), prev_session


def _is_fresh(snapshot: PriorSurfaceSnapshot | None, prev_close: datetime) -> bool:
    """Whether a saved snapshot is posterior to the previous close (ladder step 1)."""
    if snapshot is None:
        return False
    try:
        return datetime.fromisoformat(snapshot.dataTs) > prev_close
    except ValueError:
        return False


def _recalibrate_at_prev_close(
    state: AppState, ticker: str, prev_session, fit_mode: str
) -> tuple[PriorSurfaceSnapshot | None, str]:
    """Ladder steps 2-3: calibrate the ticker on-the-fly from the 15-min-before-
    previous-close chain, falling back to the actual previous close.

    Mirrors workflow.seed_priors: switch the as-of to the historical moment,
    recalibrate the lit nodes there, snapshot, and restore the live as-of (the
    restore re-clears the live chain caches, so the live surface re-bootstraps —
    the accepted cost of an on-the-fly fetch). Returns (snapshot, source) or
    (None, "none") when no historical moment is serveable."""
    from volfit.api import asof as asof_mod, service, workflow

    live = state.as_of
    for moment, offset, label in (("before_close", 15, "15min"), ("close", None, "close")):
        try:
            selection = asof_mod._resolve_moment(state, prev_session, moment, offset)
        except ValueError:
            continue  # this moment is not serveable on the active provider
        snap: PriorSurfaceSnapshot | None = None
        try:
            state.set_as_of(selection)
            for t, iso in workflow.lit_nodes(state, [ticker]):
                service.calibrate_node(state, t, iso, fit_mode)
            snap = capture_snapshot(state, ticker, fit_mode)
        except Exception:  # noqa: BLE001 — a provider gap falls through to the next step
            snap = None
        finally:
            state.set_as_of(live)
        if snap is not None:
            state.save_prior_snapshot(snap)
            return snap, label
    return None, "none"


def fetch_all(state: AppState, fit_mode: str = "mid") -> PriorFetchResult:
    """Activate each active ticker's prior and set it as the dotted, spot-updated
    overlay (+ Bayesian anchor).

    Per ticker: (1) use the latest SAVED snapshot — the prior the user explicitly
    captured (via "Save priors"), whatever observation it reflects; else (2) when
    nothing has been saved, calibrate one on-the-fly from 15-min-before the
    previous close, else the actual previous close. The resolved prior becomes the
    active prior, drawn dotted and **transported to the current spot** (so it can
    be compared with the prevailing calibrated smile, also at the current spot).

    A saved snapshot is used regardless of its age: a prior is, by definition, a
    past observation the user chose — the freshness ladder is only the *fallback*
    when no prior has been saved. (Earlier this used the saved snapshot only if it
    was newer than the previous close, so a deliberately-past prior was silently
    replaced by a prev-close recalc — which often coincided with the live smile,
    making "Fetch priors" look like a no-op.)

    The on-the-fly fallback switches the global as-of to a past close and back,
    which clears the live chain caches; we snapshot and restore the live surface
    around the whole resolve so the user's calibrated live smile / quotes survive
    (in the gated workflow a read no longer lazily re-bootstraps them). The active
    prior is stored separately from the chain caches, so the set_active_prior
    calls below survive the restore."""
    _, prev_session = _prev_close_instant(state)
    live_state = state.capture_chain_state()
    out: list[PriorFetchTicker] = []
    try:
        for ticker in state.active_tickers():
            latest = state.latest_prior_snapshot(ticker)
            if latest is not None:  # the user's explicitly-saved prior wins
                state.set_active_prior(ticker, latest, "saved")
                out.append(
                    PriorFetchTicker(
                        ticker=ticker, source="saved", dataTs=latest.dataTs,
                        nodeCount=len(latest.nodes),
                    )
                )
                continue
            snap, source = _recalibrate_at_prev_close(state, ticker, prev_session, fit_mode)
            state.set_active_prior(ticker, snap, source)
            out.append(
                PriorFetchTicker(
                    ticker=ticker, source=source,
                    dataTs=snap.dataTs if snap is not None else None,
                    nodeCount=len(snap.nodes) if snap is not None else 0,
                )
            )
    finally:
        state.restore_chain_state(live_state)  # undo the transient as-of round-trip
    return PriorFetchResult(tickers=out)

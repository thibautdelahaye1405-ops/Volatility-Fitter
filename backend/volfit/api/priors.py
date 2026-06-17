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
from datetime import datetime, timezone

import numpy as np

from volfit.api.displayed import displayed_atm_vol, displayed_skew
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.schemas_prior import (
    LvSurfaceSnapshot,
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


def capture_snapshot(state: AppState, ticker: str, fit_mode: str = "mid") -> PriorSurfaceSnapshot | None:
    """Freeze the ticker's calibrated surface into a PriorSurfaceSnapshot.

    Captures every LIT expiry's displayed fit (the frozen calibrated slice +
    its LQD backbone), the market state (ref spot, per-expiry forward/discount,
    MarketSettings, event calendar) and the affine LV grid if present. Returns
    None when the ticker has no lit nodes to snapshot.
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
        lvSurface=_lv_surface_snapshot(state, ticker, fit_mode),
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
    """Saved-prior availability per active ticker (for the Fetch button)."""
    out: list[PriorTickerStatus] = []
    for ticker in state.active_tickers():
        snap = state.latest_prior_snapshot(ticker)
        if snap is None:
            out.append(PriorTickerStatus(ticker=ticker))
            continue
        out.append(
            PriorTickerStatus(
                ticker=ticker,
                dataTs=snap.dataTs,
                savedTs=snap.savedTs,
                asOfLabel=snap.asOfLabel,
                nodeCount=len(snap.nodes),
                hasLvSurface=snap.lvSurface is not None,
            )
        )
    return PriorStatus(tickers=out)

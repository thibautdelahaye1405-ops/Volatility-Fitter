"""Fit time-series persistence and queries ([REQ 2026-06-12] scaffold).

Every slice calibration the API produces (volfit.api.service.fit_or_get and
fit_surface) is mirrored into the VolStore `fits` table, keyed by the chain
SNAPSHOT timestamp — one snapshot is one observation of the surface, so the
snapshot timestamp (not wall-clock fit time) is the time-series key. GET
/history/{ticker}/{tenor_days} then reads those rows back as a
constant-maturity series: per snapshot, the listed expiry nearest to the
requested tenor (no interpolation at scaffold stage; charting UI deferred).

Persistence is strictly opt-in (AppState.store_path, env VOLFIT_DB in
serve.py) and strictly best-effort: `persist_fit` swallows every exception
into a warning, because a broken disk/DB must never fail a fit. A fresh
VolStore connection is opened per call — sqlite connections are bound to
their creating thread and fits run on uvicorn/anyio worker threads, so a
shared handle would raise; with WAL mode an open is cheap and concurrent
reads never block, making per-call connections the simple correct choice.
"""

from __future__ import annotations

import warnings
from datetime import date

import numpy as np

from volfit.api.schemas import HistoryPoint, HistoryResponse
from volfit.api.state import AppState, FitRecord, UnknownNodeError
from volfit.data.store import VolStore
from volfit.models.lqd.atm import atm_handles


def _params_dict(params) -> dict:
    """LQDParams -> plain JSON-able dict (floats and lists only)."""
    return {"L": float(params.L), "R": float(params.R), "a": [float(x) for x in params.a]}


def persist_fit(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str, record: FitRecord
) -> None:
    """Mirror one cached slice fit into the store's `fits` table.

    No-op without a store path. Deduped on (ticker, expiry, snapshot ts,
    fitMode): refetches of a cache-hit fit and repeated surface fits of the
    same snapshot insert nothing. The dedupe scans load_fits(ticker, expiry)
    — O(rows per node), fine at scaffold scale; an SQL EXISTS (or a unique
    index) is the upgrade path when history grows. Never raises: any failure
    becomes a warning, persistence must not break fitting.
    """
    if state.store_path is None:
        return
    try:
        expiry = date.fromisoformat(expiry_iso)
        created_ts = state.snapshot(ticker).timestamp  # the time-series key
        prepared, result = record.prepared, record.result
        handles = atm_handles(result.slice, prepared.t)
        diagnostics = {
            "t": float(prepared.t),
            "fitMode": fit_mode,
            "forward": float(prepared.forward),
            "discount": float(prepared.discount),
            "atmVol": handles.sigma0,
            "skew": handles.skew,
            "curvature": handles.curvature,
            "varSwapVol": float(np.sqrt(result.slice.var_swap_strike() / prepared.t)),
            "maxIvErrorBp": float(result.max_iv_error) * 1e4,
            "nQuotes": int(len(prepared.k)),
        }
        with VolStore(state.store_path) as store:
            for row in store.load_fits(ticker, expiry):
                same_mode = (row.diagnostics or {}).get("fitMode") == fit_mode
                if row.created_ts == created_ts and same_mode:
                    return  # already persisted for this snapshot
            store.save_fit(
                ticker,
                expiry,
                model=state.fit_settings().model,
                params=_params_dict(result.params),
                diagnostics=diagnostics,
                created_ts=created_ts,
            )
    except Exception as exc:  # noqa: BLE001 — persistence is best-effort
        warnings.warn(f"fit history persistence failed for {ticker} {expiry_iso}: {exc}")


def history_payload(
    state: AppState, ticker: str, tenor_days: int, fit_mode: str
) -> HistoryResponse:
    """Constant-maturity fit history of one ticker at one tenor.

    Groups persisted fits by snapshot timestamp (one snapshot = one surface
    observation) and, within each snapshot, keeps the expiry whose
    days-to-expiry is nearest to ``tenor_days``. Unknown tickers are 404s
    (UnknownNodeError); a missing store path or an empty store is simply an
    empty series — history being unconfigured is not an error.
    """
    if ticker not in state.provider.list_tickers():
        raise UnknownNodeError(f"unknown ticker {ticker!r}")
    points: list[HistoryPoint] = []
    if state.store_path is not None:
        with VolStore(state.store_path) as store:  # fresh handle, see module note
            records = store.load_fits(ticker)
        by_snapshot: dict[str, list] = {}
        for rec in records:
            if (rec.diagnostics or {}).get("fitMode") != fit_mode:
                continue
            by_snapshot.setdefault(rec.created_ts.isoformat(), []).append(rec)
        for ts in sorted(by_snapshot):
            rec = min(
                by_snapshot[ts],
                key=lambda r: abs((r.expiry - r.created_ts.date()).days - tenor_days),
            )
            diag = rec.diagnostics or {}
            points.append(
                HistoryPoint(
                    ts=ts,
                    expiry=rec.expiry.isoformat(),
                    t=diag["t"],
                    atmVol=diag["atmVol"],
                    skew=diag["skew"],
                    curvature=diag["curvature"],
                    varSwapVol=diag["varSwapVol"],
                    maxIvErrorBp=diag["maxIvErrorBp"],
                    forward=diag["forward"],
                )
            )
    return HistoryResponse(
        ticker=ticker, tenorDays=tenor_days, fitMode=fit_mode, points=points
    )

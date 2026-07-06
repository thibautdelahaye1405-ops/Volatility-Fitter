"""Surface export behind GET /export/surfaces (commercial-MVP publish flow).

Serializes the CACHED calibrations — the same frozen fits every view displays
— into downloadable artifacts, stamped with a reproducibility manifest (data
source, as-of, snapshot timestamps, version counters, fit settings) so a
published surface can be traced back to exactly what produced it.

Formats: ``json`` (full fidelity: model curves, LQD backbone params, the LV
grid, per-node quality) and ``csv`` (one row per curve point, Excel-friendly,
flat metadata columns). Parquet is a follow-up (pyarrow is not a dependency).

STRICTLY NO FIT ON READ, like the quality report: only fitted nodes export
(publish what is calibrated), fetched via the calibrated pointer + fit cache;
the per-node quality columns are joined from volfit.api.quality.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel

import volfit
from volfit.api import service
from volfit.api.quality import build_quality_report
from volfit.api.schemas_quality import QualityNode
from volfit.api.state import AppState


class ExportPoint(BaseModel):
    """One model-curve sample: log-moneyness, absolute strike, IV, total var."""

    k: float
    strike: float
    iv: float
    w: float


class ExportNodeQuality(BaseModel):
    rmsBp: float
    maxIvBp: float
    stale: bool
    ready: bool
    issues: list[str]


class ExportNode(BaseModel):
    expiry: str
    t: float  # calendar year fraction
    tau: float  # variance-time year fraction (event clock)
    forward: float
    discount: float
    model: str  # displayed model id
    varSwapVol: float
    lqdParams: dict  # the analytic LQD backbone {L, R, a[]} (reproducibility)
    quality: ExportNodeQuality
    curve: list[ExportPoint]


class ExportLocalVol(BaseModel):
    tNodes: list[float]
    xNodes: list[float]
    vol: list[list[float]]  # nodal local VOLS, one row per t-node


class ExportTicker(BaseModel):
    ticker: str
    spot: float
    snapshotTimestamp: str
    dataVersion: int
    nodes: list[ExportNode]
    localVol: ExportLocalVol | None = None


class ExportManifest(BaseModel):
    """Where this surface came from — enough to reproduce or audit it."""

    generatedAt: str  # UTC ISO instant of the export
    appVersion: str
    source: str  # active data-source id
    asOf: str  # as-of selection ("live", "prev_close", "eod 2026-07-03", ...)
    fitMode: str
    fitSettings: dict  # the full hyperparameter panel (FitSettings)
    optionsSummary: dict  # the calibration-relevant Options toggles
    settingsVersion: int
    optionsVersion: int
    tickers: list[str]
    fittedNodes: int
    litNodes: int  # fitted + not-yet-calibrated (export carries fitted only)
    readyNodes: int  # publish-ready per the quality rule


class SurfaceExport(BaseModel):
    manifest: ExportManifest
    tickers: list[ExportTicker]


def _as_of_label(state: AppState) -> str:
    sel = state.as_of
    parts = [sel.mode]
    for attr in ("on", "ts"):
        value = getattr(sel, attr, None)
        if value is not None:
            parts.append(str(value))
    return " ".join(parts)


def build_manifest(state: AppState, fit_mode: str, report, tickers: list[str]) -> ExportManifest:
    opts = state.options()
    return ExportManifest(
        generatedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        appVersion=volfit.__version__,
        source=state.active_source,
        asOf=_as_of_label(state),
        fitMode=fit_mode,
        fitSettings=state.fit_settings().model_dump(),
        optionsSummary={
            "enforceCalendar": opts.enforceCalendar,
            "varSwapEnabled": opts.varSwapEnabled,
            "localVolEnabled": opts.localVolEnabled,
            "priorPersistenceMode": opts.priorPersistenceMode,
            "observationFilterMode": opts.observationFilterMode,
        },
        settingsVersion=state.settings_version,
        optionsVersion=state.options_version,
        tickers=tickers,
        fittedNodes=report.summary.fitted,
        litNodes=report.summary.litNodes,
        readyNodes=report.summary.readyNodes,
    )


def _export_node(state: AppState, ticker: str, row: QualityNode, fit_mode: str) -> ExportNode | None:
    """One fitted node's export payload (None if its cache entry vanished)."""
    ptr = state.get_calibrated_ptr(ticker, row.expiry, fit_mode)
    record = state.get_fit(ptr[0]) if ptr is not None else None
    if record is None:
        return None
    prepared = record.prepared
    forward = float(prepared.forward)
    tau = float(prepared.tau)
    curve = [
        ExportPoint(
            k=p.k,
            strike=forward * float(np.exp(p.k)),
            iv=p.vol,
            w=p.vol * p.vol * tau,
        )
        for p in service.model_curve(record)
    ]
    params = record.result.params
    var_swap_w = service.displayed_var_swap_w(record)
    return ExportNode(
        expiry=row.expiry,
        t=float(prepared.t),
        tau=tau,
        forward=forward,
        discount=float(prepared.discount),
        model=row.model,
        varSwapVol=float(np.sqrt(max(var_swap_w, 0.0) / tau)) if tau > 0.0 else 0.0,
        lqdParams={"L": float(params.L), "R": float(params.R), "a": [float(v) for v in params.a]},
        quality=ExportNodeQuality(
            rmsBp=row.rmsBp, maxIvBp=row.maxIvBp, stale=row.stale,
            ready=row.ready, issues=row.issues,
        ),
        curve=curve,
    )


def _export_local_vol(state: AppState, ticker: str) -> ExportLocalVol | None:
    from volfit.api import affine_fit

    ptr = state.get_affine_ptr(ticker)
    hit = affine_fit._cache(state).get(ptr) if ptr is not None else None
    if hit is None:
        return None
    return ExportLocalVol(tNodes=hit.tNodes, xNodes=hit.xNodes, vol=hit.localVol)


def build_surface_export(
    state: AppState, fit_mode: str | None = None, tickers: list[str] | None = None
) -> SurfaceExport:
    """Assemble the export from cached fits only (fitted nodes; publish set)."""
    mode = fit_mode if fit_mode is not None else state.last_fit_mode
    report = build_quality_report(state, mode)
    chosen = set(tickers) if tickers else None
    rows_by_ticker: dict[str, list[QualityNode]] = {}
    for row in report.nodes:
        if row.hasFit and (chosen is None or row.ticker in chosen):
            rows_by_ticker.setdefault(row.ticker, []).append(row)

    out: list[ExportTicker] = []
    for ticker, rows in rows_by_ticker.items():
        nodes = [
            node
            for row in rows
            if (node := _export_node(state, ticker, row, mode)) is not None
        ]
        if not nodes:
            continue
        snapshot = state.snapshot(ticker)  # present: the ticker has cached fits
        out.append(
            ExportTicker(
                ticker=ticker,
                spot=float(snapshot.spot),
                snapshotTimestamp=str(snapshot.timestamp),
                dataVersion=state.data_version(ticker),
                nodes=nodes,
                localVol=_export_local_vol(state, ticker),
            )
        )
    return SurfaceExport(
        manifest=build_manifest(state, mode, report, [t.ticker for t in out]),
        tickers=out,
    )


#: CSV column order — flat, one row per curve point, Excel-friendly.
_CSV_COLUMNS = (
    "ticker", "expiry", "t", "tau", "forward", "discount", "spot",
    "snapshot_ts", "model", "k", "strike", "iv", "w",
    "rms_bp", "stale", "ready",
)


def surface_export_csv(export: SurfaceExport) -> str:
    """Flatten a SurfaceExport into CSV text (header + one row per point)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for ticker in export.tickers:
        for node in ticker.nodes:
            for p in node.curve:
                writer.writerow(
                    (
                        ticker.ticker, node.expiry,
                        f"{node.t:.10g}", f"{node.tau:.10g}",
                        f"{node.forward:.10g}", f"{node.discount:.10g}",
                        f"{ticker.spot:.10g}", ticker.snapshotTimestamp,
                        node.model,
                        f"{p.k:.10g}", f"{p.strike:.10g}",
                        f"{p.iv:.10g}", f"{p.w:.10g}",
                        f"{node.quality.rmsBp:.4f}",
                        int(node.quality.stale), int(node.quality.ready),
                    )
                )
    return buf.getvalue()

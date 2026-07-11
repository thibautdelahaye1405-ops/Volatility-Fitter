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
from volfit.models.projection import ProjectedWings, project_published_wings


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
    #: Notes 09/10 Phase 3: the published wings were projected onto the
    #: discrete arb-free set (traded core byte-identical). When True, the
    #: curve's wings differ from the raw displayed model — and from a curve
    #: reconstructed from ``lqdParams``, which stay the UNPROJECTED model.
    curveProjected: bool = False
    #: False when the previous expiry's published wing exceeded this node's
    #: pinned traded edge — a core calendar conflict the wing projection must
    #: not repair (it belongs to the fit / quality gate).
    wingsClean: bool = True


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
    #: Notes 09/10 Phase 3 provenance: whether the publish-time wing projection
    #: ran, and how many nodes it actually moved (0 with wingProjection=True
    #: means every wing was already arb-clean — the projection is a no-op).
    wingProjection: bool = True
    projectedNodes: int = 0
    #: Governance kernel (R1 item 8): the persisted manifest's content-hash id
    #: and its parent in the publish chain. None when no store is configured —
    #: the artifact then visibly lacks lineage. A published manifest is never
    #: mutated; a new publish supersedes it, a recall flips its state.
    manifestId: str | None = None
    parentId: str | None = None


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


def _export_node(
    state: AppState,
    ticker: str,
    row: QualityNode,
    fit_mode: str,
    project: bool = True,
    prev_pub: tuple[np.ndarray, np.ndarray] | None = None,
) -> tuple[ExportNode, tuple[np.ndarray, np.ndarray]] | None:
    """One fitted node's export payload (None if its cache entry vanished).

    With ``project`` the PUBLISHED wings are projected onto the discrete
    arb-free set (Notes 09/10 Phase 3): traded core byte-identical, wings
    lifted to butterfly cleanliness and to the calendar floor of the previous
    expiry's PUBLISHED curve ``prev_pub`` (call ascending in maturity). The
    second return element is this node's published (k, w) — the next expiry's
    floor. In-app views and cached fits are untouched.
    """
    ptr = state.get_calibrated_ptr(ticker, row.expiry, fit_mode)
    record = state.get_fit(ptr[0]) if ptr is not None else None
    if record is None:
        return None
    prepared = record.prepared
    forward = float(prepared.forward)
    tau = float(prepared.tau)
    points = service.model_curve(record)
    k_arr = np.array([p.k for p in points])
    w_arr = np.array([p.vol * p.vol * tau for p in points])
    projected = ProjectedWings(w=w_arr, changed=False, fully_clean=True)
    if project and prepared.k.size:
        projected = project_published_wings(
            k_arr, w_arr,
            float(np.min(prepared.k)), float(np.max(prepared.k)),
            prev_k=prev_pub[0] if prev_pub is not None else None,
            prev_w=prev_pub[1] if prev_pub is not None else None,
        )
    w_pub = np.asarray(projected.w, dtype=float)
    iv_pub = np.sqrt(np.maximum(w_pub, 0.0) / tau) if tau > 0.0 else w_pub * 0.0
    curve = [
        ExportPoint(
            k=p.k,
            strike=forward * float(np.exp(p.k)),
            # Samples the projection moved re-derive IV from the projected w;
            # untouched samples (the whole core) stay byte-identical.
            iv=float(iv_pub[i]) if w_pub[i] != w_arr[i] else p.vol,
            w=float(w_pub[i]),
        )
        for i, p in enumerate(points)
    ]
    params = record.result.params
    var_swap_w = service.displayed_var_swap_w(record)
    node = ExportNode(
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
        curveProjected=projected.changed,
        wingsClean=projected.fully_clean,
    )
    return node, (k_arr, w_pub)


def _export_local_vol(state: AppState, ticker: str) -> ExportLocalVol | None:
    from volfit.api import affine_fit

    ptr = state.get_affine_ptr(ticker)
    hit = affine_fit._cache(state).get(ptr) if ptr is not None else None
    if hit is None:
        return None
    return ExportLocalVol(tNodes=hit.tNodes, xNodes=hit.xNodes, vol=hit.localVol)


def build_surface_export(
    state: AppState,
    fit_mode: str | None = None,
    tickers: list[str] | None = None,
    project_wings: bool = True,
) -> SurfaceExport:
    """Assemble the export from cached fits only (fitted nodes; publish set).

    ``project_wings`` (default ON) runs the Notes 09/10 Phase-3 publish-time
    wing projection per ticker in ascending maturity, so the published surface
    is jointly wing-arb-free; clean wings export byte-identical curves."""
    mode = fit_mode if fit_mode is not None else state.last_fit_mode
    report = build_quality_report(state, mode)
    chosen = set(tickers) if tickers else None
    rows_by_ticker: dict[str, list[QualityNode]] = {}
    for row in report.nodes:
        if row.hasFit and (chosen is None or row.ticker in chosen):
            rows_by_ticker.setdefault(row.ticker, []).append(row)

    out: list[ExportTicker] = []
    projected_nodes = 0
    for ticker, rows in rows_by_ticker.items():
        nodes: list[ExportNode] = []
        prev_pub: tuple[np.ndarray, np.ndarray] | None = None
        # Ascending maturity: each node's calendar floor is the PREVIOUS
        # expiry's published (projected) curve, so the artifact is ordered.
        for row in sorted(rows, key=lambda r: r.tau):
            built = _export_node(state, ticker, row, mode,
                                 project=project_wings, prev_pub=prev_pub)
            if built is None:
                continue
            node, prev_pub = built
            projected_nodes += int(node.curveProjected)
            nodes.append(node)
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
    manifest = build_manifest(state, mode, report, [t.ticker for t in out])
    manifest = manifest.model_copy(
        update={"wingProjection": project_wings, "projectedNodes": projected_nodes}
    )
    return _publish(state, SurfaceExport(manifest=manifest, tickers=out))


def _publish(state: AppState, export: SurfaceExport) -> SurfaceExport:
    """Persist the governance manifest for this publish (R1 item 8).

    Stores, in one transaction: the per-ticker chain snapshots the surfaces
    were built from, the full settings/policy inputs, and the stamped artifact
    itself — everything ``python -m volfit.replay_report`` needs to reproduce
    the published numbers. The manifest id is the content hash of the document
    chained to the previous publish (which it supersedes). Without a store the
    export still succeeds but carries no lineage (manifestId stays None);
    a persistence failure is surfaced as a warning, never a broken export.
    """
    if state.store_path is None or not export.tickers:
        return export
    import warnings

    from volfit.data import governance
    from volfit.data.store import VolStore

    try:
        with VolStore(state.store_path) as store:
            snapshot_ids = {
                t.ticker: store.save_snapshot(state.snapshot(t.ticker))
                for t in export.tickers
            }
            doc = {
                "referenceDate": state.reference_date.isoformat(),
                "generatedAt": export.manifest.generatedAt,
                "appVersion": export.manifest.appVersion,
                "source": export.manifest.source,
                "asOf": export.manifest.asOf,
                "fitMode": export.manifest.fitMode,
                "projectWings": export.manifest.wingProjection,
                "tickers": export.manifest.tickers,
                "fittedNodes": export.manifest.fittedNodes,
                "snapshotIds": snapshot_ids,
                "fitSettings": export.manifest.fitSettings,
                "options": state.options().model_dump(),
                "marketSettings": {
                    t.ticker: state.market_settings(t.ticker).model_dump()
                    for t in export.tickers
                },
                "forwardPolicies": {
                    t.ticker: {
                        n.expiry: state.forward_policy(t.ticker, n.expiry).model_dump()
                        for n in t.nodes
                        if state.forward_policy(t.ticker, n.expiry).mode != "parity"
                    }
                    for t in export.tickers
                },
                "nodes": {t.ticker: [n.expiry for n in t.nodes] for t in export.tickers},
                # Replay fidelity (R1 item 9, closing the v0 gaps): the manifest
                # captures session quote edits, var-swap quotes and active-prior
                # CONTENT for the published scope, so volfit.replay_report can
                # restore them and reproduce edited/anchored fits exactly. The
                # editedNodes/activePriors counts stay for readability and for
                # readers of legacy (v0) manifests.
                **_session_capture(state, export),
                "editedNodes": sum(
                    1
                    for t in export.tickers
                    for n in t.nodes
                    if (s := state.session_if_exists((t.ticker, n.expiry))) is not None
                    and s.edits
                ),
                "activePriors": sum(
                    1 for t in export.tickers if state.active_prior(t.ticker) is not None
                ),
                # A STALE node exports its frozen fit, calibrated at OLDER
                # inputs than this manifest captures — replay recalibrates
                # from the captured inputs, so diffs there are expected and
                # the count is surfaced as a fidelity note.
                "staleNodes": sum(
                    1 for t in export.tickers for n in t.nodes if n.quality.stale
                ),
                "artifactHash": governance.content_id(export.model_dump()),
            }
            mid, parent = governance.chain_ids(store, doc)
            stamped = export.model_copy(
                update={
                    "manifest": export.manifest.model_copy(
                        update={"manifestId": mid, "parentId": parent}
                    )
                }
            )
            governance.save_manifest(
                store, doc, stamped.model_dump_json(), mid=mid, parent=parent
            )
    except Exception as exc:  # noqa: BLE001 — export must not break on lineage
        warnings.warn(f"publish manifest not persisted: {exc}")
        return export
    state.log_event(
        "publish",
        scope=",".join(export.manifest.tickers),
        payload={"manifest": mid, "parent": parent,
                 "nodes": export.manifest.fittedNodes},
    )
    return stamped


def _session_capture(state: AppState, export: SurfaceExport) -> dict:
    """The replay-fidelity content of a publish (R1 item 9), scoped to the
    published nodes: quote-edit sessions (net edit map only — no undo history),
    var-swap quotes, and each published ticker's active-prior snapshot + its
    freshness-ladder source. Keys are always present (possibly empty): their
    PRESENCE is how replay distinguishes a content-capturing manifest from a
    legacy v0 one that only carried counts."""
    session_edits: dict[str, dict] = {}
    varswap_quotes: dict[str, dict] = {}
    prior_content: dict[str, dict] = {}
    prior_sources: dict[str, str] = {}
    for t in export.tickers:
        for n in t.nodes:
            s = state.session_if_exists((t.ticker, n.expiry))
            if s is not None and s.edits:
                session_edits.setdefault(t.ticker, {})[n.expiry] = s.to_doc(history=False)
            vs = state.varswap_session_if_exists((t.ticker, n.expiry))
            if vs is not None and (vs.state.level is not None or vs.state.excluded):
                varswap_quotes.setdefault(t.ticker, {})[n.expiry] = vs.to_doc(history=False)
        snap = state.active_prior(t.ticker)
        if snap is not None:
            prior_content[t.ticker] = snap.model_dump(mode="json")
            prior_sources[t.ticker] = state.active_prior_source(t.ticker) or "saved"
    return {
        "sessionEdits": session_edits,
        "varSwapQuotes": varswap_quotes,
        "activePriorContent": prior_content,
        "activePriorSources": prior_sources,
    }


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

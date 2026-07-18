"""GET /export/* — the publish workflow (surfaces + quality report).

Pure cached-state reads (never fit), like /quality. Responses carry a
Content-Disposition filename so the browser downloads a dated artifact; the
HTML report is served inline (open-in-tab, save from there).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from volfit.api.export import PublishBlockedError, build_surface_export, surface_export_csv
from volfit.api.export_report import build_quality_report_html

router = APIRouter(tags=["export"])


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


def _tickers_param(tickers: str | None) -> list[str] | None:
    if tickers is None or tickers.strip() == "":
        return None
    return [t.strip().upper() for t in tickers.split(",") if t.strip()]


@router.get("/export/surfaces")
def export_surfaces(
    request: Request,
    format: str = "json",
    tickers: str | None = None,
    fit_mode: str | None = None,
    project_wings: bool = True,
    allow_dirty: bool = False,
    inputs: bool = True,
) -> Response:
    """Download the calibrated surfaces (fitted nodes only) + manifest.

    ``format=json`` is the full-fidelity artifact (curves, LQD params, LV grid,
    per-node quality) and by default embeds its INPUTS — the fetched chains,
    market settings, prepared quotes and forward provenance — so the file is
    self-contained for offline recalibration and comparisons; ``inputs=false``
    keeps the slim artifact. ``format=csv`` flattens the curves for Excel
    (never embeds). ``project_wings`` (default on) applies the Notes 09/10
    Phase-3 publish-time wing projection — the published wings are
    discrete-arb-free, the traded core byte-identical; ``project_wings=false``
    exports the raw model wings. A publish set with UNRESOLVED intrinsic or
    calendar inconsistency FAILS with 409 before anything persists (the R2
    exit gate); ``allow_dirty=true`` exports the draft artifact with the
    defects stamped in per-node quality."""
    state = request.app.state.volfit
    try:
        export = build_surface_export(
            state, fit_mode, _tickers_param(tickers),
            project_wings=project_wings, require_clean=not allow_dirty,
            include_inputs=inputs and format != "csv",
        )
    except PublishBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if format == "csv":
        return Response(
            content=surface_export_csv(export),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="volfit_surfaces_{_stamp()}.csv"'
            },
        )
    return JSONResponse(
        content=export.model_dump(),
        headers={
            "Content-Disposition": f'attachment; filename="volfit_surfaces_{_stamp()}.json"'
        },
    )


@router.get("/publish/history")
def publish_history(request: Request, limit: int = 50):
    """The manifest chain, newest first (governance kernel, R1 item 8):
    id, timestamp, parent, lifecycle state, tickers, node count."""
    from volfit.data import governance
    from volfit.data.store import VolStore

    state = request.app.state.volfit
    if state.store_path is None:
        return []
    with VolStore(state.store_path) as store:
        return governance.list_manifests(store, limit)


@router.post("/publish/{manifest_id}/recall")
def recall_publish(manifest_id: str, request: Request):
    """Recall a published surface — the lifecycle transition, not a delete:
    the manifest row, document and artifact all remain for audit/replay."""
    from volfit.data import governance
    from volfit.data.store import VolStore

    state = request.app.state.volfit
    if state.store_path is None:
        raise HTTPException(status_code=409, detail="no persistence store configured")
    with VolStore(state.store_path) as store:
        if not governance.set_manifest_state(store, manifest_id, "recalled"):
            raise HTTPException(status_code=404, detail="unknown manifest id")
    state.log_event("recall", payload={"manifest": manifest_id})
    return {"id": manifest_id, "state": "recalled"}


@router.get("/export/report", response_class=HTMLResponse)
def export_report(
    request: Request,
    fit_mode: str | None = None,
    rms_budget_bp: float | None = None,
) -> HTMLResponse:
    """The self-contained HTML quality/publish report (served inline)."""
    state = request.app.state.volfit
    return HTMLResponse(build_quality_report_html(state, fit_mode, rms_budget_bp))

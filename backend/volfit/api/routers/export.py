"""GET /export/* — the publish workflow (surfaces + quality report).

Pure cached-state reads (never fit), like /quality. Responses carry a
Content-Disposition filename so the browser downloads a dated artifact; the
HTML report is served inline (open-in-tab, save from there).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from volfit.api.export import build_surface_export, surface_export_csv
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
) -> Response:
    """Download the calibrated surfaces (fitted nodes only) + manifest.

    ``format=json`` is the full-fidelity artifact (curves, LQD params, LV grid,
    per-node quality); ``format=csv`` flattens the curves for Excel."""
    state = request.app.state.volfit
    export = build_surface_export(state, fit_mode, _tickers_param(tickers))
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


@router.get("/export/report", response_class=HTMLResponse)
def export_report(
    request: Request,
    fit_mode: str | None = None,
    rms_budget_bp: float | None = None,
) -> HTMLResponse:
    """The self-contained HTML quality/publish report (served inline)."""
    state = request.app.state.volfit
    return HTMLResponse(build_quality_report_html(state, fit_mode, rms_budget_bp))

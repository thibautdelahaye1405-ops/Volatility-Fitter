"""Self-contained HTML fit-quality report behind GET /export/report.

The end-of-day publish artifact: the universe quality screen (summary tiles,
per-ticker rollup, exceptions, full node table) rendered as one static HTML
file with inline CSS — no external assets, safe to email or archive. Built
from the same cached-state quality report as the dashboard (never fits) and
stamped with the export manifest for reproducibility.
"""

from __future__ import annotations

from html import escape

from volfit.api.export import ExportManifest, build_manifest
from volfit.api.quality import build_quality_report
from volfit.api.schemas_quality import QualityNode, QualityReport
from volfit.api.state import AppState

_CSS = """
body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 24px auto; max-width: 1100px;
       color: #1e293b; background: #ffffff; }
h1 { font-size: 20px; margin-bottom: 2px; }
h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b;
     margin: 28px 0 8px; }
.meta { color: #64748b; font-size: 12px; margin-bottom: 18px; }
.tiles { display: flex; flex-wrap: wrap; gap: 10px; }
.tile { border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 14px; min-width: 96px; }
.tile .label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; }
.tile .value { font-size: 18px; font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; font-size: 12px; }
th, td { border-bottom: 1px solid #e2e8f0; padding: 4px 8px; text-align: right;
         font-variant-numeric: tabular-nums; white-space: nowrap; }
th { background: #f8fafc; color: #64748b; font-weight: 600; }
th:first-child, td:first-child { text-align: left; }
.ok { color: #059669; } .warn { color: #b45309; } .bad { color: #dc2626; }
.muted { color: #94a3b8; }
.issues { text-align: left; white-space: normal; }
footer { margin-top: 28px; color: #94a3b8; font-size: 11px; }
"""


def _bp(value: float) -> str:
    """Format a bp figure: 1 decimal normally, 2 sig figs when sub-0.1 (a
    near-exact fit must not display as a fake hard zero)."""
    return f"{value:.1f}" if value >= 0.1 or value == 0.0 else f"{value:.2g}"


def _tile(label: str, value: str, tone: str = "") -> str:
    cls = f"value {tone}".strip()
    return (
        f'<div class="tile"><div class="label">{escape(label)}</div>'
        f'<div class="{cls}">{escape(value)}</div></div>'
    )


def _summary_tiles(report: QualityReport) -> str:
    s = report.summary
    all_ready = s.readyNodes == s.litNodes and s.litNodes > 0
    tiles = [
        _tile("Publish ready", f"{s.readyNodes}/{s.litNodes}", "ok" if all_ready else ""),
        _tile("Fitted", str(s.fitted)),
        _tile("Stale", str(s.stale), "warn" if s.stale else ""),
        _tile("No fit", str(s.noFit), "muted" if s.noFit else ""),
        _tile("Arb flags", str(s.arbFlags), "bad" if s.arbFlags else ""),
        _tile("Median RMS", _bp(s.medianRmsBp) + " bp"),
        _tile("Worst RMS", _bp(s.worstRmsBp) + " bp",
              "warn" if s.worstRmsBp > report.rmsBudgetBp else ""),
        _tile("LV surfaces", f"{s.lvArbFree}/{s.lvTickers} arb-free" if s.lvTickers else "—",
              "bad" if s.lvTickers and s.lvArbFree < s.lvTickers else ""),
    ]
    return f'<div class="tiles">{"".join(tiles)}</div>'


def _ticker_table(report: QualityReport) -> str:
    rows = []
    for t in report.tickers:
        if t.lv is None:
            lv = '<span class="muted">—</span>'
        else:
            tone = "bad" if not t.lv.arbitrageFree else ("warn" if t.lv.stale else "")
            flags = ("" if t.lv.arbitrageFree else f" · arb ({t.lv.calendarViolations} cal)") + (
                " · stale" if t.lv.stale else ""
            )
            lv = f'<span class="{tone}">{_bp(t.lv.rmsIvErrorBp)} bp{escape(flags)}</span>'
        ready_cls = "ok" if t.ready == t.nodes else ""
        rows.append(
            f"<tr><td>{escape(t.ticker)}</td>"
            f'<td class="{ready_cls}">{t.ready}/{t.nodes}</td>'
            f'<td class="{"warn" if t.stale else ""}">{t.stale}</td>'
            f"<td>{_bp(t.surfaceRmsBp)}</td><td>{_bp(t.worstNodeRmsBp)}</td>"
            f'<td class="{"bad" if t.arbFlags else ""}">{t.arbFlags}</td>'
            f"<td>{lv}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Ticker</th><th>Ready</th><th>Stale</th>"
        "<th>Surface RMS bp</th><th>Worst node bp</th><th>Arb</th><th>Local vol</th>"
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def _node_cells(n: QualityNode, budget: float) -> str:
    if not n.hasFit:
        empty = "<td>—</td>" * 6
        return f'<tr><td>{escape(n.ticker)} {escape(n.expiry)}</td>{empty}<td class="issues muted">no fit</td></tr>'
    rms_cls = "warn" if n.rmsBp > budget else ""
    lee_cls = "" if n.leeOk else "bad"
    cal_cls = "" if n.calendarOk else "bad"
    status = '<span class="ok">ready</span>' if n.ready else (
        f'<span class="{"bad" if not (n.leeOk and n.calendarOk) else "warn"}">'
        f"{escape(' · '.join(n.issues))}</span>"
    )
    cal = f"{n.calendarViolation:.1e}" if n.calendarViolation > 0 else "0"
    return (
        f"<tr><td>{escape(n.ticker)} {escape(n.expiry)}</td>"
        f"<td>{escape(n.model)}</td><td>{n.nQuotes}</td>"
        f'<td class="{rms_cls}">{_bp(n.rmsBp)}</td><td>{_bp(n.maxIvBp)}</td>'
        f'<td class="{lee_cls}">{n.leeLeft:.2f}/{n.leeRight:.2f}</td>'
        f'<td class="{cal_cls}">{cal}</td><td class="issues">{status}</td></tr>'
    )


def _node_table(nodes: list[QualityNode], budget: float) -> str:
    header = (
        "<table><thead><tr><th>Node</th><th>Model</th><th>#Q</th><th>RMS bp</th>"
        "<th>Max IV bp</th><th>Lee L/R</th><th>Cal viol</th><th>Status</th></tr></thead>"
    )
    return header + "<tbody>" + "".join(_node_cells(n, budget) for n in nodes) + "</tbody></table>"


def _manifest_block(manifest: ExportManifest) -> str:
    fs = manifest.fitSettings
    parts = [
        f"generated {manifest.generatedAt}",
        f"volfit {manifest.appVersion}",
        f"source {manifest.source}",
        f"as-of {manifest.asOf}",
        f"fit mode {manifest.fitMode}",
        f"model {fs.get('model', '?')}",
        f"prior {manifest.optionsSummary.get('priorPersistenceMode', '?')}",
        f"filter {manifest.optionsSummary.get('observationFilterMode', '?')}",
        f"versions s{manifest.settingsVersion}/o{manifest.optionsVersion}",
    ]
    return f'<div class="meta">{escape(" · ".join(parts))}</div>'


def build_quality_report_html(
    state: AppState, fit_mode: str | None = None, rms_budget_bp: float | None = None
) -> str:
    """Render the publish report (one self-contained HTML document)."""
    from volfit.api.quality import DEFAULT_RMS_BUDGET_BP

    budget = rms_budget_bp if rms_budget_bp is not None else DEFAULT_RMS_BUDGET_BP
    mode = fit_mode if fit_mode is not None else state.last_fit_mode
    report = build_quality_report(state, mode, budget)
    manifest = build_manifest(state, mode, report, [t.ticker for t in report.tickers])
    exceptions = [n for n in report.nodes if not n.ready]
    exceptions_html = (
        _node_table(exceptions, budget)
        if exceptions
        else '<p class="meta ok">None — every lit node is publish-ready.</p>'
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>volfit quality report — {escape(manifest.generatedAt)}</title>
<style>{_CSS}</style></head><body>
<h1>volfit — surface quality report</h1>
{_manifest_block(manifest)}
{_summary_tiles(report)}
<h2>Tickers</h2>
{_ticker_table(report)}
<h2>Exceptions ({len(exceptions)})</h2>
{exceptions_html}
<h2>All nodes ({len(report.nodes)})</h2>
{_node_table(report.nodes, budget)}
<footer>Publish rule: fitted ∧ not stale ∧ Lee ≤ 2 ∧ calendar-clean ∧ RMS ≤ {budget:.0f} bp.
Report reads cached calibrations only.</footer>
</body></html>"""

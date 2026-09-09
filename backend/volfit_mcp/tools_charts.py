"""Chart tools: the same numbers as ``tools_views`` with an inline UI attached.

Each chart tool is bound (MCP Apps, ``mcp.server.apps``) to a ``ui://volfit/...``
HTML resource from ``volfit_mcp/ui`` that the host renders in a sandboxed
iframe and feeds the tool's ``structuredContent``. Hosts that did not
negotiate MCP Apps (Claude Code, mobile) still get the structured data and the
text summary, plus a matplotlib PNG when ``png=True`` (``render_png``).

Structured-content contracts (the HTML reads exactly these keys):

* ``chart_lv_compare`` -> ``{"kind": "lv_compare", "tickers": [{ticker, tNodes,
  xNodes, affine, twin, diff, expiries: [{expiry, t, affineRmsBp, twinRmsBp,
  parametricRmsBp, roundTripBp}], hasAffine, affineStale, twinRepairs}], ...}``
* ``chart_smile`` -> ``compact_smile`` + ``{"kind": "smile", "expiries": [...],
  "lv": [[k, vol], ...] | null}``
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import resources
from typing import Any, Literal

from mcp.server.apps import Apps, ResourceCsp, client_supports_apps
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.utilities.types import Image
from mcp.types import CallToolResult, ContentBlock, TextContent, ToolAnnotations

from volfit_mcp import aliases, render_png
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import compact_compare, compact_smile, curve, md_table

READ_ONLY = ToolAnnotations(read_only_hint=True)
FitMode = Literal["mid", "bidask", "haircut"]
LV_COMPARE_URI = "ui://volfit/lv-compare.html"
SMILE_URI = "ui://volfit/smile.html"
#: Plotly is loaded from its CDN inside the sandbox; nothing else is external.
CSP = ResourceCsp(resource_domains=["https://cdn.plot.ly"])


def _html(name: str) -> str:
    """One UI page with the shared postMessage bridge inlined."""
    ui = resources.files("volfit_mcp") / "ui"
    bridge = (ui / "bridge.js").read_text(encoding="utf-8")
    page = (ui / name).read_text(encoding="utf-8")
    return page.replace("/*__BRIDGE__*/", bridge)


def build_apps() -> Apps:
    apps = Apps()
    apps.add_html_resource(LV_COMPARE_URI, _html("lv_compare.html"), name="volfit-lv-compare",
                           title="Local Vol compare", csp=CSP, prefers_border=True)
    apps.add_html_resource(SMILE_URI, _html("smile.html"), name="volfit-smile",
                           title="Smile viewer", csp=CSP, prefers_border=True)
    return apps


def _blocks(text: str, png: bytes | None) -> list[ContentBlock]:
    blocks: list[ContentBlock] = [TextContent(type="text", text=text)]
    if png:
        blocks.append(Image(data=png, format="png").to_image_content())
    return blocks


def register(api: VolfitApi, apps: Apps) -> None:
    """Bind the chart tools to ``apps``. Must run BEFORE ``MCPServer(extensions=
    [apps])`` is built: the server consumes an extension's tools at construction."""

    @apps.tool(resource_uri=LV_COMPARE_URI, annotations=READ_ONLY)
    async def chart_lv_compare(
        ctx: Context,
        tickers: list[str] | None = None,
        fit_mode: FitMode | None = None,
        t_interp: Literal["smooth", "buckets"] = "smooth",
        png: bool = False,
    ) -> CallToolResult:
        """Chart the comparative Local-Vol surfaces of one or more tickers
        (default: the whole universe): the affine LV sheet calibrated to the
        quotes, the Dupire twin of the parametric surface on the same (t, K/F)
        lattice, their signed difference, and the per-expiry rms of each
        against the quotes — as an interactive 3D / heatmap view rendered in
        the chat (Claude Desktop / claude.ai). ``png=True`` adds a static
        image for hosts without inline apps. Requires a calibration with
        Local-Vol on."""
        if tickers:
            names = [aliases.resolve(t).ticker for t in tickers]
        else:
            names = list((await api.get("/universe")).get("tickers", []))
        panels: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for t in names:
            body: dict[str, Any] = {"tInterp": t_interp}
            if fit_mode:
                body["fitMode"] = fit_mode
            try:
                cmp = compact_compare(await api.post(f"/fit/affine/{t}/compare", body), with_grid=True)
            except Exception as exc:  # one ticker without a fit must not sink the chart
                skipped.append({"ticker": t, "reason": str(exc)[:300]})
                continue
            panels.append({
                "ticker": cmp["ticker"],
                "hasAffine": cmp["hasAffine"],
                "affineStale": cmp["affineStale"],
                "tNodes": cmp["tNodes"],
                "xNodes": cmp["xNodes"],
                "affine": cmp["localVolAffine"],
                "twin": cmp["localVolTwin"],
                "diff": cmp["diffLocalVol"],
                "twinRepairs": cmp["twinRepairs"],
                "expiries": [
                    {"expiry": e["expiry"], "t": e["t"],
                     "affineRmsBp": (e["affine"] or {}).get("rmsBp"),
                     "twinRmsBp": (e["twin"] or {}).get("rmsBp"),
                     "parametricRmsBp": (e["parametric"] or {}).get("rmsBp"),
                     "roundTripBp": e["roundTripBp"]}
                    for e in cmp["expiries"]
                ],
            })
        structured = {"kind": "lv_compare", "fitMode": fit_mode, "tInterp": t_interp,
                      "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "tickers": panels, "skipped": skipped}
        lines = []
        for p in panels:
            lines.append(f"{p['ticker']}: affine {'present' if p['hasAffine'] else 'MISSING'}"
                         f"{' (stale)' if p['affineStale'] else ''}, twin repairs "
                         f"{'none' if p['twinRepairs'].get('clean') else p['twinRepairs']}")
            lines.append(md_table(p["expiries"], ["expiry", "t", "affineRmsBp", "twinRmsBp", "parametricRmsBp", "roundTripBp"]))
        for s in skipped:
            lines.append(f"{s['ticker']}: skipped — {s['reason']}")
        if not panels:
            lines.append("Nothing to chart: no ticker has a Local-Vol compare (calibrate with Local-Vol on first).")
        elif not client_supports_apps(ctx):
            lines.append("(This host does not render inline apps; the surfaces are in structuredContent"
                         + (", a PNG is attached." if png else "; pass png=true for an image.)"))
        image = render_png.lv_compare_png(structured) if (png and panels) else None
        return CallToolResult(content=_blocks("\n".join(lines), image), structured_content=structured)

    @apps.tool(resource_uri=SMILE_URI, annotations=READ_ONLY)
    async def chart_smile(
        ctx: Context,
        ticker: str,
        expiry: str,
        fit_mode: FitMode | None = None,
        with_lv: bool = False,
        png: bool = False,
    ) -> CallToolResult:
        """Chart one smile in the chat: the fitted curve against the bid/ask
        IV bands, the saved prior, and (``with_lv``) the Local-Vol surface's
        reconstruction of the same expiry, with the slice diagnostics; the
        view can step to the previous / next expiry. ``expiry`` is an ISO date
        from ``list_expiries``."""
        res = aliases.resolve(ticker)
        sm = await api.get(f"/smiles/{res.ticker}/{expiry}", fit_mode=fit_mode)
        out = compact_smile(sm, max_points=81)
        out["kind"] = "smile"
        lit = await api.get("/universe/lit")
        out["expiries"] = [n["expiry"] for n in lit.get("nodes", []) if n["ticker"] == res.ticker and n.get("lit")]
        out["lv"] = None
        if with_lv:
            body = {"fitMode": fit_mode} if fit_mode else {}
            try:
                fit = await api.post(f"/fit/affine/{res.ticker}", body)
                match = next((s for s in fit.get("smiles", []) if s["expiry"] == expiry), None)
                if match:
                    out["lv"] = curve(match["model"], 81)
                    out["lvRmsBp"] = round(1e4 * float(match.get("rmsError", 0.0)), 1)
            except Exception as exc:
                out["lvError"] = str(exc)[:300]
        d = out["diagnostics"]
        text = (f"{out['ticker']} {out['expiry']} {out['model']}: rms {d['rmsBp']} bp over {out['nQuotes']} quotes, "
                f"ATM {d['atmVol']}, skew {d['skew']}, curvature {d['curvature']}, Lee {d['leeLeft']}/{d['leeRight']}"
                + (f"; LV reconstruction rms {out['lvRmsBp']} bp" if out.get("lvRmsBp") is not None else ""))
        image = render_png.smile_png(out) if png else None
        return CallToolResult(content=_blocks(text, image), structured_content=out)

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

import os
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from mcp.server.apps import APP_MIME_TYPE, Apps, ResourceCsp, client_supports_apps
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.resources import FunctionResource
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


def _legacy_meta(uri: str) -> dict[str, str]:
    """The pre-2026-01-26 tool metadata key. The reference app servers (the
    TypeScript ``registerAppTool``) stamp BOTH ``_meta.ui.resourceUri`` and
    ``_meta["ui/resourceUri"]``; hosts of the older vintage (Claude Desktop
    on protocol 2025-11-25) mount the app from the legacy key."""
    return {"ui/resourceUri": uri}


#: Plotly bundle per page: (cache file, CDN URL, the exact tag the page carries).
_PLOTLY = {
    "lv_compare.html": ("plotly-3.1.0.min.js", "https://cdn.plot.ly/plotly-3.1.0.min.js"),
    "smile.html": ("plotly-basic-3.1.0.min.js", "https://cdn.plot.ly/plotly-basic-3.1.0.min.js"),
}
_TAG = '<script src="{url}" async onload="window.__plotlyLoaded()" onerror="window.__plotlyFailed()"></script>'
_CACHE = Path(os.environ.get("VOLFIT_MCP_CACHE") or Path(__file__).resolve().parent.parent / ".cache")


def _plotly_bundle(name: str) -> str | None:
    """The Plotly source to inline, or ``None`` to keep the CDN tag.

    Self-contained pages are what the reference app servers ship and the only
    thing every host sandbox renders (a CSP that ignores ``resourceDomains``
    silently blocks the CDN). ``VOLFIT_MCP_PLOTLY=cdn`` keeps the 15 KB page
    + CDN load; the default inlines a cached bundle (downloaded once into
    ``backend/.cache``), falling back to the CDN when it cannot be fetched."""
    if os.environ.get("VOLFIT_MCP_PLOTLY", "inline").lower() == "cdn":
        return None
    fname, url = _PLOTLY[name]
    path = _CACHE / fname
    if not path.exists():
        try:
            import httpx

            data = httpx.get(url, timeout=60.0, follow_redirects=True)
            data.raise_for_status()
            _CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(data.text, encoding="utf-8")
        except Exception:
            return None
    src = path.read_text(encoding="utf-8")
    return src.replace("</script", "<\/script")  # never close our own tag


def _html(name: str) -> str:
    """One UI page with the shared postMessage bridge (and Plotly) inlined."""
    ui = resources.files("volfit_mcp") / "ui"
    bridge = (ui / "bridge.js").read_text(encoding="utf-8")
    page = (ui / name).read_text(encoding="utf-8").replace("/*__BRIDGE__*/", bridge)
    bundle = _plotly_bundle(name)
    if bundle is not None:
        tag = _TAG.format(url=_PLOTLY[name][1])
        assert tag in page, f"{name}: Plotly tag drifted from _TAG"
        page = page.replace(tag, "<script>" + bundle + "</script><script>window.__plotlyLoaded()</script>")
    return page


def _page_resource(uri: str, name: str, title: str, page: str) -> FunctionResource:
    """A ``ui://`` resource rendered from disk on EVERY read, so an edit to the
    page (or the bridge) reaches a host that keeps the server process alive
    across app restarts — Claude Desktop lingers in the tray — without a
    relaunch. Same ``_meta.ui`` as ``Apps.add_html_resource`` would stamp."""
    return FunctionResource(
        uri=uri, name=name, title=title, mime_type=APP_MIME_TYPE,
        meta={"ui": {"csp": CSP.model_dump(by_alias=True, exclude_none=True), "prefersBorder": True}},
        fn=lambda: _html(page),
    )


def build_apps() -> Apps:
    apps = Apps()
    apps.add_resource(_page_resource(LV_COMPARE_URI, "volfit-lv-compare", "Local Vol compare", "lv_compare.html"))
    apps.add_resource(_page_resource(SMILE_URI, "volfit-smile", "Smile viewer", "smile.html"))
    return apps


def _blocks(text: str, png: bytes | None) -> list[ContentBlock]:
    blocks: list[ContentBlock] = [TextContent(type="text", text=text)]
    if png:
        blocks.append(Image(data=png, format="png").to_image_content())
    return blocks


def register(api: VolfitApi, apps: Apps) -> None:
    """Bind the chart tools to ``apps``. Must run BEFORE ``MCPServer(extensions=
    [apps])`` is built: the server consumes an extension's tools at construction."""

    @apps.tool(resource_uri=LV_COMPARE_URI, meta=_legacy_meta(LV_COMPARE_URI), annotations=READ_ONLY)
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

    @apps.tool(resource_uri=SMILE_URI, meta=_legacy_meta(SMILE_URI), annotations=READ_ONLY)
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

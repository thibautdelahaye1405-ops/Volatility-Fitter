"""Chart tools two and three: the implied-vol surface and the term structure.

* ``chart_vol_surface`` — the parametric surface sigma(k, T) on the app's
  shared log-moneyness grid (``GET /surface``) with the per-expiry display
  crops (the quoted range at three tail-probability levels), the exact ATM
  handle and forward per expiry; rendered as a 3D surface or heatmap.
* ``chart_term_structure`` — ``POST /term``: the ATM term structure and the
  fair var-swap vol per expiry, the dense interpolated curve in vol and in
  total variance, the event-dilated calendar (t vs tau), calendar violations,
  dividend markers and the event calendar (``GET /events``).

Same conventions as ``tools_charts``: bound to a ``ui://volfit/...`` page,
structured content the page reads verbatim, a text summary for the model, a
matplotlib PNG on request.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.apps import Apps, client_supports_apps
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, ToolAnnotations

from volfit_mcp import aliases, ops, render_png
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import md_table, r, thin
from volfit_mcp.tools_charts import TERM_URI, VOL_SURFACE_URI, _blocks, _legacy_meta, workbench_url

READ_ONLY = ToolAnnotations(read_only_hint=True)
FitMode = Literal["mid", "bidask", "haircut"]


def compact_surface(sf: dict[str, Any], max_k: int = 71) -> dict[str, Any]:
    """``SurfaceResponse`` thinned to ``max_k`` strike columns, crops kept."""
    keep = [p["j"] for p in thin([{"k": k, "j": j} for j, k in enumerate(sf["k"])], max_k)]
    crops = []
    for c in sf.get("cropRanges") or []:
        crops.append([{"u": u, "lo": r(lo), "hi": r(hi)} for u, lo, hi in zip(c["u"], c["lo"], c["hi"])])
    return {
        "kind": "vol_surface",
        "ticker": sf["ticker"],
        "expiries": sf["expiries"],
        "t": [r(v) for v in sf["t"]],
        "tau": [r(v) for v in sf.get("tau") or sf["t"]],
        "k": [r(sf["k"][j]) for j in keep],
        "vol": [[r(row[j]) for j in keep] for row in sf["vol"]],
        "atmVol": [r(v) for v in sf["atmVol"]],
        "forward": [r(v) for v in sf["forward"]],
        "crop": crops,
    }


def compact_term(tm: dict[str, Any], events: list[dict[str, Any]], fit_mode: str | None) -> dict[str, Any]:
    pts = [{"expiry": p["expiry"], "t": r(p["t"]), "tau": r(p["tau"]), "atmVol": r(p["atmVol"]),
            "w0": r(p.get("w0"), 6), "varSwapVol": r(p.get("varSwapVol")), "varSwapQuote": r(p.get("varSwapQuote")),
            "varSwapExcluded": p.get("varSwapExcluded", False), "maxIvErrorBp": r(p.get("maxIvErrorBp"), 1),
            "priorVol": r(p.get("priorVol"))} for p in tm["points"]]
    cv = tm["curve"]
    return {
        "kind": "term",
        "ticker": tm["ticker"],
        "fitMode": fit_mode,
        "points": pts,
        "curve": {"t": [r(v) for v in cv["t"]], "tau": [r(v) for v in cv["tau"]],
                  "w": [r(v, 6) for v in cv["w"]], "vol": [r(v) for v in cv["vol"]]},
        "calendarViolations": tm.get("calendarViolations", 0),
        "dividends": [{"exDate": d["exDate"], "t": r(d["t"]), "tau": r(d["tau"]), "amount": r(d["amount"])}
                      for d in tm.get("dividends") or []],
        "events": [{"time": r(e["time"]), "weight": r(e["weight"]), "label": e.get("label", "")} for e in events],
    }


def register(api: VolfitApi, apps: Apps) -> None:
    """Bind both tools to their pages (before the server is built)."""

    @apps.tool(resource_uri=VOL_SURFACE_URI, meta=_legacy_meta(VOL_SURFACE_URI), annotations=READ_ONLY)
    async def chart_vol_surface(
        ctx: Context, ticker: str, fit_mode: FitMode | None = None, png: bool = False
    ) -> CallToolResult:
        """Chart the implied-vol surface of one ticker in the chat: every
        calibrated expiry's smile on a shared log-moneyness grid as a 3D
        surface or heatmap (axis in k = ln K/F, K/F or strike), the quoted
        range per expiry (crop chip), the ATM ridge, and the ATM / forward
        table. ``png=True`` adds a static image for hosts without inline apps."""
        res = aliases.resolve(ticker)
        sf = await api.get(f"/surface/{res.ticker}", fit_mode=fit_mode)
        out = compact_surface(sf)
        out["fitMode"] = fit_mode
        out["workbenchUrl"] = workbench_url()
        rows = [{"expiry": e, "t": t, "atmVol": a, "forward": f}
                for e, t, a, f in zip(out["expiries"], out["t"], out["atmVol"], out["forward"])]
        text = [f"{out['ticker']} implied-vol surface: {len(out['expiries'])} expiries x {len(out['k'])} strikes "
                f"(k from {out['k'][0]} to {out['k'][-1]}); ATM term structure:",
                md_table(rows, ["expiry", "t", "atmVol", "forward"])]
        if not client_supports_apps(ctx):
            text.append("(This host does not render inline apps; the mesh is in structuredContent"
                        + (", a PNG is attached.)" if png else "; pass png=true for an image.)"))
        image = render_png.vol_surface_png(out) if png else None
        return CallToolResult(content=_blocks("\n".join(text), image), structured_content=out)

    @apps.tool(resource_uri=TERM_URI, meta=_legacy_meta(TERM_URI), annotations=READ_ONLY)
    async def chart_term_structure(
        ctx: Context, ticker: str, fit_mode: FitMode | None = None, png: bool = False
    ) -> CallToolResult:
        """Chart the term structure of one ticker in the chat: ATM vol and the
        fair var-swap vol per expiry with the dense interpolated curve, in vol
        and in total variance, on the calendar clock or the event-dilated
        clock (tau), with the event calendar, dividend ex-dates and any
        calendar violation flagged. Clicking an expiry asks for its smile."""
        res = aliases.resolve(ticker)
        body: dict[str, Any] = {}
        if fit_mode:
            body["fitMode"] = fit_mode
        tm = await api.post(f"/term/{res.ticker}", body)
        events = (await api.get(f"/events/{res.ticker}")).get("events") or []
        out = compact_term(tm, events, fit_mode)
        out["workbenchUrl"] = workbench_url()
        rows = [{"expiry": p["expiry"], "t": p["t"], "tau": p["tau"], "atmVol": p["atmVol"],
                 "varSwapVol": p["varSwapVol"], "w0": p["w0"], "maxIvErrorBp": p["maxIvErrorBp"]} for p in out["points"]]
        text = [f"{out['ticker']} term structure: {len(rows)} expiries, calendar violations {out['calendarViolations']}, "
                f"events {len(out['events'])}, dividend ex-dates {len(out['dividends'])}",
                md_table(rows, ["expiry", "t", "tau", "atmVol", "varSwapVol", "w0", "maxIvErrorBp"])]
        if out["events"]:
            text.append("Events: " + md_table(out["events"], ["time", "weight", "label"]))
        if not client_supports_apps(ctx):
            text.append("(This host does not render inline apps; the curves are in structuredContent"
                        + (", a PNG is attached.)" if png else "; pass png=true for an image.)"))
        image = render_png.term_png(out) if png else None
        return CallToolResult(content=_blocks("\n".join(text), image), structured_content=out)

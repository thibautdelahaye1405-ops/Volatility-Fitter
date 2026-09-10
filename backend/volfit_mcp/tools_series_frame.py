"""The frame views of a series (SERIES ARC S6): ``series_frame`` — the
model-sized summary of one frame plus the curves and quotes of ONE expiry —
and ``chart_series_frame``, the same document bound to the series app
(``ui/series.html``): the frame's bid/ask bands and every lane's smile for
the shown expiry, an expiry select, prev / next buttons and a slider over
the frames that call ``series_frame`` through ``tools/call`` and redraw
without a second round trip (the smile app's prev / next pattern).

Structured-content contract (the page reads exactly these keys)::

    {"kind": "series_frame", seriesId, name, ticker, mode, step, fitMode,
     status, nFrames, requestedLanes, laneOrder: [id], laneNames: {id: name},
     laneColours: {id: colour | null},
     frame: {idx, ts, quoteKind, spot, status, nQuotes, expiries},
     lanes: {id: {status, rmsBp, maxIvBp, fitMs, nSlices,
                  slices: {expiry: {atmVol, rmsBp, maxIvBp, skew}}}},
     shown: {expiry, t, forward, quotes: [{k, bid, ask, mid, strike}],
             curves: {id: {k: [], iv: [], rmsBp, atmVol}}},
     workbenchUrl}

Units as everywhere in the connector: vols as decimals, rms in vol bp,
``k = ln(K/F)``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.apps import Apps, client_supports_apps
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ToolAnnotations

from volfit_mcp import render_png
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import md_table, r, thin
from volfit_mcp.tools_charts import SERIES_URI, _blocks, _legacy_meta, _page_resource
from volfit_mcp.tools_series import _result, series_link

READ_ONLY = ToolAnnotations(read_only_hint=True)
MAX_POINTS = 81


def _keep(n: int, max_points: int) -> list[int]:
    return [p["j"] for p in thin([{"j": j} for j in range(n)], max_points)]


async def frame_doc(api: VolfitApi, series_id: str, frame: int, lanes: list[str] | None,
                    expiry: str | None, max_points: int = MAX_POINTS) -> dict[str, Any]:
    """``GET /series/{id}`` + ``GET /series/{id}/frame/{idx}`` compacted to
    the contract above. ``frame`` counts from 0; negative = from the end."""
    doc = await api.get(f"/series/{series_id}")
    frames = doc.get("frames") or []
    n = len(frames)
    if n == 0:
        raise ToolError(f"series {series_id} has no frame")
    idx = frame + n if frame < 0 else frame
    if not 0 <= idx < n:
        raise ToolError(f"frame {frame} is out of range: series {series_id} has frames 0..{n - 1}")
    fp = await api.get(f"/series/{series_id}/frame/{idx}", lanes=",".join(lanes) if lanes else None)
    fr = frames[idx]
    expiries = fp.get("expiries") or fr.get("expiries") or []
    if expiry and expiry not in expiries:
        raise ToolError(f"expiry {expiry} is not in frame {idx} of series {series_id} (expiries: {expiries})")
    shown = expiry or (expiries[0] if expiries else None)
    spec = doc["spec"]
    lane_specs = [ln for ln in spec.get("lanes") or [] if not lanes or ln["id"] in lanes]
    lanes_out: dict[str, Any] = {}
    curves: dict[str, Any] = {}
    for lid, ld in (fp.get("lanes") or {}).items():
        m = ld.get("metrics") or {}
        slices: dict[str, Any] = {}
        for s in ld.get("slices") or []:
            sm = s.get("metrics") or {}
            slices[s["expiry"]] = {"atmVol": r(s.get("atmVol")), "rmsBp": r(sm.get("rmsBp"), 1),
                                   "maxIvBp": r(sm.get("maxIvBp"), 1), "skew": r(s.get("skew"))}
            if s["expiry"] == shown:
                keep = _keep(len(s.get("k") or []), max_points)
                curves[lid] = {"k": [r(s["k"][j]) for j in keep], "iv": [r(s["iv"][j]) for j in keep],
                               "rmsBp": r(sm.get("rmsBp"), 1), "atmVol": r(s.get("atmVol"))}
        lanes_out[lid] = {"status": ld.get("status"), "rmsBp": r(m.get("rmsBp"), 1), "maxIvBp": r(m.get("maxIvBp"), 1),
                          "fitMs": r(m.get("fitMs"), 0), "nSlices": m.get("nSlices"), "slices": slices}
    mk = (fp.get("market") or {}).get(shown) or {}
    quotes = [{"k": r(q["k"]), "bid": r(q["bid"]), "ask": r(q["ask"]), "mid": r(q["mid"]), "strike": r(q.get("strike"), 2)}
              for q in mk.get("quotes") or []]
    return {
        "kind": "series_frame", "seriesId": series_id, "name": spec["name"], "ticker": spec["ticker"],
        "mode": spec["mode"], "step": spec["clock"]["step"], "fitMode": spec["fitMode"],
        "status": (doc.get("progress") or {}).get("status"), "nFrames": n, "requestedLanes": lanes,
        "laneOrder": [ln["id"] for ln in lane_specs], "laneNames": {ln["id"]: ln["name"] for ln in lane_specs},
        "laneColours": {ln["id"]: ln.get("colour") for ln in lane_specs},
        "frame": {"idx": idx, "ts": fp.get("ts") or fr["ts"], "quoteKind": fp.get("quoteKind") or fr.get("quoteKind"),
                  "spot": r(fp.get("spot") if fp.get("spot") is not None else fr.get("spot")), "status": fr.get("status"),
                  "nQuotes": fr.get("nQuotes"), "expiries": expiries, "error": fr.get("error")},
        "lanes": lanes_out,
        "shown": {"expiry": shown, "t": r(mk.get("t")), "forward": r(mk.get("forward")), "quotes": quotes, "curves": curves},
        "workbenchUrl": series_link(doc, idx, shown),
    }


def frame_text(out: dict[str, Any]) -> str:
    f, sh = out["frame"], out["shown"]
    rows = [{"lane": lid, "expiry": e, **v}
            for lid, ln in out["lanes"].items() for e, v in ln["slices"].items()]
    head = (f"{out['name']} ({out['ticker']}, {out['mode']}, {out['status']}) frame {f['idx'] + 1}/{out['nFrames']} "
            f"· {f['ts']} · {f['quoteKind'] or 'quotes'} · spot {f['spot']}; shown expiry {sh['expiry']} "
            f"({len(sh['quotes'])} quotes, F {sh['forward']}, t {sh['t']})")
    if f.get("status") != "ready":
        head += f" — frame {f.get('status')}" + (f": {f['error']}" if f.get("error") else "")
    return head + "\n" + md_table(rows, ["lane", "expiry", "atmVol", "rmsBp", "maxIvBp", "skew"])


def register_apps(api: VolfitApi, apps: Apps) -> None:
    """Bind the series page + the chart tool to ``apps`` (before the server is built)."""
    apps.add_resource(_page_resource(SERIES_URI, "volfit-series", "Series frame", "series.html"))

    @apps.tool(resource_uri=SERIES_URI, meta=_legacy_meta(SERIES_URI), annotations=READ_ONLY)
    async def chart_series_frame(
        ctx: Context, id: str, frame: int = 0, expiry: str | None = None,
        lanes: list[str] | None = None, png: bool = False,
    ) -> CallToolResult:
        """Chart one frame of a series in the chat: the frame's bid/ask bands
        and every lane's fitted smile for one expiry (default the first),
        the instant, quote kind and frame i/n in the title, an expiry
        select, prev / next buttons and a slider over the frames (each step
        fetches the neighbouring frame), a legend with the per-lane rms bp
        and a Workbench button. ``frame`` counts from 0 (negative = from the
        end). ``png=True`` adds a static image for hosts without inline apps."""
        out = await frame_doc(api, id, frame, lanes, expiry)
        text = frame_text(out)
        if not client_supports_apps(ctx):
            text += ("\n(This host does not render inline apps; the curves are in structuredContent"
                     + (", a PNG is attached.)" if png else "; pass png=true for an image.)"))
        image = render_png.series_frame_png(out) if png else None
        return CallToolResult(content=_blocks(text, image), structured_content=out)


def register(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def series_frame(id: str, frame: int, lanes: list[str] | None = None,
                           expiry: str | None = None) -> CallToolResult:
        """One frame of a series: the instant, spot and quote kind, and per
        lane per expiry the ATM vol / rms bp / skew (model-sized), plus the
        quotes and every lane's smile curve for ONE expiry (``expiry``, else
        the first) — the document the series chart redraws from. ``frame``
        counts from 0 (negative = from the end); ``lanes`` restricts the
        lanes (default all)."""
        out = await frame_doc(api, id, frame, lanes, expiry)
        return _result(frame_text(out), out)

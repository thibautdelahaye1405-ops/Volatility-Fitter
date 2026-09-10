"""Series tools (SERIES ARC S6): a stored series driven from the chat.

A *series* is one ticker x an ordered set of instants x a set of *lanes*
(model configurations evaluated THROUGH TIME: a lane's prior at frame i is
its own frame i-1 fit, a filter lane carries its state frame to frame, a
free lane has no temporal state). The app harvests the frames — from a
source with history (historical), from now on (live: a frame per tick, and
every frame whose instant is already past lands at once), or from stored
snapshots (import) — then calibrates every lane over them in a background
job of its own, never the Calibrate slot.

These tools wrap ``/series``: ``create_series`` (the dialog's lane presets
resolved through ``GET /series/presets``), ``import_series``,
``wait_for_series`` (the ``wait_for_workflow`` idiom: returns on a terminal
status or when the wait elapses, never raises on a pending series),
``series_report`` (the Lanes stage's evidence as a table), ``series_control``
and ``list_series``. The frame views (``series_frame`` and the inline chart)
live in ``tools_series_frame``.
"""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any, Literal
from urllib.parse import quote

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from volfit_mcp import aliases, ops
from volfit_mcp.client import ApiError, VolfitApi
from volfit_mcp.report import md_table, r
from volfit_mcp.tools_charts import workbench_url

MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)
READ_ONLY = ToolAnnotations(read_only_hint=True)
FitMode = Literal["mid", "bidask", "haircut"]
SeriesStep = Literal["1m", "5m", "15m", "30m", "1h", "session_close", "daily", "weekly"]
ImportKind = Literal["store", "fixtures", "captures"]
DEFAULT_PRESETS = ("lqd_free", "lqd_prior")
DEFAULT_WAIT_S = 60.0
POLL_S = 1.0
#: A wait returns on these: the runner has stopped, or never started (draft).
TERMINAL = frozenset({"done", "failed", "cancelled", "paused", "draft"})
RUNNING = frozenset({"queued", "harvesting", "calibrating"})
EVIDENCE_COLS = ["lane", "name", "frames", "failed", "meanRmsBp", "meanMaxBp", "worstFrame",
                 "roughnessAtmBp", "roughnessSkew", "meanAbsPullAtmBp", "zetaAtmStd", "fitMs"]


def _result(text: str, structured: dict[str, Any]) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=structured)


def _detail(exc: ApiError) -> str:
    """The app's ``detail`` out of ``METHOD /path -> 422: detail``."""
    return str(exc).split(": ", 1)[-1]


# ------------------------------------------------------------ shared bits
def series_link(doc: dict[str, Any], frame: int | None = None, expiry: str | None = None) -> str | None:
    """The Workbench deep link of a series (frontend ``useDeepLink``):
    ``/?node=T|E&activity=series&series=<id>&frame=<n>``. The node's expiry
    is the shown one, else the first a frame carries, else the pinned
    ladder's first rung (a draft has frames without expiries yet)."""
    base = workbench_url()
    if base is None:
        return None
    spec = doc["spec"]
    exp = expiry or next((f["expiries"][0] for f in doc.get("frames") or [] if f.get("expiries")), None)
    exp = exp or next(iter((spec.get("ladder") or {}).get("expiries") or []), None)
    node = f"node={quote(spec['ticker'] + '|' + exp)}&" if exp else ""
    tail = f"&frame={frame}" if frame is not None else ""
    return f"{base}/?{node}activity=series&series={quote(doc['id'])}{tail}"


def lane_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The lanes of a spec in the chat's vocabulary (prior / filter modes)."""
    out = []
    for ln in spec.get("lanes") or []:
        po = ln.get("patchOptions") or {}
        out.append({"id": ln["id"], "name": ln["name"], "family": ln["family"],
                    "production": ln.get("production", False),
                    "prior": po.get("priorPersistenceMode"), "filter": po.get("observationFilterMode")})
    return out


async def resolve_presets(api: VolfitApi, presets: list[str] | None) -> list[dict[str, Any]]:
    """The dialog presets as LaneSpecs, resolved by the app against the live
    fit settings (LQD presets pin the order in force). Unknown ids are a
    ToolError naming the presets that exist."""
    avail = {p["id"]: p for p in await api.get("/series/presets")}
    want = list(dict.fromkeys(presets or DEFAULT_PRESETS))
    bad = [p for p in want if p not in avail]
    if bad:
        raise ToolError(f"unknown lane preset(s) {bad}; the presets are {list(avail)}")
    return [avail[p] for p in want]


def _counts(p: dict[str, Any]) -> tuple[float, float]:
    if p.get("status") == "calibrating":
        return float(p.get("fitsDone") or 0), float(p.get("fitsTotal") or 1)
    return float(p.get("framesReady") or 0), float(p.get("framesTotal") or 1)


def _frame_tally(doc: dict[str, Any]) -> dict[str, int]:
    frames = doc.get("frames") or []
    return {"total": len(frames), **{s: sum(1 for f in frames if f.get("status") == s)
                                     for s in ("ready", "failed", "skipped", "pending")}}


async def _created(api: VolfitApi, sid: str, estimate: dict[str, Any] | None, start_job: bool) -> CallToolResult:
    """After a create / import: start (or not), then the reply with the handle."""
    st = await api.post(f"/series/{sid}/start") if start_job else await api.get(f"/series/{sid}/status")
    doc = await api.get(f"/series/{sid}")
    spec, p = doc["spec"], st.get("progress") or {}
    tally = _frame_tally(doc)
    est = estimate or {}
    out = {
        "kind": "series_created", "id": sid, "name": spec["name"], "ticker": spec["ticker"],
        "mode": spec["mode"], "step": spec["clock"]["step"], "count": spec["clock"].get("count"),
        "fitMode": spec["fitMode"], "lanes": lane_rows(spec), "frames": tally,
        "estimate": {"nFrames": est.get("nFrames", tally["total"]),
                     "servable": sum(1 for ok in est.get("servable") or [] if ok),
                     "harvestSeconds": est.get("harvestSeconds"), "calibrateSeconds": est.get("calibrateSeconds"),
                     "perLaneSeconds": est.get("perLaneSeconds"), "warnings": est.get("warnings") or []},
        "status": p.get("status"), "running": st.get("running"), "queue": st.get("queue") or [],
        "workbenchUrl": series_link(doc),
    }
    lanes = ", ".join(f"{ln['id']} ({ln['name']})" for ln in out["lanes"])
    skipped = f" ({tally['skipped']} skipped as unservable)" if tally["skipped"] else ""
    text = [f"Series '{spec['name']}' (id {sid}) created: {tally['total']} frames{skipped}, "
            f"{spec['clock']['step']} x {spec['clock'].get('count') or tally['total']}, target {spec['fitMode']}; "
            f"lanes {lanes}."]
    if est:
        text.append(f"Estimate: harvest {est.get('harvestSeconds')} s + calibrate {est.get('calibrateSeconds')} s.")
    text.extend(f"Warning: {w}" for w in out["estimate"]["warnings"])
    text.append(f"Status: {p.get('status')}" + (f" (queued behind {st['running']})" if st.get("running") not in (None, sid) else "")
                + (f". Call wait_for_series(id=\"{sid}\") until it is done, then series_report / chart_series_frame."
                   if start_job else f". Not started: series_control(id=\"{sid}\", action=\"start\")."))
    return _result("\n".join(text), out)


# ------------------------------------------------------------------ tools
def register(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_series(ticker: str | None = None) -> CallToolResult:
        """The stored series (all, or one ticker's — spoken names accepted):
        id, name, ticker, mode, status, frames ready / total, lanes."""
        name = aliases.resolve(ticker).ticker if ticker else None
        rows = [{"id": s["id"], "name": s["name"], "ticker": s["ticker"], "source": s.get("source"),
                 "mode": s["mode"], "status": s["status"], "frames": f"{s['nFramesReady']}/{s['nFrames']}",
                 "nFrames": s["nFrames"], "nFramesReady": s["nFramesReady"], "nLanes": s["nLanes"],
                 "createdTs": s["createdTs"]}
                for s in (await api.get("/series", ticker=name)).get("series") or []]
        text = (f"{len(rows)} series" + (f" on {name}" if name else "") + ":\n"
                + md_table(rows, ["id", "name", "ticker", "mode", "status", "frames", "nLanes", "createdTs"]))
        return _result(text, {"kind": "series_list", "ticker": name, "series": rows})

    @mcp.tool(annotations=MUTATING)
    async def create_series(
        ticker: str,
        name: str | None = None,
        mode: Literal["historical", "live"] = "historical",
        step: SeriesStep = "15m",
        count: int = 20,
        start: str | None = None,
        presets: list[str] | None = None,
        max_expiries: int | None = None,
        fit_mode: FitMode = "mid",
        session_only: bool = True,
        start_job: bool = True,
    ) -> CallToolResult:
        """Create a series on one ticker (in the universe; spoken names
        accepted) and start its job: ``count`` frames every ``step``
        (historical: backward from the latest servable instant, or forward
        from ``start``, on a source with history such as Massive; live: from
        now or from ``start`` — instants already past land at once), each
        frame calibrated under every lane. ``presets`` are the dialog's lane
        presets (default lqd_free + lqd_prior; lqd_prior_filter, svi_free,
        mcs_free, lv_free, lv_prior, current). ``start`` is ISO 8601;
        ``session_only`` skips out-of-session instants; ``max_expiries``
        crops the pinned ladder nearest-first. Returns the id, the estimate
        (frames, servable, seconds, warnings), the status and the Workbench
        link; then ``wait_for_series``. Needs the app to run with a store."""
        res = aliases.resolve(ticker)
        lanes = await resolve_presets(api, presets)
        clock: dict[str, Any] = {"step": step, "count": count, "sessionOnly": session_only}
        if start:
            clock["start"] = start
        spec = {"name": name or f"{res.ticker} {mode} {step} x {count}", "ticker": res.ticker, "mode": mode,
                "clock": clock, "fitMode": fit_mode, "lanes": lanes,
                "ladder": {"policy": "pinned", "expiries": [], "maxExpiries": max_expiries}}
        try:
            created = await api.post("/series", spec)
        except ApiError as exc:
            if exc.status == 422:
                raise ToolError(f"the app refused the series: {_detail(exc)}") from None
            raise
        return await _created(api, created["id"], created.get("estimate"), start_job)

    @mcp.tool(annotations=MUTATING)
    async def import_series(
        ticker: str,
        path: str | None = None,
        kind: ImportKind = "store",
        name: str | None = None,
        presets: list[str] | None = None,
        max_frames: int | None = None,
        max_expiries: int | None = None,
        start_job: bool = True,
    ) -> CallToolResult:
        """Import stored snapshots as a series and start its job: ``kind``
        store = another VolStore file (a backtest campaign), fixtures = a
        capture fixture file / directory, captures = the app's own captures
        of the ticker (no path). ``max_frames`` keeps the first n in time;
        lanes come from ``presets`` (default lqd_free + lqd_prior)."""
        res = aliases.resolve(ticker)
        lanes = await resolve_presets(api, presets)
        body = {"name": name or f"{res.ticker} import ({kind})", "ticker": res.ticker, "lanes": lanes,
                "source": {"kind": kind, "path": path, "maxFrames": max_frames},
                "ladder": {"policy": "pinned", "expiries": [], "maxExpiries": max_expiries}}
        try:
            doc = await api.post("/series/import-store", body)
        except ApiError as exc:
            if exc.status == 422:
                raise ToolError(f"the app refused the import: {_detail(exc)}") from None
            raise
        return await _created(api, doc["id"], None, start_job)

    @mcp.tool(annotations=READ_ONLY)
    async def wait_for_series(ctx: Context, id: str, wait_seconds: float = DEFAULT_WAIT_S) -> CallToolResult:
        """Wait for a series job, polling its status every second with the
        progress streamed (frames harvested, fits done): returns when it is
        done / failed / cancelled / paused (or never started) or when
        ``wait_seconds`` elapse — the reply says which (``outcome``) and
        carries the progress; call again while ``outcome`` is pending."""
        t0 = monotonic()
        while True:
            st = await api.get(f"/series/{id}/status")
            p = st.get("progress") or {}
            status = p.get("status") or "draft"
            if status in TERMINAL or monotonic() - t0 >= wait_seconds:
                break
            done, total = _counts(p)
            await ops.progress(ctx, done, total, f"{status}: {p.get('current') or ''}".strip(" :"))
            await asyncio.sleep(POLL_S)
        waited = round(monotonic() - t0, 1)
        outcome = status if status in TERMINAL else "pending"
        out = {"kind": "series_wait", "id": id, "status": status, "outcome": outcome,
               "finished": status in ("done", "failed", "cancelled"), "progress": p,
               "running": st.get("running"), "queue": st.get("queue") or [], "waitedSeconds": waited}
        head = (f"Series {id} {status}: frames {p.get('framesReady')}/{p.get('framesTotal')}, "
                f"fits {p.get('fitsDone')}/{p.get('fitsTotal')} ({waited} s waited)")
        if outcome == "pending":
            head += f"; now {p.get('current') or status}. Call wait_for_series(id=\"{id}\") again."
        elif status == "draft":
            head += f". Not started: series_control(id=\"{id}\", action=\"start\")."
        elif status == "paused":
            head += f". Paused: series_control(id=\"{id}\", action=\"resume\") continues at the next frame."
        elif status == "done":
            head += ". Next: series_report / chart_series_frame."
        if p.get("error"):
            head += f"\nLast error: {p['error']}"
        return _result(head, out)

    @mcp.tool(annotations=READ_ONLY)
    async def series_report(id: str, expiry: str | None = None, lanes: list[str] | None = None) -> CallToolResult:
        """The evidence of a series per lane over its ready frames, for one
        expiry (default the first): frames, mean rms / max error (vol bp),
        the worst frame, the handle-path ROUGHNESS (mean frame-to-frame move
        of the ATM vol in bp and of the skew — what a prior or a filter damps,
        read beside the rms it costs), the mean |pull| against the free lane
        of the same family, the filter's ATM zeta spread and the fit time."""
        doc = await api.get(f"/series/{id}")
        ev = await api.get(f"/series/{id}/evidence", lanes=",".join(lanes) if lanes else None, expiry=expiry)
        spec = doc["spec"]
        names = {ln["id"]: ln["name"] for ln in spec.get("lanes") or []}
        rows = []
        for lid, e in (ev.get("lanes") or {}).items():
            w = e.get("worstFrame") or {}
            rows.append({"lane": lid, "name": names.get(lid, lid), "frames": e.get("nFrames"),
                         "failed": e.get("nFailed"), "meanRmsBp": r(e.get("meanRmsBp"), 1),
                         "meanMaxBp": r(e.get("meanMaxIvBp"), 1),
                         "worstFrame": f"#{w['idx']} ({w['rmsBp']:.1f} bp)" if w else None,
                         "roughnessAtmBp": r(e.get("roughnessAtmBp"), 2), "roughnessSkew": r(e.get("roughnessSkew"), 4),
                         "meanPullAtmBp": r(e.get("meanPullAtmBp"), 2), "meanAbsPullAtmBp": r(e.get("meanAbsPullAtmBp"), 2),
                         "zetaAtmStd": r(e.get("zetaAtmStd"), 3), "fitMs": r(e.get("meanFitMs"), 0)})
        tally = _frame_tally(doc)
        p = doc.get("progress") or {}
        link = series_link(doc, expiry=ev.get("expiry"))
        failed = f" ({tally['failed']} failed)" if tally["failed"] else ""
        text = [f"Series '{spec['name']}' (id {id}): {spec['ticker']}, {spec['mode']}, "
                f"{spec['clock']['step']} x {spec['clock'].get('count') or tally['total']}, target {spec['fitMode']}, "
                f"status {p.get('status')}, frames {tally['ready']}/{tally['total']} ready{failed}; "
                f"expiry {ev.get('expiry')}.",
                md_table(rows, EVIDENCE_COLS),
                "Roughness = the mean frame-to-frame move of the ATM vol (bp) and of the skew: "
                "what a prior or a filter damps, at the rms cost beside it."]
        scored = [x for x in rows if x["roughnessAtmBp"] is not None and x["meanRmsBp"] is not None]
        if len(scored) > 1:
            smooth = min(scored, key=lambda x: x["roughnessAtmBp"])
            tight = min(scored, key=lambda x: x["meanRmsBp"])
            text.append(f"Smoothest ATM path: {smooth['lane']} ({smooth['roughnessAtmBp']} bp per frame, rms "
                        f"{smooth['meanRmsBp']} bp); lowest rms: {tight['lane']} ({tight['meanRmsBp']} bp, "
                        f"roughness {tight['roughnessAtmBp']} bp).")
        if link:
            text.append(f"Workbench: {link}")
        out = {"kind": "series_report", "id": id, "name": spec["name"], "ticker": spec["ticker"], "mode": spec["mode"],
               "step": spec["clock"]["step"], "fitMode": spec["fitMode"], "status": p.get("status"), "frames": tally,
               "expiry": ev.get("expiry"), "lanes": rows, "evidence": ev, "workbenchUrl": link}
        return _result("\n".join(text), out)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def series_control(id: str, action: Literal["start", "resume", "pause", "cancel", "delete"]) -> dict[str, Any]:
        """Control a series job: start / resume (a paused, failed or done
        series re-runs its unfinished frames; a second series queues behind
        the running one), pause (checkpointed; resume continues at the next
        frame), cancel, or delete the series and its frames. Pause / cancel
        on a series that is not running is a no-op and says so."""
        if action == "delete":
            await api.delete(f"/series/{id}")
            return {"id": id, "action": action, "deleted": True, "changed": True, "message": f"series {id} deleted"}
        before = ((await api.get(f"/series/{id}/status")).get("progress") or {}).get("status")
        if action in ("pause", "cancel") and before not in RUNNING:
            return {"id": id, "action": action, "status": before, "changed": False,
                    "message": f"nothing to {action}: series {id} is {before}"}
        st = await api.post(f"/series/{id}/{action}")
        p = st.get("progress") or {}
        return {"id": id, "action": action, "status": p.get("status"), "changed": True, "running": st.get("running"),
                "queue": st.get("queue") or [], "progress": p,
                "message": f"{action}: series {id} is now {p.get('status')}"
                           + (f" (queued behind {st['running']})" if st.get("running") not in (None, id) else "")}

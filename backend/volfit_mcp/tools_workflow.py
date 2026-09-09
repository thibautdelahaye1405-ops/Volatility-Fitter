"""Macro tools: the desk routine in one call, and an A/B settings comparison.

``run_desk_workflow`` chains universe → fetch → configure → calibrate →
report (+ the Local-Vol compare panels), so "fetch X and Y, calibrate LQD-24
and Local-Vol, chart the LV surfaces" is ONE tool call in the chat. It is
bound to the Local-Vol compare app, so the same call renders the chart.

Both macros run as background jobs (``volfit_mcp.jobs``): the call waits up
to ``wait_seconds`` forwarding progress, returns the full result when the job
finishes in time, else a handle that ``wait_for_workflow`` resumes — a host's
tool-call budget never truncates a live Bloomberg run. Every step is recorded
and a failing step stops the chain with the partial results kept.

``compare_settings`` runs two calibrations under two partial settings (each
applied on top of the settings in force when the call started) and returns
the per-expiry / per-ticker differences. The run to ``keep`` goes last.
"""

from __future__ import annotations

from time import monotonic
from typing import Any, Literal

from mcp.server.apps import Apps
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from volfit_mcp import ops
from volfit_mcp.client import VolfitApi
from volfit_mcp.jobs import Job, JobRegistry
from volfit_mcp.report import md_table, r
from volfit_mcp.tools_charts import LV_COMPARE_URI, _legacy_meta, workbench_url

MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False)
READ_ONLY = ToolAnnotations(read_only_hint=True)
FitMode = Literal["mid", "bidask", "haircut"]
DEFAULT_WAIT_S = 60.0  # under any host's per-call budget seen so far


class SettingsPatch(BaseModel):
    """A partial settings change in the chat's vocabulary (all optional)."""

    label: str | None = Field(None, description="display name for this run, e.g. 'LQD-24'")
    model: Literal["lqd", "svi", "sigmoid"] | None = None
    n_order: int | None = Field(None, ge=4, le=24, description="LQD Legendre order")
    fit_mode: FitMode | None = None
    local_vol: bool | None = None
    weight_scheme: Literal["equal", "uniform_density", "tv_density", "vega_density", "delta_density"] | None = None
    haircut: float | None = None
    reg_lambda: float | None = None
    tail_alpha_left: float | None = None
    tail_alpha_right: float | None = None
    enforce_calendar: bool | None = None
    grid_x_nodes: int | None = None
    grid_t_nodes: int | None = None
    grid_reg_lambda: float | None = None
    time_scheme: Literal["implicit", "rannacher", "bdf2"] | None = None
    lv_lattice: Literal["uniform", "graded"] | None = None
    lv_solver: Literal["trf", "gn"] | None = None

    def patch(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if k != "label" and v is not None}

    def name(self, default: str) -> str:
        return self.label or (", ".join(f"{k}={v}" for k, v in self.patch().items()) or default)


def _result(text: str, structured: dict[str, Any]) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=structured)


def _pending(job: Job) -> CallToolResult:
    """The reply while a job is still running: a handle to resume with."""
    h = job.handle()
    step = f"step '{h['steps'][-1]['step']}' done, " if h["steps"] else ""
    text = (f"{job.kind} still running after {h['elapsedSeconds']} s ({step}now: {h['progress']['message'] or '…'}). "
            f"Call wait_for_workflow(job_id=\"{job.id}\") to keep waiting; the full result and the chart arrive with it.")
    return _result(text, {**h, "kind": "workflow_pending", "jobKind": job.kind})


async def _await_job(registry: JobRegistry, job: Job, ctx: Context, wait_seconds: float) -> CallToolResult:
    if await registry.wait(job, ctx, wait_seconds) and job.result is not None:
        return job.result
    if not job.running and job.error:
        raise ToolError(f"{job.kind} job {job.id} failed: {job.error}")
    return _pending(job)


# ------------------------------------------------------------ workflow
async def _run_workflow(job: Job, api: VolfitApi, a: dict[str, Any]) -> CallToolResult:
    """The desk routine; ``job.progress`` is the progress sink, ``job.steps`` the ledger."""
    t0 = monotonic()
    steps = job.steps
    wf: dict[str, Any] = {"steps": steps, "stoppedAt": None}
    text: list[str] = []
    tickers, fit_mode = a["tickers"], a["fit_mode"]

    async def step(name: str, coro):
        s0 = monotonic()
        await job.progress.report_progress(float(len(steps)), 6.0, name)
        try:
            out = await coro
        except ToolError as exc:  # ApiError and the ops' own ToolErrors
            steps.append({"step": name, "ok": False, "ms": round(1000 * (monotonic() - s0)), "error": str(exc)[:400]})
            wf["stoppedAt"] = name
            raise
        steps.append({"step": name, "ok": True, "ms": round(1000 * (monotonic() - s0))})
        return out

    panels: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    try:
        if tickers:
            wf["universe"] = await step("universe", ops.set_universe(api, tickers, a["replace_universe"]))
            text.append("Universe: " + ", ".join(f"{p['ticker']} ({p['source']}, {p['action']})" for p in wf["universe"]["resolution"]))
            for t in wf["universe"]["tickers"]:
                if t.get("error"):
                    text.append(f"  {t['ticker']}: {t['error']}")
        if a["fetch"]:
            ftxt, wf["fetch"] = await step("fetch", ops.fetch_quotes(api, tickers, fit_mode, a["refetch_if_older_than"]))
            text.append(ftxt)
        patch = {k: v for k, v in (("model", a["model"]), ("n_order", a["n_order"]), ("fit_mode", fit_mode),
                                   ("local_vol", a["local_vol"])) if v is not None}
        wf["settings"] = await step("configure", ops.configure(api, patch))
        f, o = wf["settings"]["fit"], wf["settings"]["options"]
        fit_mode = fit_mode or o["fitMode"]  # the run, the report and the panels name ONE target
        text.append(f"Settings: {f['model'].upper()}{'-' + str(f['nOrder']) if f['model'] == 'lqd' else ''}, "
                    f"target {fit_mode}, Local-Vol {'on' if o['localVolEnabled'] else 'off'}, "
                    f"weights {f['weightScheme']}, LV grid {o['gridXNodes']}x{o['gridTNodes']}")
        wf["calibration"] = await step("calibrate", ops.calibrate(
            api, job.progress, tickers=None, stage="all", fit_mode=fit_mode, wait_seconds=a["calibration_budget"], prefix="calibrate: "))
        c = wf["calibration"]
        text.append(f"Calibration: {'finished' if c['finished'] else 'STILL RUNNING (wait_for_calibration)'} — "
                    f"{c['done']}/{c['total']} nodes in {c.get('waitedSeconds', 0)} s"
                    + (f", last error: {c['error']}" if c.get("error") else ""))
        rtxt, wf["report"] = await step("report", ops.report(api, tickers, fit_mode))
        text.append(rtxt)
        if o["localVolEnabled"]:
            names = ops.names_of(tickers) or [t["ticker"] for t in wf["report"]["tickers"]]
            panels, skipped = await step("lv_compare", ops.lv_panels(api, names, fit_mode, "smooth"))
            text.append("Local-Vol compare (affine vs Dupire twin), rendered inline where the host supports apps:")
            text.extend(ops.lv_panels_text(panels, skipped))
    except ToolError as exc:
        text.insert(0, f"STOPPED at step '{wf['stoppedAt']}': {exc}")
    wf["elapsedSeconds"] = round(monotonic() - t0, 1)
    wf["fitMode"] = fit_mode
    wf["jobId"] = job.id
    structured = {"kind": "lv_compare", "fitMode": fit_mode, "tInterp": "smooth", "generatedAt": ops.now_iso(),
                  "tickers": panels, "skipped": skipped, "workflow": wf, "workbenchUrl": workbench_url()}
    head = f"Desk workflow ({wf['elapsedSeconds']} s): " + " → ".join(f"{s['step']}{'' if s['ok'] else ' ✗'}" for s in steps)
    return _result("\n".join([head, *text]), structured)


def register_apps(api: VolfitApi, apps: Apps, registry: JobRegistry) -> None:
    """Bind the workflow + its wait to the Local-Vol compare app (before the server is built)."""

    @apps.tool(resource_uri=LV_COMPARE_URI, meta=_legacy_meta(LV_COMPARE_URI), annotations=MUTATING)
    async def run_desk_workflow(
        ctx: Context,
        tickers: list[str] | None = None,
        model: Literal["lqd", "svi", "sigmoid"] | None = None,
        n_order: int | None = None,
        fit_mode: FitMode | None = None,
        local_vol: bool | None = None,
        fetch: bool = True,
        replace_universe: bool = True,
        refetch_if_older_than: float = 120.0,
        wait_seconds: float = DEFAULT_WAIT_S,
    ) -> CallToolResult:
        """The whole desk routine in one call: set the universe (spoken names
        accepted; omit ``tickers`` to keep the current one), fetch quotes
        (skipping tickers whose chain is younger than ``refetch_if_older_than``
        seconds — a ticker just added was quoted on the way in), apply the
        settings given (e.g. model="lqd", n_order=24, local_vol=True),
        calibrate every lit expiry, and return the fit-quality report — plus,
        when Local-Vol is on, the comparative Local-Vol surfaces rendered
        inline. Runs in the background: the call waits ``wait_seconds`` with
        streamed progress and returns the full result if done, else a job
        handle — call ``wait_for_workflow`` to keep waiting (the chart arrives
        with whichever call completes). Each step is recorded; a failing step
        stops the chain and the reply says which."""
        args = {"tickers": tickers, "model": model, "n_order": n_order, "fit_mode": fit_mode, "local_vol": local_vol,
                "fetch": fetch, "replace_universe": replace_universe, "refetch_if_older_than": refetch_if_older_than,
                "calibration_budget": 3600.0}
        try:
            job = registry.start("run_desk_workflow", args, lambda j: _run_workflow(j, api, args))
        except RuntimeError as exc:
            raise ToolError(str(exc)) from None
        return await _await_job(registry, job, ctx, wait_seconds)

    @apps.tool(resource_uri=LV_COMPARE_URI, meta=_legacy_meta(LV_COMPARE_URI), annotations=READ_ONLY)
    async def wait_for_workflow(ctx: Context, job_id: str | None = None, wait_seconds: float = DEFAULT_WAIT_S) -> CallToolResult:
        """Keep waiting for a background job started by ``run_desk_workflow``
        or ``compare_settings`` (default: the latest), streaming its progress;
        returns the job's full result (numbers + chart) once it finishes, else
        the handle again. Call repeatedly until it completes."""
        job = registry.get(job_id)
        if job is None:
            raise ToolError("no such job" + (f" {job_id!r}" if job_id else " (nothing has been started)"))
        return await _await_job(registry, job, ctx, wait_seconds)


# ------------------------------------------------------- compare A vs B
async def _run_compare(job: Job, api: VolfitApi, a: dict[str, Any]) -> CallToolResult:
    base = await ops.read_settings(api)
    keep, specs, tickers = a["keep"], a["specs"], a["tickers"]
    order = [("a", specs["a"]), ("b", specs["b"])] if keep == "b" else [("b", specs["b"]), ("a", specs["a"])]
    runs: dict[str, dict[str, Any]] = {}
    for i, (label, spec) in enumerate(order):
        name = spec.name(label.upper())
        settings = await ops.configure(api, spec.patch(), base=base)
        job.steps.append({"step": f"configure {name}", "ok": True, "ms": 0})
        fm = spec.fit_mode or str(base[1].get("fitMode") or "mid")
        cal = await ops.calibrate(api, job.progress, tickers=None, stage="all", fit_mode=fm,
                                  wait_seconds=3600.0, prefix=f"{name}: ")
        job.steps.append({"step": f"calibrate {name}", "ok": bool(cal.get("finished")), "ms": round(1000 * cal.get("waitedSeconds", 0))})
        rtxt, rep = await ops.report(api, tickers, fm)
        runs[label] = {"label": name, "patch": spec.patch(), "settings": settings, "calibration": cal,
                       "summary": rep.get("summary"), "tickers": rep["tickers"]}
        await job.progress.report_progress(float(i + 1), float(len(order)), f"{name} done")
    rows = _diff_rows(runs["a"], runs["b"])
    tick = _diff_tickers(runs["a"], runs["b"])
    na, nb = runs["a"]["label"], runs["b"]["label"]
    text = [f"A = {na} | B = {nb} | kept in force: {keep.upper()} ({runs[keep]['label']})",
            "Per ticker (vol bp):", md_table(tick, ["ticker", "surfaceRmsA", "surfaceRmsB", "dSurfaceRms",
                                                     "lvRmsA", "lvRmsB", "lvConvergedA", "lvConvergedB", "arbFlagsA", "arbFlagsB"]),
            "Per expiry (vol bp, d = B − A):", md_table(rows, ["ticker", "expiry", "rmsA", "rmsB", "dRms",
                                                                 "maxA", "maxB", "readyA", "readyB"])]
    structured = {"kind": "compare_settings", "kept": keep, "a": runs["a"], "b": runs["b"],
                  "tickers": tick, "rows": rows, "jobId": job.id}
    return _result("\n".join(text), structured)


def register(mcp: MCPServer, api: VolfitApi, registry: JobRegistry) -> None:
    @mcp.tool(annotations=MUTATING)
    async def compare_settings(
        ctx: Context,
        a: SettingsPatch,
        b: SettingsPatch,
        tickers: list[str] | None = None,
        keep: Literal["a", "b"] = "a",
        wait_seconds: float = DEFAULT_WAIT_S,
    ) -> CallToolResult:
        """Calibrate twice — once under settings A, once under B (each a partial
        change on top of the settings in force now, e.g. A={n_order: 24},
        B={n_order: 16}, or A={fit_mode: "mid"}, B={fit_mode: "haircut"}) —
        and compare: per ticker the surface rms and the Local-Vol scores, per
        expiry the rms / max error / readiness under each, and the difference
        B − A in vol bp. The run to ``keep`` goes last, so the app ends
        calibrated under it. Runs in the background like ``run_desk_workflow``:
        if the reply is a job handle, call ``wait_for_workflow``."""
        args = {"specs": {"a": a, "b": b}, "tickers": tickers, "keep": keep}
        try:
            job = registry.start("compare_settings", {"a": a.patch(), "b": b.patch(), "tickers": tickers, "keep": keep},
                                 lambda j: _run_compare(j, api, args))
        except RuntimeError as exc:
            raise ToolError(str(exc)) from None
        return await _await_job(registry, job, ctx, wait_seconds)

    @mcp.tool(annotations=READ_ONLY)
    async def workflow_status(job_id: str | None = None) -> dict[str, Any]:
        """The state of a background job (default: the latest): running,
        elapsed, progress, the steps so far, any error. Cheap; poll-safe."""
        job = registry.get(job_id)
        if job is None:
            return {"running": False, "jobId": None, "note": "no job has been started"}
        return job.handle()


def _diff_rows(ra: dict[str, Any], rb: dict[str, Any]) -> list[dict[str, Any]]:
    by_b = {(t["ticker"], e["expiry"]): e for t in rb["tickers"] for e in t["expiries"]}
    rows = []
    for t in ra["tickers"]:
        for e in t["expiries"]:
            eb = by_b.get((t["ticker"], e["expiry"])) or {}
            rows.append({"ticker": t["ticker"], "expiry": e["expiry"],
                         "rmsA": r(e.get("rmsBp"), 1), "rmsB": r(eb.get("rmsBp"), 1),
                         "dRms": r((eb.get("rmsBp") or 0) - (e.get("rmsBp") or 0), 1),
                         "maxA": r(e.get("maxIvBp"), 1), "maxB": r(eb.get("maxIvBp"), 1),
                         "readyA": e.get("ready"), "readyB": eb.get("ready")})
    return rows


def _diff_tickers(ra: dict[str, Any], rb: dict[str, Any]) -> list[dict[str, Any]]:
    by_b = {t["ticker"]: t for t in rb["tickers"]}
    out = []
    for t in ra["tickers"]:
        tb = by_b.get(t["ticker"]) or {}
        la, lb = t.get("lv") or {}, tb.get("lv") or {}
        out.append({"ticker": t["ticker"],
                    "surfaceRmsA": r(t.get("surfaceRmsBp"), 1), "surfaceRmsB": r(tb.get("surfaceRmsBp"), 1),
                    "dSurfaceRms": r((tb.get("surfaceRmsBp") or 0) - (t.get("surfaceRmsBp") or 0), 1),
                    "lvRmsA": r(la.get("rmsIvErrorBp"), 1), "lvRmsB": r(lb.get("rmsIvErrorBp"), 1),
                    "lvConvergedA": r(la.get("rmsConvergedBp"), 1), "lvConvergedB": r(lb.get("rmsConvergedBp"), 1),
                    "arbFlagsA": t.get("arbFlags"), "arbFlagsB": tb.get("arbFlags")})
    return out

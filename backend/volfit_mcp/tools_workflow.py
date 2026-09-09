"""Macro tools: the desk routine in one call, and an A/B settings comparison.

``run_desk_workflow`` chains universe → fetch → configure → calibrate →
report (+ the Local-Vol compare panels) with streamed progress, so "fetch X
and Y, calibrate LQD-24 and Local-Vol, chart the LV surfaces" is ONE tool
call and one approval in the chat. It is bound to the Local-Vol compare app,
so the same call renders the chart; every step is recorded and a failing
step stops the chain with the partial results kept.

``compare_settings`` runs two calibrations under two partial settings
(each applied on top of the settings in force when the call started) and
returns the per-expiry / per-ticker differences. The run to ``keep`` goes
last, so the app ends calibrated under it with nothing stale.
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
from volfit_mcp.report import md_table, r
from volfit_mcp.tools_charts import LV_COMPARE_URI, _legacy_meta

MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False)
FitMode = Literal["mid", "bidask", "haircut"]


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


# ------------------------------------------------------------ workflow
def register_apps(api: VolfitApi, apps: Apps) -> None:
    """Bind the workflow to the Local-Vol compare app (before the server is built)."""

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
        wait_seconds: float = 240.0,
    ) -> CallToolResult:
        """The whole desk routine in one call: set the universe (spoken names
        accepted; omit ``tickers`` to keep the current one), fetch quotes,
        apply the settings given (e.g. model="lqd", n_order=24,
        local_vol=True), calibrate every lit expiry with streamed progress,
        and return the fit-quality report — plus, when Local-Vol is on, the
        comparative Local-Vol surfaces rendered inline (affine sheet vs
        Dupire twin vs difference, per-expiry rms). Each step is recorded;
        a failing step stops the chain and the reply says which."""
        t0 = monotonic()
        steps: list[dict[str, Any]] = []
        wf: dict[str, Any] = {"steps": steps, "stoppedAt": None}
        text: list[str] = []

        async def step(name: str, coro):
            s0 = monotonic()
            await ops.progress(ctx, float(len(steps)), 6.0, name)
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
                wf["universe"] = await step("universe", ops.set_universe(api, tickers, replace_universe))
                text.append("Universe: " + ", ".join(f"{p['ticker']} ({p['source']}, {p['action']})" for p in wf["universe"]["resolution"]))
                for t in wf["universe"]["tickers"]:
                    if t.get("error"):
                        text.append(f"  {t['ticker']}: {t['error']}")
            if fetch:
                ftxt, wf["fetch"] = await step("fetch", ops.fetch_quotes(api, tickers, fit_mode))
                text.append(ftxt)
            patch = {k: v for k, v in (("model", model), ("n_order", n_order), ("fit_mode", fit_mode),
                                       ("local_vol", local_vol)) if v is not None}
            wf["settings"] = await step("configure", ops.configure(api, patch))
            f, o = wf["settings"]["fit"], wf["settings"]["options"]
            text.append(f"Settings: {f['model'].upper()}{'-' + str(f['nOrder']) if f['model'] == 'lqd' else ''}, "
                        f"target {o['fitMode']}, Local-Vol {'on' if o['localVolEnabled'] else 'off'}, "
                        f"weights {f['weightScheme']}, LV grid {o['gridXNodes']}x{o['gridTNodes']}")
            wf["calibration"] = await step("calibrate", ops.calibrate(
                api, ctx, tickers=None, stage="all", fit_mode=fit_mode, wait_seconds=wait_seconds, prefix="calibrate: "))
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
        structured = {"kind": "lv_compare", "fitMode": fit_mode, "tInterp": "smooth", "generatedAt": ops.now_iso(),
                      "tickers": panels, "skipped": skipped, "workflow": wf}
        head = f"Desk workflow ({wf['elapsedSeconds']} s): " + " → ".join(
            f"{s['step']}{'' if s['ok'] else ' ✗'}" for s in steps)
        return _result("\n".join([head, *text]), structured)


# ------------------------------------------------------- compare A vs B
def register(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.tool(annotations=MUTATING)
    async def compare_settings(
        ctx: Context,
        a: SettingsPatch,
        b: SettingsPatch,
        tickers: list[str] | None = None,
        keep: Literal["a", "b"] = "a",
        wait_seconds: float = 240.0,
    ) -> CallToolResult:
        """Calibrate twice — once under settings A, once under B (each a partial
        change on top of the settings in force now, e.g. A={n_order: 24},
        B={n_order: 16}, or A={fit_mode: "mid"}, B={fit_mode: "haircut"}) —
        and compare: per ticker the surface rms and the Local-Vol scores, per
        expiry the rms / max error / readiness under each, and the difference
        B − A in vol bp. The run to ``keep`` goes last, so the app ends
        calibrated under it. Two full calibrations: allow the time."""
        base = await ops.read_settings(api)
        order = [("a", a), ("b", b)] if keep == "b" else [("b", b), ("a", a)]
        runs: dict[str, dict[str, Any]] = {}
        for i, (label, spec) in enumerate(order):
            name = spec.name(label.upper())
            settings = await ops.configure(api, spec.patch(), base=base)
            fm = spec.fit_mode
            cal = await ops.calibrate(api, ctx, tickers=None, stage="all", fit_mode=fm,
                                      wait_seconds=wait_seconds, prefix=f"{name}: ")
            rtxt, rep = await ops.report(api, tickers, fm)
            runs[label] = {"label": name, "patch": spec.patch(), "settings": settings, "calibration": cal,
                           "summary": rep.get("summary"), "tickers": rep["tickers"], "reportText": rtxt}
            await ops.progress(ctx, float(i + 1), float(len(order)), f"{name} done")
        rows = _diff_rows(runs["a"], runs["b"])
        tick = _diff_tickers(runs["a"], runs["b"])
        na, nb = runs["a"]["label"], runs["b"]["label"]
        text = [f"A = {na} | B = {nb} | kept in force: {keep.upper()} ({runs[keep]['label']})",
                "Per ticker (vol bp):", md_table(tick, ["ticker", "surfaceRmsA", "surfaceRmsB", "dSurfaceRms",
                                                         "lvRmsA", "lvRmsB", "lvConvergedA", "lvConvergedB", "arbFlagsA", "arbFlagsB"]),
                "Per expiry (vol bp, d = B − A):", md_table(rows, ["ticker", "expiry", "rmsA", "rmsB", "dRms",
                                                                     "maxA", "maxB", "readyA", "readyB"])]
        structured = {"kind": "compare_settings", "kept": keep, "a": _strip(runs["a"]), "b": _strip(runs["b"]),
                      "tickers": tick, "rows": rows}
        return _result("\n".join(text), structured)


def _strip(run: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in run.items() if k != "reportText"}


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

"""Calibration tools: settings, the run (with progress), the wait, the report.

The app's model choice is GLOBAL state (``PUT /settings/fit``: model family
+ LQD order; ``PUT /settings/options``: Local-Vol on/off, fit target, LV
grid), not a calibrate argument — so "calibrate LQD-24 and Local-Vol" is
``configure_fit(model="lqd", n_order=24, local_vol=True)`` followed by one
``calibrate`` (the parametric stage feeds the LV stage). One background job
runs at a time; ``calibrate`` streams MCP progress while it waits (bounded by
``wait_seconds``) and ``wait_for_calibration`` resumes the wait.
"""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from volfit_mcp import aliases
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import compact_status, md_table, quality_summary, r

READ_ONLY = ToolAnnotations(read_only_hint=True)
MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False)
FitMode = Literal["mid", "bidask", "haircut"]
POLL_S = 0.5

#: FitSettings fields a chat may set (snake_case argument -> API field).
_FIT_FIELDS = {"model": "model", "n_order": "nOrder", "weight_scheme": "weightScheme",
               "haircut": "haircut", "reg_lambda": "regLambda",
               "tail_alpha_left": "tailAlphaLeft", "tail_alpha_right": "tailAlphaRight"}
#: OptionsSettings fields a chat may set.
_OPT_FIELDS = {"local_vol": "localVolEnabled", "fit_mode": "fitMode",
               "enforce_calendar": "enforceCalendar", "grid_x_nodes": "gridXNodes",
               "grid_t_nodes": "gridTNodes", "auto_calibrate": "autoCalibrate",
               "events_enabled": "eventsEnabled"}
_ECHO_FIT = ("model", "nOrder", "lqdCoords", "regLambda", "regPower", "weightScheme",
             "haircut", "tailAlphaLeft", "tailAlphaRight")
_ECHO_OPT = ("localVolEnabled", "fitMode", "enforceCalendar", "surfaceSolver", "gridXNodes",
             "gridTNodes", "gridRegLambda", "timeScheme", "lvLattice", "lvSolver",
             "autoCalibrate", "eventsEnabled")


def _echo(fit: dict[str, Any], opt: dict[str, Any]) -> dict[str, Any]:
    return {"fit": {k: fit.get(k) for k in _ECHO_FIT}, "options": {k: opt.get(k) for k in _ECHO_OPT}}


async def _poll(api: VolfitApi, ctx: Context | None, wait_seconds: float, fit_mode: str | None) -> dict[str, Any]:
    """Poll /calibration/status until idle or the wait budget runs out,
    forwarding progress to the client. Returns the compact final status."""
    t0 = monotonic()
    st = await api.get("/calibration/status", fit_mode=fit_mode)
    while st["running"] and monotonic() - t0 < wait_seconds:
        if ctx is not None:
            act = (st.get("activity") or {}).get("message") or ""
            msg = f"{st.get('phase') or 'Calibrating'} {st.get('current') or ''} {act}".strip()
            try:
                await ctx.report_progress(float(st["done"]), float(max(st["total"], 1)), msg)
            except Exception:  # a client without progress support — keep polling
                pass
        await asyncio.sleep(POLL_S)
        st = await api.get("/calibration/status", fit_mode=fit_mode)
    out = compact_status(st)
    out["finished"] = not st["running"]
    out["waitedSeconds"] = round(monotonic() - t0, 1)
    return out


def register(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_fit_settings() -> dict[str, Any]:
        """The global calibration settings in force: model family (lqd / svi /
        sigmoid), LQD order, weighting scheme, haircut, tail exponents; and the
        options that shape a run: Local-Vol on/off, fit target (mid / bidask /
        haircut), calendar enforcement, LV grid sizes, time scheme, solver."""
        fit = await api.get("/settings/fit")
        opt = await api.get("/settings/options")
        return _echo(fit, opt)

    @mcp.tool(annotations=MUTATING)
    async def configure_fit(
        model: Literal["lqd", "svi", "sigmoid"] | None = None,
        n_order: int | None = None,
        fit_mode: FitMode | None = None,
        local_vol: bool | None = None,
        weight_scheme: Literal["equal", "uniform_density", "tv_density", "vega_density", "delta_density"] | None = None,
        haircut: float | None = None,
        reg_lambda: float | None = None,
        tail_alpha_left: float | None = None,
        tail_alpha_right: float | None = None,
        enforce_calendar: bool | None = None,
        grid_x_nodes: int | None = None,
        grid_t_nodes: int | None = None,
        auto_calibrate: bool | None = None,
        events_enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Set the global calibration settings (only the given fields change).
        "LQD-24" = ``model="lqd", n_order=24`` (order 4..24; the app default is
        16). ``local_vol`` turns the Local-Vol stage on/off; ``fit_mode`` picks
        the target the fits are judged against (mid, the bid-ask band, or a
        haircut band tightened by ``haircut`` vol points, e.g. 0.005). A changed
        setting makes every fit stale: run ``calibrate`` afterwards. Returns
        the settings now in force."""
        args = locals()
        fit_patch = {api_k: args[k] for k, api_k in _FIT_FIELDS.items() if args.get(k) is not None}
        opt_patch = {api_k: args[k] for k, api_k in _OPT_FIELDS.items() if args.get(k) is not None}
        fit = await api.get("/settings/fit")
        opt = await api.get("/settings/options")
        if fit_patch:
            fit = await api.put("/settings/fit", {**fit, **fit_patch})
        if opt_patch:
            opt = await api.put("/settings/options", {**opt, **opt_patch})
        out = _echo(fit, opt)
        out["changed"] = {**fit_patch, **opt_patch}
        return out

    @mcp.tool(annotations=MUTATING)
    async def calibrate(
        ctx: Context,
        tickers: list[str] | None = None,
        stage: Literal["all", "parametric", "lv"] = "all",
        fit_mode: FitMode | None = None,
        wait_seconds: float = 90.0,
    ) -> dict[str, Any]:
        """Calibrate the lit nodes under the current settings and wait for the
        result (progress is streamed). ``stage``: "all" = the parametric slices
        then the Local-Vol surfaces (when Local-Vol is on), "parametric" or "lv"
        alone. With ``tickers`` the run is restricted to them (synchronous, one
        ticker at a time). ``fit_mode`` overrides the target for this run. If
        the job outlives ``wait_seconds`` the reply says ``finished: false``;
        call ``wait_for_calibration`` to keep waiting. Follow with
        ``calibration_report``."""
        if tickers:
            names = [aliases.resolve(t).ticker for t in tickers]
            last: dict[str, Any] = {}
            for i, t in enumerate(names):
                await ctx.report_progress(float(i), float(len(names)), f"Calibrating {t}")
                last = await api.post(f"/calibrate/{t}", fit_mode=fit_mode)
            out = compact_status(last)
            out["finished"] = not last["running"]
            out["tickers"] = names
            return out
        path = {"all": "/calibrate", "parametric": "/calibrate/parametric", "lv": "/calibrate/lv"}[stage]
        st = await api.post(path, fit_mode=fit_mode)
        if not st["running"] and st.get("litNodes", 0) == 0:
            return {**compact_status(st), "finished": True,
                    "note": "no lit nodes to calibrate — fetch quotes first (fetch_quotes)"}
        return await _poll(api, ctx, wait_seconds, fit_mode)

    @mcp.tool(annotations=READ_ONLY)
    async def wait_for_calibration(ctx: Context, wait_seconds: float = 90.0) -> dict[str, Any]:
        """Keep waiting for the background calibration (progress streamed);
        returns the status with ``finished`` once idle or the budget is spent."""
        return await _poll(api, ctx, wait_seconds, None)

    @mcp.tool(annotations=READ_ONLY)
    async def calibration_status() -> dict[str, Any]:
        """The calibration job state right now (running, done/total, phase,
        last error) and the stale accounting (lit nodes, stale nodes, LV-stale
        tickers). Cheap; poll-safe."""
        return compact_status(await api.get("/calibration/status"))

    @mcp.tool(annotations=MUTATING)
    async def cancel_calibration() -> dict[str, Any]:
        """Cancel the running background calibration (cooperative: the node in
        flight completes)."""
        return compact_status(await api.post("/calibrate/cancel"))

    @mcp.tool(annotations=READ_ONLY)
    async def calibration_report(
        tickers: list[str] | None = None, fit_mode: FitMode | None = None, rms_budget_bp: float | None = None
    ) -> CallToolResult:
        """The fit-quality report after a calibration: per ticker the pooled
        surface rms (vol bp), the worst node, arbitrage flags, data age and the
        Local-Vol surface score (rms / converged rms / max, calendar
        violations, worst density); per expiry the rms, max error, ATM vol,
        skew, Lee and calendar checks, publish readiness and the reasons it
        fails. ``rms_budget_bp`` sets the readiness budget (default 15 bp)."""
        names = [aliases.resolve(t).ticker for t in tickers] if tickers else None
        q = await api.get("/quality", fit_mode=fit_mode, rms_budget_bp=rms_budget_bp)
        out = quality_summary(q, names)
        tick_rows = [{k: t.get(k) for k in ("ticker", "nodes", "fitted", "stale", "surfaceRmsBp",
                                             "worstNodeRmsBp", "arbFlags", "dataAgeMin")} for t in out["tickers"]]
        s = out.get("summary") or {}
        text = [f"Fit quality (target {out['fitMode']}, readiness budget {out['rmsBudgetBp']} bp): "
                f"{s.get('readyNodes')}/{s.get('litNodes')} lit nodes ready, {s.get('stale')} stale, "
                f"{s.get('arbFlags')} arb flags, median rms {r(s.get('medianRmsBp'), 1)} bp, worst {r(s.get('worstRmsBp'), 1)} bp",
                md_table(tick_rows, ["ticker", "nodes", "fitted", "stale", "surfaceRmsBp", "worstNodeRmsBp", "arbFlags", "dataAgeMin"])]
        for t in out["tickers"]:
            lv = t.get("lv")
            if lv:
                text.append(f"{t['ticker']} Local-Vol: rms {lv.get('rmsIvErrorBp')} bp, converged {lv.get('rmsConvergedBp')} bp, "
                            f"max {lv.get('maxIvErrorBp')} bp, {'arb-free' if lv.get('arbitrageFree') else 'ARB FLAGS'}"
                            f"{' (stale)' if lv.get('stale') else ''}")
            text.append(f"{t['ticker']} expiries:\n" + md_table(
                t["expiries"], ["expiry", "nQuotes", "rmsBp", "maxIvBp", "atmVol", "skew", "leeOk", "calendarOk", "ready", "issues"]))
        return CallToolResult(content=[TextContent(type="text", text="\n".join(text))], structured_content=out)

"""Calibration tools: settings, the run (with progress), the wait, the report.

The app's model choice is GLOBAL state (``PUT /settings/fit``: model family
+ LQD order; ``PUT /settings/options``: Local-Vol on/off, fit target, LV
grid), not a calibrate argument — so "calibrate LQD-24 and Local-Vol" is
``configure_fit(model="lqd", n_order=24, local_vol=True)`` followed by one
``calibrate`` (the parametric stage feeds the LV stage). One background job
runs at a time; ``calibrate`` streams MCP progress while it waits (bounded by
``wait_seconds``) and ``wait_for_calibration`` resumes the wait. The steps
themselves live in ``volfit_mcp.ops`` (shared with the macro tools).
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from volfit_mcp import ops
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import compact_status

READ_ONLY = ToolAnnotations(read_only_hint=True)
MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False)
FitMode = Literal["mid", "bidask", "haircut"]


def register(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_fit_settings() -> dict[str, Any]:
        """The global calibration settings in force: model family (lqd / svi /
        sigmoid), LQD order, weighting scheme, haircut, tail exponents; and the
        options that shape a run: Local-Vol on/off, fit target (mid / bidask /
        haircut), calendar enforcement, LV grid sizes, time scheme, solver."""
        fit, opt = await ops.read_settings(api)
        return ops.echo_settings(fit, opt)

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
        grid_reg_lambda: float | None = None,
        auto_calibrate: bool | None = None,
        events_enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Set the global calibration settings (only the given fields change).
        "LQD-24" = ``model="lqd", n_order=24`` (order 4..24; the app default is
        16). ``local_vol`` turns the Local-Vol stage on/off; ``fit_mode`` picks
        the target the fits are judged against (mid, the bid-ask band, or a
        haircut band tightened by ``haircut`` vol points, e.g. 0.005);
        ``grid_reg_lambda`` is the Local-Vol smoothness weight. A changed
        setting makes every fit stale: run ``calibrate`` afterwards. Returns
        the settings now in force."""
        args = dict(locals())  # taken before the comprehension (3.11 scoping); includes the closure's `api`
        known = set(ops.FIT_FIELDS) | set(ops.OPT_FIELDS)
        patch = {k: v for k, v in args.items() if k in known and v is not None}
        return await ops.configure(api, patch)

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
        return await ops.calibrate(api, ctx, tickers=tickers, stage=stage, fit_mode=fit_mode,
                                   wait_seconds=wait_seconds)

    @mcp.tool(annotations=READ_ONLY)
    async def wait_for_calibration(ctx: Context, wait_seconds: float = 90.0) -> dict[str, Any]:
        """Keep waiting for the background calibration (progress streamed);
        returns the status with ``finished`` once idle or the budget is spent."""
        return await ops.wait_idle(api, ctx, wait_seconds, None)

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
        text, out = await ops.report(api, tickers, fit_mode, rms_budget_bp)
        return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=out)

"""Assembly of the vol-fitter MCP server: tools, apps, resources, prompts.

``build_server(api)`` returns an ``MCPServer`` bound to one ``VolfitApi``.
The server ``instructions`` are the model's operating manual (global
settings, one job at a time, the fetch → configure → calibrate → report →
chart order, spoken ticker names); the resources expose the app's own
documentation (settings schema, Docs/ catalogue) so the model can answer
"what does gridXNodes do" without guessing; the prompts are the two desk
routines a user will type most.
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.mcpserver import MCPServer

from volfit_mcp import __version__, aliases, tools_calibrate, tools_charts, tools_universe, tools_views
from volfit_mcp.client import VolfitApi
from volfit_mcp.trace import TraceMiddleware

INSTRUCTIONS = """\
vol-fitter: implied-volatility surface fitter (LQD / SVI / sigmoid smiles, Local-Vol
surfaces, graph extrapolation) driven through its running desktop app. You are a
client of that app: every tool reads or changes the SAME state the user sees in the
workbench, so say what you changed.

Workflow for "fetch X and Y, calibrate LQD-24 and Local-Vol, chart the LV surfaces":
1. set_universe(["EuroStoxx", "SPX"])  — spoken names resolve to app tickers and each
   ticker is pinned to a source that lists it (SX5E: Bloomberg or Eurex; SPX: Bloomberg,
   Cboe, Massive; Yahoo has no EuroStoxx options).
2. fetch_preview() when the data moment matters, then fetch_quotes().
3. configure_fit(model="lqd", n_order=24, local_vol=True) — settings are GLOBAL
   (not per run); "LQD-24" means n_order=24 (app default 16, max 24). One calibrate
   produces BOTH the parametric slices and the Local-Vol surfaces when local_vol is on.
   Comparing two parametric settings (e.g. LQD-24 vs LQD-16) needs two calibrations.
4. calibrate() — one background job at a time; progress is streamed; if it returns
   finished=false call wait_for_calibration().
5. calibration_report() for the numbers (rms in vol bp per expiry, converged-operator
   rms for Local-Vol, arbitrage flags, readiness); get_smile / get_lv_surface /
   get_lv_compare for detail.
6. chart_lv_compare([...]) / chart_smile(ticker, expiry) — inline interactive charts
   on hosts that render MCP Apps (Claude Desktop, claude.ai); elsewhere use the
   structured data (pass png=true for a static image).

Units: rms and errors in vol basis points (1 bp = 0.01 vol point); vols as decimals
(0.18 = 18 %); k = ln(K/F); x = K/F; t in years. A fit is "stale" when its inputs
moved since it was calibrated — recalibrate before quoting it. Expiries are ISO dates
(list_expiries). Never invent numbers: if a tool errors, report the error text.
"""


def build_server(
    api: VolfitApi | None = None,
    *,
    with_apps: bool = True,
    log_level: str = "WARNING",
    trace_path: str | None = None,
) -> MCPServer:
    api = api or VolfitApi()
    extensions = []
    if with_apps:
        # The server consumes an extension's tools + resources at construction,
        # so the chart tools must be bound to the Apps instance first.
        apps = tools_charts.build_apps()
        tools_charts.register(api, apps)
        extensions.append(apps)
    trace_path = trace_path or os.environ.get("VOLFIT_MCP_TRACE") or None
    middleware = [TraceMiddleware(trace_path)] if trace_path else None
    mcp = MCPServer(
        "vol-fitter",
        title="Vol-Fitter",
        instructions=INSTRUCTIONS,
        version=__version__,
        extensions=extensions,
        log_level=log_level,  # type: ignore[arg-type]
        middleware=middleware,
    )
    tools_universe.register(mcp, api)
    tools_calibrate.register(mcp, api)
    tools_views.register(mcp, api)
    _register_resources(mcp, api)
    _register_prompts(mcp)
    return mcp


# ------------------------------------------------------------- resources
def _register_resources(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.resource("volfit://status", name="status", title="App status",
                  description="Calibration job state, data sources and data age, right now.",
                  mime_type="application/json")
    async def status_resource() -> str:
        st = await api.get("/calibration/status")
        ds = await api.get("/datasources")
        return _json({"calibration": st, "dataSources": ds})

    @mcp.resource("volfit://settings", name="settings", title="Calibration settings",
                  description="The global fit + options settings in force (full JSON).",
                  mime_type="application/json")
    async def settings_resource() -> str:
        return _json({"fit": await api.get("/settings/fit"), "options": await api.get("/settings/options")})

    @mcp.resource("volfit://help/settings-schema", name="settings-schema", title="Settings schema",
                  description="Every fit / options setting with its type, range, default and doc string.",
                  mime_type="application/json")
    async def settings_schema() -> str:
        return _json(await api.get("/help/settings-schema"))

    @mcp.resource("volfit://help/docs", name="docs-catalog", title="Documentation catalogue",
                  description="The Docs/ and Papers/ notes the app ships (ids for volfit://help/docs/{id}).",
                  mime_type="application/json")
    async def docs_catalog() -> str:
        cat = await api.get("/help/docs")
        entries = [{k: e.get(k) for k in ("id", "title", "kind", "root", "name")} for e in cat.get("entries", [])]
        return _json({"available": cat.get("available"), "entries": entries})

    @mcp.resource("volfit://help/docs/{doc_id}", name="doc", title="Documentation note",
                  description="One note as Markdown (ids from volfit://help/docs).",
                  mime_type="text/markdown")
    async def doc_markdown(doc_id: str) -> str:
        doc = await api.get(f"/help/docs/{doc_id}")
        return f"# {doc.get('title', doc_id)}\n\n{doc.get('markdown', '')}"

    @mcp.resource("volfit://aliases", name="ticker-aliases", title="Ticker aliases",
                  description="Spoken names the connector resolves (EuroStoxx -> SX5E, ...).",
                  mime_type="application/json")
    def aliases_resource() -> str:
        return _json(aliases.known_aliases())


def _json(obj: Any) -> str:
    return json.dumps(obj, indent=1, default=str)


# --------------------------------------------------------------- prompts
def _register_prompts(mcp: MCPServer) -> None:
    @mcp.prompt(name="desk_calibration", title="Desk calibration",
                description="Fetch, calibrate and chart a list of tickers end to end.")
    def desk_calibration(tickers: str = "EuroStoxx, SPX", model: str = "lqd", n_order: int = 24,
                         fit_mode: str = "mid", local_vol: bool = True) -> str:
        return (
            f"Fetch quotes on {tickers}, calibrate every lit expiry with model {model.upper()}"
            f"{f'-{n_order}' if model == 'lqd' else ''} against the {fit_mode} target"
            f"{' and the Local-Vol surface' if local_vol else ''}. Report the fit quality per ticker "
            "and per expiry (rms in bp, arbitrage flags, readiness), flag anything stale or "
            f"unlisted, then {'chart the comparative Local-Vol surfaces' if local_vol else 'chart the worst smile'}."
        )

    @mcp.prompt(name="morning_check", title="Morning check",
                description="Verify data sources, data age and calibration state before trading.")
    def morning_check() -> str:
        return (
            "Check the data sources (which are green / amber / red), the age of the loaded quotes, "
            "the universe and its lit expiries, and whether any fit is stale. If quotes are older "
            "than 20 minutes or anything is stale, refetch and recalibrate, then give me the "
            "calibration report."
        )

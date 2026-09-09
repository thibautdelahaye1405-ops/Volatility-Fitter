"""volfit_mcp — the vol-fitter MCP connector (Model Context Protocol server).

Wraps the running vol-fitter HTTP API (``backend/serve.py`` on :8000) as an
MCP server so a Claude chat (Claude Desktop, claude.ai, Claude Code) can say
"fetch quotes on EuroStoxx and SPX, calibrate LQD-24 and Local-Vol, chart the
comparative LV surfaces" and get numbers, diagnostics and in-chat charts.

Design (ratified 2026-09-09):

* **Thin client, not a second engine.** Every tool is an HTTP call to the
  live app (``volfit_mcp.client``), so the workbench on :5173 mirrors what the
  chat did — same universe, same settings, same fits. Nothing numerical lives
  here.
* **Curated verbs, not the OpenAPI surface.** About a dozen workflow tools
  (``tools_universe`` / ``tools_calibrate`` / ``tools_views`` /
  ``tools_charts``) with compact, model-sized outputs (``report``), instead of
  the app's ~140 routes and their global-state pitfalls.
* **Charts are MCP Apps.** ``tools_charts`` binds tools to ``ui://`` HTML
  resources (``volfit_mcp/ui``) rendered inline by hosts that negotiate MCP
  Apps (Claude Desktop, claude.ai). Other hosts get the structured data plus
  an optional matplotlib PNG (``render_png``).
* **Long runs are async.** ``calibrate`` streams MCP progress while it waits
  (bounded), then hands back a job status a ``wait_for_calibration`` call can
  resume.

Entry points: ``python -m volfit_mcp`` (stdio, for Claude Desktop) or
``python -m volfit_mcp --transport streamable-http --port 8765`` (remote).
"""

__version__ = "0.1.0"

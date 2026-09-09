# The vol-fitter MCP connector

Drive the fitter from a Claude chat. The connector (`backend/volfit_mcp`) is a
Model Context Protocol server that wraps the running app's HTTP API, so a
prompt such as

> fetch quotes on EuroStoxx and SPX, calibrate in LQD-24 and Local-Vol, and
> chart the comparative LV surfaces

becomes ONE tool call (`run_desk_workflow`), the numbers come back as tables,
and the charts render inside the conversation.

## What it is (and is not)

* **A thin client of the app.** Every tool is an HTTP call to `serve.py` on
  :8000. The workbench on :5173 shows the same universe, settings and fits the
  chat produced, so you can pivot between the two at any time. Nothing
  numerical lives in the connector.
* **Curated verbs.** About twenty workflow tools with compact outputs, not the
  app's ~140 routes. Chart tools are MCP Apps: interactive Plotly views (3D
  surfaces, heatmaps, smiles with bid/ask bands) rendered inline by Claude
  Desktop and claude.ai. Other hosts (Claude Code, mobile) get the structured
  data and, on request, a PNG.
* **Same global state as the UI.** Model choice and Local-Vol on/off are the
  app's global settings (`configure_fit`), one calibration job runs at a
  time, and a settings change makes fits stale. This is deliberate: what you
  see in the chat is what runs in the workbench.

## Setup — Claude Desktop (local, recommended)

The app must be running (`.\restart.ps1` from the repo root, any data source).
The connector is registered in `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "vol-fitter": {
      "command": "C:\\Users\\thiba\\vol-fitter\\.venv\\Scripts\\python.exe",
      "args": ["-m", "volfit_mcp"],
      "env": { "VOLFIT_API_URL": "http://127.0.0.1:8000", "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

Restart Claude Desktop; the "vol-fitter" server appears under Settings ▸
Developer and its tools under the chat's "+" menu. The first chart prompts
"Allow this app to render?" — choose Always allow. Local stdio is the right
first transport here: the Bloomberg Terminal lives on this machine and a
cloud-hosted connector could not reach it.

After changing connector code, quit Claude Desktop from the system-tray icon
(closing the window leaves the app and its connector processes running, so the
old server keeps answering). Pages reload from disk on every read; the tool
list and the bridge need that full quit. LIVE-VERIFIED 2026-09-09: SPX from
Cboe, LQD-24 + Local-Vol, the interactive LV compare rendered in the chat.

Manual check: `.venv\Scripts\python -m volfit_mcp` from any directory starts
the server on stdio (Ctrl-C to stop); `--api-url` points it elsewhere.

## Setup — remote connector (claude.ai, mobile)

```
.venv\Scripts\python -m volfit_mcp --transport streamable-http --port 8765
```

serves the same server at `http://127.0.0.1:8765/mcp`. Claude reaches custom
connectors from Anthropic's cloud, so expose it over HTTPS (a Cloudflare
tunnel, or the hosted single-tenant container of Forward Roadmap v2) and add
it under Customize ▸ Connectors ▸ Add custom connector. Authentication is
None (URL secret), an API key request header, or OAuth 2.1 — the SDK's
`MCPServer(auth=...)` hooks are the place to wire OAuth. One app instance per
tenant; Bloomberg stays local-only.

## The tools

| Step | Tool | What it does |
|---|---|---|
| **Routine** | `run_desk_workflow` | ONE call: universe → fetch → settings → calibrate (progress) → report, and the LV compare chart rendered inline; each step recorded, a failing step stops the chain |
| **A vs B** | `compare_settings` | two calibrations under two partial settings (LQD-24 vs LQD-16, mid vs haircut, calendar on/off…), per-ticker / per-expiry differences in vol bp; the app ends under `keep` |
| Sources | `list_data_sources` | status light per feed, data age |
| Universe | `set_universe`, `get_universe`, `list_expiries` | spoken names ("EuroStoxx", "the S&P") → app tickers pinned to a source that lists them |
| Data | `fetch_preview`, `fetch_quotes` | coverage dry-run; chains + spots |
| Settings | `get_fit_settings`, `configure_fit` | model / LQD order / target / Local-Vol / grid |
| Run | `calibrate`, `wait_for_calibration`, `calibration_status`, `cancel_calibration` | background job with streamed progress |
| Numbers | `calibration_report`, `get_smile`, `get_vol_surface`, `get_lv_surface`, `get_lv_compare` | rms in vol bp, arbitrage flags, readiness, grids |
| Charts | `chart_lv_compare`, `chart_smile` | inline MCP Apps (affine LV vs Dupire twin vs difference, 3D or heatmap, per-expiry rms; smile vs bands with prev/next expiry) |

Resources: `volfit://status`, `volfit://settings`, `volfit://help/settings-schema`,
`volfit://help/docs` (+ `/{id}`), `volfit://aliases`. Prompts: `desk_calibration`,
`morning_check`.

Units everywhere: rms in vol basis points (1 bp = 0.01 vol point), vols as
decimals, `k = ln(K/F)`, `x = K/F`, `t` in years.

## Verification

* `cd backend ; ..\.venv\Scripts\python -m pytest tests/test_mcp_connector.py tests/test_mcp_stdio.py -q`
  — the whole pipeline in-process against the synthetic app, plus the real
  stdio launch against a live uvicorn.
* `cd frontend ; node scripts/mcp_app_check.mjs` — headless Edge plays the MCP
  Apps host, feeds the recorded fixtures to both chart apps, drives their
  controls and screenshots `.smoke/mcp-*.png`.

## Diagnostics

* `VOLFIT_MCP_TRACE=<file>` (or `--trace`): one JSON line per inbound MCP
  message — the host's advertised capabilities, every `resources/read` URI,
  every `tools/call` and its outcome. Chat hosts log message names only, so
  this is how a silent "no card" is diagnosed. The Desktop launch writes
  `backend\.mcp_trace.jsonl`.
* The chart pages carry a status line for every failure state ("Connecting
  to the host", "Loading the chart library", "the host blocked the chart
  library", "no chart data") instead of a blank card.
* `VOLFIT_MCP_PLOTLY=inline|cdn` (default inline): the pages embed a Plotly
  bundle cached once under `backend\.cache` — self-contained like the
  reference app servers, so a sandbox that ignores the declared CSP still
  renders; `cdn` serves the 15 KB page and loads Plotly from cdn.plot.ly.
* The handshake sends exactly what the ext-apps host schema validates
  (`appInfo`, `appCapabilities`, `protocolVersion`), and the tools carry the
  legacy `ui/resourceUri` metadata key next to `ui.resourceUri`, as the
  reference servers do.

## Known limits

* One desk per app instance: two chats against the same :8000 share the
  universe and settings.
* Chart hosts: Claude Desktop renders local-server apps (verified here);
  claude.ai rendering of apps from *custom remote* connectors had an open
  report in June 2026 — verify with the remote path before relying on it.
* Tool-call time budgets in chat hosts are undocumented: `calibrate` waits at
  most `wait_seconds` (default 90) and hands back a resumable status.

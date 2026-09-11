# The vol-fitter MCP connector

Drive the fitter from a Claude chat. The connector (`backend/volfit_mcp`) is a
Model Context Protocol server that wraps the running app's HTTP API, so a
prompt such as

> fetch quotes on EuroStoxx and SPX, calibrate in LQD-24 and Local-Vol, and
> chart the comparative LV surfaces

becomes ONE tool call (`run_desk_workflow`), the numbers come back as tables,
and the charts render inside the conversation.

In-app: Help ▾ Guides ▸ *Drive the desk from a Claude chat* is the desk-voice
edition of this note (setup, the tools by step, the routine, the charts, the
fit-target rule); the Documentation page lists this note itself.

## What it is (and is not)

* **A thin client of the app.** Every tool is an HTTP call to `serve.py` on
  :8000. The workbench on :5173 shows the same universe, settings and fits the
  chat produced, so you can pivot between the two at any time. Nothing
  numerical lives in the connector.
* **Curated verbs.** About thirty workflow tools with compact outputs, not the
  app's ~150 routes. Chart tools are MCP Apps: interactive Plotly views (3D
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
Cboe, LQD-24 + Local-Vol, the interactive LV compare rendered in the chat;
then EuroStoxx + SPX from the Bloomberg Terminal through `run_desk_workflow`
(SX5E 9 expiries, SPX 5; 176 s end to end, of which 136 s were the two
Bloomberg chain fetches).

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
| **Routine** | `run_desk_workflow`, `wait_for_workflow`, `workflow_status` | ONE call: universe → fetch → settings → calibrate (progress) → report, and the LV compare chart rendered inline; each step recorded, a failing step stops the chain. Runs as a background job: the call waits `wait_seconds` (default 60) and returns the full result if done, else a job handle that `wait_for_workflow` resumes (the chart arrives with whichever call completes) — no host tool-call budget can truncate a live Bloomberg run. A ticker just added is not quoted twice: `refetch_if_older_than` (default 120 s) leaves fresh chains alone |
| **A vs B** | `compare_settings` | two calibrations under two partial settings (LQD-24 vs LQD-16, mid vs haircut, calendar on/off…), per-ticker / per-expiry differences in vol bp; the app ends under `keep` |
| Sources | `list_data_sources` | status light per feed, data age |
| Universe | `set_universe`, `get_universe`, `list_expiries` | spoken names ("EuroStoxx", "the S&P") → app tickers pinned to a source that lists them |
| Data | `fetch_preview`, `fetch_quotes` | coverage dry-run; chains + spots |
| Settings | `get_fit_settings`, `configure_fit` | model / LQD order / target / Local-Vol / grid |
| Run | `calibrate`, `wait_for_calibration`, `calibration_status`, `cancel_calibration` | background job with streamed progress |
| Numbers | `calibration_report`, `get_smile`, `get_vol_surface`, `get_lv_surface`, `get_lv_compare` | rms in vol bp, arbitrage flags, readiness, grids |
| Charts | `chart_lv_compare`, `chart_smile`, `chart_vol_surface`, `chart_term_structure` | inline MCP Apps: affine LV vs Dupire twin vs difference (3D / heatmap, per-expiry rms); smile vs bands with prev/next expiry; the implied-vol surface (3D / heatmap, k / K/F / strike axis, quoted-range crop, ATM ridge); the term structure (ATM + var-swap vol and total variance, calendar or event-dilated clock, events, dividends, calendar violations). Every card has a **Workbench** button that opens the node in the app (`/?node=TICKER|YYYY-MM-DD&activity=...`, `VOLFIT_WORKBENCH_URL`, default the Vite dev server) |
| **Series** | `create_series`, `import_series`, `wait_for_series`, `series_report`, `series_frame`, `chart_series_frame`, `series_control`, `list_series` | a stored series through time (below): create or import, wait for its job, the per-lane evidence, one frame's numbers, the inline frame chart, the job controls, the list |

Resources: `volfit://status`, `volfit://settings`, `volfit://help/settings-schema`,
`volfit://help/docs` (+ `/{id}`), `volfit://aliases`. Prompts: `desk_calibration`,
`morning_check`.

## Series — the fitter through time

A *series* (SERIES ARC, `Docs/series_replay_roadmap.md`) is one ticker x an
ordered set of instants x a set of *lanes* — model configurations evaluated
frame after frame, a lane's prior being its own previous fit and a filter
lane carrying its state — run as a background job of the app's own (never the
Calibrate slot) and stored, so the chat, the Series lens and a later session
read the same frames. The connector wraps `/series`:

| Step | Tool | Arguments |
|---|---|---|
| Create | `create_series` | `ticker` (spoken names accepted; must be in the universe), `name?`, `mode` = `historical` (a source with history — Massive) \| `live` (from now, or from `start`; instants already past land at once), `step` = `1m` … `1h` \| `session_close` \| `daily` \| `weekly` (default `15m`), `count` (20), `start?` (ISO 8601), `presets` (the dialog's lane presets, default `["lqd_free", "lqd_prior"]`; also `lqd_prior_filter`, `svi_free`, `mcs_free`, `lv_free`, `lv_prior`, `current` — an unknown id is a tool error naming the eight), `max_expiries?`, `fit_mode` (`mid`), `session_only` (true), `frame_budget_seconds` (300; the most one lane may spend on one frame — past it the lane keeps its committed slice fits, its repair / LV rows fail with the reason and the run moves on; null = no cap), `start_job` (true). Returns the id, the estimate (frames, servable, harvest / calibrate seconds, warnings — read them: a lane can be warned unusable at this cadence, e.g. the active filter on a sub-day series), the status and the Workbench link |
| Import | `import_series` | `ticker`, `path?`, `kind` = `store` (another VolStore file) \| `fixtures` (a capture fixture file or directory) \| `captures` (the app's own captures, no path), `name?`, `presets?`, `max_frames?`, `max_expiries?`, `start_job` |
| Wait | `wait_for_series` | `id`, `wait_seconds` (60): polls the status every second with the progress streamed and returns when the job is done / failed / cancelled / paused (or never started) or the wait elapses — `outcome` says which; a pending series is never an error, call again |
| Evidence | `series_report` | `id`, `expiry?` (default the first), `lanes?`: per lane over the ready frames — frames, mean rms / max error (vol bp), the worst frame, the handle-path **roughness** (mean frame-to-frame move of the ATM vol in bp and of the skew: what a prior or a filter damps, read beside the rms it costs), mean \|pull\| against the free lane of the same family, the filter's ATM ζ spread, the fit time; the raw evidence in `structuredContent` |
| Frame | `series_frame` | `id`, `frame` (from 0; negative = from the end), `lanes?`, `expiry?`: the instant, spot, quote kind, per lane per expiry ATM vol / rms / skew, plus the quotes and every lane's curve for ONE expiry — the document the chart redraws from |
| Chart | `chart_series_frame` | `id`, `frame` (0), `expiry?`, `lanes?`, `png`: the inline app — the frame's bid/ask bands and every lane's smile for the shown expiry, the instant · quote kind · frame i/n in the title, an expiry select, prev / next buttons and a slider over the frames (each step calls `series_frame` and redraws), a legend with the per-lane rms bp, a **Workbench** button that opens the Series lens at that frame (`/?node=T\|E&activity=series&series=<id>&frame=<n>`) |
| Control | `series_control` | `id`, `action` = `start` \| `resume` \| `pause` \| `cancel` \| `delete`; pause / cancel on a series that is not running is a no-op that says so |
| List | `list_series` | `ticker?`: id, name, ticker, mode, status, frames ready / total, lanes |

One call, then two: *create a 20-frame 15-minute SPY series under LQD free +
prior and report it* is `create_series(ticker="SPY", step="15m", count=20,
presets=["lqd_free", "lqd_prior"])` → `wait_for_series(id)` until `outcome`
is `done` → `series_report(id)`; `chart_series_frame(id, frame=-1)` shows the
last frame. Creation needs the app to run with a store (`VOLFIT_DB`, which
`restart.ps1` sets; 409 otherwise) and the ticker in the universe (422 →
tool error); a historical series needs a source with history (Massive), a
live series harvests from now on at the step (every instant already past
lands at once, which is also the test path on the synthetic source).

Fit target: a tool called without `fit_mode` targets the Options' `fitMode`
(what `configure_fit` / `get_fit_settings` echo), never the target the UI
last viewed — the run, its report and its charts always name one target.

Units everywhere: rms in vol basis points (1 bp = 0.01 vol point), vols as
decimals, `k = ln(K/F)`, `x = K/F`, `t` in years.

## Verification

* `cd backend ; ..\.venv\Scripts\python -m pytest tests/test_mcp_connector.py tests/test_mcp_stdio.py tests/test_mcp_series.py -q`
  — the whole pipeline in-process against the synthetic app, plus the real
  stdio launch against a live uvicorn, plus the series tools on a synthetic
  app with a store (a live series in the past: create → wait → report →
  frame → chart → control, ~10 s).
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
* `VOLFIT_WORKBENCH_URL` (default `http://localhost:5173`): base of the cards' Workbench links; empty hides the button.
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
  most `wait_seconds` (default 90) and hands back a resumable status; the
  macros run as background jobs and hand back a `wait_for_workflow` handle.
* Live Bloomberg timing (2026-09-09, SX5E 9 expiries + SPX): the routine is
  102 s, of which ~75 s is the first quote request of each new ticker (the
  Terminal's reference-data throughput, ~800 rows/s); calibration is ~15 s.

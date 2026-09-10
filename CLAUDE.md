Volatility Fitter

The goal is to create a impplied volatility fitter, like https://voladynamics.com/products/vola-fitter but with an additional feature : extrapolate sparse observations to the full universe of smiles, across expiries and assets. The idea for this extrapolation is to propoagate the signal through a graph, which nodes are smile (underlying, T). 


******************

Several components : 

1) Data layer
- options prices / IV : Yahoo Finance scraping, Bloomberg API, Massive
- To be determined for dividends
- Universe selection : user picks among all possible asset tickers and expiries available

2) Hyper parameters
- Vol surface models : SVI-JW, LQD (see document in \Docs), Sigmoid, Full Local Volatility grid (continuous and piecewise affine across a strike x T grid)
- Optimization parameters (penalties coefficients)
- Activation toggle for calendar arbitrage prevention
- Activation toggle for event dilation of time
- Vol-Spot dynamics : SSR on ATM-vol, sticky-strike, sticky local-vol grid
- Graph solver and related parameters

3) Smile viewer
- chart prior / current fit vs quote bands, in normalized or fixed strike
- chart quantile fu ction and LQD prior / current
- save prior
- chart Term-STructure and event-dilated calendar, in vol and in variance
- slide-bars for strike range, zoom capabilities
- select / erase / amend quote points for calibration
- var-swap level
- fit to bid-ask or fit to mid or fit to haircut bid-ask

4) Graph viewer
- Weights inoput
- Nodes selection lit / dark
- Visualization
- Solver (see note in \Docs)

**********************

Tech stack :
Python backend
React Front-End (or anything better ?)
SQL Lite for data (or anything more suitable ?)

**********************

Policies :
Avoid files exceeding 400 lines
Comment codebase clearly and cleanly, so it can be read by human or other agents
Compute time should be optimized ; calculations should be lightning-fast
UX should be professional, commercial, super sleek
Lead and Spawn multiple sub-specialized sub-agents

**********************

Development state & how to resume :

BOOK sessions ("continue the book" / "next chapter"): read ONLY
Papers/book/ROADMAP.md and follow its context-hygiene rules — do NOT load
the app roadmap, backtests, or engineering history into a book session.

APP sessions: READ ROADMAP.md FIRST — its "STATUS" section at the top says exactly what is
done, what is next (in priority order), and all environment caveats.
When the user says "continue implementing the roadmap", work down that
STATUS "Next up" list, keeping the same conventions already in the code:
golden tests against the Docs/ notes, module docstrings citing equation
numbers, files <= 400 lines, commit after each green test batch.

Key commands (Windows, repo root):
- Tests:    cd backend ; ..\.venv\Scripts\python -m pytest tests -q   (2352 passed / 7 skipped as of 2026-09-10, ~12 min — split it in two halves [tests/test_[a-k]*.py | test_[l-z]*.py] when a tool caps runs at 10 min, incl. the perf rails — NB the graph perf rail needs a quiet box [dense BLAS]; +1 live test via $env:VOLFIT_LIVE="1"; perf-only: -m perf -s)
- Benchmark pack: `-m backtest.benchmark_pack run|report` (chunked/resumable
            graph-LOO parts under backtest\results\benchmark\ + HTML/JSON
            artifact); full sweep via backend\backtest\run_benchmark_pack.ps1
            in the USER'S window (hours; tool background jobs get killed).
            The script passes the RATIFIED knobs by default (`-Eta 10 -CrossMult 25`,
            overridable; `-Tag _x` names the sweep, `-DryRun` prints the argument
            list) — a bare `benchmark_pack run` is eta 1 / cross-mult 1 and NOT an
            adjudication (2026-09-10b). Fixtures are cleaned at replay
            (`backtest.fixture_hygiene`: one option series per expiry — the XOM
            adjusted series, SPX+SPXW; `VOLFIT_FIXTURE_DEDUPE=0` replays raw;
            `-m backtest.fixture_scan [--regime R]` lists collisions); the graph LOO
            quarantines non-finite / absurd nodes (reported per part + in the HTML).
- Certification: `-m backtest.certification run|report` (15 named stress cases
            — every historical bug — run via their pytest locks; client-facing
            HTML/JSON under backtest\results\certification\, ~5-10 min).
- Parallel calibrate: background Calibrate ships slice fits AND per-ticker LV
            (affine) fits to a process pool ($env:VOLFIT_CALIB_WORKERS, default
            cpu-1 capped 8; 0/1 = serial, byte-identical fits either way;
            tests/conftest.py pins 1 for the suite).
- Run app:  .\restart.ps1   (kills :8000/:5173, starts backend + Vite, registers
            ALL data sources [Yahoo/Bloomberg/Massive/Synthetic] and auto-picks
            the best-reachable active one; switch live via the TopBar Data
            Source selector. Force one active: -Live/-Bloomberg/-Cboe/-Nasdaq/-Asx/-Hkex/-Sgx/-Eurex/-Massive/
            -Synthetic. Set $env:VOLFIT_MASSIVE_KEY to light up Massive. Sets
            VOLFIT_DB so named universes / fit history persist; -NoDb disables.
            Secrets/env persist via gitignored restart.local.ps1 [copy from
            restart.local.ps1.example] — Massive API key, VOLFIT_MASSIVE_WS_URL
            [delayed-tier keys: wss://delayed.polygon.io/options], and the
            flat-file S3 creds VOLFIT_FLATFILES_KEY/_SECRET/_ENDPOINT
            [files.massive.com] that light up Massive past-day history.)
- API only: .venv\Scripts\python backend\serve.py   (uvicorn on :8000, CORS for Vite)
- Live API: $env:VOLFIT_PROVIDER='yahoo'; $env:VOLFIT_TICKERS='SPY,QQQ,AAPL'; then serve.py
- Snapshot: .venv\Scripts\python backend\snapshot.py SPY QQQ   (Yahoo -> SQLite + forwards)
- Massive diag: $env:VOLFIT_MASSIVE_KEY='...'; .venv\Scripts\python backend\massive_diag.py SPY
            (probes api.massive.com + api.polygon.io, every call, to pinpoint a feed gate)
- LV bench:  .venv\Scripts\python backend\lv_benchmark.py [--fixture <json>] [--fit-mode
            mid|bidask|haircut] [--nodes N] [--convex-wing]   (offline Local-Vol fit
            over a static fixture; the desk options as flags since 2026-09-10; prints
            per-expiry Phase-0 diagnostics [vtxInRange / vegaFloored / PDE steps].
            The affine module is a façade since 2026-09-10: affine_surface /
            affine_precompute / affine_dupire hold the surface, the step precompute
            and the Dupire march; affine_march / affine_steps are the Numba kernels. capture_massive_weekly.py refreshes
            the true-weekly fixture tests\fixtures\lv_weekly_massive.json from Massive Live.)
- Demo:     .venv\Scripts\python backend\demo.py
- Backtest: offline harness in backend\backtest\ (run `-m backtest.<mod>` from backend\,
            needs the flat-file creds: dot-source restart.local.ps1 first). Capture
            historical NBBO fixtures: `-m backtest.capture --universe pilot --regimes
            spike_aug2024 --window 23:30-06:30` (nightly window; quotes_v1 firehose
            ~8.85h/day, resumable). Compute sweep + reports: `-m backtest.run_compute
            --regime spike_aug2024 --lv` then `-m backtest.analyze --results ...json`.
            Plan/params: backend\backtest\SPEC.md; module map: backend\backtest\README.md.
- Frontend: cd frontend ; npm run dev   (talks to :8000 if up, else mock fallback + MOCK badge)
- Frontend tests: cd frontend ; npm test   (vitest, 740 tests / 104 files as of 2026-09-10l) ; npm run smoke:ui
            (headless-Edge WORKBENCH smoke; LIVE on a synthetic single-origin
            server — backend\smoke_server.py on :4188, throw-away DB — when
            ..\.venv exists, else vite preview + mock: first-run Welcome, lenses,
            3D crosshair, nodes-pane→tab, menus, dialogs, Ctrl+K palette,
            drag-to-light, split editors, chart PNG / workspace / snapshot file
            round trips, Help Center [10 pages · Ask · search · F1 · Ctrl+/ ·
            Walkthrough — scripts\smoke_help.mjs]; screenshots .smoke\; needs
            npm run build first). Focused live checks on their own ports:
            scripts\lv_compare_check.mjs (the Local Vol Compare tab, :4194),
            scripts\surface_crop_check.mjs (the 3D surfaces' crop / zoom, :4195),
            scripts\weight_strip_check.mjs (the Weights strip on the smile's axis
            + the Uniform scheme, :4196), scripts\series_check.mjs (the Series lens:
            a live series created through the API on the synthetic source, the
            picker, play / scrub / keys, the Frames stage, the dialog, :4197).
- Series (SERIES ARC, 2026-09-10): Docs\series_replay_roadmap.md = the spec (D1–D12
            ratified) + per-phase as-built notes; backend volfit\api\series_*.py
            (schemas / store / import / instants / harvest / create / jobs / lanes /
            metrics / payload) + routers\series.py; the Series lens (Alt+6) =
            frontend src\views\SeriesViewer.tsx + components\series\* + lib\series*.ts;
            a series needs VOLFIT_DB. Backend locks tests\test_series_*.py +
            test_store_series.py (~73, ~25 s).
- MCP connector (2026-09-09c): backend\volfit_mcp = the app's API as a Model
            Context Protocol server for Claude Desktop / claude.ai (Docs\mcp_connector.md).
            `.venv\Scripts\python -m volfit_mcp` (stdio; registered in
            %APPDATA%\Claude\claude_desktop_config.json, needs the app on :8000) or
            `--transport streamable-http --port 8765` (remote, /mcp). Macro tools
            run_desk_workflow (one call: universe→fetch→settings→calibrate→report + the LV
            compare chart; a BACKGROUND job — wait_for_workflow resumes past any host
            tool-call budget; volfit_mcp\jobs.py) and compare_settings (A vs B
            calibrations, bp differences); /fetch/snapshot maxAgeSeconds skips fresh chains;
            step tools (set_universe / fetch_quotes / configure_fit / calibrate /
            calibration_report / get_* / chart_lv_compare / chart_smile / chart_vol_surface /
            chart_term_structure); every card's Workbench button deep-links the app
            (`/?node=TICKER|YYYY-MM-DD&activity=...`, frontend src/state/useDeepLink.ts); shared steps in
            volfit_mcp\ops.py; inline chart apps (MCP Apps, Plotly inlined, volfit_mcp\ui).
            After changing connector code: QUIT Claude Desktop from the tray (the window
            close keeps the old server alive). Tests: tests\test_mcp_connector.py + test_mcp_stdio.py
            (~25 s); headless app check: cd frontend ; node scripts\mcp_app_check.mjs
            (screenshots .smoke\mcp-*.png). `mcp>=2.2` is in the venv (pyproject extra `mcp`).
            In-app help (2026-09-09i): Help ▾ Guides ▸ "Drive the desk from a Claude chat"
            (frontend src/lib/help/guides/connector.ts, GuideId `connector`), the Docs
            catalog entry `docs_mcp_connector`, glossary `mcp-connector` / `mcp-app`, a
            shell tip and a What's new entry.
- Help Center: Help ▾ (HELP CENTER ARC 2026-08-31) — corpora in frontend\src\lib\help\*
            (commandDocs · settingsDocs · glossary · tips · guides · docsCatalog ·
            whatsNew · walkthrough), vitest-locked complete vs the command
            registry and the settings schema. After ANY pydantic settings-field
            change: cd backend ; ..\.venv\Scripts\python gen_help_schema.py
            (rewrites frontend\src\lib\help\settingsSchema.json;
            tests\test_help_schema.py fails on drift) and add the SettingDoc.
            Backend router volfit\api\routers\help.py serves the docs catalog
            (Docs\ + Papers\), the live schema and Ask's Claude tier
            ($env:VOLFIT_ANTHROPIC_KEY on the server; no key = local retrieval
            tier).
- UI shell = VS Code-like workbench since 2026-08-26 (App.tsx + src/components/
            shell/; state/workbench.tsx owns the editor groups + tabs; menu
            rows come from the command registry lib/commands.ts).
- volfit is pip-installed editable in .venv; fastapi/uvicorn/httpx/yfinance/numba installed
  (numba is a real dep now — the LV Numba march; graceful banded fallback if it's missing).
- PyPI is intermittently flaky here (TLS resets; pip.ini has retries=15 — just retry).
- Sub-agents have no shell access: they write code; the lead agent runs and verifies.
- UI smoke tests: npm i --no-save puppeteer-core (frontend), drive headless Edge
  ('C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + screenshots.

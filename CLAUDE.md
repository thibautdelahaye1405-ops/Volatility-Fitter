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

READ ROADMAP.md FIRST — its "STATUS" section at the top says exactly what is
done, what is next (in priority order), and all environment caveats.
When the user says "continue implementing the roadmap", work down that
STATUS "Next up" list, keeping the same conventions already in the code:
golden tests against the Docs/ notes, module docstrings citing equation
numbers, files <= 400 lines, commit after each green test batch.

Key commands (Windows, repo root):
- Tests:    cd backend ; ..\.venv\Scripts\python -m pytest tests -q   (947 passed, 1 skipped as of 2026-07-06, incl. 7 perf rails; +1 live test via $env:VOLFIT_LIVE="1"; perf-only: -m perf -s)
- Parallel calibrate: background Calibrate ships slice fits AND per-ticker LV
            (affine) fits to a process pool ($env:VOLFIT_CALIB_WORKERS, default
            cpu-1 capped 8; 0/1 = serial, byte-identical fits either way;
            tests/conftest.py pins 1 for the suite).
- Run app:  .\restart.ps1   (kills :8000/:5173, starts backend + Vite, registers
            ALL data sources [Yahoo/Bloomberg/Massive/Synthetic] and auto-picks
            the best-reachable active one; switch live via the TopBar Data
            Source selector. Force one active: -Live/-Bloomberg/-Massive/
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
- LV bench:  .venv\Scripts\python backend\lv_benchmark.py [--fixture <json>]   (offline
            Local-Vol fit over a static fixture; prints per-expiry Phase-0 diagnostics
            [vtxInRange / vegaFloored / PDE steps]. capture_massive_weekly.py refreshes
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
- volfit is pip-installed editable in .venv; fastapi/uvicorn/httpx/yfinance/numba installed
  (numba is a real dep now — the LV Numba march; graceful banded fallback if it's missing).
- PyPI is intermittently flaky here (TLS resets; pip.ini has retries=15 — just retry).
- Sub-agents have no shell access: they write code; the lead agent runs and verifies.
- UI smoke tests: npm i --no-save puppeteer-core (frontend), drive headless Edge
  ('C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') + screenshots.

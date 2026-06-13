# Vol Fitter

Implied-volatility surface fitter with graph-based extrapolation of sparse
smile observations to a full universe of smiles (across expiries and assets).

- Roadmap & current status: see [ROADMAP.md](ROADMAP.md) (STATUS section at the top)
- Technical notes: see [Docs/](Docs/) (LQD smile model, OT-Bayesian graph
  extrapolation, piecewise-affine local-variance calibration)

## Layout

```
backend/   Python quant engine + FastAPI service (package: volfit)
frontend/  React + TypeScript UI (Vite, Tailwind, pure-SVG charts)
Docs/      Technical notes (LaTeX)
```

## What works today

- **Quant core**: LQD slice engine (reproduces both paper benchmarks), SVI-JW,
  sigmoid, local-vol grid with Dupire forward-PDE pricer; calendar-constrained
  surface fits; exact ATM handles; SSR spot-scenario engine.
- **Graph extrapolation**: OT-Bayesian propagation of sparse ATM-handle
  observations across a (ticker, expiry) smile universe with credible bands.
- **Data**: four interchangeable providers — deterministic **synthetic**
  (offline), **Yahoo Finance** (yfinance), **Bloomberg** (xbbg, live Terminal),
  **Massive** (Massive.com / ex-Polygon REST) — behind one in-app **Data Source
  selector** with per-source status lights (green real-time / amber delayed /
  red unavailable). An **as-of selector** (Live / Previous Close / past EOD day /
  captured intraday snapshot) lets any view be priced historically.
  Parity-implied + theoretical/manual forwards, dividend models, SQLite VolStore,
  snapshot CLI.
- **API** (FastAPI on :8000): universe + data-source/as-of switching, slice/
  surface fits (WebSocket progress), quote edit sessions with undo/redo, priors,
  density/quantile, term structure with event-dilated clock, graph solve, SSR
  scenarios.
- **UI**: Smile viewer (live fits, quote editing, scenario + Massive-IV overlays,
  density/quantile views), Local-Vol viewer, Term-Structure viewer (editable
  event markers), Graph viewer (light nodes, solve, uncertainty overlay),
  Universe manager (provider symbol search, named universes); TopBar Data Source
  + As-of selectors.

## Run everything (Windows, from repo root)

```powershell
.\restart.ps1            # backend (all data sources) + Vite frontend; auto-picks
                         # the best-reachable source; switch live in the TopBar
```

`restart.ps1` registers all four data sources and persists named universes /
fit history (VOLFIT_DB). Force a specific source active on launch with
`-Live` (Yahoo) / `-Bloomberg` / `-Massive` / `-Synthetic`. Set
`$env:VOLFIT_MASSIVE_KEY` to light up Massive; Bloomberg needs an open Terminal
(`pip install xbbg blpapi`).

## Backend setup & tests

```powershell
python -m venv .venv
.venv\Scripts\pip install -e backend[dev]   # PyPI can be flaky here: just retry
cd backend; ..\.venv\Scripts\python -m pytest tests -q   # 284 green
$env:VOLFIT_LIVE="1"; ..\.venv\Scripts\python -m pytest tests\test_yahoo.py -k live  # opt-in live test
```

## Other entry points

```powershell
.venv\Scripts\python backend\demo.py              # console engine walkthrough
.venv\Scripts\python backend\snapshot.py SPY QQQ  # Yahoo universe -> SQLite + forwards
```

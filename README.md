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
- **Data**: deterministic synthetic provider (offline), live **Yahoo Finance**
  provider (yfinance), parity-implied forwards, SQLite VolStore, snapshot CLI.
- **API** (FastAPI on :8000): universe, slice/surface fits (WebSocket
  progress), quote edit sessions with undo/redo, priors, density/quantile,
  term structure with event-dilated clock, graph solve, SSR scenarios.
- **UI**: Smile viewer (live fits, quote editing, scenario overlay,
  density/quantile views), Term-Structure viewer (editable event markers),
  Graph viewer (light nodes, solve, uncertainty overlay).

## Run everything (Windows, from repo root)

```powershell
Start-Process .venv\Scripts\python.exe backend\serve.py; cd frontend; npm run dev -- --open
```

Live market data instead of the synthetic universe:

```powershell
$env:VOLFIT_PROVIDER='yahoo'; $env:VOLFIT_TICKERS='SPY,QQQ,AAPL'
# then the same Start-Process / npm run dev line
```

## Backend setup & tests

```powershell
python -m venv .venv
.venv\Scripts\pip install -e backend[dev]   # PyPI can be flaky here: just retry
cd backend; ..\.venv\Scripts\python -m pytest tests -q   # 125 green, ~15 s
$env:VOLFIT_LIVE="1"; ..\.venv\Scripts\python -m pytest tests\test_yahoo.py -k live  # opt-in live test
```

## Other entry points

```powershell
.venv\Scripts\python backend\demo.py              # console engine walkthrough
.venv\Scripts\python backend\snapshot.py SPY QQQ  # Yahoo universe -> SQLite + forwards
```

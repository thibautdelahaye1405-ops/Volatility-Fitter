# Vol Fitter

Implied-volatility surface fitter with graph-based extrapolation of sparse
smile observations to a full universe of smiles (across expiries and assets).

- Roadmap & current status: see [ROADMAP.md](ROADMAP.md) (STATUS section at the top)
- Technical notes: see [Docs/](Docs/) (LQD smile model, Multi-Core SIV,
  OT-Bayesian graph extrapolation, piecewise-affine local-variance calibration,
  time-value density quote weights)

## Layout

```
backend/   Python quant engine + FastAPI service (package: volfit)
frontend/  React + TypeScript UI (Vite, Tailwind, pure-SVG charts)
Docs/      Technical notes (LaTeX)
```

## What works today

- **Quant core**: LQD slice engine (reproduces both paper benchmarks), SVI-JW,
  **Multi-Core SIV** (zero-wing-hat sigmoid for WW/dual-hat smiles, cores
  slider), local-vol grid with Dupire forward-PDE pricer; calendar-constrained
  surface fits; exact ATM handles; SSR spot-scenario engine. Per-quote weighting
  schemes (equal / time-value density), mid / bid-ask-band / haircut-band fit
  objectives, and a weighted RMS fit-error diagnostic — all model-agnostic.
  **Variance-swap quotes** add a calibration penalty pulling the model's fair
  var-swap to a quoted level (shared across Parametric & Local Vol). An
  **event-weighted variance clock** (events add day-weights; optional 1Y-budget
  normalization) re-prices every vol in event time, with **auto-calibration** of
  the event calendar from the term structure.
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
  surface fits (WebSocket progress), quote edit sessions with undo/redo, var-swap
  quote sessions, priors, density / log-quantile-density / stacked densities, term
  structure on the event-weighted variance clock (shared per-ticker event
  calendar + auto-calibration), local-vol surface fit (+ derived
  density/term/table), per-node lit/dark designation, graph solve, SSR scenarios. Every smile-derived
  view follows the chosen model; **all** fit/optimization coefficients (model,
  weighting, haircut, SIV cores, penalty strengths, the A_R barrier, the SVI
  no-arb penalty + Lee bound, the SIV ridge, the band mid-anchor, the local-vol
  roughness, and the graph prior strength) are global, explicit settings.
- **UI** — six workspaces (TopBar Data Source + As-of selectors, global
  expiry-format toggle):
  - **Parametric** — live fits, quote editing, var-swap quotes (add/slide/exclude
    + undo/redo), scenario (spot slider) + Massive-IV overlays; chart sub-tabs
    Smile / Stacked densities (no-butterfly check) / Log-Q-density / Term (forward
    variance + editable & auto-calibratable event calendar) / 3D Surface /
    Stacked IV (total variance, no-calendar check) / Table.
  - **Local Vol** — direct piecewise-affine surface fit (var-swap quotes + the
    same event clock), sub-tabs Smile / Density / Term / LV-surface heatmap /
    3D IV-surface / Table.
  - **Forwards** — per-ticker forwards table (parity / theoretical / manual) +
    dividend-schedule editor, shared by both fit workspaces.
  - **Options** — every global meta-parameter and calibration/optimization
    coefficient (defaults, penalty catalogue with formulas, var-swap weight %,
    event clock + normalization toggle, dynamics regime + SSR, grid defaults,
    graph prior, display format).
  - **Graph** — light/dim nodes (shared with Universe), solver panel (κ/η/λ/ν,
    auto-tune η, lasso), posterior shift + uncertainty overlay.
  - **Universe** — provider symbol search, per-ticker expiry selection, a
    lit/dark node matrix, and named universes.

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
cd backend; ..\.venv\Scripts\python -m pytest tests -q   # 363 green
$env:VOLFIT_LIVE="1"; ..\.venv\Scripts\python -m pytest tests\test_yahoo.py -k live  # opt-in live test
```

## Other entry points

```powershell
.venv\Scripts\python backend\demo.py              # console engine walkthrough
.venv\Scripts\python backend\snapshot.py SPY QQQ  # Yahoo universe -> SQLite + forwards
```

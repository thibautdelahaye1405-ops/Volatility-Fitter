# Vol Fitter

Implied-volatility surface fitter with graph-based extrapolation of sparse
smile observations to a full universe of smiles (across expiries and assets).

- Roadmap & current status: see [ROADMAP.md](ROADMAP.md) (STATUS section at the top)
- Technical notes: see [Docs/](Docs/) (LQD smile model, Multi-Core SIV,
  OT-Bayesian graph extrapolation, piecewise-affine local-variance calibration,
  time-value density quote weights, fast spot-move surface updates)

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
- **Fast spot-move transport** (`Docs/spot_move_vol_surface_note_updated.tex`): a
  spot change refreshes the calibrated smile / term-structure / LV-grid
  *analytically* (no recalibration) — total-variance horizontal transport
  `w₁ᴿ(k)=w₀(k+R·h_T)`, the exact sticky-local-vol `ℓ_T` displacement, and the
  LV-grid node rule `Kᵢ¹=Kᵢ⁰e^{(1−R/2)h_t}`, with `h_T` from forwards. Both the
  original and the transported smile are drawn, so the regime (sticky-strike =
  lateral shift, sticky-moneyness = coincident) is visible at a glance.
- **Trigger-gated calibration workflow**: calibration is decoupled from input
  changes. With Auto-calibrate ON, lit nodes (and each ticker's LV surface) refit
  in a **background job with progress**; OFF freezes the last fit and flags it
  STALE until an explicit **Calibrate**. Spot updates (manual or a backend
  scheduler in real-time mode) only transport; option-chain fetches (on-demand or
  every X min) re-anchor. Priors point to the latest saved prior, else a
  previous-close fit seeded on demand.
  **Variance-swap quotes** add a calibration penalty pulling the model's fair
  var-swap to a quoted level (shared across Parametric & Local Vol). An
  **event-weighted variance clock** (events add day-weights; optional 1Y-budget
  normalization) re-prices every vol in event time, with **auto-calibration** of
  the event calendar from the term structure.
- **Graph extrapolation**: OT-Bayesian propagation across a (ticker, expiry) smile
  universe — a manual-shift **sandbox** plus a **prior-anchored production path**
  (transported prior → lit-calibration innovation → graph posterior → reconstructed
  dark smiles, in the chosen model, with credible bands + quote-vs-market metrics),
  data-derived precision, a leave-one-node-out **backtest**, a persisted per-edge
  **weight+beta editor**, and projection of the extrapolated smiles onto a
  **local-vol surface**.
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
  density/term/table, density taken from the Dupire PDE prices so it stays smooth
  and non-negative), per-node lit/dark designation, graph solve, SSR scenarios,
  fast spot-move transport (`/spot`), and the calibration/fetch workflow
  (`/fetch/spots`, `/fetch/options`, `/calibrate`, `/calibration/status`,
  `/scheduler`). Every smile-derived
  view follows the chosen model; **all** fit/optimization coefficients (model,
  weighting, haircut, SIV cores, penalty strengths, the A_R barrier, the SVI
  no-arb penalty + Lee bound, the SIV ridge, the band mid-anchor, the local-vol
  roughness, and the graph prior strength) are global, explicit settings.
- **UI** — eight workspaces (TopBar Data Source + As-of selectors [the captured
  snapshot picker splits date → time, weekdays only], global expiry-format
  toggle, and workflow controls: **Fetch spots** / **Fetch Options Quotes** (or
  an auto-fetch countdown) / **Calibrate** with a live progress gauge + a
  stale-node badge). All charts support wheel-zoom / drag-pan / double-click
  reset (x beyond the observed quotes; y where it helps); the Smile plots
  geometry in the *selected* strike coordinate (ln(K/F) / strike / %ATM / Δ /
  normalized), so the shape itself changes with the axis; time-axis charts toggle
  T / √T:
  - **Parametric** — live fits, quote editing, var-swap quotes (add/slide/exclude
    + undo/redo), a **Spot-move panel** (slider transports the surface with no
    recalibration; the previous fit is drawn dimmed; Calibrate re-anchors) +
    Massive-IV overlays; a STALE badge when inputs drift; chart sub-tabs
    Smile / Stacked densities (no-butterfly check) / Log-Q-density / Term (forward
    variance + editable & auto-calibratable event calendar) / 3D Surface /
    Stacked IV (total variance, no-calendar check) / Table.
  - **Local Vol** — direct piecewise-affine surface fit (var-swap quotes + the
    same event clock; grid + roughness set in Options; density from the PDE
    prices; STALE badge), sub-tabs Smile / Density / Term / LV-surface heatmap /
    3D IV-surface / Table.
  - **Forwards** — a forward-curve chart (active forward vs maturity, T / √T,
    dividend ex-date verticals; click to add a dividend, slider to set its
    amount), the per-ticker forwards table (parity / theoretical / manual) and
    the dividend-schedule editor, shared by both fit workspaces.
  - **Options** — every global meta-parameter and calibration/optimization
    coefficient, grouped by theme: **Model & hyperparameters** (model + order /
    damping / SIV cores, model penalties, the local-vol vertex grid + roughness
    with an **Optimal size** button), **Calibration** (fit target, haircut, quote
    weighting, band mid anchor, var-swap weight %, event-clock normalization,
    calendar weight, calibration penalties, graph prior), **Workflow & engine
    features** (arb-fix / events / var-swaps / auto-load-prior + the
    calibration/fetch triggers) and **Spot-vol dynamics**. One Apply commits both
    the fit and options settings.
  - **Graph** — a **Sandbox** mode (light/dim nodes shared with Universe, solver
    panel κ/η/λ/ν, auto-tune η, lasso, posterior shift + uncertainty overlay) and a
    production **Extrapolate** mode over the selected lit+dark universe: per-node
    prior→posterior moves with provenance, flat-baseline + cross-β knobs, a
    leave-one-node-out backtest, an edge editor, and drill-in to a node's
    reconstructed smile + band overlaid on its live quotes.
  - **Quality** — the universe fit-quality / publish-readiness dashboard:
    headline tiles (ready / stale / arb / RMS), a per-ticker rollup including
    LV-surface health, a per-node exception table (data-age staleness fails
    readiness), and CSV/JSON surface export — served from cached calibrations
    (never fits).
  - **Universe** — provider symbol search, per-ticker expiry selection, and a
    lit/dark node matrix beside the active set, plus named universes.
  - **View** — display preferences (colour scheme: Dark / Light / High-contrast /
    Warm, contrast + brightness, expiry-label format), client-side + persisted.
- **Backtest harness** (`backend/backtest/`, offline) — captures historical
  15:45-ET NBBO chains (Massive/Polygon `quotes_v1` flat files) into immutable
  fixtures, then replays them through the production engine to measure calibration
  precision / speed / breaks across models & hyperparameters vs an SVI-JW baseline
  (LQD-6/8/10/12, Multi-Core SIV-0/1/2/3, mid & haircut targets, equal & tv-density
  weighting), attribute end-to-end time, and score graph leave-one-out. See
  `backend/backtest/SPEC.md` and `README.md` there.

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
cd backend; ..\.venv\Scripts\python -m pytest tests -q   # 419 green
$env:VOLFIT_LIVE="1"; ..\.venv\Scripts\python -m pytest tests\test_yahoo.py -k live  # opt-in live test
```

## Other entry points

```powershell
.venv\Scripts\python backend\demo.py              # console engine walkthrough
.venv\Scripts\python backend\snapshot.py SPY QQQ  # Yahoo universe -> SQLite + forwards
```

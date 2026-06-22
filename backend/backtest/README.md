# Vol-Fitter backtest harness

Offline harness for measuring calibration **precision, speed, and breaks** across
models/hyperparameters, and graph extrapolation quality, over a large historical
quote set. Runs entirely outside the FastAPI app; imports the production `volfit`
engine but changes none of it.

## Two phases

1. **Capture** (slow, run once) — `capture.py` reconstructs the 15:45-ET NBBO
   chain per (asset, trading-day) from the Massive/Polygon **`quotes_v1`** flat
   files (real bid/ask), selects an expiry ladder, computes parity forwards, and
   writes one immutable JSON fixture per (asset, date) under `fixtures/`.
2. **Compute** (fast, offline, re-runnable) — `run_compute.py` replays the
   fixtures through a `StaticProvider` + `AppState` and fits the parametric model
   sweep (`dispatch.py`) and the Local-Vol surface, writing a tidy metrics table
   under `results/`. `analyze.py` turns that into the Pareto/attribution/break
   report.

## Modules

| file | role |
|---|---|
| `probe_flatfiles.py` | Phase-0 gate: confirm the `quotes_v1` entitlement + history reach. |
| `quotes_store.py` | `QuotesFlatFileStore` — NBBO reconstruction at a target instant. |
| `universe.py` | asset set (display ticker → OCC roots, exercise style) + regime windows. |
| `capture.py` | capture-phase driver (resumable; one daily scan shared across the universe). |
| `replay.py` | fixture loader + `StaticProvider` + `state_for_day`. |
| `dispatch.py` | uniform per-model fit + precision/speed/arb metrics. |
| `run_compute.py` | compute-phase driver (parametric sweep + `--lv` surface). |
| `analyze.py` | model Pareto vs SVI-JW, time attribution, break inventory → markdown. |

## Run (Windows, repo root)

```powershell
. .\restart.local.ps1                          # load flat-file creds into env
cd backend
..\.venv\Scripts\python.exe -m backtest.probe_flatfiles            # one-time gate
..\.venv\Scripts\python.exe -m backtest.capture --universe pilot --regimes spike_aug2024
..\.venv\Scripts\python.exe -m backtest.run_compute --regime spike_aug2024 --lv
..\.venv\Scripts\python.exe -m backtest.analyze --results backtest\results\spike_aug2024_parametric.parquet
```

## Cost note (measured 2026-06-21)

The `quotes_v1` product is the OPRA NBBO firehose: one gzipped CSV per day, many
GB, **not splittable**, so each *day* costs one full streamed scan (network-bound,
~tens of minutes). It is paid **once per day** and shared across the whole asset
universe (the daily scan is filtered to our roots and the reduced NBBO cached as a
tiny Parquet under `_cache/`), so adding assets is ~free but adding days is not.
Plan the capture as a background job; it is resumable (existing fixtures skipped).

## Status

Phase 0 (quotes reader) + Phase 1 (capture) + Phase 2 (dispatch/replay) +
Phases 4/5/8 (metrics/analyze) built and unit-tested offline. Pilot = 1 regime
(Aug-2024 spike) × 8 assets. Graph leave-one-out (Phase 6) and the NN dataset
emitter (Phase 7) follow once multi-day fixtures exist.

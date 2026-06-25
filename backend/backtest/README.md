# Vol-Fitter backtest harness

Offline harness for measuring calibration **precision, speed, and breaks** across
models/hyperparameters, and graph extrapolation quality, over a large historical
quote set. Runs entirely outside the FastAPI app; imports the production `volfit`
engine but changes none of it.

## Two phases

1. **Capture** (run once, resumable) — `capture.py` reconstructs the 15:45-ET NBBO
   chain per (asset, trading-day), selects an expiry ladder, computes parity
   forwards, and writes one immutable JSON fixture per (asset, date) under
   `fixtures/`. Two sources via `--source`:
   - **`rest` (default)** — per-contract REST quotes (`rest_quotes.py`):
     ~**4.4 min/day** for 8 assets, no overnight window. Needs `VOLFIT_MASSIVE_KEY`.
   - **`flatfile`** — the `quotes_v1` firehose (`quotes_store.py`): ~hours/day, run
     windowed (`--window 23:30-06:30`). Fallback when there's no REST key.
2. **Compute** (fast, offline, re-runnable) — `run_compute.py` replays the
   fixtures through a `StaticProvider` + `AppState` and fits the parametric model
   sweep (`dispatch.py`) and the Local-Vol surface, writing a tidy metrics table
   under `results/`. `analyze.py` turns that into the Pareto/attribution/break
   report.

## Modules

| file | role |
|---|---|
| `rest_quotes.py` | `RestQuotesClient` — fast per-contract REST NBBO capture (default source). |
| `probe_rest.py` | feasibility probe for the REST path (entitlement, rate limit, latency). |
| `probe_flatfiles.py` | gate: confirm the `quotes_v1` flat-file entitlement + history reach. |
| `quotes_store.py` | `QuotesFlatFileStore` — flat-file NBBO reconstruction (fallback source). |
| `universe.py` | asset set (display ticker → OCC roots, exercise style) + regime windows. |
| `capture.py` | capture-phase driver (`--source rest|flatfile`; resumable, captured days skip). |
| `replay.py` | fixture loader + `StaticProvider` + `state_for_day`. |
| `dispatch.py` | uniform per-model fit + precision/speed/arb metrics. |
| `run_compute.py` | compute-phase driver (parametric sweep + `--lv` surface). |
| `analyze.py` | model Pareto vs SVI-JW, time attribution, break inventory → markdown. |

## Run / resume (Windows, repo root)

```powershell
. .\restart.local.ps1                          # load creds
# KEY GOTCHA: the real 32-char VOLFIT_MASSIVE_KEY is shadowed by a stale 4-char
# env var (restart.local.ps1's `if (-not $env:..)` guard skips it). Force-set it,
# or clear the stale var so the guard sets the real one:
$env:VOLFIT_MASSIVE_KEY = '<your 32-char Massive/Polygon REST key>'
cd backend
..\.venv\Scripts\python.exe -m backtest.capture --source rest --universe pilot --regimes spike_aug2024
..\.venv\Scripts\python.exe -m backtest.run_compute --regime spike_aug2024 --lv
..\.venv\Scripts\python.exe -m backtest.analyze --results backtest\results\spike_aug2024_parametric_tv_density_mid.json --kind parametric
```

The capture is **fully resumable** — already-captured (asset, date) fixtures are
skipped — so re-running the same command continues where a prior run stopped
(after a crash, a session quit, or an interrupt). That is the handover mechanism:
just re-run it.

## Cost

- **`rest` (default)** — ~**4.4 min/day** for the 8 pilot assets (concurrent
  per-contract NBBO; Options-Advanced plan = no rate limit, ~110 quotes/s). The
  20-day pilot ≈ ~90 min; runs anytime (no overnight window, bandwidth-light).
- **`flatfile`** — the OPRA firehose: one non-splittable gzip/day, **~4.8 h/day**
  (network-bound); run windowed. ~65× slower than REST. Reduced NBBO cached under
  `_cache/` (a 0-byte cache from a kill mid-scan is treated as absent + re-scanned).

## Prior-persistence mode scoring (Docs/prior_persistence_roadmap.md, Phase 8)

This harness scores **single-snapshot** fit precision; prior persistence is a
**temporal** behaviour (yesterday's prior vs today's market), so it is validated
separately:

- **Now (runnable):** `backend/tests/test_prior_nodamp.py` — a synthetic
  "overnight ATM jump, shape unchanged, wings unquoted" scenario that asserts the
  design goal across modes: operators/factors follow the level and reconstruct the
  jumped wing (shape is level-invariant), while the legacy strike-gap anchor clings
  to yesterday's absolute level. This is the self-contained mode comparison.
- **Future (empirical, needs ≥2 captured days):** a temporal extension — fit
  day _T-1_ as the prior, then on day _T_ thin the chain to the ATM region and
  score each `priorPersistenceMode` (off / strike_gap / quote_operator /
  smile_factor / hybrid) by the reconstructed-wing error vs the full day-_T_ chain.
  This is what would tune the two flagged defaults: the var-swap coverage probe
  (`operators._VARSWAP_PROBE_STD`, now 1.4σ) and the operator support bandwidth
  (`OptionsSettings.priorOperatorBandwidth`, 0.06 — leaks ATM support into the
  wing legs). Wire it as a `dispatch`-level axis once the temporal fixtures exist.

## Status

Capture (REST + flat-file) + compute (dispatch/replay) + metrics/analyze built and
tested. Pilot = Aug-2024 spike × 8 assets. **Remaining:** graph leave-one-out
(Phase 6 — runs once ≥2 days are captured; sticky-moneyness + SSR 1.0), the
NN-dataset emitter (Phase 7, feeds off `volfit/data/columnar.py`), and the
prior-mode temporal axis (above).

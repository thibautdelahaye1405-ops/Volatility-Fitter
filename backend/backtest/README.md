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
- **Empirical (BUILT — `temporal.py`):** the temporal extension, now that ≥2
  consecutive days are captured per regime. For every consecutive day pair (_T-1_,
  _T_) and asset it fits _T-1_'s full chain → freezes it as the active prior
  (`priors.capture_snapshot`, `lv=False`), thins day _T_ to its ATM region
  (`|k| ≤ c_atm·σ√τ`, fed to the fit) and scores the reconstructed MODERATE wing
  (`c_atm·σ√τ < |k| ≤ c_wing·σ√τ`, held out) for each `priorPersistenceMode`
  (off / strike_gap / quote_operator / smile_factor / hybrid) vs the true day-_T_
  quotes. `off` (no prior) is the baseline each mode must beat; the deep tail beyond
  `c_wing` σ is excluded (no operator reaches it and LQD far-wing extrapolation off a
  narrow ATM set is fragile). Sweeps the two flagged defaults — the var-swap coverage
  probe (`operators._VARSWAP_PROBE_STD`, 1.4σ) and the operator support bandwidth
  (`OptionsSettings.priorOperatorBandwidth`, 0.06) — and reports, per (mode, bandwidth,
  probe), median wing RMS, median improvement over off, and the win-rate.

      python -m backtest.temporal --regime spike_aug2024
      python -m backtest.temporal --regime spike_aug2024 --asset SPX \
          --modes off,quote_operator,hybrid --bandwidths 0.04,0.06,0.10 --probes 1.0,1.4,2.0

  Writes `results/<regime>_temporal_prior.json` (per-node rows + the aggregate
  summary). Covered by `tests/test_temporal_backtest.py` (helpers + a synthetic
  self-prior end-to-end). **Findings + the tuning verdict:**
  `FINDINGS_prior_temporal.md` (TL;DR: the full spike regime confirms `hybrid` is the
  best mode at every bandwidth/probe; the operator bandwidth is not a useful lever —
  no shipped default changed).

## Graph leave-one-out (roadmap Phase 6, `graph_loo.py`)

Validates the headline differentiator — graph smile-extrapolation across the
universe — **temporally** on the captured day pairs. For each consecutive (T-1, T):
freeze T-1's surface as the active prior per ticker (`capture_snapshot(lv=False)`),
transport it under SSR regime R, form the lit innovation `d = calibrated_T −
transported_prior`, propagate through the **directed graph** (`graph_edges.py`), and
compare the graph posterior for held-out nodes with their ACTUAL day-T calibration —
all three handles (ATM/skew/curvature) + the reconstructed full-smile **wing RMS** —
and against the pure transported-prior baseline (the graph's **skill**: does the
signal beat the mechanical spot-transport?).

- **SSR sweep R∈{0,1}** (Q1): R=0 (sticky-moneyness) leaves an underperformer's
  baseline vol unmoved and OVER-credits the graph; R=1 (sticky-strike) bakes in the
  full leverage and UNDER-credits it — the truth is bracketed, so both are reported.
- **Two designs** (`--designs`): **full_loo** withholds each validation-clean node in
  turn (calendar + cross-asset neighbours carry it); **liquid_split** lights only
  indices/ETFs and scores the single names as dark extrapolation targets (the real
  product use case).
- **Directed edges** (`graph_edges.py`): calendar (high conductance, β=√(T_to/T_from)),
  Index→name (β=0.7 vol-normalized), SectorETF→name (β=0.8), name→name same-sector
  (β=0.6), everything else β=0. **Direction:** `w_ij` = "j informs i", so a
  `GraphEdgeInput` flows `to`→`from` — "index informs name" is emitted as
  `from=NAME, to=INDEX`. Vol-normalized β becomes the absolute edge β = β_vn·σ_from/σ_to.

      python -m backtest.graph_loo --regime spike_aug2024
      python -m backtest.graph_loo --regime spike_aug2024 --designs liquid_split --max-pairs 4

  Writes `results/<regime>_graph_loo.json`. Covered by `tests/test_graph_loo_backtest.py`
  (taxonomy + the direction/vol-normalization/√T edge logic). **NB (pilot caveat):**
  the captured 8-asset pilot has no US sector ETF and its single names share no sector
  (AAPL/NVDA/JPM), so the ETF→name and name→name edge classes are **dormant** — only
  Index→name + calendar are exercised. The full name→name / sector tests need the
  25-asset capture.

## Status

Capture (REST + flat-file) + compute (dispatch/replay) + metrics/analyze built and
tested. Pilot = Aug-2024 spike × 8 assets. The **prior-mode temporal axis**
(`temporal.py`) and the **graph leave-one-out** (`graph_loo.py`, Phase 6) are both
built and runnable. **Remaining:** the NN-dataset emitter (Phase 7, feeds off
`volfit/data/columnar.py`), the full 25-asset capture (lights up the dormant
name→name / sector-ETF graph edges), and the LV `wall_ms_pde_*` timing wiring.

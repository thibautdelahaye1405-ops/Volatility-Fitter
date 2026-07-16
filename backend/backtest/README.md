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
| `ablation_arb.py` | R3 (convex de-Am) × R6 (put-wing penalty) ablation on SIV wing arb. |
| `capture_intraday.py` | R2-item-10 0DTE capture, flat-file source: N instants/day from ONE `quotes_v1` scan (`chains_at`) — but one day file is ~111 GB, hours of fragile streaming. |
| `capture_intraday_rest.py` | R2-item-10 0DTE capture, REST source (the light default): same fixture schema/ladder/instants, NBBO per (contract, instant) via `/v3/quotes` with a day-bounded `gte`; ~30 s/instant, per-instant checkpoint. |
| `run_capture_intraday.ps1` | stall supervisor for the flat-file intraday scan (kills+relaunches a frozen stream). |
| `validate_intraday_clock.py` | acceptance CLI: replay a captured VolStore snapshot, calibrate every expiry with `intradayClock` ON, require sub-day t + sane fits. |
| `observation_filter_intraday.py` | filter-clock tuning on the 0DTE campaign: `--build` a per-instant measurement table (~940 data-only LQD fits, resumable), `--sweep` the pure Kalman core over (clock, process-bp) configs — zeta per step type is the verdict (found: session share 0.60, non-trading 0.0). |

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
  **Reverse cross edges** (`EdgeConfig.cross_reverse_frac`, default 1, inverse β) are
  REQUIRED: with one-way cross edges single names are transient under the trust kernel
  (stationary π=0 ⇒ reversibilized conductance 0 ⇒ dark names fully decoupled), which
  silently zeroed every liquid_split result until 2026-07-09; 0 reproduces that legacy
  topology for ablation.

      python -m backtest.graph_loo --regime spike_aug2024
      python -m backtest.graph_loo --regime spike_aug2024 --designs liquid_split --max-pairs 4

  Writes `results/<regime>_graph_loo.json`. Covered by `tests/test_graph_loo_backtest.py`
  (taxonomy + the direction/vol-normalization/√T edge logic). **Verdict (2026-07-09,
  25 assets × 3 regimes, fixed topology; tables in `FINDINGS_graph_loo.md`):**
  neighbour-supported indexes +10…+76 bp / ETFs +3…+7 bp ATM skill; fully-dark single
  names +7.9…+14.2 bp in the Aug-2024 spike and +3.8…+7.2 bp out-of-sample in Oct-2022,
  ≈0 (never negative) in the Jul-2023 calm — whose dark-name bands read overconfident
  (ζ std ~1.9, open follow-up).

## R3 × R6 wing-arb ablation (`ablation_arb.py`, FINDINGS follow-up)

R3 (`volfit/calib/convex_deam.py`, convex de-Am of the call *inputs*) and R6
(`models/sigmoid/calibrate.py` `wing_penalty`, the put-wing Durrleman penalty on the
SIV *output*) both defend the SAME F4 put-wing butterfly pathology from opposite ends,
and both ship default-on. This isolates which one actually removes the arb by fitting
every American node under the 2×2 `{R3 off/on} × {R6 off/on}` → `neither / R3 / R6 /
both` and measuring the model's **analytic** Durrleman g (no FD noise, the R2 lesson)
on a grid extended ±2 ATM-std past the traded range (the F4 region), alongside in- and
leave-every-3rd-out RMS so the precision **cost** of each defence sits next to the arb
it removes. The aggregate scopes to the **arb-prone** population (nodes whose `neither`
cell is materially arbitraged) and reports a per-cell repair fraction (the attribution).

    python -m backtest.ablation_arb --regime spike_aug2024
    python -m backtest.ablation_arb --regime spike_aug2024 --assets EEM,EFA --cores 2

Writes `results/<regime>_ablation_arb.json`. `ablate_node` is fixture-independent (takes
a live `AppState`), so `tests/test_ablation_arb.py` drives it on a synthetic American
chain (real de-Am) plus deterministic aggregation/grid unit tests. Findings:
`FINDINGS_ablation_arb.md`.

## Status

Capture (REST + flat-file) + compute (dispatch/replay) + metrics/analyze built and
tested. The 25-asset capture and the full 3-regime benchmark pack (full_loo +
liquid_split, fixed topology) are DONE (2026-07-09; verdict above). **Remaining:**
the NN-dataset emitter (Phase 7, feeds off `volfit/data/columnar.py`), the LV
`wall_ms_pde_*` timing wiring, and the calm-regime dark-name band widening.

## Observation-filter temporal backtest (Note 15, Phase 5+)

`observation_filter.py` � drives the PRODUCTION `on_fit_commit` per captured
day pair: carry the T-1 posterior into day T, commit a thinned measurement
under scenarios `thinned / contradiction / shock`, score vs the raw-fit and
gain-0 baselines + zeta calibration + retargeted wing RMS. Sweeps
`--cov-modes jacobian,factors`, `--process-bps`, `--modes overlay,active`,
`--adaptive`; `--tag` keeps A/B runs off the canonical result files.
Full-regime launcher: `run_filter_full.ps1` (resumable; run it in YOUR OWN
PowerShell window). Verdicts F1-F11: `FINDINGS_observation_filter.md`.
NB the synthetic shock perturbs the thinned FIT inputs only, not the
prepared mids the active-path ATM probe reads (F10 is unit-locked instead).

## 25-asset capture

`run_capture_full.ps1` � resumable REST capture of the FULL universe across
all 3 regimes (~5 min/trading day for the 17 non-pilot names; force-sets
VOLFIT_MASSIVE_KEY from restart.local.ps1). Fed the 25-asset graph
leave-one-out (verdict 2026-07-09 above; graph/precision.py DARK_BASE_SCALE
proved a DEAD lever — the levers are reach η and cross conductance).

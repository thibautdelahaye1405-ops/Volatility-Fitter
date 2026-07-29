# Vol-Fitter work-environment handoff pack

**Generated 2026-07-29 from the reference project. Everything in this folder
is plain Markdown — no PDFs, no images, no source code, no executables — so
the whole pack (~1.3 MB, 25 files) can be transferred under the work
environment's file constraints. It is self-contained: with these files alone,
a strong coding model (Opus-class, GPT-class, via GitHub Copilot or similar)
can re-develop the application from scratch.**

## What this pack is

A clean-room *capability* specification for rebuilding the Vol-Fitter — an
implied-volatility surface fitting application (smile calibration under
several arbitrage-aware models, local volatility, forwards/dividends
inference, de-Americanization, event clocks, prior persistence, observation
filtering, and graph-based extrapolation of sparse observations to a full
universe of smiles) — plus the complete prevailing technical-note series in
lightweight Markdown form.

The rebuild does not need to reproduce the old application file-for-file.
It needs all functionality present and a workflow at least as fast and
efficient. The spec states exactly which contracts are binding and where
improvement is welcome.

## Reading order

1. `VOL_FITTER_CLEAN_ROOM_REBUILD.md` — the contract. Read first, fully.
2. `SETTINGS_REFERENCE.md` — the exact control surface (machine-extracted).
3. `PITFALLS_AND_ADJUDICATIONS.md` — named production failures and measured
   verdicts behind the defaults.
4. `API_AND_UI_INVENTORY.md` — the reference API (107 routes) and the
   eight-workspace UI as a completeness checklist.
5. `notes/` — the mathematics, one primary note per topic (the rebuild spec
   §2.2 maps primaries vs supplements and §15 gives the per-phase reading
   list). Feed notes to the coding model per phase, not all at once.

## Manifest

### Engineering layer

| File | Lines | Role |
|---|---:|---|
| `VOL_FITTER_CLEAN_ROOM_REBUILD.md` | 1327 | Rebuild contract: scope, invariants, architecture, phases, acceptance |
| `SETTINGS_REFERENCE.md` | 229 | Every tunable: type, range, default, unit, activation, cache semantics |
| `API_AND_UI_INVENTORY.md` | 176 | Route-by-route API surface + workspace-by-workspace UI inventory |
| `PITFALLS_AND_ADJUDICATIONS.md` | 236 | 22 certification cases + 12 adjudicated experiment verdicts |
| `README.md` | — | This manifest |

### Mathematical layer (`notes/`) — the prevailing lecture editions

Each converted from LaTeX on 2026-07-29: figures replaced by caption +
panel-by-panel descriptions, every measured number inlined as a literal,
reference-implementation listings replaced by exact algorithm specifications
(inputs, steps, tolerances — no code), equation numbering preserved.
As of 2026-07-27 these editions were audited line-by-line against the working
code; they are current, not historical.

| File | Lines | Topic (angle) |
|---|---:|---|
| `00_system_overview.md` | 254 | System map + full control index (76 surfaced + 26 hidden parameters) |
| `01_lqd_model_coordinates.md` | 1069 | **Primary 01** — LQD model; the chart where no-arbitrage is free |
| `01_lqd_model_lecture.md` | 1050 | Supplement — distribution-first desk lecture |
| `01_lqd_model_percentile_ruler.md` | 1086 | Supplement — monotone transport / fresh audit |
| `02_svi_jw_rewrite.md` | 778 | **Primary 02** — SVI raw vs JW charts; the structural chart |
| `02_svi_jw_moments.md` | 588 | Supplement — wings and belly; Lee's bound as a tail statement; certificates |
| `03_multicore_mcs_corrections.md` | 329 | Multi-Core SIV — base and correction; capacity control |
| `04_local_volatility_forward.md` | 506 | Local volatility — Dupire read backward, parameters up |
| `05_deamericanization_stopping.md` | 455 | De-Americanization — subtracting the unobservable premium |
| `06_forwards_dividends_inference.md` | 355 | Forwards/dividends — inference on one straight line |
| `07_calibration_objective_measure.md` | 263 | The objective as units, measure, tolerance |
| `08_varswap_representations.md` | 361 | Variance swaps — one number, three integrals |
| `09_wings_last_quote.md` | 323 | Wings — beyond the last quote: prove / choose / police |
| `10_calendar_unnamed_martingale.md` | 271 | Calendar — Kellerer as the organizing theorem |
| `11_event_market_clock.md` | 225 | Event/intraday clocks — the market keeps its own clock |
| `12_spotvol_missing_derivative.md` | 207 | Spot-vol dynamics — SSR as the one dial |
| `13_prior_flat_directions.md` | 388 | Prior persistence — the prior confined to the null space of today's data |
| `14_graph_three_priors.md` | 545 | **Primary 14** — three priors for a dark universe (all propagation modes) |
| `14_graph_messages.md` | 377 | Supplement — the precision-message system, standalone deep spec |
| `15_kalman_computed_trust.md` | 422 | Observation filter — trust is computed, not configured |

## Transfer and usage notes

- Every file is independently small (largest ~90 KB); send individually or
  zipped, as the channel allows.
- The conversion is content-complete, not summarized: all theorems, proofs,
  case files, exercises, hyperparameter atlases, traceability tables, and
  references survive. Traceability module/test names refer to the reference
  implementation — treat them as capability and test checklists.
- Math renders as standard `$…$` / `$$…$$` LaTeX in GitHub, VS Code preview,
  and Copilot Chat; it degrades to readable plain text elsewhere.
- Precedence when documents disagree, and the per-phase note reading list,
  are in the rebuild spec (§2.3 and §15).
- The suggested first prompt for the new environment is the rebuild spec §19.

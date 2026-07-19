# Phase-4 adjudication — precision-message operator (PREP; sweep NOT run yet)

Status 2026-07-19: **machinery shipped + smoke-validated; the multi-hour
campaign is a USER action** (`backtest\run_message_adjudication.ps1` in your
own PowerShell window — tool background jobs get killed on this box).
Nothing below is a verdict until the sweep populates the tags.

## What ships in this phase

- `benchmark_pack` CLI grew the message-variant knobs: `--mode`
  (smooth_field | precision_messages | hybrid), `--alpha-t`, `--amp-cal`,
  `--amp-cross`, `--cal-precision`, `--cal-epsilon`, `--cal-decay`,
  `--cross-precision-mult`. Rows from message sweeps carry provenance
  stamps (mode/alphaT/ampCal/ampCross/calDecay).
- `graph_edges.build_message_edges`: the SAME economic taxonomy as the
  smooth-field edge builder (calendar + SPX-hub index + sector ETF + sector
  peers), expressed as one relation factor per relation in canonical
  orientation — the adjudication compares OPERATORS, not topologies.
  Betas are the unit vol-normalized relations (sigma ratios); the amplitude
  LEVEL rides the request's rho multipliers through the node-linked anchor.
  Cross-class precision seeds from message_phase0: index 1.3e4, peer 0.9e4,
  ETF 1.1e4 (1/vol^2).
- New metrics on every scored summary (retroactive for zeta-carrying rows):
  **cov50/cov80/cov95 band coverage** (P(|zeta| <= z_p), the spec-22.4
  gate-4 readout) in `graph_loo.summarize` + `benchmark_pack.summarize_by`
  + the HTML report (80%/95% columns). New per-row fields: `hops` (BFS
  graph distance to the nearest lit source — the calibration-by-path-length
  axis; the report gains a "By graph distance" table) and `q_in`
  (message-mode receiver conditional precision — the conditional-vs-realized
  axis).
- Runbook `run_message_adjudication.ps1`: SIX variants over the strict-OOS
  window (pairs >= 10), absorbing the parked b14 sweep —
  `_b14_base`, `_b14_learned`, `_p4_msg_desk`, `_p4_msg_learned`
  (amp-cal 0.23 / amp-cross 0.39, the Phase-0 single-source targets),
  `_p4_msg_a05` (shape ablation), `_p4_msg_const` (decay ablation) —
  then `benchmark_compare` across all six tags.

## Pre-registered adoption gate (spec §22.4 — restated verbatim intent)

Precision-message becomes the product default ONLY IF, on liquid_split dark
names over the OOS window:

1. ATM/calendar skill improves materially vs the transported prior AND
   `_b14_base`;
2. non-degrading in the stressed regimes (spike_aug2024, high_oct2022);
3. calm-regime (low_jul2023) skill not negative beyond tolerance;
4. zeta std ~ 1 and cov80/cov95 near nominal after the idio floor;
5. no unstable cycles (the taxonomy is gauge-consistent by construction —
   cycleDiagnostics must stay empty);
6. wing RMS does not deteriorate.

Expectations to hold ourselves to (recorded BEFORE the sweep):

- `_p4_msg_desk` (rho=1) is EXPECTED to lose day-horizon RMS — full force is
  the desk-belief preset, not the statistical optimum; it ships opt-in
  regardless. The gate adjudicates the DEFAULT preset.
- `_p4_msg_learned` is the candidate: single-source amplitudes 0.23/0.39
  with the node-linked corroboration lift (validated to 0.3% offline).
- `_p4_msg_const` probes whether the near-gap-flat day-horizon noise
  (message_phase0 [B]) makes the inverse-sqrt decay superfluous.
- Item-14 rule carries over unchanged for `_b14_learned`: activate learned
  betas only on positive spike liquid_split delta, non-negative elsewhere,
  zeta std not degrading.

## Smoke validation (2026-07-19, in-session; part deleted afterwards)

One day-pair (2024-07-30, spike_aug2024), `--mode precision_messages
--amp-cal 0.23 --amp-cross 0.39`, tag `_p4_smoke`: 898 rows, zero solver
failures; every row carries mode/alphaT/ampCal/ampCross/calDecay stamps,
`hops` in {1,2,3}, and `q_in`; coverage columns render.

Single-pair numbers (NOT a verdict; recorded to seed expectations):

| variant | design | R | ATM skill bp | zeta mean/std | cov80 | cov95 |
|---|---|---|---|---|---|---|
| message learned | full_loo | 0 | +5.83 | 0.57 / 1.40 | 0.78 | 0.88 |
| message learned | full_loo | 1 | +1.85 | 0.39 / 1.23 | 0.83 | 0.90 |
| message learned | liquid_split | 0 | +0.39 | 0.69 / 1.54 | 0.77 | 0.87 |
| message learned | liquid_split | 1 | +0.10 | 0.54 / 1.31 | 0.75 | 0.89 |
| legacy untagged | full_loo | 0 | +0.69 | 0.24 / 0.64 | 0.96 | 0.98 |
| legacy untagged | full_loo | 1 | +0.26 | 0.17 / 0.58 | 0.98 | 0.99 |

Read: on THIS pair the message operator's mean skill dominates while its
bands run slightly narrow (zeta std 1.2-1.4) where the legacy's ran wide
(0.6, cov95 0.98 vs nominal 0.95). The full OOS sweep decides.

## Decision table (FILL AFTER THE SWEEP)

| variant | liquid_split ATM skill (spike / high / low, R-bracket) | zeta std | cov95 | verdict |
|---|---|---|---|---|
| _b14_base | | | | baseline |
| _b14_learned | | | | |
| _p4_msg_desk | | | | expected RMS loser; opt-in preset |
| _p4_msg_learned | | | | THE candidate |
| _p4_msg_a05 | | | | shape ablation |
| _p4_msg_const | | | | decay ablation |

Fill from `results/benchmark/ablation_compare.json` +
`python -m backtest.benchmark_pack report --tag <tag>`; then record the
gate verdict here and flip (or don't) `OptionsSettings.graphPropagationMode`
/ the amplitude preset defaults in a dedicated commit.

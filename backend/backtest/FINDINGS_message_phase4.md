# Phase-4 adjudication — precision-message operator

**Status 2026-07-27: TABLE FILLED from the stored 2026-07-19 sweep parts
(intersected natural keys, 21,962 OOS rows). The §22.4 gate did NOT clear
at the daily horizon (gates 1, 4, 6 fail — see the filled table). The
default was nonetheless FLIPPED to `precision_messages` on 2026-07-27 by
USER RATIFICATION, on the strength of the intraday async-replay
separation (FINDINGS_dynamic_intraday.md: msg 65.8bp vs smooth_field
168.6bp vs transport 172.7 — the legacy operator is nearly inert
intraday) — recorded below with full caveats.**

Status 2026-07-19 (historical): machinery shipped + smoke-validated; the
multi-hour campaign was run in the user's window the same day.

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

## Decision table (FILLED 2026-07-27 from the stored parts; intersected
## keys, 21,962 rows; skill = base RMS − graph RMS, bp; liquid_split
## unless noted; R-bracket = R0 / R1)

| variant | spike | high | low | zeta std | cov80 | cov95 | verdict |
|---|---|---|---|---|---|---|---|
| `_b14_base` | +0.08 / +0.03 | +0.09 / +0.10 | +0.02 / +0.01 | 0.84 | 0.973 | 0.987 | baseline (over-wide bands) |
| `_b14_learned` | +0.17 / +0.06 | +0.15 / +0.16 | +0.05 / +0.03 | 0.83 | 0.973 | 0.987 | fractions-of-a-bp; item-14 hold stands |
| `_p4_msg_desk` | −21.15 / +6.51 | +6.41 / +8.99 | −12.47 / +1.21 | 1.81 | 0.875 | 0.945 | expected RMS loser confirmed; opt-in preset |
| `_p4_msg_learned` | +2.01 / +0.74 | +1.03 / +0.44 | +0.75 / +0.35 | 2.29 | 0.816 | 0.908 | THE candidate — gates 1/4/6 fail |
| `_p4_msg_a05` | +2.03 / +0.75 | +1.03 / +0.43 | +0.76 / +0.36 | 2.27 | 0.817 | 0.910 | shape ≈ inert at day horizon |
| `_p4_msg_const` | +2.02 / +0.74 | +1.03 / +0.45 | +0.76 / +0.36 | 2.32 | 0.815 | 0.907 | decay ≈ inert at day horizon |

full_loo pooled RMS (bp): base 280.8 / msg_learned 281.7 (skill vs
transport +7.0 vs +8.9). Wing medians (liquid_split): base arm 99.6 vs
its baseline 97.6; msg_learned 105.2 vs 97.3.

### §22.4 gate verdict at the DAILY horizon (recorded)

| gate | criterion | verdict |
|---|---|---|
| 1 | material liquid_split skill vs prior AND base | **FAIL** (+0.35…+2.01bp — positive everywhere, material nowhere) |
| 2 | stressed regimes non-degrading | PASS |
| 3 | calm regime not negative | PASS (+0.35/+0.75) |
| 4 | ζ ≈ 1, coverage near nominal | **FAIL** (ζ std 2.29/2.07, cov95 0.908 — overconfident; base is over-wide 0.84) |
| 5 | no unstable cycles | PASS (empty by construction) |
| 6 | wing RMS non-deteriorating | **MARGINAL FAIL** (median 105.2 vs base-arm 99.6, +5.6bp) |

**Daily-horizon conclusion (what the 2026-07-19 hold already said,
now recorded in the pre-registered table): at one-day granularity the
message operator is statistically indistinguishable from smooth_field
on RMS, with overconfident bands and mildly worse wings — the gate does
not clear.**

## THE FLIP (2026-07-27, user-ratified)

`OptionsSettings.graphPropagationMode` default: `smooth_field` →
`precision_messages`. Basis: NOT this gate (which failed at the daily
horizon and is recorded verbatim above) but the intraday async-replay
campaign (FINDINGS_dynamic_intraday.md), where the operators separate
decisively — smooth_field is nearly inert (168.6bp vs 172.7 transport;
intraday innovations are shrunk to nothing by the zero-innovation
anchor at day-scale κ/η), while the message operator carries the signal
(65.8bp, ζ 0.88, cov95 0.964, no wing regression). The user ratified the
flip 2026-07-27 with the daily verdict on the table.

Scope (mirrors the sviChart flip precedent):

- The flip is the OPTIONS default (what Options ▸ Graph seeds and the
  UI runs). The WIRE default (`GraphExtrapolateRequest.propagationMode`)
  stays `smooth_field`: bare API solves, workspace replay, the §21.10
  byte-identity locks and the whole backtest harness are untouched —
  smooth_field remains explicit configuration and the rollback.
- Amplitude defaults stay at desk (1.0): the intraday evidence was
  measured at desk amplitude; the learned preset (0.23/0.39) remains
  selectable and its daily numbers are in the table above.
- Persisted stores with an EXPLICIT graphPropagationMode keep their
  value (the leeSlopeMax precedent): a dev store that ever saved
  Options pins smooth_field until Options ▸ Graph is re-saved.
- Known characteristics the default now carries at the daily horizon,
  stated plainly: ζ std ~2 (bands narrow — the graph credible bands, not
  fit quality) and wing medians ~+5bp vs the legacy arm. The intraday
  horizon shows the reverse ordering. Follow-ups that would repair the
  daily calibration: the D6 joint anchors and the §15.2/§21.13 baseline
  placement are already recorded candidates in the dynamic findings.

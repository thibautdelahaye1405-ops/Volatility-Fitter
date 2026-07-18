# Phase-0 findings — precision-message graph redesign

Date: 2026-07-18. Study module: `backtest/message_phase0.py` (rerun with
`python -m backtest.message_phase0` from `backend/`); artifact:
`results/message_phase0.json`. Data: ALL stored untagged full_loo benchmark
rows (ssr=0), three regimes (high_oct2022 19 days, low_jul2023 18,
spike_aug2024 17), innovations `d = -base_atm` (knob-independent), sigma
scales fit-free from first-day fixtures. This is a DESIGN study — the
adoption gate remains Phase 4's strict-time-split sweep
(`Docs/graph_precision_message_framework.md` §22.4).

## [A] Anchor mechanization: node-linked (fixed kappa) — CHOSEN

Question (spec §14.2): when a dark name has corroborating sources, does the
realized innovation transfer rise (node-linked, fixed per-node anchor) or
stay constant (edge-linked, anchor scaling with incoming precision)?

Through-origin slopes of a name's vol-normalized innovation, pooled over
name-days that HAVE same-sector peers (n=1007), lit predictors:

| predictor                    | slope | t     | R^2   |
|------------------------------|-------|-------|-------|
| index (SPX) alone            | 0.391 | 40.7  | 0.622 |
| sector-peer average alone    | 0.762 | 33.7  | 0.531 |
| equal-weight (idx+peer)/2    | 0.561 | 42.4  | 0.641 |
| bivariate (free weights)     | 0.292 idx + 0.255 peer = 0.547 total | | |

Corroboration uplift = 0.561/0.391 - 1 = **+43%** (pre-registered bar 15%,
both slopes t >> 2) → **node-linked**.

**Quantitative validation, zero free parameters:** the fixed-kappa Gaussian
anchor model calibrated ONLY on the single-source slope
(0.391 ⇒ kappa/p = (1-0.391)/0.391 = 1.555) predicts the two-source
equal-precision transfer 2p/(kappa+2p) = 2/3.555 = **0.563**; measured
**0.561** (0.3% agreement). The edge-linked rule (constant transfer rho
regardless of source count) is rejected by the same measurement.

Production consequence (spec §14.2): kappa_i = p_primary*(1-rho_class)/rho_class,
fixed at build time from the receiver's primary relation class; corroborating
edges then lift the effective transfer q/(kappa+q) exactly as measured.
Golden contracts: single-source rho*beta*z and two-source 2rho/(1+rho) in
`tests/fixtures/graph_message_golden.json`.

## [B] Calendar precision family (alphaT=1 shape)

Adjacent-ladder pairs in canonical short-receiver orientation
(y = d_short, x = (T_l/T_s)*d_long), n=11,735, raw ATM-vol units:

- Level (predictive): b = **0.232** (t = 51). NB the learned artifact's 0.34
  is the multiplier for the sqrt(T)-shape — the level is SHAPE-DEPENDENT;
  under alphaT=1 the equivalent learned amplitude preset is ~0.23.
- Residual variance by sqrt-gap bucket (sqrt-years → RMS vol points):
  0.13→2.72, 0.16→2.39, 0.28→2.77, 0.30→2.68, 0.41→2.89. Nearly GAP-FLAT.
- Family fit Var(e) = (epsT + sqrt(dT))/p0: **p0 ≈ 1690** (1/vol^2),
  **epsT ≈ 0.97** (sqrt-years) → tau(1M gap) ≈ 2.7 vol points. The large
  epsT means the decay term is nearly inactive at the day horizon — the
  family degrades gracefully to near-constant precision; whether the decay
  earns its keep is a Phase-4 question.
- Shape preview: refitting the level per alphaT gives R^2 0.1803 / 0.1810 /
  0.1813 for alphaT 0 / 0.5 / 1 — the SHAPE is weakly identified at this
  horizon. alphaT=1.0 is retained for its constant-variance-injection
  semantics (spec §8.1); Phase 4 sweeps it.

## [C] Cross-class message-noise seeds

Residual noise around each class's own predictive slope, normalized units
converted at sigma_med = 0.270 (ATM-vol units, 0.01 = 1 vol point):

| class        | slope | resid RMS (volpts) | precision seed (1/vol^2) | n    |
|--------------|-------|--------------------|--------------------------|------|
| index→name   | 0.394 | 0.87               | ~1.3e4                   | 1063 |
| sector peer  | 0.679 | 1.05               | ~0.9e4                   | 1484 |

CAVEAT: measured on ticker-day MEDIAN innovations (median across scored
expiries suppresses per-expiry noise), so these are UPPER bounds on
per-edge precision; the calendar figures in [B] are per-expiry and not
directly comparable. Phase 4 sweeps the scales around these seeds.

## Phase-0 exit status

- Golden fixtures + brute-force reference: `tests/test_graph_message_golden.py`
  (24 tests, green) over `tests/fixtures/graph_message_golden.json`.
- Anchor mechanization: node-linked — CHOSEN (this study).
- Numeric seeds: recorded here and in spec §9.2.
- Spec amendments: complete (spec §27 amendment log).

Phase 0 exit gate MET → Phase 1 (`volfit/graph/message.py`) is next.

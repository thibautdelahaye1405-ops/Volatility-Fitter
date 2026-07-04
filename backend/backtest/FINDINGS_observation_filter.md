# Observation-filter temporal backtest — findings (Phase 5, Note 15)

**Run:** `spike_aug2024`, all 8 pilot assets, first day pair each (2024-07-29→30),
scenarios `thinned / contradiction / shock`, sweep `filterCovarianceMode ×
filterProcessVolBpSqrtDay ∈ {10, 30}` — 666 steps. Harness:
`backtest/observation_filter.py` (drives the PRODUCTION `on_fit_commit`);
merged results: `results/spike_aug2024_observation_filter.json`.
**Scope caveat:** one pair per asset, one regime, foreground chunks; the
full-regime overnight run should confirm before any default flips (Phase 7).

## Headline verdict

At the recommended pilot config (**jacobian route, diagonal update, clock
noise 30 bp/√day, >30 DTE**) the filter is a *calibrated denoiser*:

| scenario | errPost(ATM) | errMeas (raw) | errPred (gain-0) | win | gain | ζ mean | ζ std |
|---|---|---|---|---|---|---|---|
| thinned | **7.1 bp** | 7.6 bp | 26 bp | **0.73** | 0.90 | −0.29 | **1.30** |
| contradiction | 13.4 bp | 8.2 bp | 25.5 bp | 0.54 | 0.66 | 0.57 | 1.62 |
| shock (+5 pts) | 58 bp lag | 4 bp | 530 bp | 0.23 | 0.90 | 4.1 | 3.3 |

ζ ≈ N(0, 1.3) on plain days = the posterior uncertainty is honest (slightly
tight). The `contradiction` ATM column under-sells the mechanism — the kink
attacks curvature, where the per-handle gains show the rejection (curvature
gain ≪ level gain, the Note 15 case file behaviour; per-handle columns in the
JSON).

## Findings

**F1 — Cross-handle coupling blowup → the update is now DIAGONAL (shipped).**
With the full-covariance update, EEM/EFA (coarse-strike ETF chains) produced
posterior ATM errors of 3–28 *vol points* — worse than BOTH baselines, which a
scalar update cannot do. Mechanism: the Jacobian R carries strong
level–curvature correlations, so a junk curvature innovation dragged the ATM
level through the OFF-diagonal gain terms (`filterMaxGain` caps own-gains only
and cannot prevent this). Fix: `api/observation_filter.DIAGONAL_UPDATE = True`
— per-handle scalar gains, the Note 14 graph convention. Post-fix EEM wins
(4.5 vs 8.1 bp, ζ 0.14) and EFA degrades gracefully (near-zero gain from its
wide-spread R, ζ 0.26 = conservative). Full-covariance stays available for
later study.

**F2 — ζ must include the truth's own noise (shipped in the harness).** The
held-out "truth" is itself a fitted estimate; scoring against √P⁺ alone
overstated miscalibration ~3× (factors-route ζ std 12 → 1.8 at bp=10 after
adding R_truth per the note's §9 item 6).

**F3 — The ≤30 DTE bucket is a different regime.** Short-dated nodes show
90–160 bp thinned-vs-full ATM discrepancies (the LV short-dated quote/de-Am
noise diagnosis, not a filter defect); the filter loses to raw there and ζ
runs 3–4. Candidates before active mode: exclude <30 DTE nodes from the
filter, or a maturity-scaled measurement-noise floor (∝ 1/√τ). The summary
now reports the buckets separately so neither regime masks the other.

**F4 — Shock lag is the open tuning item.** A +5-pt overnight jump is ~50σ
under a 10 bp/√day clock: gain 0.60, 219 bp residual lag. bp=30 lifts gain to
0.90 (58 bp lag) AND fixes plain-day calibration (ζ std 3.1 → 1.3), so **30 is
the recommended pilot value** (schema default stays 10 until the full run —
Phase 7's job). A fixed clock cannot span calm + spike regimes; the
pre-active-mode follow-up is an adaptive Q (innovation-gated widening, or a
transport-noise term that actually bites on |h| spike days).

**F5 — Jacobian vs factors (the user-confirmed route holds).** Jacobian is
better calibrated (ζ std 1.30 vs 1.55) and clearly better on contradiction
(13.4 vs 24.8 bp, win 0.54 vs 0.15 — its geometry-aware R downweights the
kinked cluster). Factors' blunter, larger R gives slightly higher shock gain
(0.94 vs 0.90). Both viable; jacobian stays the default.

## Remaining before the Phase-6/7 verdict

1. Full-regime run (19 pairs × 8 assets; overnight foreground chunks:
   `python -m backtest.observation_filter --regime spike_aug2024 --asset X`),
   then `high_oct2022` / `low_jul2023` for regime robustness.
2. Adaptive-Q design for F4; short-dated policy for F3.
3. Re-check the contradiction verdict on the curvature columns explicitly.

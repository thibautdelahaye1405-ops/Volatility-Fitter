# SVI structural-chart default decision (committee R3 rider)

Adjudicates `FitSettings.sviChart` default: `"raw"` (historical) vs
`"structural"` — the committee's (β_L, β_R, k\*, w\*, κ\*) chart, shipped
opt-in 2026-07-24 (52e4827). Spot-check evidence (12 reference nodes):
0.0000 bp agreement wherever the raw chart converged, but raw exhausted its
500-evaluation budget on 5/12 real nodes while structural converged in
30–86 evals on all, ~3× faster despite its FD Jacobian.

## Design

Three arms over the frozen 25-asset, 3-regime fixture set
(`run_compute --models SVI-JW,SVI-JW-195,SVI-STRUCT --tag svichart`),
weights `tv_density`, fit modes `mid` + `haircut`:

- **SVI-JW** — raw chart @ the frozen harness cap 2.0 (anchors against
  every older part; NOT a decision arm).
- **SVI-JW-195** — raw chart @ the production buffered cap 1.95.
- **SVI-STRUCT** — structural chart @ 1.95.

The decision compares SVI-JW-195 vs SVI-STRUCT (like-for-like at the
production cap; the chart is the ONLY difference).

## Pre-registered gate (written 2026-07-26, BEFORE the sweep ran)

Flip the default to `"structural"` iff, in EVERY (regime × fit-mode) cell:

1. **Precision parity** — median in-sample RMS and median leave-every-3rd-out
   RMS within 0.5 vol bp of SVI-JW-195 (either direction);
2. **No new breaks** — fit exception rate ≤ SVI-JW-195's, and no NaN/non-
   finite fitted slices;
3. **Robustness win** — strictly fewer evaluation-cap exhaustions
   (nfev ≥ 500) than SVI-JW-195 in aggregate, and median wall time not
   more than 1.5× SVI-JW-195's;
4. **No arb regression** — analytic-butterfly violation incidence and
   magnitude no worse than SVI-JW-195 in aggregate.

Any gate failing → default stays `"raw"`, findings recorded, and the
failing cell becomes the next investigation.

## Results — round 1 (2026-07-26, tag `svichart`)

**VERDICT: HOLD raw default** (gates 2 and 4 failed). Full table via
`python -m backtest.analyze_svi_chart`. The evidence split:

- **Gate 1 (precision parity): PASS everywhere** — structural is in fact
  slightly BETTER in 11 of 12 medians (e.g. spike/mid in-sample 28.60 vs
  28.89 bp; OOS 33.09 vs 33.31).
- **Gate 3 (robustness/speed): PASS, spectacularly** — eval-cap
  exhaustions 573 (struct) vs **9,472** (raw@1.95) aggregate: the raw
  chart burns its 500-evaluation budget on ~33% of ALL real fits in the
  spike regime (2,141/4,796) and ~21-34% elsewhere — the reference-
  fixture spot-check's 5/12 was not an outlier, it is the raw chart's
  NORMAL behaviour on real chains. Median fit 9-11 ms vs 24-46 ms
  (~3x faster despite the FD Jacobian).
- **Gate 2 (no new breaks): FAIL** — 30 vs 7 hard breaks of ~29k fits.
  Diagnosis: ALL 30 are ONE bug — `exp(theta_4)` UNDERFLOWS to float 0.0
  in the kappa* lift → ZeroDivisionError in `s = b(1-rho^2)^{3/2}/kappa`.
  The lift must be a strict diffeomorphism in floating point; unbounded
  theta breaks that contract (the probe run's overflow warning was the
  mirror symptom).
- **Gate 4 (no arb regression): FAIL, marginally** — genuine-arb rate
  0.865% vs 0.826% aggregate, and deeper worst-g dips in some cells
  (low/mid −25.5 vs −5.5): the unbounded curvature lift explores steeper
  vertices. NB the harness fits WITHOUT the display path's belly repair;
  in production these slices are exactly what the R2 certificate
  repairs-or-blocks.

Round 2 (below) re-runs the SAME pre-registered gate after the one-line
lift hardening (clip theta into [−80, 80] — every lift strictly interior
in float), which addresses the entire gate-2 break class at its root.

## Results — round 2 (2026-07-26, tag `svichart2`, lift hardened)

**Pre-registered verdict: HOLD raw default — gate 4 alone fails**
(0.864% vs 0.826% aggregate genuine-arb incidence). Everything else:

- **Gate 1 PASS** — structural better or equal in every cell (e.g.
  spike/mid 28.61 vs 28.89 in-sample, 33.16 vs 33.31 OOS).
- **Gate 2 PASS** — structural now breaks ZERO times in all six cells;
  the raw arms still break 6 times (low_jul2023). Strictly MORE robust.
- **Gate 3 PASS** — exhaustions 594 vs 9,472; median fit ~10ms vs
  ~23-40ms.

**The gate-4 failure is a survivorship artifact.** Conditioning the raw
arm on convergence:

| population | genuine-arb rate | n |
|---|---|---|
| raw@1.95, CONVERGED fits | **1.076%** | 19,330 |
| raw@1.95, EXHAUSTED fits (nfev ≥ 500) | 0.317% | 9,472 |
| structural, all fits (all converge) | **0.864%** | 28,808 |

The raw chart's headline 0.826% blends a 1.076% converged population
with an artificially clean non-converged third — fits that stopped
BEFORE reaching any optimum, arb-y or otherwise (their higher RMS in
gate 1 corroborates). Like-for-like — converged against converged —
the structural chart has the LOWER arb rate, on top of winning every
other criterion. Gate 4 as pre-registered compares unlike populations.

## Recommendation (2026-07-26 — awaiting user ratification)

The pre-registered verdict stands as recorded: HOLD. But the evidence
reads FLIP: the single failing criterion measures raw-chart
non-convergence, not a structural-chart defect, and the marginal arb
incidence it penalizes is precisely what the R2 belly certificate
repairs-or-blocks downstream in production (the harness fits without
the display path's repair). Proposed amendment, for ratification:
score gate 4 on CONVERGED populations (or post-repair), under which
round 2 passes all four gates → default `sviChart="structural"`, with
the analytic structural Jacobian as the adoption follow-up.

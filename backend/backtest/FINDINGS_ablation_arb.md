# R3 × R6 ablation — which defence removes the SIV wing arb, and are they redundant?

*Follow-up to `FINDINGS_calibration_arb.md` (R3, R6). Harness:
`backtest/ablation_arb.py`; tests `tests/test_ablation_arb.py`. Run on the captured
`spike_aug2024` fixtures, 2026-07-03.*

## The question

R3 (`volfit/calib/convex_deam.py`) convex-repairs the de-Americanized call **inputs**;
R6 (`models/sigmoid/calibrate.py` `wing_penalty`) adds a put-wing Durrleman penalty on
the SIV **output**. Both defend the same F4 put-wing butterfly pathology, from opposite
ends, and **both ship default-on**. So on any illiquid node it was unknown *which* one
actually removes the arb, whether they are redundant, and what each costs in precision.

## Setup

For each American node, SIV-2 (the production cap) is fit under the 2×2
`{R3 off/on} × {R6 off/on}` → `neither / R3 / R6 / both`. Butterfly arb is read from the
model's **analytic** Durrleman g (no FD reconstruction noise — the R2 lesson) on a grid
extended **±2 ATM-std past the traded range** (the F4 wing region: median worst
violation at z ≈ −3.2). The aggregate scopes to the **arb-prone** population — nodes
whose `neither` cell is materially arbitraged (min g < −0.05, a threshold set between
genuine violations O(1–10) and benign SIV far-wing curvature O(1e-2)) — and reports a
per-cell **repair fraction**. `in_bp` is the in-sample weighted RMS vol error.

## Results — illiquid ETFs (EEM, EFA; 2 days, 38 of 40 nodes arb-prone)

| cell | median min-g | median put-g | arb % | repaired % | in-RMS bp |
|---|---:|---:|---:|---:|---:|
| **neither** | −30.35 | −14.40 | 100 | 0 | 92 |
| **R3** only | −10.32 | −1.56 | 97 | 3 | **25** |
| **R6** only | −0.02 | −0.02 | 29 | 71 | **749** |
| **both** | −0.02 | −0.01 | 26 | **74** | **225** |

## Results — liquid single names (AAPL, NVDA, JPM; 1 day, 17 of 30 nodes flagged)

| cell | median min-g | median put-g | arb % | repaired % | in-RMS bp |
|---|---:|---:|---:|---:|---:|
| **neither** | −0.23 | −0.22 | 100 | 0 | 10.9 |
| **R3** only | −0.23 | −0.22 | 100 | 0 | 10.9 |
| **R6** only | −0.04 | −0.03 | 41 | 59 | 36.9 |
| **both** | −0.04 | −0.03 | 41 | 59 | 36.9 |

## Verdict — **complementary, NOT redundant.** Each does different work.

1. **R3 targets the INPUT non-convexity — and is precision-POSITIVE where it fires.**
   On illiquid ETFs it cuts the raw violation ~3× (min-g −30 → −10, put −14 → −1.6)
   **and improves in-sample RMS 92 → 25 bp** — because it removes the arbitraged de-Am
   input noise the flexible SIV was otherwise chasing. It rarely *eliminates* the
   violation on its own (3% repaired), but it is close to free (better, actually).
   **On liquid names it is byte-identical to `neither`** (−0.23 = −0.23, 10.9 = 10.9 bp,
   `R6` ≡ `both`): dense chains have convex de-Am wings, so `convex_wing_repair` returns
   `None`. This is the shipped gating **confirmed on real data** — R3 fires only where
   the input is genuinely non-convex.

2. **R6 targets the OUTPUT wing-g — it eliminates the violation, but is expensive
   alone.** On illiquid ETFs it nearly zeroes the arb (min-g −30 → −0.02, 71% repaired)
   but at a **brutal in-sample cost: 92 → 749 bp** — it is fighting arbitraged quotes to
   flatten the wing. On liquid names, where the underlying arb is mild, it mops it up
   cheaply (+26 bp).

3. **Both = R6's arb removal at ONE-THIRD the precision cost.** `both` matches `R6`'s arb
   elimination (74% vs 71% repaired, min-g −0.02) but at **225 bp instead of 749** —
   because R3 cleans the inputs first, so R6's constraint no longer has to fight against
   non-convex de-Am noise. **R3 is what makes R6 affordable.** That is the concrete
   payoff of running both, and it **validates shipping both default-on**: R6 alone would
   impose a ~3× larger fit distortion on illiquid names.

So the two are not doing the same job twice. R3 is the cheap, precision-positive first
line that removes the arbitrage *source*; R6 is the enforcement that *guarantees* the
no-butterfly constraint; and the two compose — R3 makes R6's guarantee cheap.

## Caveats (honest scope)

- **Slice, not the full regime.** EEM/EFA 2 days (38 arb-prone), liquid 3 names × 1 day.
  The effect sizes are enormous and consistent, but full-regime + `high_oct2022` /
  `low_jul2023` confirmation is the follow-up (each ~1.9 min/fixture; background jobs on
  this box were being killed, so runs were done foreground in day-capped chunks).
- **Harsher metric than the original R6 finding.** The ±2-std extended grid reaches
  deeper into the wings than the R6 note's measurement, so the absolute min-g (−30) and
  R6's in-sample cost (+650 bp) here are larger than the note's illiquid-EEM figures
  (−7.86 → −0.019 at +79 bp). The *ranking and mechanism* are what transfer; the
  absolute bp are metric-dependent.
- **The 0.05 threshold slightly over-counts on liquid names.** The mild −0.23 liquid
  wing-g flagged as "arb-prone" is benign SIV far-wing curvature, not de-Am arbitrage —
  the R3-byte-identical result proves the inputs there are already convex. The
  continuous median min-g / put-g are the primary, threshold-free signal.

## Suggested follow-up

- The R6-alone illiquid cost (749 bp) suggests the default `sivWingPenaltyPct=100` is
  doing heavy lifting on illiquid names; worth a small sweep of the strength on EEM/EFA
  now that R3 (which absorbs most of the need) is also default-on — the affordable
  `both` cost (225 bp) may still be reducible without re-admitting arb.
- Re-run across the other two regimes for robustness (same harness, `--regime`).

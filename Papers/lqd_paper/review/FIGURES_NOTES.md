# Figures engineer's notes — decisions, deviations, caveats

Pipeline: `scripts/gen_figures.py` (helpers in `scripts/figlib/`, every file
<= 400 lines). Full run ~8 s, exit 0, writes 14 `figures/fig_*.pdf` +
`figures/paper_macros.tex` (151 macros) + `figures/MACROS.md`.
`--only <target>` rebuilds one figure or macro block; macros persist across
partial runs via `figures/_macros_store.json`. Deterministic (seed 20260804
for the certification battery) except the two wall-clock timing blocks.
Real nodes are REBUILT from the frozen (L, R, a) via `build_slice` — never
refitted; the rebuild gate reproduces the frozen display curves to
**0.0000 vol bp** worst-case across all 16 nodes (`\MacRebuildWorstBp`).

Style: serif STIX, 9/8 pt at final size; figures 6.3 in wide (2.1 in per
three-panel column). Palette = first three categorical slots of the
validated dataviz reference palette — blue `#2a78d6` (model), orange
`#eb6834` (market data), aqua `#1baf7a` (comparator; always direct-labeled
per the contrast-relief rule) — validated all-pairs colorblind-safe on a
white surface (validator run: worst pair CVD deltaE 9.2, normal 24.0).
Diverging heat map (F12) is RdBu (blue/red poles, neutral mid).

## Deviations the author MUST reflect in captions/text

1. **SPY haircut bands are 100% degenerate** (median spreads 4–14 bp,
   all < 2h = 100 bp), so every SPY node is effectively a mid fit. F4 and
   F5 therefore draw **raw bid–ask whiskers + quote mids**, and F5(b)'s
   ledger envelope is the bid–ask spread, not the haircut band. NVDA bands
   are live (47% / 52% of quotes on the featured nodes) and F6 draws the
   true haircut band. Macros: `\Mac*BandLivePct`, `\Mac*MedianSpreadBp`.
   This is exactly the "degenerate-band behavior" the section 9 plan wants
   defined — here it is live in the data.
2. **F11 order-control story**: at this mixture separation the N = 6
   comparator does NOT erase the two modes (`\MacDhModeCountLow` = 2); it
   distorts the density — overshoots the peaks, half-fills the valley —
   while the smile moves <= 42 bp (`\MacDhIvGapBp`). Phrase the claim via
   the L1 distances (0.047 vs 0.108, `\MacDhLOne*`), not via mode
   destruction. The valley-to-peak macros barely discriminate (0.39 vs
   0.40) — prefer L1 in the text.
3. **F3 audit levels**: the brief's "~1e-15" is not what the production
   grid delivers. Measured: transport-map linearity <= 1.1e-11 (cumulative-
   Simpson roundoff), martingale shift vs the closed form <= 3.0e-9
   (trapezoid + analytic-tail truncation, grows toward the s -> 1 wall),
   E[e^X] - 1 <= 3.3e-16. Quote `\MacExactMuWorst` / `\MacExactMapWorst`,
   don't hand-write 1e-15. Cold-start ATM variance mismatch −7.9% at 20%
   vol (the briefed ~8%).
4. **F13 forensics recomputed, README partly wrong**: replicating the
   production projection audit on the frozen display curves (near curve
   interpolated onto the far grid, both legs sqrt(w/t_far)) reproduces the
   manifest value exactly — 1840.6 bp at k = +0.981 on the 2026-08-05 /
   2026-08-07 pair, common quote span [−0.028, +0.016]. But the calls at
   the gap strike are **5.4e-107 F (2d) and 1.6e-26 F (4d)** — the data
   README's "both ~1e-20" is loose; use `\MacCalendarCallShort/Long`.
   Price-space check across all adjacent SPY pairs: worst 2.2e-15 (clean).
   Also: the pair's maturities are 2/365 and 4/365 **calendar** days; the
   README's "1-day/3-day" is business-day counting. Figures label them
   (2d)/(4d); `\MacNvdaOneDay*` keeps the brief's node naming.
   F13(b) truncates each solid curve where the node's rebuilt call drops
   below 1e-13 of forward (lead-review revision; same rule as F9): the 2d
   curve ends at k = +0.093, the 4d at k = +0.414, each continued by a
   light dotted flat segment marking the censored region. Beyond those
   points the stored w(k) is Black-inversion noise — which is the
   argument for support-confined enforcement; the annotation says so.
5. **F9 wings truncated** where the OTM price drops below 1e-13 of forward
   (beyond that, "w(k)" is inversion noise; the right wing dies near
   k ~ 1.8 since A_R = 0.066). Honesty result: the left 1-delta effective
   slope is 70% of the Lee limit (approach from below); the right 1-delta
   sits at 105% (approach from ABOVE — small-beta wings overshoot at
   finite k). Both directions are real; the caption should not claim
   monotone approach.
6. **F8**: NVDA 2027-12-17 has A_L = 1.42 > 1 — legal (only A_R < 1 is
   structural); its left critical moment p_- = 0.70 < 1.

## Choices

- **F6 long node = NVDA 2027-12-17** (1.37 y, 69 quotes, N = 16, rms
  7.4 bp): the longest NVDA maturity maximizes the contrast with the
  guarded 1-day node (N = 7 from 17 quotes, params 8 <= 17/2, rms 24.6 bp
  = the snapshot's worst). Runner-up 2026-12-18 (167 quotes) rejected —
  same order story, less maturity contrast.
- **F5 / F7 / F9 / F12 / F14 node = SPY 2026-12-18** (the brief's
  deep-dive node); the worked ticket prices the **December 800 call**
  (real listed strike, k = +0.0409): u = 65.27%, ledger share 0.378366,
  cash leg 0.361834, C = 0.016532 (= $12.70 on F = 767.92), IV 13.37%.
  The ledger identity C = G − cash is asserted to 1e-12 in the pipeline.
- **F10/F11 double-hump regularization = the production defaults**
  (lambda 1e-6, r = 1, the snapshot's own regLambda/regPower). Weaker
  ridges (1e-8, 1e-7) make the N = 16 density ring with 4 shallow modes;
  the production ridge recovers exactly 2 at −0.099/+0.088 vs true
  −0.101/+0.089, max IV error 11.3 bp (consistent with the certified
  double-hat lineage: ~11 bp, < 15 bp, exactly 2 modes).
- **Certification battery = 27 draws** (orders {4, 8, 16} x {plain,
  near-wall, wild} x 3), not the brief's "e.g. 24" — kept the cells
  symmetric. Seed 20260804, drawn through the logistic chart, audited in
  STRIKE space at sub-grid points. Worsts: bounds 1.1e-11, butterfly
  8.2e-13, digital 1.5e-12, 8001-vs-32001 grid 2.3e-9 — same orders of
  magnitude as the production 60-slice battery.
- **Timing** = one interleaved run, 9 solves/arm after warm-up, 40-quote
  SSVI strip, medians + IQR: analytic 16/24/30 ms vs FD 22/39/52 ms at
  N = 6/12/16 → speedups 1.38/1.62/1.74x. The production brief's range is
  1.44–1.97x; N = 6 lands slightly under on this box. Re-run on a quiet
  machine before print if the text quotes the range.
- **F12** audits at the PRICE level (one-pass `dC/dtheta` vs central FD,
  step 2e-6): worst column error 3.7e-6 ~ FD truncation, not an analytic
  defect; the production residual-level lock is < 1e-3 vs 3-point FD.
- Gallery rms annotations use the frozen `quality.rmsBp`; the pipeline
  recomputes SPY Dec rms from the rebuilt slice and gets the same 3.3 bp
  (`\MacSpyDecRecomputedRmsBp`).

## Macro reconciliation (REQUESTED_MACROS.md, 2026-08-03)

All author-contract names are now emitted (220 macros total; `macro_diff`
MISSING = `MacFallback` only, a paper-internal helper). New modules:
`figlib/aliases.py` (pure aliases + derivations, runs LAST),
`figlib/incidents.py` (cliff, fit/belly timings, rank-saturation fly,
phantom drag, optimum robustness), `figlib/multistart.py` (basin audit).
Canonical macros are untouched; aliases copy the stored value string so
the two names can never disagree.

**Flags the lead/author must see:**

1. **Lee-ratio direction VIOLATED on the put side** (contract says stop
   and tell the lead): `\MacLeeRatioTenDeltaPut` = `\MacLeeRatioOneDeltaPut`
   = **0.70 < 1** on SPY Dec — the left-wing effective slope approaches its
   Lee limit from BELOW. Call side is fine (1.69 / 1.05, from above). The
   section-6 sentence asserting "descends to the limit from above" is true
   only for the right wing on this node and must be rewritten.
2. **No latency cliff on the prescribed source.** On the frozen 17-quote
   NVDA 1d node: N=7/9/11 -> 14/15/9 evals, 25/25/30 ms (flat). Diagnostic
   probes at N=13/15 (ratios 0.82/0.94): still 10 evals, <40 ms. The
   historical cliff (0.47/0.58/0.68 -> 7/63/2568 evals) was an error-bar-
   saturated 19-quote 0DTE book; this clean book does not reproduce it.
   The Cliff* macros carry the flat measured values — the section-9
   "measured latency cliff" sentence cannot cite them as a cliff.
3. **Phantom drag reproduced with the shipped confinement-lock scenario**
   (near 13 quotes on +-0.06, w = 0.0008+0.6k^2, t=0.02; far 25 quotes on
   +-0.30, w = 0.010+0.004k^2, t=0.25; the far strip extends beyond the
   near span): worst far-quote error 10.6 bp (confined price floor) vs
   1095.0 bp (full-grid ledger floor) — the historical literals exactly.
   Metric is WORST quote error (the incident's own); rms equivalents are
   4.9 -> 502.1 bp.
4. **`\MacNvdaLamL/R`, `\MacNvdaBetaL/R` are computed from NVDA
   2027-12-17** (the figure-featured long node), but REQUESTED_MACROS
   glosses them as "NVDA Dec = 2026-12-18". Values differ materially
   (2027-12-17: lam 1.421/0.225; 2026-12-18: lam 0.755/0.146). If the
   text means NVDA Dec, say so and we re-point the alias.
5. **Ticket strike**: the worked ticket is the REAL listed SPY Dec 800
   call (k = +0.0409), not the contract's k = +0.05. All Ticket* macros
   (old and new names) price the same strike off the same slice.
6. `\MacFitMsOrderSixteen` = 42 ms measured on SPY Dec (94 quotes) per
   the lead's source decision; the section-12 sentence says "40-quote
   strip", whose measured number is `\MacTimingAnalyticMedNSixteen`
   (~29 ms). Pick one and phrase accordingly.
7. `\MacBellyCertMs` measures 1.5 ms via the public certificate call —
   30x the implementation brief's "~0.05 ms". Quote the macro.
8. `\MacCalWingPriceOrder` = 10^-26: the LARGER of the two calls at the
   audit strike (1.6e-26 F; the other is 5.4e-107 F). The data README's
   "~1e-20" was loose.
9. `\MacAuditPostFixFly` is exactly 0 (no violation at the audited
   stencil); the pre-fix violation is 1.9e-2.
10. Percent formatting: NEW contract macros that render with % carry
    `\%` in the body (TicketRankPct, SpyDecForwardRankPct); the OLDER
    canonical *Pct macros (SpyDecAtmVolPct, TicketIvPct, ...) do not —
    untouched per instruction. The text must not double-unit them.
11. **Multi-start audit: the claim HOLDS** — 10 randomized starts x
    {SPY Dec, NVDA 2027-12-17}, one basin per node (worst intra-cluster
    max|dtheta| 2.3e-6, max-IV-error spread 0.00 bp).

**Mutual-consistency confirmation** (author requirement): F5, F7, F8,
F9, F12, F14, the worked ticket, the ATM handles, the forward rank and
the Lee ratios all read the SAME SPY 2026-12-18 slice: nodes are built
once (`data._nodes()` is lru-cached) and `Node.slice` caches the single
`build_slice(params)` object every consumer shares. F12's sensitivity
pass rebuilds from the same frozen params (bit-identical pricing).

## Regeneration

```powershell
$env:VOLFIT_CALIB_WORKERS = '1'
.venv\Scripts\python.exe Papers\lqd_paper\scripts\gen_figures.py          # all
.venv\Scripts\python.exe Papers\lqd_paper\scripts\gen_figures.py --list   # targets
.venv\Scripts\python.exe Papers\lqd_paper\scripts\gen_figures.py --only fig_spy_node timing
```

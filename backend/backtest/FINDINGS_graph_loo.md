# Graph leave-one-out — findings (2026-06-26)

Temporal validation of the graph smile-extrapolator (`backtest/graph_loo.py`,
roadmap Phase 6) over the captured **spike_aug2024** regime (8 assets, 18
consecutive day pairs, 4134 scored held-out nodes, 0 pairs skipped). Method: freeze
T-1's surface as the active prior, transport under SSR R, propagate the lit
innovation `d = calibrated_T − transported_prior` through the directed graph, and
compare the held-out node's graph posterior with its ACTUAL day-T calibration —
versus the pure transported-prior baseline (the **skill**: does the graph beat the
mechanical spot-transport?). Lit calibration runs in mode `off` (pure market), so
the innovation is the genuine market-vs-prior move.

`atmGr/atmBs` = graph vs baseline ATM-vol residual RMS (bp); `atmSk` = skill (base −
graph, **positive ⇒ graph wins**); `wGr/wBs` = reconstructed full-smile wing RMS
(bp); ζ = standardized residual (well-specified ⇒ N(0,1)).

    design          R    n    atmGr   atmBs   atmSk    wGr     wBs    zMean   zStd
    full_loo        0  1497  277.0   314.1   +37.1    97.9   104.5   -0.01   0.90
    full_loo        1  1497  222.1   247.7   +25.6   112.6   115.2   -0.01   0.72
    liquid_split    0   570  369.3   369.3    +0.0   108.6   104.3   +0.00   1.16
    liquid_split    1   570  298.3   298.3    +0.0   128.2   121.1   -0.01   0.94

## Verdict

1. **The graph adds large, robust skill when a held-out node has lit neighbours
   (`full_loo`): +26 to +37 bp ATM, +3 to +7 bp wing.** This is the "fill a
   temporarily-missing / sparse node from its calendar + cross-asset neighbours" use
   case, and the graph clearly beats the transported prior. The uncertainty is
   well-calibrated: **ζ mean ≈ 0 (unbiased)** and ζ std 0.72–0.90 (slightly
   conservative). The win is driven mainly by the strong CALENDAR coupling.

2. **The SSR sweep brackets the skill, exactly as posed (Q1).** R=0
   (sticky-moneyness) leaves an underperformer's baseline vol unmoved → larger
   residual AND larger apparent skill (+37); R=1 (sticky-strike) pre-absorbs the
   leverage → smaller residual and smaller skill (+26). The genuine graph value sits
   **between +26 and +37 bp ATM**; both are reported rather than committing to one R.

3. **Cross-asset extrapolation to FULLY-dark names (`liquid_split`) adds ~nothing on
   this pilot — ATM skill ≈ 0, wing slightly negative.** Two compounding reasons,
   both measured:
   - the transported prior is already an excellent SAME-name predictor and enters at
     very high baseline precision (`[1e6,1e6,1e4]`), so a dark node stays glued to it;
     a single weak cross-asset index edge can't move it (verified: a 96 bp SPX
     innovation shifts the dark AAPL node by 0.01 bp);
   - the 8-asset pilot is **structurally starved** of cross-asset edges — no US sector
     ETF, and AAPL/NVDA/JPM share no sector, so the `name→name` and `SectorETF→name`
     edge classes are **dormant**. Only Index→name (one weak edge per name) + calendar
     (all dark in this design) are present.

   So this is **not a verdict against cross-asset extrapolation** — the experiment
   can't exercise it. Two concrete follow-ups would give it a fair test:
   - **the 25-asset capture** (same-sector name clusters: tech AAPL/MSFT, semis
     NVDA/AVGO, financials BRK.B/JPM/GS, … + real sector ETFs would light the dormant
     edges);
   - **a lower baseline precision for DARK nodes** in the production graph
     (`graph/precision.py`): a dark extrapolation target is inherently less certain
     than a lit observed prior, so its baseline should not pin the posterior — let the
     propagated signal express. (A production change; validate on the 25-asset data.)

**Net:** the graph extrapolator is empirically validated for neighbour-supported
nodes (large, well-calibrated skill) on the spike regime; the fully-dark cross-asset
case is inconclusive on the pilot and needs the 25-asset capture + a dark-node
precision revisit. Next: rerun across `high_oct2022` / `low_jul2023` for
regime-robustness, then the 25-asset capture.

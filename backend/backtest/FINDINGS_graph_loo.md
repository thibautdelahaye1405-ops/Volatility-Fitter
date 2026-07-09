# Graph leave-one-out — findings

## 2026-07-09 — full 25-asset benchmark pack (3 regimes)

The full benchmark pack (`backtest/benchmark_pack.py`, 46,995 scored rows:
25 assets × 19 day pairs × 3 regimes × {full_loo, liquid_split} × R∈{0,1};
artifact `results/benchmark/benchmark_report.html` + `.json`, generated
2026-07-09 01:09). This run had `DARK_BASE_SCALE = 0.25` active (the pilot's
dark-precision follow-up) and the full 25-asset edge set live: index→name
(β 0.7, w 2), same-sector name↔name (β 0.6, w 2), calendar (w 10). No US
sector ETF is captured, so ETF→name stays dormant (EEM/EFA are intl funds).

ATM skill (bp, base − graph, positive ⇒ graph wins), by design × regime:

    regime         design         R     n    atmGr   atmBs   atmSk   zMean  zStd
    high_oct2022   full_loo       0  4602    184.7   186.9   +2.15   -0.02  0.60
    high_oct2022   full_loo       1  4601    163.8   165.6   +1.79   -0.03  0.53
    high_oct2022   liquid_split   0  3674    200.9   200.9   +0.00   -0.02  0.64
    high_oct2022   liquid_split   1  3674    178.1   178.1   +0.00   -0.03  0.57
    low_jul2023    full_loo       0  4417    405.5   406.0   +0.52   -0.03  1.33
    low_jul2023    full_loo       1  4417    405.7   406.0   +0.34   -0.05  1.33
    low_jul2023    liquid_split   0  3536    452.3   452.3   +0.00   -0.04  1.48
    low_jul2023    liquid_split   1  3536    452.8   452.8   +0.00   -0.06  1.48
    spike_aug2024  full_loo       0  4049    424.2   431.1   +6.89   +0.02  0.95
    spike_aug2024  full_loo       1  4049    398.5   402.3   +3.81   -0.01  0.84
    spike_aug2024  liquid_split   0  3220    461.5   461.5   +0.00   +0.02  0.99
    spike_aug2024  liquid_split   1  3220    437.6   437.6   +0.00   -0.02  0.89

full_loo by asset kind (ATM skill bp, R=1 … R=0 bracket):

    kind     high_oct2022   low_jul2023   spike_aug2024
    index    +18.5 … +21.9  +10.5 … +16.6  +50.3 … +76.4
    etf       +4.8 …  +7.1   +3.3 …  +4.2   +4.5 …  +7.2
    name      +0.27 … +0.32  +0.14 … +0.14  +0.25 … +0.32

### Verdict

1. **Neighbour-supported skill is real and concentrates exactly where the
   graph has information: indexes (+11…+76 bp, largest in the spike regime)
   and ETFs (+3…+7 bp).** ζ mean ≈ 0 everywhere; bands conservative on
   indexes/ETFs (ζ std 0.16–0.41 per-kind).
2. **Single names get ~nothing even WITH calendar support (+0.1…+0.3 bp)**,
   and they dominate the row count (~80%), which is why the aggregate
   full_loo skill (+0.3…+6.9 bp) looks so much smaller than the pilot's
   headline (+26…+37 bp — an 8-asset, index/ETF-weighted composition, NOT
   name skill). Name base RMS is enormous (452 bp even in the LOW regime —
   earnings-dominated idiosyncratic moves), and the bands under-state it
   there (name ζ std 1.48 = overconfident in low_jul2023).
3. **The pilot's dark-name null REPLICATES at 25 assets: liquid_split ATM
   skill = 0.000 in all three regimes** (graph RMS = baseline RMS to 3
   decimals). Universe starvation was therefore NOT the cause — same-sector
   name↔name and index→name edges were live this time. **Root cause found
   2026-07-09 (topology bug in the HARNESS edge builder, not a market
   fact):** see the next section.

## 2026-07-09 — liquid_split root cause: one-way cross edges disconnect dark names

A sensitivity sweep (`DARK_BASE_SCALE` 0.25→0.001 × cross conductance ×1→×25,
spike regime, 4 day pairs) produced **exactly zero median dark shift in every
cell** — not damped, disconnected. Diagnosis on one solve (49 lit obs with
median +56 bp ATM innovation, 260 cross edges present in the graph):

- the directed kernel row of a dark AAPL node was healthy (SPX 0.417,
  MSFT 0.417, own calendar 0.083 each), **but the reversibilized conductance
  c_ij = f(π, K) was 0.0 on every edge touching a single name**;
- `backtest/graph_edges.build_directed_edges` emitted cross edges ONE-WAY
  (informer → name; "indices/ETFs receive calendar edges only"), so single
  names are TRANSIENT states of the directed walk: all their mass drains into
  the index/ETF calendar chains and none returns ⇒ stationary mass π = 0 on
  every name ⇒ conductance 0 ⇒ the increment prior fully decouples them.
  `DARK_BASE_SCALE` never mattered: no signal ever arrived. (The pilot's
  measured "96 bp SPX innovation moves dark AAPL 0.01 bp" was this same
  artifact — the baseline-precision explanation was a misdiagnosis.)
- the PRODUCT auto-lattice is unaffected (its cross edges are symmetric, so
  π > 0 everywhere — which is why in-app extrapolation demos propagate).

**Fix (`EdgeConfig.cross_reverse_frac`, default 1.0):** emit the reverse edge
(name informs its index/ETF informer) with the same weight and the INVERSE
beta — both directions then encode the same linear relation, so no second
economic claim is introduced; names become recurrent and their conductance is
nonzero. `cross_reverse_frac=0` reproduces the legacy disconnected topology
(locked in `tests/test_graph_loo_backtest.py`). Note: name↔name same-sector
edges were already bidirectional, but could not help — the whole name cluster
drained one-way into the index chains.

Consequence: **every liquid_split row in the benchmark pack (pilot + 25-asset)
was produced under the disconnected topology and is void as a test of
cross-asset extrapolation.** full_loo index/ETF results flow through calendar
edges within recurrent chains and stand.

### Post-fix sensitivity sweep (spike, 4 day pairs, 799 dark name-nodes/cell)

Grid: η ∈ {1, 10} × cross-conductance ×{1, 5, 25} × DARK_BASE_SCALE
∈ {0.25, 0.05, 0.01}, liquid_split, R ∈ {0, 1}. Headline rows (ATM, bp):

    eta  crossX  R    atmGraph  atmBase   skill   med|shift|   zMean  zStd
      1       1  0      657.9    658.0   +0.08        0.6      0.25  1.20
      1      25  0      657.2    658.0   +0.81        2.7      0.24  1.20
     10       1  0      657.3    658.0   +0.72        4.2      0.29  1.38
     10       5  0      655.0    658.0   +3.00       13.3      0.25  1.37
     10      25  0      653.0    658.0   +4.93       20.6      0.22  1.36
     10      25  1      642.3    644.0   +1.66        4.5      0.13  1.29

Findings:

1. **DARK_BASE_SCALE is a dead lever**: shifts and skill are IDENTICAL across
   0.25 / 0.05 / 0.01 (only ζ moves in the 2nd decimal via the band). The
   binding constraints are reach η and edge conductance — the baseline
   precision never was the bottleneck, post-fix or pre-fix.
2. **Dark-name skill is real but small once the topology is fixed: +1.7…+4.9
   bp (R-bracket) at the strongest tested cell (η 10 × cross ×25)**, monotone
   in both η and cross weight with no overshoot in the tested range.
3. **The ceiling is signal-to-noise, not plumbing**: single-name day-over-day
   ATM moves run ~650 bp RMS on these spike pairs while the propagated
   (β-scaled, damped) index innovation delivers ~20 bp median shift — the
   graph can only harvest the systematic sliver of a name's move. Bands are
   modestly overconfident on names (ζ std 1.2–1.4).

**Net:** cross-asset extrapolation to fully-dark names WORKS mechanically
after the reverse-edge fix and adds genuine-but-modest skill in stress; its
honest product claim is "keeps dark names marked and moving with the market,
with stated uncertainty" — not "predicts single-name vol". A benchmark-pack
resweep under the fixed topology (+ η at the LOO-tuned reach rather than the
default 1) is required before quoting any liquid_split number; the
`results/benchmark/` liquid_split rows must not be cited.

---

# Pilot findings (2026-06-26, 8 assets, spike only) — historical

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

# Graph leave-one-out — findings

## 2026-07-18 — item-14 adjudication PREPPED + verified end-to-end (still not a verdict)

Prepped the parked adjudication for the user's window. Done + verified here:

- **Artifact regenerated** (`learn_betas fit`) — matches the 2026-07-17 read
  exactly (index→name raw 0.22–0.49 shrunk 0.43–0.58; sector class raw 0.760
  n=756 t=32; calendar mult raw 0.338 n=12,062 t=44; ETF class rejected n<8 →
  prior). eval pair start {high 10, low 9, spike 9} → confirms `--pair-start 10`.
- **All three variants + the compare smoke-ran** on one OOS pair
  (spike, liquid_split, pair 10) to de-risk the multi-hour run. The **OT path
  (`--lambda 1.0`) executed for the first time ever without crashing.**
- **BUG FIXED — `benchmark_compare` crashed on the LAST step**: it prints
  ζ/—/− and a cp1252 Windows console UnicodeError'd *after* the sweep (the JSON
  verdict was still written, but the readable table was lost to a traceback).
  Now forces `sys.stdout.reconfigure("utf-8")`. Would have bitten the user at
  the finish line.
- **`--max-pairs` TRAP** (documented in the runbook): it caps the TOTAL pair
  count, so `--max-pairs 1 --pair-start 10` scores an EMPTY range and silently
  no-ops. The real runbook uses `--pair-start 10` alone — do not add
  `--max-pairs`.
- **Runbook shipped**: `backtest/run_b14_adjudication.ps1` (regenerate artifact
  → 3 tagged sweeps → verdict table), pre-registered decision rule inline.

**One-pair PREVIEW (spike/liquid_split/pair 10 — NOT the verdict; the rule
needs all 3 regimes × pairs 10–18):** learned betas skill +0.159 vs +0.092
baseline (**Δ +0.067**), ζ std 0.63 (stable) → *leans activate*. OT λ=1.0 skill
+0.008 (**Δ −0.084**, worse) with ζ std blowing out to **1.127** (overconfident)
→ *leans reposition-as-Bayesian-graph-propagation*, consistent with the deck
honesty pass. The full sweep decides.

## 2026-07-17 — learned shrunk betas: machinery + first estimation read (R3 item 14)

Machinery shipped (`backtest/learn_betas.py` + `EdgeConfig.overrides` +
`benchmark_pack --beta-table/--lambda/--nu/--pair-start` + `benchmark_compare`);
the ADJUDICATION SWEEP HAS NOT RUN YET — nothing below is a production verdict.

**Estimator design.** Ticker-day ATM innovations reconstructed from the stored
benchmark rows (`-base_atm`, knob-independent so all sweeps pool), median across
each ticker's scored expiries; vol-normalized by a fit-free per-(regime, ticker)
ATM scale read from the first estimation day's fixtures. STRICT TIME-SPLIT:
regressions see only the first half of each regime's day pairs (evalPairStart =
{high 10, low 9, spike 9} → evaluate with `--pair-start 10`, strictly disjoint
everywhere). Through-origin OLS, DELIBERATELY predictive (the graph predicts the
influenced node FROM the observed informer innovation, so the conditional-
expectation slope — attenuation included — is the decision-relevant beta; a
noise-corrected structural beta would over-propagate). Hard shrinkage
(K = 20 equivalent obs) toward the hand-set priors; auto-reject (n < 8, |t| < 2,
sign flip) reverts a cell to its prior EXACTLY. Locked in
`tests/test_learn_betas.py` (planted-beta recovery through the normalization,
poisoned-eval-window leak test, reject rules, override→edge path,
empty-overrides byte-identity).

**First estimation read (split 0.5, ssr 0, artifact
`results/learned_betas.json`):**

- index→name, per name: raw 0.22–0.49 (every t ≥ 2.6), shrunk 0.43–0.58 — the
  hand-set 0.7 looks predictively HIGH at the daily innovation horizon; defensive
  names (WMT/COST/CVX) read tighter t's than high-idio ones (META/NFLX/TSLA).
- name↔name same sector: raw 0.76 (n = 756, t = 32) vs prior 0.6 — sector peers
  carry MORE cross-information than assumed.
- sector-ETF→name: dormant as designed (no US sector ETF captured) — prior kept,
  named reason.
- calendar multiplier on √(T ratio): raw 0.34 (n = 12,062, t = 44, both
  directions pooled) — daily ATM innovations are far LESS calendar-coherent than
  the √T rule assumes; if the ablation confirms, the calendar β rule
  over-propagates along the ladder by ~3×.

**Adjudication runbook (user's window, ~half a normal pack sweep — 10 of 19
pairs; each variant its own tag):**

    # baseline, evaluation half only
    python -m backtest.benchmark_pack run --pair-start 10 --tag _b14_base
    # learned betas, same window
    python -m backtest.benchmark_pack run --pair-start 10 --tag _b14_learned `
        --beta-table backtest\results\learned_betas.json
    # OT ablation (lambda comparable to the kappa belief strength)
    python -m backtest.benchmark_pack run --pair-start 10 --tag _b14_ot --lambda 1.0
    # verdict table (skill deltas vs baseline on the SHARED scored set)
    python -m backtest.benchmark_compare --tags _b14_base,_b14_learned,_b14_ot

Decision rule (pre-registered): activate learned betas only if the liquid_split
dark-name ATM skill delta is positive in spike AND non-negative in the other two
regimes with ζ std not degrading; otherwise the artifact stays a diagnostic.
Same bar for OT (λ=1.0 probe) — else reposition the OT story as Bayesian graph
propagation (the deck honesty pass already leans that way).

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
with stated uncertainty" — not "predicts single-name vol". The void
liquid_split rows were STRIPPED from the `results/benchmark/` parts
(originals archived in `void_liquid_pre_topofix/`) and the full liquid_split
benchmark was RE-RUN under the fixed topology.

## 2026-07-09 — liquid_split resweep (fixed topology, η 10 × cross ×25)

Full 3-regime resweep (user's window; parts `*_topofix_eta10.json`; command:
`-m backtest.benchmark_pack run --designs liquid_split --eta 10
--cross-mult 25 --tag _topofix_eta10`, then `report`). η 10 / cross ×25 were
TUNED ON SPIKE (the sensitivity sweep's strongest cell); high_oct2022 and
low_jul2023 are therefore out-of-sample for the knob choice. Dark single
names only, ~3.4–3.7k scores per regime × R:

    regime         R    n     atmGr   atmBs    atmSk   med|shift|  zMean   zStd
    spike_aug2024  0  3419    489.5   503.7   +14.15      10.4    -0.01   1.10
    spike_aug2024  1  3419    475.5   483.5    +7.91       2.8    -0.06   1.02
    high_oct2022   0  3674    193.6   200.9    +7.24       5.5    -0.02   0.78
    high_oct2022   1  3674    174.3   178.1    +3.82       3.9    -0.03   0.70
    low_jul2023    0  3536    451.6   452.3    +0.67       4.2    -0.04   1.91
    low_jul2023    1  3536    452.0   452.8    +0.78       3.4    -0.06   1.85

### Final verdict on cross-asset extrapolation to fully-dark names

1. **Real, quotable skill in stressed regimes**: +7.9…+14.2 bp on the spike
   (in-sample for the knobs, but the skill is 3× the sensitivity-sweep
   preview once the crash/snapback days enter) and **+3.8…+7.2 bp
   out-of-sample on high_oct2022**, with unbiased, honest-to-conservative
   bands (ζ std 0.70–1.10).
2. **~Nothing in the calm regime** (+0.7 bp on low_jul2023): single-name
   moves there are earnings/idiosyncratic, the systematic component the graph
   can carry is negligible — and the bands are markedly OVERCONFIDENT there
   (ζ std ~1.9). Skill is never negative in any cell: propagation never
   hurts, it just can't manufacture idiosyncratic information.
3. **Follow-up (band honesty in calm tape):** dark-name posterior uncertainty
   should widen when the name's own regime is idiosyncratic (e.g. an
   event/earnings-aware term in the dark baseline precision, or a per-kind ζ
   recalibration) — ζ std 1.9 in low_jul2023 is the one dishonest cell in
   the pack.

**Product framing this supports:** graph propagation to fully-dark names
earns its keep exactly when the desk needs it — when the market reprices
together — adding up to ~14 bp of ATM accuracy over mechanical transport in
stress, never subtracting in calm; uncertainty is honest in stress and needs
an idiosyncratic-regime widening in calm tape.

## 2026-07-10 — idio band floor closes the calm-regime overconfidence (SHIPPED)

The follow-up above is implemented as a **band floor from the node's own
trailing unexplained move** (`volfit/graph/idio.py`, wired into the shared
`solve()` so production, the in-app LOO and this harness all exercise it):

    sd_atm'^2 = max(sd_atm^2, 0.30 * sigma_I^2)

`sigma_I` = shrunk EWMA-RMS (half-life 5 trading days, shrink k=4 toward the
cross-sectional pool) of the ticker's past ATM innovations vs the transported
prior, pooled across expiries, STRICTLY causal (cold start ⇒ no floor ⇒
byte-identical legacy field). Key mechanics: a dark node's baseline precision
enters ONLY its band variance (never the posterior mean — `posterior.py`'s
`1/p0` term is absent from the mean's observed columns), so the floor is
mean-invariant by construction; production records lit-node innovations at
every solve (`AppState.record_graph_innovations`, persisted) and floors a
node from the days it was lit; the harness accumulates the same quantity
across day pairs (`graph_loo._idio_sigma_map`), with `benchmark_pack` seeding
each chunk from earlier same-tag parts so chunked runs match a single process.

**Design + validation were OFFLINE on the stored rows** (band-only ⇒ stored
residuals stay exact; `zeta' = -res_atm / sqrt(var' + 1/r)` with `1/r`
recovered from the stored `zeta`/`sd`/`res_atm`). Sweep over rule ∈
{additive, floor} × λ ∈ {0.25…1.0} × half-life {3, 5, flat}: additive
widening degrades the honest stress cells; the floor at λ=0.30 is surgical.
Shipped-estimator replay on the resweep parts (dark names, η10×cross25):

    regime         R    zStd before -> after   floor binds
    low_jul2023    0        1.91 -> 1.02          12.5%
    low_jul2023    1        1.85 -> 1.03          12.9%
    spike_aug2024  0        1.10 -> 0.99          26.2%
    spike_aug2024  1        1.02 -> 0.94          18.7%
    high_oct2022   0        0.78 -> 0.77           0.8%
    high_oct2022   1        0.70 -> 0.70           0.8%

ζ means stay unbiased (drift ≤ 0.06). full_loo cells improve the same way
(low-regime names 1.48 → 0.87). The floor **self-gates across asset kinds**
(index/ETF trailing innovations are small, so their already-conservative
bands are essentially untouched, binds ≈ 0%) — no asset taxonomy or regime
input needed, which is what makes it production-clean. Posterior means and
ATM skill are UNCHANGED everywhere by construction; `GraphExtrapolateRequest.
idioFloor=false` restores legacy bands exactly. Contracts locked in
`tests/test_graph_idio.py` (11 tests). Follow-up: skew/curvature band
widening rides the full handle-covariance work (roadmap R3).

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

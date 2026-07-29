# Pitfalls and adjudications — every production bug and every measured verdict

**Companion to `VOL_FITTER_CLEAN_ROOM_REBUILD.md`. Two kinds of hard-won
knowledge: (1) the named certification cases — real production failures, each
now a frozen regression test in the reference implementation; (2) adjudicated
experiments — pre-registered benchmarks whose verdicts set today's defaults.
The rebuild should reproduce the *cases* as tests and inherit the *verdicts*
as defaults unless a new pre-registered benchmark overturns them.**

---

## 1. Certification cases (the named failures)

### Market regimes (the benchmark must keep passing)

| Case | What must hold |
|---|---|
| **Aug-2024 vol spike** (yen-carry unwind) | Dark-name graph propagation adds skill (+7.9…+14.2 bp ATM over mechanical prior transport) with honest bands (standardized-residual std ≈ 1 after the idiosyncratic floor). |
| **Oct-2022 bear-market lows** | Out-of-sample regime for graph knobs tuned on the spike: skill stays positive (+3.8…+7.2 bp), bands conservative-to-honest. |
| **Jul-2023 calm tape** (earnings-idiosyncratic) | Propagation must never hurt (skill ≥ 0); the idio band floor keeps dark bands honest (ζ std 1.91 → ~1.0). |

### Data failures

1. **Zero-carry synthesized chains.** A delayed-tier provider synthesized
   chains at F = spot with zero spreads; parity regression then produced
   garbage forwards (recurring index breakage). Fix: detect and **pin
   F = spot, D = 1** rather than regressing invented carry; the pin persists
   with the snapshot. Legitimate zero-spread EOD closes still resolve sane
   forwards.
2. **Duplicate strikes across listings** divided the de-Americanization anchor
   slope by zero and killed whole capture days. The core slope uses the
   nearest *strictly distinct* strike; clean chains byte-identical.
3. **Few-tick OTM quotes.** Deep-OTM quotes worth a couple of ticks carry no
   vol information and whipsawed wings. Real-feed chains screen them (3-tick
   OTM floor **tested against the bid**), and tick size persists with the
   snapshot schema.
4. **Stale / crossed wing pairs** dragged the parity regression: an outlier
   filter drops the pair; a discount clamp keeps the forward sane even when
   wings break.
5. **Delayed / idle feed.** A perfect fit of yesterday's book is still
   yesterday's book: red-stale chain age fails publish-readiness; amber only
   warns.

### Model stress

6. **SVI Lee cap exactly at the broken boundary.** A slice sitting AT Lee's
   bound (wing slope 2.0) passes floor and wing screens with ZERO penalty yet
   carries negative tail density (counterexample: g(10) = −0.0485 with min
   variance 0.44). The trap was live: a real index expiry sat at wing 2.0000;
   the buffered refit moved IV by 0.03 bp. Default cap now **1.95**; 2.0 only
   as explicit configuration.
7. **Uncertified belly cannot become a mark.** Cheap screens fence only the
   wings: Axel Vogt's classical slice passes them yet has negative belly
   density (min g ≈ −0.033). An independent dense-grid belly certificate
   (801 points on the traded range, model derivatives, ~0.05 ms) fails
   readiness and hard-blocks publish (409); a failed certificate triggers ONE
   belly-hinge repair refit, kept only if it certifies; the publish-time wing
   projection is audited to introduce no calendar crossings.
8. **SVI adversarial battery.** Every hostile input either fits to a finite,
   fence-respecting slice or refuses with a typed reason: 1–2-quote boards
   refuse deterministically (no solver crash), one-sided chains, missing ATM,
   0DTE-scale variance, |ρ|≈1, duplicate strikes, 50% quote noise, crossed
   bands, evaluation-cap exhaustion — on BOTH charts. The guarded JW→raw map
   replaces case-dependent NaNs with structured domain-error reasons.
9. **True-weekly LV resolution.** A 1-week expiry fitted 108 bp RMS at default
   grids because the shared strike axis put only 3 vertices in its traded
   range; per-expiry coverage floor + short-expiry PDE refinement → ~24 bp
   with normal surfaces byte-identical.
10. **In-operator LV RMS hides operator error.** The optimizer bends the
    parameter to cancel PDE time-discretization error: in-operator RMS reads
    ~0 while a converged reprice shows the real error (weekly: 11 vs 46 bp).
    Quality metrics must reprice on a refined operator.
11. **Convex-wing fighting dense quotes.** The convex-wing constraint on a
    fine grid fought dense index quotes (26 bp regression); its authority is
    confined to the unquoted extrapolation tail.
12. **Phantom calendar violations in the wings.** A fixed wide floor grid let
    SVI's linear wings manufacture violations that flattened far-expiry fits.
    Calendar comparison is confined to the traded range; the no-floor path is
    byte-identical.
13. **Acute short expiry vs the calendar ladder.** A front-to-back calendar
    floor compared slices on a tail-dense quantile grid, so one acutely convex
    short-dated slice dragged every later wing off its quotes (far fit:
    10.6 bp free, 1095 bp under the full-grid floor, 10.6 bp confined).
    Confinement must live in **price space at fixed strike** (the quantile-
    domain ledger integrates the whole upper tail; a windowed floor removes
    only half the drag). The symmetric solver fits expiries independently,
    screens *identified* violations on common quote support, and jointly
    repairs only violating runs — clean ladders are exactly their independent
    fits.
14. **De-Americanization repair authority.** Extending a price-moving convex
    repair beyond the data turned a 27% put wing into 104% and gapped live ATM
    smiles (a shipped fix had to be reverted). The repair keeps its authority
    confined to the wing defect it exists for; clean chains are a no-op.
15. **Extrapolated-region contracts.** Beyond the last quote the surface is a
    stated contract: measurement is always on (advisory), enforcement is
    opt-in and tapered (clean pair = exact no-op), and published wings are
    projected onto the discrete arb-free set with the traded core pinned.
16. **One-way cross edges strand dark names.** Directed informer→name edges
    made single names transient in the diffusion sense (stationary mass 0 →
    conductance 0): dark names silently decoupled and the harness reported
    zero skill. Reverse edges with inverse beta restore recurrence.
17. **Dark-name band honesty.** Calm-tape dark bands understated realized
    moves ~1.9×; an idiosyncratic floor lifts a non-observed node's band to
    ~0.55× its own trailing innovation RMS — strictly causal, mean-invariant,
    cold-start silent.
18. **0DTE exit gates.** On real captured 0DTE NBBO (862 quotes, 12:30 ET):
    the same-day node prices sub-day (t = 3.5 h, never an unrepresentable 0),
    replays bitwise across fresh states, a publish set with unresolved
    intrinsic or calendar inconsistency fails hard (409) before any manifest
    persists, and a warm 0DTE slice refit stays inside the 50 ms design
    target (~20 ms measured).
19. **Precision-message graph goldens.** The full acceptance contract of the
    message operator — full transmission, competing signals, dead-informer
    zero dilution, baseline-uncertainty-enters-once, cycle diagnostics — is
    locked three times over: against an independent brute-force Gaussian
    reference, through the production assembly, and through the HTTP API;
    smooth-field stays byte-identical at defaults; the layered pipeline
    replays its async A/B exit gate; the config lifecycle round-trips.

### Additional latent bugs found by construction (worth testing from day one)

- **Float-boundary chart bugs:** ρ rounding to ±1 → σ = 0 / m = NaN; a
  logistic map rounding to exactly 1 → wing == cap. Fix: interior-one clipping
  and an exactly-stable wing-geometry denominator.
- **LQD far-wing expit overflow** and a beyond-grid asymptote error in the
  quantile chart (fixed during committee review).
- **Wall-clock observation age in replay:** intraday replay observations were
  never "certified fresh" because age was computed on the wall clock, not the
  replay clock. Any freshness gate must read the *scenario* clock.
- **Dense per-step LV basis tensors** can OOM on big grids: a memory budget
  with a sparse store + compiled scatter is required.
- **Bulk text edits via shell pipelines corrupt UTF-8** on Windows
  (mojibake); edit files with proper tooling only.

---

## 2. Adjudicated experiments (why the defaults are what they are)

These were run as pre-registered benchmarks — gates written down before the
data was looked at. Record the verdicts; do not silently relitigate them.

1. **SVI structural chart flip (ratified).** Two rounds, gates pre-registered.
   Round 2 held on one gate — the raw chart's lower headline arbitrage rate —
   which was then **proven a survivorship artifact**: raw's converged fits had
   *worse* arb (1.076% vs 0.864%) and the headline was diluted by 9,472
   exhausted fits (33% of the arm) that never converged. Structural won all 12
   precision medians, had zero breaks, and ran ~3× faster. Default flipped to
   structural; raw kept as rollback. *Lesson: an aggregate metric over a
   mixed-convergence population can invert the truth — always split by
   convergence status.*
2. **Analytic structural Jacobian.** The 5×5 chain-rule Jacobian made
   identical smiles 2.1–2.4× faster and, in building it, exposed the two
   float-boundary chart bugs above. *Lesson: writing the analytic derivative
   is also an audit of the chart.*
3. **Message-mode default flip (user-ratified).** The *daily*-granularity
   benchmark failed its gates for messages (bands too narrow at the daily
   horizon among others), but intraday async replay separated the modes
   decisively: messages 65.8 bp vs transported prior 172.7 bp, with the
   legacy smooth-field operator nearly inert (168.6). The Options default
   became precision messages at desk amplitude; smooth-field remains the wire
   default and rollback. *Lesson: choose the measurement horizon that matches
   the product's actual use.*
4. **Layered dynamic-harmonic mode: HOLD (twice).**
   - *Daily campaign:* residual memory was **negative** at the 1-day horizon —
     error monotone in half-life, optimum H→0 (hl1 285 vs memoryless 280 vs
     base 279 bp); layered had a spatial edge in stressed regimes (−9/−15 bp)
     but calm-tape cost, a wing regression (ATM betas broadcast to
     skew/curvature is the suspect), and overdispersed bands (ζ 1.7).
   - *Intraday campaign:* the residual **mechanism validated** — interior
     optimum half-life ≈ 0.1 day (73.7 bp vs 80.6 memoryless vs 108.1 with
     infinite persistence; OU persistence decays 18.1 → 2.5 bp; ζ 0.80) — but
     the layered *carrier* still lost to static messages (65.8 bp): the
     spatial operator, not memory, is the bottleneck; residual value lives
     inside the session and is gone by the next day.
   - Verdict: layered stays opt-in; **never default to infinite residual
     persistence** ("desk mode" was the worst arm at 108.1 bp).
5. **Campaign-invalidation bug (methodological).** The first daily campaign
   was invalidated because a harness change silently altered the residual
   store's structural config hash, purging state every pair — all four arms
   became byte-identical without erroring. Fix: a caller-owned stable
   *residual config version*. *Lesson: ablation arms must PROVE they differ
   (assert arm divergence), and state-store identity must be explicit, not
   derived from incidental config hashes.*
6. **Learned graph betas + optimal transport: HOLD.** A ~14-hour sweep
   (23,758 out-of-sample rows): learned betas met the liquidity-split rule but
   gained only fractions of a bp and regressed the full-LOO metric; the OT
   term at λ = 1.0 showed negative skill with blown uncertainty calibration
   (ζ 1.3–2.6). Verdict: no production change; learned betas stay diagnostic;
   OT available but weight 0.
7. **Observation-filter process noise.** The design note's 10 bp/√day was
   one-sidedly wrong on a 3-regime backtest: at 30 bp/√day the posterior is
   calibrated (ζ std 0.8–1.9 vs 1.3–6.2) and shock lag drops 3–8×. The
   session clock (share 0.60, non-trading weight 0.0) was needed because no
   calendar-clock q can simultaneously calibrate a 30-minute step (19.5 bp),
   an overnight (55 bp), and a weekend (also 55 bp).
8. **LV performance levers — measured accept/reject.** Accepted: compiled
   Thomas march (~6×), matrix-free GN (1.3–1.65×, smooth mid target only),
   early stop (1.45–3.3×), delta grid, warm starts. Rejected: Rannacher/CN
   time stepping (only ~1.1× net AND not monotone — an arb violation appeared
   on a coarse grid), thread parallelism inside a fit, coarse calibration
   grids (quality), cutting the American-tree depth below 192 steps. *Lesson:
   benchmark on real chains, never accept a synthetic-only speedup, and never
   trade monotonicity for speed.*
9. **Joint borrow/de-Am identifiability.** The fixed point converges (planted
   300 bp borrow recovered at 299.8 bp) but: a flat rate curve biases borrow
   estimates 1:1 (a rate *curve* is required for unbiased borrow), and
   held-out validation on thin boards is inconclusive below noise. Hence the
   materiality gate (engage per expiry only at ≥25 bp converged borrow) and
   off-by-default.
10. **Calendar repair economics.** In a sequential pass the later expiry
    always pays for a violation; the symmetric solver splits the correction by
    quote information. "ATM monotonicity certifies the calendar" is false —
    full convex order on common support is the test.
11. **Prior persistence must not damp real jumps.** Persist *shape*, not
    market *level*: a true overnight ATM jump must pass through untouched
    (locked as a golden); the activation gate turns a prior row exactly off
    when live quotes identify the feature.
12. **Graph validation discipline.** Dark-node quotes never influence the
    solve (they score it afterwards); holdout/what-if solves never write
    state (the store update is split from the read path); replay clocks are
    scenario clocks. Each of these was a real bug class once.

---

## 3. Environment traps (development-machine class)

Not portable facts, but the *categories* recur in any environment:

- Package-index flakiness → configure retries; don't debug phantom failures.
- LaTeX/tooling assumptions (a build tool missing a dependency silently using
  stale artifacts) → always build twice / verify outputs fresh.
- Port hygiene: check who owns a dev port before killing or smoke-testing
  against it; long-running background jobs from tool sessions get killed —
  run multi-hour campaigns in a user-owned window/session.
- Perf rails need a quiet box; CI ceilings should be ratios against a stored
  baseline, not absolute times.

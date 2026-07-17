# Vol-Fitter — Development Roadmap

Implied-volatility fitter (à la VolaDynamics) with a differentiating feature:
**extrapolation of sparse smile observations to the full universe of smiles**
(across expiries and assets) by propagating signal through a graph whose nodes
are smiles `(underlying, T)`, using the OT-regularized Bayesian solver of
`Docs/ot_bayesian_graph_extrapolation_expanded.tex`.

---

## FORWARD ROADMAP v2 — adopted 2026-07-10 (hosted-product arc)

User-ratified plan (strategy session 2026-07-10). Guiding constraint, applied
to ourselves first: **no new sophistication without calibrated uncertainty,
replayable lineage, and a benchmark showing it adds value.** Work down the
releases in order; within a release, items are independent unless noted.

### Strategic decisions (settled 2026-07-10 — do not re-litigate)

- **Deployment model: hosted multi-user product**, reached via single-tenant
  instances first (one container per client desk; own state + DB; dodges the
  AppState multi-tenancy rewrite; SQLite stays viable for v1). This CLOSES the
  "Phase 2 deployment-model decision" that earlier STATUS entries left open.
- **Data rights: bring-your-own-entitlement ASSUMED (user, 2026-07-10)** —
  the client's instance connects with THEIR feed credentials (provider
  registry already supports this); we ship computation + surfaces + lineage,
  not market data. Redistribution talks PARKED; revisit only if BYO fails
  commercially with a design partner.
- **0DTE ambition: research/replay grade v1** (flat-file intraday capture +
  deterministic replay; SPY/QQQ/IWM, no index-feed or realtime spend). Live
  0DTE is a post-hosting, client-entitled feature.
- **Borrow: option-implied (tier 2) is the best available input** — the
  identifiability diagnostic is the CORE object; "unidentified" is the common
  state for single names and the UX must present it calmly. Publish blocking
  only on (material American correction × unidentified carry).
- **Governance audience: prospective-client due diligence** — replay bar is
  "documented tolerance", not bit-exactness; certification/ζ/replay artifacts
  are sales collateral and should emit client-facing reports.

### R0 — Honest measurement + certification pack  ← CURRENT

1. **Calm-regime dark-name band widening** (the ζ std ~1.9 overconfident cell
   in low_jul2023): event/earnings-aware dark baseline uncertainty, then ζ
   calibration conditioned on regime / asset type / liquidity / earnings
   proximity. Must NOT degrade spike-regime honesty (ζ 1.02–1.10).
2. **LV quality on converged-operator reprices** — quality-tab LV rmsBp shares
   the in-operator blindness found in the short-dated diagnosis; judge LV on
   reprices from the converged operator.
3. **Extrapolated-arb Phase 3** — publish-time wing-only projection (core
   pinned), so hard publish gates have teeth.
4. **Stress/certification pack v0** — freeze the 3 captured regimes + every
   named historical bug (liquid_split one-way edges, zero-carry synthesis,
   convex-wing×fine-grid 26bp, fig_siv_g arb target, R3 ATM gap, React-#300
   smoke catch, …) into a regenerable matrix: market regimes × data failures ×
   model stress. Quality publish gate consumes the SAME case definitions.
   Emits a client-facing certification report (deck-tooling precedent).
   Fold in dangling follow-ups: 25-asset capture reruns, deck slide-7 refresh.

### R1 — Foundations, multi-tenant-ready by design

5. **Exact timestamp/settlement semantics** (schema bump — valuation, last
   trading, exercise, settlement times; AM/PM, holidays, half-days). Do BEFORE
   more captures accumulate day-granular maturities.
6. **Short-dated quote preparation**: price/bid-ask-space residuals as the
   authoritative object near zero vega, explicit intrinsic tolerance,
   vega-floor incidence diagnostics, quarantine (not unstable IVs). NOT
   0DTE-specific — validate on tests/fixtures/lv_weekly_massive.json first.
7. **CarryCurve v0**: versioned {discount, dividends, borrow} with per-
   component source tags (observed/desk/parity-implied/prior), identifiability
   diagnostics, explicit "unidentified" state, publish block. No joint solve
   yet.
8. **Governance kernel**: SurfaceManifest (hash-chained parents, dedupe,
   retention policy), append-only event log (actor field, constant "desk" for
   now), lifecycle state machine (Captured→Prepared→Calibrated→Reviewed→
   Published; →Rejected; Published→Superseded/Recalled), one-command
   replay-to-tolerance report.
9. ~~**State-scoping refactor**: AppState → serializable workspace object.
   Prerequisite for hosting, replay, AND durable filter state. Land it early
   and ALONE — it can silently break byte-identical conventions the suite
   locks.~~ DONE 2026-07-11 (see STATUS) — R1 COMPLETE.

**Hosting track (parallel, decision-first):** provider redistribution terms vs
BYO-entitlement (start now); single-tenant container packaging spike (the
desktop-exe single-origin refactor is a head start); auth deferred to R4.

### R2 — Robustness release

10. ~~**0DTE v1 (research grade)**: intraday variance clock; intraday capture
    campaign; absolute-timestamp calendar constraints; temporal-filter
    tuning; fast degraded mode. Exit gates FROM the stress pack: no NaN on
    valid quotes, deterministic replay, hard publish failure on unresolved
    intrinsic/calendar inconsistency, sub-50ms warm slice, price/band-space
    quality, next-snapshot held-out.~~ **COMPLETE 2026-07-16** (see STATUS
    2026-07-15/16: REST campaign 312 snapshots + sweep 0 failures; session
    filter clock; settlement-instant ordering; degraded mode v1; the
    certification case `0dte_exit_gates` locks the acceptance bar).
    Residual follow-ups, not gates: per-maturity filter handle scales,
    degraded-v2 uncertainty band, live-universe 0DTE seeding decision,
    same-date AM/PM expiry-key redesign (rides index-root onboarding).
11. **Joint borrow/de-Am fixed point** (borrow/divs → de-Am → parity forward →
    updated borrow, iterate): discrete dividends consistent in both legs,
    isolated maturity specials allowed, IV-sensitivity to borrow uncertainty,
    trader carry view (implied borrow, parity residuals, EEP, confidence by
    expiry). Exit gates: held-out parity error improves vs implicit forward;
    known HTB names recover stably; tree-inversion/joint-solve failure rates
    explicit; ordinary names byte-identical (test-locked from day one).

### R3 — Moat release

12. **Functional posterior for parametric slices**: propagate 3-handle joint
    covariance (delta-method on the slice map) → full smile credible bands,
    density/tail-mass bands, var-swap uncertainty, extrapolated-calendar
    confidence. LV-surface uncertainty CUT from v1 (expensive outlier).
13. **Active observation selection** (pulled forward from the draft's phase 5
    — closed-form on graph/precision.py, rank-one/Schur, no refit): "which
    dark node to quote next for max posterior-variance reduction", optionally
    exposure-weighted. Prospect-demo centerpiece. Prereq: item 1 (calibrated
    bands), else recommendations mislead.
14. **Learned shrunk betas** as a benchmark-adjudicated ablation (index↔ETF,
    ETF↔constituents, sector peers, calendar-within-underlying; shrink hard —
    3 regimes × 25 assets is thin; strict time-split; auto-reject unstable/
    sign-flipping edges; every edge editable + versioned). Plus the **OT
    ablation decision**: demonstrate repeatable incremental value and activate,
    or reposition as Bayesian graph propagation (deck honesty pass already
    leans that way). Expect a modest delta over β=1 — let the pack decide.

### R4 — State release + first hosted deployment

15. **Graph-coupled temporal state**: durable filter state (rides the R1
    workspace object), adaptive-Q shock handling in active MAP, then one
    sparse update combining temporal prediction + graph precision. Overlay
    ONLY, benchmarked vs raw fit / single-node Kalman / static graph
    posterior / transported prior, with PRE-REGISTERED kill criteria. Goal:
    separate systematic repricing / idio moves / observation noise / missing
    information — not smoother surfaces.
16. **First single-tenant hosted instance** with a design-partner desk —
    forces auth, live actor field in the event log, and the enterprise slice
    of model/config governance (registry: model+version, approved scope,
    limitations, default rationale, validation-pack version, perf budget,
    change→which-certifications-rerun) driven by a real user.

### Named risks

- **Data rights have the longest fuse** — if BYO-entitlement fails
  commercially, R4's shape changes; get the answer during R0/R1.
- **State-scoping refactor** can silently break byte-identical test locks —
  isolate it.
- **Manifest volume at intraday cadence** — hash-chain + parent dedupe +
  retention policy or SQLite eats the disk.
- **Gate false positives kill the story** — "refuses to publish what it can't
  defend" only sells if gates rarely cry wolf; hence R0 first.

---

## STATUS — updated 2026-07-11 (resume here)

### 🧭 SESSION WRAP (2026-07-10) — ROADMAP v2 ADOPTED + R0 ITEMS 1-2 SHIPPED

- **FORWARD ROADMAP v2 adopted** (section above; commit `4256dc4`): R0 honest
  measurement → R1 multi-tenant-ready foundations → R2 0DTE/borrow robustness
  → R3 moat → R4 state + first hosted instance. Settles the deployment model
  (hosted, single-tenant instances first, BYO data entitlement) — the old
  "Phase 2 deployment-model decision" is CLOSED.
- **R0 item 1 SHIPPED — idio band floor** (the calm-regime dark-name ζ std
  ~1.9 overconfidence, the pack's one dishonest cell): new
  `volfit/graph/idio.py` — a non-observed node's ATM band std is floored at
  `sqrt(0.30) ×` the ticker's trailing innovation RMS (shrunk EWMA, half-life
  5d, strictly causal, cold-start silent). Wired into the shared
  `graph_extrapolation.solve()` (production + in-app LOO + benchmark all
  exercise it); production records lit innovations per solve
  (`AppState.record_graph_innovations`, persisted `graph_idio_history`);
  `graph_loo` accumulates the same across day pairs; `benchmark_pack` seeds
  chunks from earlier same-tag parts. **Design + validation offline on the
  47,393 stored benchmark rows** (band-only ⇒ stored residuals exact):
  low_jul2023 ζ std 1.91→1.02 / 1.85→1.03, spike 1.10→0.99 / 1.02→0.94,
  high_oct2022 untouched (0.8% binds); means/skill unchanged by construction;
  self-gates across kinds (no taxonomy needed). Full numbers + method in
  `backend/backtest/FINDINGS_graph_loo.md` (2026-07-10 section). Escape
  hatch: `GraphExtrapolateRequest.idioFloor=false` = legacy bands exactly.
  11 new tests (`test_graph_idio.py`).
- **R0 item 2 SHIPPED — converged-operator LV quality metric.** New
  `volfit/models/localvol/reprice.py`: a value-only implicit-Euler march that
  mirrors `solve_affine_dupire`'s numerics bit-for-bit (test-locked) but
  evaluates `surface.variance` per step (O(n_x) memory), so the calibrated
  surface is repriced ONCE on a refined operator (every calibration time step
  ÷4, strike step ÷2) at fit-commit. Rides the response as
  `rmsConvergedBp`/`maxConvergedBp` (+ per-expiry `AffineSmile.
  rmsConvergedBp`), into `LvQuality.rmsConvergedBp`, the QualityViewer LV
  cell (converged rms is the headline; `op-err` flag when it dwarfs the
  in-operator rms), the LocalVol footer, and `lv_benchmark`'s per-expiry
  table (`conv` column). Calibration byte-identical (computed after the
  solve). Tests: `test_lv_reprice.py` (6 — bitwise parity, grid contracts,
  Black convergence, the blindness-exposure fit test).
- **⚠️ THE METRIC'S FIRST CATCH — the calibration operator is NOT converged
  past the first expiry.** Synthetic ALPHA: in-operator rms 0.009bp but
  converged rms 47bp, front expiry (~30d, 9 steps — just clears the fix-#3
  gate of 8) carries 103bp (decomposition: dt×4 alone = 93bp, dx×2 = 7bp).
  True-weekly SPY fixture (`lv_benchmark --fixture tests/fixtures/
  lv_weekly_massive.json`): surface in-op 11.2bp vs CONVERGED 46.2bp — fix #3
  refined only the FIRST interval (32 steps) while 07-01→07-06 gets 2 steps
  (conv 77bp vs in-op 13bp) and →07-17 gets 4 (69bp vs 19bp). **Follow-up
  (calibration-behavior change, own fixture-validated pass): per-interval dt
  refinement (extend the fix-#3 gate to every short inter-expiry interval,
  cost-aware); acceptance = conv rms ≈ in-op rms on the weekly fixture at
  acceptable nfev.** Note the first-order-scheme caveat: the dt/4 reference
  still carries ~25% of the operator error, so the metric slightly
  UNDERSTATES.
- **R0 item 3 SHIPPED — extrap-arb Phase 3, publish-time wing projection
  (core pinned).** New `volfit/models/projection.py`: exported curve samples
  repaired per wing in OTM-price space (calls right / puts left) — outward
  from the pinned traded edge, prices lifted onto the discrete arb-free cone
  (non-increasing, convex in strike incl. the core seam, ≥ the previous
  PUBLISHED expiry's price; ascending-maturity sweep so the artifact is
  jointly ordered) then inverted back to w. Repair only RAISES wing prices;
  clean wing ⇒ byte-identical export (exact no-op); fits/views untouched;
  floor above the pinned core edge = core conflict → capped + flagged
  `wingsClean=false`, never repaired. Rides GET /export/surfaces (default
  ON, `project_wings=false` = raw wings), `ExportNode.curveProjected` +
  manifest `wingProjection/projectedNodes`. Notes 09/10 remarks updated +
  PDFs rebuilt. Tests: test_wing_projection.py (6).
- **R0 item 4 SHIPPED — certification pack v0.** `backtest/certification.py`:
  15 NAMED cases across the matrix (market regimes × data failures × model
  stress), each = title + client-readable story + origin commit + the pytest
  LOCKS that guard it (validation and production share one set of
  definitions); market-regime verdicts pull the stored benchmark-pack
  tables. `python -m backtest.certification run|report` → per-case PASS/FAIL
  (one isolated pytest process each) + self-contained HTML/JSON artifact
  under `results/certification/` (gitignored, regenerable). Cases include:
  zero-carry chains, duplicate strikes, tick noise, stale/crossed wings,
  data age, weekly LV resolution, LV operator blindness (the 2026-07-10
  catch), convex-wing tail, calendar phantom, de-Am repair confinement,
  extrap wing contracts (Phases 1-3), graph dark disconnection, dark-band
  honesty, 3 regime verdicts. test_certification.py locks registry
  integrity (renamed test files break the registry test), report rendering,
  and one real runner round-trip.
- **R0 COMPLETE (items 1-4).** USER-ACTION items parked from R0.4: the
  benchmark ζ rerun (`-m backtest.benchmark_pack run --designs liquid_split
  --eta 10 --cross-mult 25 --tag _idiofloor_eta10`, user's window) + deck
  slide-7 refresh after it. Follow-ups parked: LV per-interval dt
  refinement; skew/curv band widening (R3).
- **R1 item 5 SHIPPED — exact timestamp/settlement semantics (store schema
  v7).** New `volfit/data/expiry_time.py`: RULE-computed NYSE calendar
  (holidays incl. Good Friday via Easter algorithm, Sat→Fri/Sun→Mon
  observation, 13:00 half-days), per-expiry `ExpirySettlement` (PM = session
  close; AM index roots SPX/NDX/RUT = 09:30 settle + prior-session 16:15
  last trade; non-trading expiries roll back), `exact_year_fraction`
  (signed, ACT/365, UTC-naive per codebase convention). ChainSnapshot gains
  trailing `settlement` map (schema v7 = `settlement_json` column, old rows
  NULL); ALL providers populate it (synthetic/yahoo/massive×5-sites/
  flatfiles/bloomberg×2). **Fits byte-identical**: prepared.t/tau untouched
  (the compute switch is R2's 0DTE path). BONUS FIX: the universe prune
  (`_reconcile_chain_selection`) was silently DROPPING zero_carry/tick_size
  on every expiry deselect (un-pinning IV-synth forwards, disabling the
  tick screen) — now carries all chain metadata, test-locked.
  tests/test_expiry_time.py (12). Known v1 simplification: PM close stamped
  16:00 ET (SPY/QQQ/SPX trade to 16:15 — per-root override rides the R2
  0DTE consumer).
- **R1 item 6 SHIPPED — short-dated quote quarantine + diagnostics.** The
  prep screens (tick floor, static bounds, wing cut, crossed markets, ...)
  used to drop quotes SILENTLY; now every drop is quarantined with a named
  reason (`ScreenedQuote` on `PreparedQuotes.screened`: tick_floor /
  missing_or_crossed / below_intrinsic [explicit `INTRINSIC_TOL` — a side at
  or below intrinsic = near-zero time value, no stable IV] / price_bound /
  iv_unresolvable / wing / nonpositive_bid). KEPT SET BYTE-IDENTICAL (the
  drops are named, not changed — evidence: weekly-fixture kept counts match
  the benchmark nQ column exactly). Plus per-quote `eep` retained on
  American chains (de-Am model-dominance signal: 32/81 kept quotes on the
  6-DTE carry EEP) and `vega_floored` count (kept quotes with Black vega
  < 1e-3 — where IV residuals are meaningless and the price-space
  objectives LQD/LV already use are authoritative). Surfaced advisory on
  QualityNode.screened/vegaFloored. tests/test_quote_screen.py (7).
  Discovery: price-space residuals ALREADY exist where they matter (LQD +
  affine LV fit vega-normalized price); SVI/MCS stay vol-space until R2.
- **R1 item 7 SHIPPED — CarryCurve v0 (provenance + identifiability).** New
  `volfit/api/carry.py` + GET /carry/{ticker}: the per-ticker carry object
  {forward, discount, option-implied borrow} per expiry, every component
  source-tagged (parity_implied / desk / model / unidentified). Borrow =
  ln(F_theo/F_parity)/T (the flat rate cancels; positive = hard-to-borrow),
  read ONLY when identifiable (parity regression present, not zero-carry,
  ≥ CARRY_MIN_STRIKES=6 pairs, residual_rms ≤ 1e-3·spot) — otherwise
  borrowBp=None, borrowSource="unidentified", the CALM common state, never
  a silent zero. Versioned by forwardsVersion/dataVersion (fit caches
  already key on resolved forwards). Surfaced: ForwardEntry.impliedBorrowBp
  + a Borrow column in the Forwards tab (em-dash + tooltip when
  unidentified); QualityTicker.carryIdentified/carryUnidentified (ADVISORY
  — gating arrives with R2's joint borrow/de-Am fixed point).
  tests/test_carry.py (5: planted 300bp borrow recovered ±2%, zero-carry →
  calmly unidentified, rollups advisory).
- **R1 item 8 SHIPPED (2026-07-11) — governance kernel.** Store schema v8:
  APPEND-ONLY `events` audit table (actor="desk" until hosting names
  sessions; no update/delete surface exists) + hash-chained `manifests`
  table. `AppState.log_event` (best-effort: in-memory tail always, store
  when configured, never breaks the operation) wired at: fit/options/market
  settings (changed-fields diffs), forward policy, quote edits (validated
  actions only), prior selection, graph edges, publish, recall. Every
  export with a store PERSISTS a SurfaceManifest (id = content hash chained
  to the previous publish, which it supersedes; recall flips state, never
  deletes; artifact blobs age out past ARTIFACT_RETAIN=50, rows/docs are
  forever) storing snapshots + settings + policies + the stamped artifact.
  Lifecycle: published → superseded / recalled. GET /publish/history +
  POST /publish/{id}/recall. **`python -m volfit.replay_report [id|latest]`
  = the roadmap-3.5 acceptance: rebuilds a FRESH state from stored inputs,
  re-calibrates the published nodes, re-exports, diffs every curve point —
  test-locked at ≤1e-9 IV** (v0 fidelity notes surfaced: session edits +
  prior content not captured; LV grid stored, not re-fit).
  tests/test_governance.py (4).
- **R1 item 9 SHIPPED (2026-07-11) — state-scoping refactor: AppState's
  user-authored state is ONE serializable Workspace object. R1 COMPLETE.**
  New `volfit/api/workspace.py`: `Workspace` owns the scoped state (fit +
  options settings, market settings, event calendars, forward policies,
  quote-edit + var-swap sessions with undo/redo, saved per-node priors,
  active fetched priors + ladder source, observation-filter node states,
  lit/dark picks, graph edge overrides + block rule, spot shifts, viewed
  fit mode, as-of); AppState delegates every historical attribute through
  `ScopedField` data descriptors, so the ~74 files touching those names are
  UNCHANGED and behaviour is byte-identical by construction (both suite
  halves green, incl. the golden locks + parallel-calibration identity).
  `AppState.workspace_doc()` / `restore_workspace()` = the JSON round-trip
  (floats exact; numpy → lists); restore is a state RESET: chain-derived +
  per-ticker derived caches drop, every version counter advances past its
  current value, universe tickers + custom picks restore lazily (no
  network). **Replay fidelity gaps CLOSED**: publish manifests now capture
  session quote edits, var-swap quotes (an unstated third gap — they shape
  fits too) and active-prior CONTENT + sources, scoped to the published
  nodes; `volfit.replay_report` restores them before recalibrating, so an
  edited + anchored publish replays at 0.0 IV diff (test-locked ≤1e-9,
  CLI-verified). Fidelity notes remain only for: legacy v0 count-only
  manifests, publishes with the ACTIVE observation filter (the MAP
  prediction state predates the published fits — not post-hoc recoverable),
  and STALE published nodes (new `staleNodes` manifest count: a frozen fit
  calibrated at older inputs than the manifest captures diffs by
  construction — surfaced, not hidden). tests/test_workspace.py (8: doc
  round-trip, session/var-swap history round-trip, restored-fit
  byte-identity, restore-is-a-reset, filter-state round-trip, exact replay
  with edits+prior, stale note, legacy-vs-captured notes).
- **R2 item 10 STARTED (2026-07-11) — intraday variance clock SHIPPED (the
  0DTE core enabler).** New `volfit/calib/intraday_time.py`: sub-day
  day-weight integrator over the NYSE session rules (volfit/data/
  expiry_time, now lru-cached) — every trading day still carries weight 1
  (the legacy integer-day convention, extended below one day), split
  ``sessionVarShare`` over the session (09:30 ET→close; half-day sessions
  scale it) and the rest off-session; non-trading days carry
  ``nonTradingWeight`` (the weekend-effect lever). The default share 6.5/24
  is the flat density: close-to-close spans integrate to exact whole days
  (across weekends AND the DST weekend), sub-day spans to wall fractions.
  Wiring: `OptionsSettings.intradayClock` (default OFF = byte-identical;
  toggle + both knobs bump the options version) → `service.node_clock`
  values each node from the SNAPSHOT timestamp (never wall clock — replay
  prices at its own moment) to the schema-v7 settlement instant (NYSE rule
  fallback), clamped at 0 past settlement; `variance_time` gains
  ``base_days`` so tau rides the session profile while the EVENT cutoff
  stays on calendar time (a fractional EventSpec.time is now a genuine
  intraday event — 08:30 CPI just works). LV/term/density follow
  automatically (they read prepared.t/tau). Audit: remaining
  `state.year_fraction` sites (forwards/carry/dividends/universe metadata)
  stay day-granular by design v1. Options-tab Events group gained the
  toggle + 2 knobs. tests/test_intraday_time.py (12).
- **LV daily-ladder fixes SHIPPED (2026-07-11, user-reported on live SPY
  dailies 07-13/15/17 from Massive; LQD fine, LV bad on 07-15/07-17).** TWO
  root causes, both measured on a captured fixture (scratch
  lv_benchmark run): **(a) 1-step inter-expiry intervals** — fix #3's dt
  gate only covered the FIRST interval, so the 2-day 07-13→07-15 and
  07-15→07-17 intervals got ONE implicit-Euler step each (in-op 8/12 bp,
  CONVERGED 93/67 bp — the R0-item-2 metric's operator blindness, exactly
  the parked "per-interval dt refinement" follow-up); the gate now applies
  to EVERY interval (any interval below _PDE_NT_FIRST_GATE=8 steps marches
  with _PDE_NT_SHORT=32; ladders whose intervals all clear the gate keep
  byte-identical grids). **(b) the fix-#1 coverage densifier never reached
  the call side** — it split the widest gap BETWEEN in-range vertices, but
  on a 2-6 DTE smile the only call-side vertex is x=1 AT the range edge
  (the next shared-axis vertex, the long-maturity 40Δ at x≈1.041, is
  outside), so all 8 added vertices landed on the put side and the
  optimizer pinned the out-of-range upside vertex at the 5% vol floor (the
  user's "variance floor" symptom: exported grid vol(1.0409)=0.050 on every
  short t-row, zigzag near-ATM). The widest-gap scan now includes the
  segments up to the traded-range edges. AFTER (same fixture): 07-15 conv
  93→31 bp, 07-17 67→25 bp, surface conv 41→23 bp, nfev 139→112; weekly
  fixture surface conv 46→41 bp; Bloomberg fixture grids untouched by
  construction. 2 new locks in test_affine_grid_design.py (29 total).
  NB: restart the app to pick the fix up, then Calibrate.
- **LV daily-ladder follow-up SHIPPED (2026-07-11, later) — chained
  sub-front tie.** After the dt/coverage fixes the user saw SPY 07-13
  noisier + NVDA 07-13 unsmooth. Root cause: the vertex rows BELOW the
  first quoted expiry (t=0 and the t1/4 pre-node) are individually
  unidentified (quotes pin only the variance integral 0→t1) and the
  frontTie only chained t=0→row1 — so the sub-front pair rang freely
  (NVDA t=0 near-ATM 0.62→0.42→0.05 across adjacent nodes) and the fit
  BASIN-HOPPED non-monotonically under operator refinement (NVDA 2-DTE
  conv 130bp, 172bp on a FINER dt). Fix: on a short front
  (< FRONT_TIE_SHORT_T = 0.08y, the fix-#3 regime) the tie chains over
  EVERY sub-front row at FRONT_TIE_CHAIN_WEIGHT = 1.0 (a structural prior
  on unidentified DOF, not a fit trade-off; user weight kept on normal
  fronts ⇒ byte-identical there). Measured: NVDA 07-13 conv 130→57bp
  (monotone under refinement again), SPY dailies surface conv 23→21bp
  (bounds-pinned 19→12), weekly fixture 41→30bp, Bloomberg ~unchanged
  (in-op 2.8→2.9bp — its 27d front is inside the gate, mildly helped).
  Deliberately NOT shipped after measuring: dt 32→128 (single-digit bp at
  4× march cost once tied). The user's "make the [0,2d] grid finer"
  intuition was inverted: fewer effective DOF there, not more. Lock:
  test_affine_grid_design.py (ringing collapses when chained, survives
  untied, normal-front gate intact). NVDA Bloomberg 27d front conv ~124bp
  = pre-existing separate issue (34 quotes, 8 coarse steps at high vol,
  clears the dt gate) — candidate for a later dt-per-vol pass.
- **LV daily-ladder round 3 SHIPPED (2026-07-11) — PDE strike-lattice
  aliasing = the residual "not smooth / monotonicity switching at every
  quote".** User round 3: SPY 07-13 upside still out-of-band + wiggly,
  NVDA 07-13 in-band but slope-flipping at every quote — while the
  calibrated theta rows were near-monotone (NOT surface ringing).
  Root cause: on 2-DTE dailies the QUOTE spacing is finer than the PDE
  strike lattice (SPY quotes every 0.13% vs dx 0.25% [the 1/400 cap];
  NVDA 1.2% vs 1%), and quote/display prices interpolate BETWEEN lattice
  nodes — at 2-DTE vega that interpolation aliases into ±5-12bp IV
  wiggle at quote frequency. Fix: `_PDE_DX_SHORT_FRAC` 0.3→0.15 +
  `_PDE_N_MAX` 400→800 (measured knee: slope switches 7→1 SPY / 9→1
  NVDA, SPY outside-band 10→5 and rms 9.1→6.5bp; the 0.10×/1600 rung
  buys nothing at 2.4× the time; cold-fit cost SPY 7.8→11.1s, dailies
  only). Fixture sweep: weekly surface conv 29.8→22.6bp (cumulative
  today 46.2→22.6), dailies SPY 20.6→19.4bp, Bloomberg SPY in-op
  2.9→2.4bp (its 27d front now crosses the refined threshold — an
  improvement, not a regression; NVDA untouched). Perf rails 23-27% of
  budget. Remaining honest residual on 2-DTE: ~3-5 SPY quotes with
  3-7bp-wide bands vs ~6.5bp fit noise = tick-grid data noise (fix-order
  #3 robust weighting territory, not grid).
- **LV daily-ladder round 4 SHIPPED (2026-07-11) — adaptive local-vol
  FLOOR (the "LV constraints wrong when expiry ≤ 2 days" the user
  guessed).** SPY 07-13 upside still out-of-band with an awkward drawn
  shape while observed IVs formed a smooth smile. Root cause: the nodal
  local-vol floor was FIXED at 5% (the cap had been made adaptive long
  ago; the floor stayed level-blind), and a low-vol smile MINIMUM needs
  local vol BELOW its implieds (BBF: implied ≈ path average of local
  vol) — SPY's 2-DTE upside dips to 6.5% implied, needing ~3.5% local
  vol, so the fit RODE the box (the exported upside vertex pinned at
  exactly 0.0500 on every short row) and no regularizer or vertex budget
  could reach the quotes. Fix: floor = min(request 5%,
  _LV_VOL_FLOOR_FRAC(0.5) × the lowest ATM implied across expiries) —
  keyed on ATM deliberately (a global quote-min let one noisy deep-wing
  implied unlock the UNQUOTED wing where the box stabilizes: the
  convexWing × fine-grid lock read 61bp/53 butterfly flags — caught by
  test_lv_benchmark), and applied WITHOUT round-tripping the request
  value through sqrt (a 1-ulp box perturbation alone flipped that
  fragile fit into the same bad basin). Result: SPY 07-13 upside now
  ±1-3bp through the smile minimum, in-op 6.5→5.7bp / conv 12.2→10.2bp;
  NVDA + Bloomberg + weekly byte-identical (ATM implieds ≥ 10%).
  The user's hidden-expiry/virtual-quote regularizer idea was NOT needed:
  fix #5's chained tie already enforces that prior (flat forward variance
  below t1) in local-variance space, and the actual blocker was the box
  constraint, which no regularizer can cross; synthetic quotes would also
  contaminate the audited objective (governance). tests: floor
  scales/ATM-keyed/wing-robust in test_affine_grid_design (29).
- **LV daily-ladder round 5 SHIPPED (2026-07-11) — side-blind coverage +
  the hidden-expiry verdict.** Diagnosed the USER'S LIVE surface over the
  API (their config: haircut, gridXNodes=20, convexWing — NOT the
  benchmark defaults; their live 07-13 read −22bp at K=759 / +34bp at
  K=762 with interior upside vertices {1.0046} only): with 20 base
  nodes the delta axis already lands ≥8 in-range vertices so the COUNT
  floor never densifies — but they are put-side-heavy, and the call side
  keeps ONE bend point → the model draws a V through the upside quotes.
  Fix: short expiries (≤ ~10d, `_COVERAGE_GAP_MAX_T`) additionally
  require EVEN coverage — no boundary-augmented in-range gap >
  range/(gridXMinPerExpiry−1) — side-aware by construction; long
  expiries keep the count rule byte-identically (the fragile
  convexWing×20 Bloomberg lock passes untouched). User-config repro:
  758–762 to ±1–5bp, rms 7.5→5.2 / conv 18.6→10.1bp; default config:
  NVDA 07-13 conv 56.9→34.8bp. ALSO: the user's hidden-virtual-expiry
  regularizer (t1/2, half variance) implemented faithfully + a
  self-similar k/√2 variant, measured across weights 1–8×: net-negative
  everywhere (fixed-strike wrecks steep-skew NVDA 18.5→50–59bp;
  self-similar degrades SPY conv 10→15–18bp) — the asserted mid-time
  smile is an unsupported observable competing with real quotes; kept
  DORMANT (`_LV_VIRTUAL_FRONT_MAX_T=0.0`), builder test-locked. Session
  lesson: check export generatedAt vs commit times — round 4's "still
  bad" was a pre-fix surface; round 5's was REAL and config-dependent.
- **R2 item 10 part 2 SHIPPED (2026-07-11) — intraday 0DTE capture
  machinery (`backtest/capture_intraday.py`).** `QuotesFlatFileStore`
  gains `chains_at` (SEVERAL instants of one day from ONE firehose scan:
  the per-instant reduction joins a VALUES list of targets and QUALIFYs
  per (target, contract) — N instants would otherwise cost N multi-GB
  streams) + a 30-min `http_timeout` / 3 retries (the 30 s default
  aborted mid-stream, seen live). The campaign module: SPY/QQQ/IWM,
  default 13 instants/day (10:00→15:45 ET, half-day-clipped via the NYSE
  session rules), ladder = dailies (DTE ≤ 7) + 2 monthly term anchors
  ≤ 90d; one resumable JSON fixture per (asset, day) under
  backtest/fixtures/intraday/ + optional `--db` writing every snapshot
  into a VolStore WITH the settlement map, so the app's as-of "captured"
  replay + the intraday clock price real 0DTE chains.
  tests/test_capture_intraday.py (6, fully offline via source_uri) +
  `-m backtest.validate_intraday_clock` (the post-capture acceptance CLI).
  **The scan itself is a USER'S-WINDOW job** (~hours/day-file on this
  link, same as the nightly capture; interactive probes get killed):
  probe = `python -m backtest.capture_intraday --start 2026-07-10 --end
  2026-07-10 --tickers SPY --db backtest\results\intraday.sqlite` (dot-
  source restart.local.ps1 first), then the clock validation script
  (scratchpad\validate_0dte_clock.py pattern: StoredChains provider +
  intradayClock ON → sub-day t + sane LQD fit on the real 0DTE node).
- **USER ACTION PENDING — the 0DTE probe capture (relaunch #4, via the
  STALL SUPERVISOR).** Three failed attempts, three distinct root causes,
  each fixed:
  #1 2026-07-11 = DuckDB OOM ("Allocation failure": default memory_limit
  is 80% of TOTAL RAM, box had ~1.3 GB physically free, the end-of-scan
  join+QUALIFY spike died before spilling) → FIXED `f12c43b`
  (quotes_store: 4GB cap, $env:VOLFIT_DUCKDB_MEM overrides, +
  temp_directory spill under _cache, 100GB cap).
  #2 2026-07-13, 17 h = both attempts streamed ~6.5h/~10.5h then died
  "Could not resolve hostname" (default HTTP retries fire ~100 ms apart,
  all burned inside one transient DNS blip) → FIXED `511f805` (retries
  spaced 10s/20s/40s/…, ~10 min of outage ridden out).
  #3 2026-07-14 = HARD STALL: half-dead socket (ESTABLISHED, zero read
  ops), CPU frozen >1 h, DuckDB's http_timeout never fired (it does not
  cover a mid-body stall) — no in-process cure exists → FIXED by
  `backtest\run_capture_intraday.ps1` (supervisor: watches the child
  tree's CPU clock, kills+relaunches after 15 quiet min [-StallMinutes],
  retries failed exits [-MaxRestarts 6], PYTHONUNBUFFERED so
  results\capture_probe.run*.out.log streams live; capture resume skips
  finished days so restarts only re-pay the day in flight).
  Relaunch (user's window, won't-sleep; creds auto-sourced from
  restart.local.ps1; NB -DbPath not -Db, which PS reserves):
  `.\backend\backtest\run_capture_intraday.ps1 -Start 2026-07-10 -End
  2026-07-10 -Tickers SPY -DbPath backtest\results\intraday.sqlite`
  Then: `-m backtest.validate_intraday_clock --db
  backtest\results\intraday.sqlite --ticker SPY --ts
  2026-07-10T16:30:00`. If clean, widen: `-Start 2026-06-30 -End
  2026-07-10 -Tickers SPY,QQQ,IWM` (resumable across evenings).
- **R2 item 10 part 3 SHIPPED (2026-07-15) — LIGHT REST CAPTURE, first real
  0DTE day CAPTURED + CLOCK VALIDATED.** The flat-file probe was diagnosed
  terminal for this link: ONE day of `quotes_v1` is **111.41 GB** (HEAD'd
  live), so the 6.5/10.5 h streams were dying near the END of an
  unresumable transfer; run #4 (7/14 16:50) died seconds in (0-byte logs).
  New `backtest/capture_intraday_rest.py`: same fixture schema / expiry
  ladder / instants / VolStore persistence as `capture_intraday`, but NBBO
  per (contract, instant) via REST `/v3/quotes` (`timestamp.lte` +
  `order=desc&limit=1` = exactly the flat-file at-or-before reduction,
  plus a day-bounded `timestamp.gte` so a contract not quoted TODAY is
  absent rather than carrying yesterday's NBBO). Contract discovery via
  `/v3/reference/options/contracts` windowed around the day close (dailies
  ±10%, term anchors ±25%); per-instant `.part.json` checkpoint; sibling
  note vs `rest_quotes.py` (the daily capture's REST source) in the
  docstring. **SPY 2026-07-10 captured from the agent session in 6.3 min**
  (13 instants × 2,270 contracts = 29.5k requests, ~29 s/instant, zero
  429s) → fixture + `results/intraday.sqlite`. `validate_intraday_clock`:
  **VALIDATION OK at 12:30 ET (0DTE t = 0.1458d = exactly 3.5 h to the
  16:00 settle; legacy 0.0d unrepresentable) AND at 15:45 ET (t =
  0.0104d, 15 min out, 7 surviving quotes, sane fit)**; all 8 nodes
  maxIvErr 80–141 bp. TWO harness fixes en route: (a) the validate CLI now
  `set_expiries` the FULL captured ladder — `default_selection` seeds only
  strictly-future expiries (`days > 0`, expiry_select.py) and was silently
  dropping the same-day rung, so `resolved_forward` hit a missing parity
  entry ('NoneType' .forward); (b) README module map gained the intraday
  rows. Tests: test_capture_intraday_rest.py (5, offline MockTransport —
  schema parity, as-of semantics, zero-bid, checkpoint resume, 429 retry).
  NOTE for the wider campaign: REST makes SPY/QQQ/IWM × a 2-week window
  ~20 min/ticker-day-set, so the 111 GB flat-file route is now the
  fallback, not the plan; `boto3` was installed for the size probe (also
  enables a resumable ranged download if the firehose is ever truly
  needed). Day-granular residue spotted for a later pass: the parity
  discount rate-band clamp + American de-bias in data/forwards.py gate on
  `(expiry - ref).days > 0`, so a same-day expiry skips both (its D=1.0005
  passed through unclamped — harmless here, listed for the R2 audit).
- **R2 item 10 CAMPAIGN CAPTURED + VALIDATED (2026-07-15, same session).**
  Full REST campaign: **SPY/QQQ/IWM × 2026-06-30→07-10 = 24 ticker-days,
  312 snapshots (13 instants each), ~500k quotes** in `backtest\results\
  intraday.sqlite` + per-day fixtures. Ops hardening en route (each fixed
  + committed): REST retries now ride out ~10-min DNS outages (40602e3 —
  the campaign died live on getaddrinfo, same lesson as 511f805); harness
  kills long background tasks → `run_capture_rest.ps1` detached relauncher
  (3c2d47f); per-instant checkpoints made every restart near-free.
  **Sweep validation (validate_intraday_clock --per-day 3, 72 snapshots):**
  first pass failed 26 nodes, ALL QQQ — root cause = the parked "backtest
  tick stamping" follow-up: captured chains had `tick_size=None`, so the
  schema-v6 3-tick OTM floor was DISABLED and cent-level lottery calls
  (9-DTE +9..16%% quoted 0.01/0.03) masqueraded as tight IV bands. Fixed
  e8d10a8 (all three harness snapshot builders stamp US_OPTION_TICK; store
  backfilled): **26 → 2 failing nodes. SPY/IWM 100%% pass; every 0DTE node
  prices sub-day; near-settle thin chains SKIPPED calmly (67dbcb7 —
  resolved_forward now raises a readable UnknownNodeError instead of an
  AttributeError when parity is missing).** Validation upgrades shipped:
  campaign sweep mode (57fd710), **band-relative acceptance gate**
  (6e589b8, BAND_EXCESS_BP=250 — |model−mid| flagged honest wide-market
  data), sub-day discount clamp (0917850), committed 0DTE fixture gate
  `test_intraday_0dte.py` (eb56272, 862 real quotes).
  **The 2 residual failures = ONE finding:** the QQQ 2026-07-17 monthly
  seen 10-16d out (dense ~150-quote chains, real premiums) carries an
  upside-wing curvature LQD cannot bend into — bid-ask mode (band-only
  objective) still escapes by ~380bp, so it is slice CAPACITY, not
  weighting (the QQQ 06-30 morning-0DTE case from the early sweep cleared
  once the tick floor engaged). NEXT fix: a fixture-driven short-dated /
  wing LQD tuning pass (the LV daily-ladder playbook), fixtures ready
  under backtest\fixtures\intraday\.
- **"LQD capacity pass" CLOSED 2026-07-15 (a9cc490) — VERDICT OVERTURNED:
  the model was right, the tick floor was gameable. CAMPAIGN VALIDATION
  OK (72 snapshots, 0 failing nodes).** Diagnosis of the 2 residual
  failures found each was ONE quote: QQQ 10-16 DTE K=835 quoted 0.01×0.07
  / K=865 quoted 0.02×0.06 amid blanket one-sided $0.03 asks — placeholder
  markets whose 4-tick MIDS cleared the mid-based 3-tick floor purely on
  the strength of a junk ask, while the fitted wing agreed with every
  neighboring ask (that is why bid-ask mode could not "thread" them
  either: one junk quote is CORRECTLY outvoted — the earlier capacity
  inference was wrong). Fix: **the tick floor now tests the BID — the
  side the market commits to** (`quotes.py`; bid ≤ mid so the new rule
  subsumes the old one and cannot be gamed by a wide ask). Evidence:
  weekly Massive LV fixture A/B byte-identical; full suite 1121 passed
  incl. the fragile Bloomberg convexWing locks; both failing nodes → band
  excess 292→41bp / 494→19bp. Consequence handled: minutes from
  settlement an entire 0DTE chain can fall to the floor (IWM 07-09
  15:45) — prepare's "no two-sided OTM quotes" is classified SKIPPED (no
  fittable market) in the sweep, surfaced in its summary lines. NB the
  bid floor is a KEPT-SET change on live ticked chains (drops junk-ask
  wing quotes the mid floor kept) — expected effect is strictly cleaner
  wings; exact-price pipelines byte-identical by the tick_size gate.
- **TEMPORAL-FILTER TUNING SHIPPED 2026-07-16 (d16f913) — the filter gains
  a SESSION variance clock.** New `backtest/observation_filter_intraday.py`
  (two-phase: `--build` = 936 data-only LQD measurements over the campaign
  store, resumable; `--sweep` = the pure Kalman core replayed across
  (clock, process-bp) configs in seconds). **The calendar clock is wrong at
  sub-day cadence, measured:** transported ATM handle moves are 19.5 bp per
  30-min step (dailies 22.6 / anchors 17.7), 54.9 bp per overnight, and
  54.4 bp per WEEKEND — a closed market accrues ~zero handle variance, so
  no calendar q calibrates all step types (best: ζ_atm 1.04 intraday /
  0.53 overnight / 0.23 weekend). **The session clock (60%% of a day's
  variance inside the 6.5h session, non-trading days 0) at q=90 bp/√day
  calibrates jointly: ζ_atm 0.95 / 0.89 / 0.84.** Production wiring:
  `OptionsSettings.filterClock` ("calendar" default = byte-identical |
  "session") + `filterSessionShare` (0.60) / `filterNonTradingWeight`
  (0.0), riding the EXISTING `intraday_variance_days` in the filter's dt
  (`api/observation_filter._filter_dt_days`); the stale-reset rule stays on
  calendar hours (staleness = data age, not variance). Tests: clock unit
  locks (test_observation_filter_app +2) + options defaults/round-trip.
  Suite 1122 passed (the graph perf rail failure A/Bs identically on the
  clean tree = the documented box-load flake). **Residual for a later
  pass:** skew/curvature ζ ≈ 1.8 / 6.4 at the default per-handle scales,
  worst on short-dated nodes (30-min curvature std 13.9 dailies vs 3.4
  anchors) — per-maturity handle process scales, an F3-style follow-up;
  the q LEVEL is regime-dependent as always (this one-window read said
  ~90 bp; the daily default 30 bp stands, adaptive inflation spans them).
- **SETTLEMENT-INSTANT CALENDAR ORDERING SHIPPED 2026-07-16 (16e98a0).**
  `service.ordered_expiries` keys every calendar-coupling chain (surface
  fit plan, coupled Calibrate items, Quality's calendar column) on the
  schema-v7 settlement INSTANT — AM 09:30 before PM 16:00 on the same
  date — with an end-of-day fallback reproducing date order exactly:
  byte-identical for every current chain (settle instants never cross
  calendar dates; full suite 1125 green incl. the perf rails).
  tests/test_expiry_order.py (2: byte-identity contract + AM<PM key
  semantics). **Honest scope**: chains key expiries by DATE, so a genuine
  same-date AM/PM pair (SPX quarterly vs SPXW EOM) collapses to one node
  at INGESTION — the seam orders whatever nodes exist; splitting the pair
  needs an expiry-key redesign ((date, settle-class) through
  ChainSnapshot/store/fit keys), which is the real prerequisite for
  index-root universes and should ride the SPX/NDX/RUT onboarding, not
  this item.
- **DEGRADED MODE v1 SHIPPED 2026-07-16 (ec2a620) — unfittable markets are
  NAMED and keep serving the prior.** Two findings drove the shape: (a) a
  no-fit node rendered identically whether it was NOT-CALIBRATED-YET or
  UNFITTABLE DATA (a 0DTE chain minutes from settlement: no parity pairs /
  every OTM quote at the tick floor) — a desk reads "press Calibrate" and
  presses it, uselessly; (b) in the UNGATED workflow the named conditions
  escaped `smile_payload` as raw errors — **an HTTP 500 on exactly the
  nodes a 0DTE desk watches into the close** (reproduced on the captured
  IWM 07-09 15:45 chain, then served cleanly end-to-end after the fix).
  Mechanics: `service.prepare_slice_or_reason` classifies the named
  conditions (`no_parity_forward` / `no_fittable_market`; unnamed failures
  keep the legacy silent None — no false labels on transient misses);
  `SmileData.degraded` rides the payload; `smile_payload` absorbs the
  named conditions into the no-fit path — which ALREADY serves the dotted
  transported active prior (`_no_fit_prior`), i.e. the "prior transport"
  half of degraded mode existed; the viewer cue turns amber ("Degraded
  market (…) — showing transported prior"); the Quality row reads
  "degraded: <reason>" with ready=False keeping the publish gate closed.
  Tests: test_degraded_mode.py (4) + the real-chain end-to-end; suite 1129
  green; frontend build + vitest 55 green. **Degraded v2 (recorded, not
  built):** conservative uncertainty BAND around the served prior via the
  idio-floor machinery (needs innovation-history plumbing + a chart band).
- **EXIT GATES SHIPPED 2026-07-16 (4ad0907) — R2 ITEM 10 COMPLETE.** The
  three remaining gates, each a lock plus the code it needed: (1)
  **deterministic replay** — the committed 0DTE fixture calibrates to a
  BITWISE-identical parameter vector across fresh states (intraday clock
  ON); (2) **hard publish failure** — `build_surface_export(require_clean=
  True)` collects per-node blockers (calendarOk beyond tolerance,
  wingsClean=False core conflicts, unpriceable curve regions w≤0 =
  intrinsic) and raises `PublishBlockedError` BEFORE any manifest persists
  → HTTP 409 naming every offending node; `allow_dirty=true` = explicit
  draft escape (en-route fix: recall_publish used HTTPException without
  importing it — a latent NameError 500); (3) **sub-50ms warm slice** —
  perf rail `warm_slice_0dte` (~20 ms measured, 50 ms design target, 3×
  ceiling). All four locks = certification case **`0dte_exit_gates`**
  (16 cases now). The other two gate clauses were already locked:
  price/band-space quality (the band-relative sweep gate) and
  next-snapshot held-out (the intraday filter harness). Suite 1133 green.
- **R2 ITEM 11 INCREMENT 1 SHIPPED 2026-07-16 (b02257d) — the joint
  borrow/de-Am fixed point, measurement-grade.** New
  `volfit/data/carry_solve.py`: iterate `b ← b + ln(F_theo(b)/F_parity(b))/t`
  where each pass de-Americanizes the paired mids at the SPLIT carry
  (rate, dividend yield + borrow, escrowed cash schedule — the SAME
  schedule in both legs), reprices European on the same tree, regresses
  parity. **Validated on tree-priced chains (the tree IS the market): a
  planted 300 bp borrow returns 299.8 bp in 7 iterations vs a 26 bp
  EEP-bias on the naive raw-parity read; dropping the dividend schedule
  from the solve while the market priced it biases the read 3× — the
  "discrete dividends consistent in both legs" clause, demonstrated.**
  The yield leg is never misread as borrow; European chains short-circuit
  exactly; per-expiry independence = isolated maturity specials by
  construction; unsupportable data → None; tree-inversion failures counted
  explicitly (the exit-gate clause). Trader view: `GET
  /carry/{ticker}?joint=true` adds jointBorrowBp/Iterations/Converged/
  DeamFailures per identifiable expiry (proportional dividend models fall
  back to v0); the default payload is byte-identical. **Honest finding
  (test-recorded): on FLAT-carry chains v0's `_refine_american`-refined
  read already ≈ the joint solve — the fixed point's edge is discrete
  dividends (ex-date exercise timing) and model-split provenance.**
  Suite 1140 green. **Remaining item-11 increments:** (2) feed the
  converged (F, D, borrow) into resolved forwards / de-Am in the fit path
  — GATED, ordinary names byte-identical test-locked from day one; (3)
  dIV/d-borrow sensitivity diagnostic; (4) held-out parity exit gate +
  known-HTB validation on REAL data (needs an HTB-name capture — GME/AMC
  class); (5) Forwards-tab joint column + confidence.
- **ITEM 11 INCREMENT 2 SHIPPED 2026-07-16 (3642c6b) — gated fit-path
  joint carry.** `OptionsSettings.jointCarry` (default OFF) +
  `jointCarryEngageBp` (25 bp), both options-version bumping;
  `state.joint_carry_read` caches the fixed-point read per (ticker,
  expiry), invalidated with the forwards cache at every death site + on
  market-settings changes; `resolved_forward` overrides the parity route
  with source "joint" ONLY when the read is converged AND material
  (|borrow| ≥ engage bp) — below the bar the parity object returns
  EXACTLY, so **ordinary names are byte-identical even with the toggle
  ON, locked bitwise on prepared arrays from day one** (the item's
  explicit bar). Carry view maps the engaged source to `joint_deam`
  provenance. Suite 1143 green.
- **ITEM 11 INCREMENT 3 SHIPPED 2026-07-17 (209dc52) — dIV/d-borrow
  sensitivity.** Closed form at fixed strike/price: dσ/db =
  √t·N(d₁)/φ(d₁) ATM (≈125√t bp per 100 bp borrow), validated vs a full
  numerical Black re-inversion to 2%; rides every CarryPoint as
  `ivBorrowSensBpPer100` (cached fit's ATM vol when present, σ→0 limit
  otherwise — read-only). The materiality number for the strategic
  publish rule ("material American correction × unidentified carry").
- **NEXT (item 11 remaining):** (4) held-out parity exit gate +
  known-HTB validation on REAL data (a GME/AMC-class REST capture, cheap
  now); (5) Forwards-tab joint column + confidence. Or: the hosting
  container spike. Item-10 residual follow-ups: per-maturity filter
  handle scales, degraded-v2 band, live-universe 0DTE seeding, same-date
  AM/PM expiry-key redesign.

### 🧭 SESSION WRAP (2026-07-09) — BENCHMARK VERDICT + LOO TOPOLOGY ROOT CAUSE + LIQUID_SPLIT RESWEEP

Full 25-asset benchmark pack finished (user's window; ~47k held-out scores,
3 regimes × 2 designs × R∈{0,1}), then a root-cause hunt and a same-day fix +
resweep (commits `61045ac`, `fadb413`, `8cfac99`; full tables in
`backend/backtest/FINDINGS_graph_loo.md`):

- **full_loo skill concentrates where the graph has support**: indexes
  +10…+76 bp, ETFs +3…+7 bp across all 3 regimes; single names ≈0 (they are
  ~80% of rows with 178–460 bp earnings-dominated base RMS, which is why the
  aggregate looked small vs the pilot's index-weighted +26…+37 bp headline).
- **liquid_split = 0.000 everywhere was a HARNESS BUG, not a market fact**:
  `backtest/graph_edges.py` emitted cross edges one-way (informer→name) ⇒
  names were TRANSIENT under the trust kernel ⇒ stationary π=0 on every name
  ⇒ reversibilized conductance 0 ⇒ dark names fully decoupled. The pilot's
  "96 bp SPX moves dark AAPL 0.01 bp" was this artifact (precision pinning =
  misdiagnosis; `DARK_BASE_SCALE` measured a DEAD lever post-fix). Product
  auto-lattice unaffected (symmetric edges). FIX: `EdgeConfig.cross_reverse_frac`
  (reverse edge, inverse β = same linear relation; 0 = legacy; test-locked).
  Void liquid rows stripped from `results/benchmark/` (archived
  `void_liquid_pre_topofix/`); benchmark artifact regenerated.
- **Resweep on fixed topology** (`--eta 10 --cross-mult 25 --tag
  _topofix_eta10`; knobs tuned on spike, others OOS): dark-name skill
  **spike +7.9…+14.2 bp (ζ std 1.02–1.10, honest) · high_oct2022 +3.8…+7.2 bp
  OUT-OF-SAMPLE (ζ 0.70–0.78) · low_jul2023 ≈0 (earnings-idio; never
  negative) with OVERCONFIDENT bands (ζ std ~1.9)**. Product claim: propagation
  earns its keep in stress, never hurts in calm.
- **Docs upgraded to the new numbers**: Note 14 (abstract, case-file
  subsection + 25-asset verdict table + traceability row), deck slides 28/34 +
  exec-deck slide 9, FINDINGS, this file.
- **NEXT**: calm-regime dark-name band widening (the one dishonest cell —
  event/earnings-aware dark baseline precision); Phase 2 deployment-model
  decision; benchmark_pack gained `--eta/--cross-mult/--tag` for future sweeps.

### 🧭 SESSION WRAP (2026-07-09, later) — NOTES CURRENCY PASS + EXTRAP-ARB MEASUREMENT (Phase 1)

- **All 15 technical notes reviewed against code + deck by 6 parallel agents**
  (commit `8e3bac3`): MCS naming series-wide; Note 00 gained the Kalman
  filter + graph verdict + zero-carry pin; Note 03's fig_siv_g bug fixed at
  the generator (synthetic target itself carried butterfly arb — now asserted
  clean, min g +0.381); Note 05 gained the real-SPY de-Am figure (+519/+817
  bp, generated macros); Note 06 gained the zero-carry case file; Note 12's
  "no re-solve" over-claim corrected; Note 15 carries the v2 full-scale
  filter results as macros. Deck: LQD 13-params, "best denoiser" scoped,
  zero-carry bullet. Two stale docstrings fixed (varswap path, EventSpec
  days). All PDFs rebuilt clean.
- **Extrapolated-region arb measurement SHIPPED (Notes 09/10 Phase 1 —
  measure first, enforce later):** `volfit/models/diagnostics.py::
  extrapolated_arb` measures, per lit node, over the TIME-VALUE ENVELOPE
  (beyond traded strikes while the model's own OTM value ≥ 1bp of forward =
  "extrapolated but not worthless"): worst Durrleman g of the displayed
  slice (one-curve), worst calendar crossing vs the previous displayed slice
  (vol bp, two-curve), and asymptotic wing-slope order. Rides GET /quality
  (`extrapMinG/extrapOk/extrapCalBp/extrapCalOk/wingOrderOk` per node,
  `extrapFlags` rollups) + a QualityViewer column — STRICTLY ADVISORY, never
  gates publish-readiness, no fit behavior changed.
- **Phase 2 SHIPPED same day — tapered enforcement, opt-in
  (`OptionsSettings.extrapEnforce`, default OFF, byte-identical off, bumps
  options_version):** `volfit/calib/extrap.py` builds the enforcement
  geometry ONCE from the quotes (envelope reach = 2·√w_edge, taper =
  OTM-value ratio) + the previous DISPLAYED slice; the SVI/MCS overlay fits
  gain three hinge blocks (one-curve Durrleman g; tapered calendar vs prev
  displayed; SCALAR wing-slope order for the far field — never pointwise
  differencing of two extrapolations). All rows in VOL units budgeted at
  ¼-quote weight each (the var-swap pattern), so the block LEANS like a few
  extra quotes and cannot outvote data: clean pair = untouched to fit
  precision; mild real crossing (~450bp) halved at ~29bp traded RMS.
  Analytic Jacobians kept via the hybrid-FD-block pattern (the MCS
  wing-penalty precedent). Options-tab "Extrapolation guard" toggle.
  test_extrap_enforce.py locks the four contracts; Notes 09/10 remarks
  updated + rebuilt. Phase 3 (publish-time wing-only projection, core
  pinned) remains open. NB conflicted extrap fits can hit the iteration cap
  (nfev ~500, ~100-200ms) — opt-in only, flagged for a Phase-2.1 look if it
  matters in practice.

### 🧭 SESSION WRAP (2026-07-08) — GRAPH UX REVAMP SHIPPED (4 phases, e36ef79→912b00b)

User-approved redesign (options confirmed via Q&A): true graph view, merged
workflow, honest cinematics, block-matrix edge input. All on **main**; gates
per phase: tsc+vite build, vitest (55), 8-tab Edge smoke, LIVE synthetic
visual checks (screenshots in frontend\.smoke\), backend suite **969 passed,
1 skipped** (8 new block tests).

- **Network view replaces the lattice (e36ef79).** `lib/graphLayout.ts` =
  deterministic ticker-pod force layout (pods = calendar spines, springs =
  aggregated cross-ticker edge weight; seeded mulberry32, 12 tests);
  `GraphNetworkChart.tsx` renders the REAL solver topology (overrides else
  lattice) with pan/zoom/Fit, per-pair edge bundles that expand on hover,
  neighborhood hover-dim; old GraphChart deleted, lasso retired.
  `scripts/graph_visual.mjs` = live visual driver (synthetic :8011).
- **One workflow, one verb (f30f73e).** Sandbox/Extrapolate fork replaced by
  an observation-source radio (From calibrations | Manual what-if) in the new
  `PropagatePanel`; single PROPAGATE button routes to /graph/extrapolate or
  /graph/solve; Backtest → Validate (LOO); solver knobs collapse into a
  details section; `ExtrapolateResults.tsx` = table+attribution extraction.
- **Attribution-wave cinematics (d646b93).** Posterior field reveals outward
  by REAL BFS hop from the lit set (`lib/graphWave`, `useWaveTimeline`,
  160ms/hop, reduced-motion instant, click skips); calibrations source also
  fetches the top-5 moved dark nodes' attributions and animates particles on
  the top gain×innovation paths (`useAttributionParticles`,
  `GraphWaveOverlay`, SMIL). Verified live: mid-wave screenshot shows the
  staged reveal (200→89→19 bp down SPY's calendar chain);
  `scripts/graph_wave_check.mjs` reproduces it.
- **Block-matrix edge editor (912b00b).** Backend `GraphBlockRule`
  (pairs/calendar/overrides) persisted VERBATIM (settings_persist
  `graph_block_rule`) with server-side expansion into /graph/edges
  (`api/graph_blocks.py` reuses the lattice's `_selected_ladders` pairing;
  raw PUT /graph/edges clears the rule); GET/PUT /graph/edges/blocks. Frontend
  `EdgeMatrixEditor` modal: sparse ticker×ticker heatmap grid (diagonal =
  calendar), cell popover (weight/β/symmetric), TSV paste, CSV export,
  per-edge overrides drill-down to the old row editor.
- **Follow-ups (updated 2026-07-09 — graph hardening session, 3e94468 +
  0a71cb9):** DONE: expiry×expiry drill-in per matrix cell (EdgeExpiryMatrix,
  overrides layered last, ⇄ mirror, inherited-cell hints, count badge);
  particles VERIFIED on real data (7 concurrent on the live universe);
  PropagatePanel vitest (7) + EdgeExpiryMatrix vitest (5). Same session:
  Edges matrix fed by the SELECTED universe (was the empty sandbox lattice);
  api.ts request timeouts (60s default, long-job overrides) so stalled
  requests can't spin forever; sandbox universe (Manual what-if) now follows
  calibrations + the viewed fit mode (calib_signature cache key — was
  hardcoded mid AND cached empty forever on the gated server; NB the running
  backend needs a restart to pick this up). REMAINING: count-up bp labels;
  graph_visual/wave_check consolidation into the smoke pack.



### 🧭 SESSION WRAP (2026-07-06, evening) — PARALLEL background calibration SHIPPED (commercial-MVP arc, item 1)

Productization arc opened (plan: quality dashboard → export/publish → graph
explainability → benchmark pack; sparse graph solver deferred until >2–3k
nodes). First item done on **main** (suite **931 passed, 1 skipped**; ruff clean):

- **Parallel per-ticker background Calibrate.** `calibrate_all` now runs its
  per-ticker groups CONCURRENTLY: stages of groups in `api/jobs.py`
  (`start_stages`; stage 2 = the LV barrier, serial as before; legacy
  `start()` contract kept), each group's warm-start/calendar chain sequential
  inside its thread. The CPU-heavy slice fits ship to a **spawn process pool**
  (`api/fit_pool.py`, `VOLFIT_CALIB_WORKERS`, default cpu−1 capped 8; 0/1 =
  historical serial) as pure picklable tasks (`calib/fit_task.py` — ONE code
  path pooled or inline, so results are byte-identical; locked by
  `test_parallel_calibration.py`'s serial-vs-parallel identity gate + a real
  spawn-pool round-trip). Assembly/commit stay main-side under the state lock
  (`service._slice_task`); `_compute_fit`/`fit_and_commit_slice` route through
  it; `fit_surface_slice`/`display_overlay` are thin wrappers over the same
  assembler.
- **Interactive fits never pool** — `fit_pool.pooled()` is a thread-local
  opt-in wrapped around background thunks only, so a single-node Calibrate /
  autoCalibrate GET can never queue behind a 25-ticker job (test-locked).
- Infra failures (spawn/pickling/killed worker) **fall back inline** and stick
  for the session; genuine fit errors keep per-item isolation. Cancel keeps
  per-node granularity across all groups. `build_display_fit` moved to
  `volfit/models/display.py` (api/fit_models.py = re-export shim) so workers
  never import the FastAPI graph; `desktop.py` gained
  `multiprocessing.freeze_support()` (frozen-exe fork-bomb guard).
  `tests/conftest.py` pins workers=1 suite-wide (dedicated tests opt in).
- **Measured (9 synthetic tickers × 4 expiries, 6 workers, LV off): warm pool
  3.26× (0.92s → 0.28s), cold first-Calibrate 0.79× (one ~1s spawn per app
  session).** Synthetic fits are ~25ms so the round-trip caps the ratio; real
  chains fit 5–10× longer ⇒ expect closer-to-linear scaling on 25 assets. The
  serial LV stage now dominates a full Calibrate — pooling it is the top
  follow-up.
- **LV stage POOLED too (same evening; suite 932 passed, 1 skipped).**
  Thread-parallel LV measured GIL-negative (0.73× — the nogil Numba march is a
  minority of the fit), so the heavy `calibrate_affine` LSQ ships to the same
  process pool as an `AffineFitTask` (its call site in `affine_fit._fit` was
  already pure data in/out — `AffineCalibration` pickles); gather + response
  assembly stay main-side. The LV stage now runs per-ticker groups
  concurrently after the parametric barrier (the cold-start seed reads the LQD
  fits). Lazy AppState side-dicts (`_affine_cache`, diag caches) hardened
  against concurrent creation. Identity locked: real-pool LV response
  `model_dump()` equality + LV surfaces added to the serial-vs-parallel
  calibrate_all gate. **Full Calibrate (9 tickers, parametric + LV, 6
  workers): warm 2.11× (6.20s → 2.94s), cold 1.45×** (was 0.99× with LV
  serial). Remaining ceiling = main-side GIL work (de-Am prep + smile
  reconstruction on the job threads).
- Follow-ups noted: job resume/queue-priorities/ETA, a `workers` field in
  CalibrationStatus for the UI, move LV response assembly off the GIL if 25-
  asset runs need it.

**Quality dashboard SHIPPED (same evening; commercial-MVP arc, item 2; suite
938 passed, 1 skipped; strict-TS + Vite green).** New **Quality** workspace
tab = the universe publish-readiness screen:

- **Backend `GET /quality`** (`api/quality.py` + `schemas_quality.py` +
  `routers/quality.py`): per lit node — calibration-consistent weighted RMS
  (same `_node_rms_terms` basis as the viewers), max-IV bp, ATM/skew, Lee wing
  slopes vs the ≤2 bound, adjacent-expiry calendar convex-order violation
  (LQD backbone slices), staleness, var-swap/filter flags; per ticker —
  pooled surface RMS + the cached LV response health (rmsIvErrorBp,
  arbitrageFree, calendarViolations, min-density); summary tiles + a
  publish-ready rule (hasFit ∧ ¬stale ∧ leeOk ∧ calendarOk ∧ RMS ≤
  `rms_budget_bp`, default 50). **STRICTLY no fit on read** — records via
  calibrated ptr + fit cache, LV via affine ptr + cache, filter via the
  memoized accessor; test-locked incl. "GET creates zero pointers" both gated
  and ungated (`tests/test_quality.py`, 6 tests).
- **Frontend**: `views/QualityViewer.tsx` + `state/useQuality.ts` (refetches
  on the shared view-version = calibration epoch/spot), headline tiles,
  per-ticker rollup with LV cell, exception-first sortable node table with
  "exceptions only" filter; live-only offline card. Tab wired in `App.tsx`.
- Smoked end-to-end (fetch → calibrate → report: 12/12 ready, median 3.4bp);
  the smoke also exercised the fit-pool BrokenProcessPool inline-fallback in
  the wild (stdin parent can't spawn on Windows — real entry points can).
- Dashboard follow-ups: drill-in to the Parametric tab on row click, prior
  activation column (needs a cheap cached signal), butterfly g-metric for
  overlay models.

**Export/publish workflow SHIPPED (same evening; commercial-MVP arc, item 3;
suite 942 passed, 1 skipped; strict-TS + Vite green).**

- **`GET /export/surfaces`** (`api/export.py` + `routers/export.py`):
  downloads the CACHED calibrations (fitted nodes only — publish what is
  calibrated; same strict no-fit-on-read as /quality) with a
  **reproducibility manifest** (generated-at, app version, data source,
  as-of, fit mode, full FitSettings, calibration-relevant Options toggles,
  settings/options versions, per-ticker snapshot timestamps + data
  versions). `format=json` = full fidelity (241-pt model curves with
  k/strike/IV/total-var, LQD backbone params, the LV grid, per-node quality
  joined from /quality); `format=csv` = one row per curve point for Excel.
  Dated `Content-Disposition` filenames; `tickers=` filter. Parquet deferred
  (pyarrow not a dep).
- **`GET /export/report`** (`api/export_report.py`): the end-of-day publish
  artifact — a self-contained HTML quality report (inline CSS, no external
  assets, email/archive-safe): manifest stamp, summary tiles, per-ticker
  rollup with LV health, exceptions section, full node table, the publish
  rule in the footer. Rendered + screenshot-verified in headless Edge.
- **Quality tab buttons**: "Quality report" (opens in a tab), "Surfaces
  JSON/CSV" (direct downloads) — plain cross-origin navigation, no fetch.
- Sub-0.1bp figures now render as 2 sig figs, not a fake "0.0" (the synthetic
  LV fits are ~0.01bp; report + viewer share the rule).
- Tests: `tests/test_export.py` (4 — never-fits guard, full-fidelity payload,
  CSV↔JSON row parity, HTTP routes incl. dispositions).
- Follow-ups: server-side publish-to-directory (scheduled EOD artifact drop),
  Parquet via optional pyarrow, per-model overlay params in the JSON export.

**Graph attribution panel SHIPPED (same evening; commercial-MVP arc, item 4;
suite 947 passed, 1 skipped; strict-TS + Vite green).** The explainability
readout for the headline differentiator: "this dark smile moved +x bp because
THAT lit node moved through gain g."

- **Math = the update's own arithmetic, not a heuristic.**
  `GraphPosterior` now keeps its observed K⁻ columns
  (`observed_columns`, `graph/posterior.py`) and gains
  `attribution(i) → (gain_row, innovation, contributions)`: with
  K_i = K⁻[i,obs]·S_y⁻¹ and d = S_y·α, node j contributes K_i[j]·d[j] and the
  contributions SUM TO THE DISPLAYED SHIFT to solver precision (locked at
  1e-14 on a hand-built system and 1e-6 bp through the production path,
  `tests/test_graph_attribution.py`, 5 tests).
- **API**: `GraphNodeSmile.attribution` (per-lit-node entries: innovationBp,
  gain, contributionBp, optional direct-edge `edgeBeta` context from explicit
  request edges; largest first, capped at 20 with the tail folded into
  `attributionOthersBp` so the sum stays exact) — rides the existing
  per-node drill-in GET `/graph/extrapolate/nodes/{t}/{e}`
  (`graph_reconstruct._attribution`), no new endpoint.
- **UI**: Extrapolate aside — clicking a node row now opens an ATTRIBUTION
  CARD (`GraphAttributionCard.tsx`: signed contribution bars, gain×innovation
  tooltip, β chips, "others" row, exact-sum footnote); ↗ per row keeps the
  reconstructed-smile drill-in.
- Sanity on synthetic: a dark ALPHA Sep node's move decomposes with calendar
  neighbours dominant (gain ≈ 0.41) and cross-ticker gains ~0.05 — matching
  the LOO finding that calendar coupling carries the skill; sum check exact.
- Follow-ups: attribution for skew/curvature coordinates (same seam, coords
  1/2), per-edge PATH decomposition (research: gains fold all paths), node
  click-selection on the graph CHART itself (today: the aside list), visual
  in-app smoke (run `.\restart.ps1` → Graph → Extrapolate → click a row).

**Benchmark pack HARNESS SHIPPED (same evening; commercial-MVP arc, item 5;
suite 954 passed, 1 skipped).** The 25-asset graph-LOO packaged as a
regenerable validation artifact; the FULL sweep is queued for the user's
window.

- **Capture inventoried**: 3 regimes × 20 days × 25 assets on disk
  (`low_jul2023` day 1 partial at 11 — the resumable capture's interruption
  point; 59/60 days full).
- **`backtest/benchmark_pack.py`**: chunked + RESUMABLE `run` (part file per
  pair-chunk under `results/benchmark/`, existing parts skipped; rows DEDUPED
  on (regime, day, design, R, node) at merge so overlapping smoke/full parts
  can't double-count) + `report` (self-contained HTML: manifest, headline
  skill/ζ tiles, per-regime design×R tables, full-LOO per-asset-kind split,
  methodology; plus machine-readable `benchmark_pack.json`).
  `graph_loo.run` gained `pair_range` for the chunking. 7 tests on the pure
  parts. **`run_benchmark_pack.ps1`** = the user's-window launcher
  (foreground, resumable; the full_loo sweep is hours — tool-managed
  background jobs get killed on this box).
- **Smoked on the real fixtures** (1 pair, liquid_split, R=0): 199 dark
  single-name nodes scored, report rendered + screenshot-verified. Early
  honest signal: dark-name ATM skill ≈ 0 on this calm pre-spike pair — in
  liquid_split only SPX informs the dark names (intl-ETF edges dormant,
  name→name edges connect dark↔dark), ζ std 0.48 = conservative posterior.
  Whether `DARK_BASE_SCALE=0.25` unlocks enough gain (and what the sector
  name→name edges do in full_loo, where names are lit) is exactly what the
  full run answers. *[SUPERSEDED 2026-07-09: the zeros were a topology bug
  (one-way cross edges → transient names → conductance 0), and
  `DARK_BASE_SCALE` proved a dead lever — see the 2026-07-09 wrap.]*
- **NEXT: run
  `powershell -ExecutionPolicy Bypass -File backend\backtest\run_benchmark_pack.ps1`
  in your own window** (resumable; rerun after any interruption), then read
  `backend\backtest\results\benchmark\benchmark_report.html` and record the
  verdict (graph-LOO FINDINGS update + DARK_BASE_SCALE tuning decision).
  NB the report currently on disk is the 1-pair SMOKE render — `report`
  regenerates it from whatever parts exist. *[DONE 2026-07-09 — verdict, root
  cause and resweep recorded in the 2026-07-09 wrap.]*
- **[2026-07-07] First sweep attempt died mid-run + spike regime SILENTLY
  EMPTY — root cause FIXED.** The spike_aug2024 fixtures carry DUPLICATE
  strikes (multiple listings at one strike; XOM 2024-12-20 was the trigger):
  the convex wing repair's anchor slope divided by zero at a core boundary,
  `lsq_linear` got an infinite lower bound, and the ValueError killed whole
  day-pairs (9 empty parts + one doubly-partial one — the per-pair skip only
  prints to the console). Fix in `volfit/calib/convex_deam.py`: anchor slope
  now measured to the nearest STRICTLY DISTINCT strike (`_core_slope`;
  byte-identical on clean chains), unmeasurable slope ⇒ that wing is skipped,
  zero-span butterflies masked in `min_norm_butterfly`. Regression tests in
  `tests/test_convex_deam.py` (7). The failing pair now scores 898 rows (was
  0). Bad spike parts DELETED (the healthy 1-pair smoke part kept); progress
  on disk: high_oct2022 7/10 parts, spike + low_jul2023 to (re)compute —
  relaunch the sweep as above.

**Frontend test harness SHIPPED (same evening; commercial-MVP arc, item 6 —
PHASE 1 COMPLETE).** The frontend had ZERO tests; now:

- **vitest + jsdom + Testing Library** (devDeps; `npm test` = `vitest run`;
  standalone `vitest.config.ts` — no Tailwind plugin needed in tests; JSX via
  esbuild automatic runtime, no React plugin). **13 tests**: pure Quality
  helpers extracted to `src/lib/qualityFormat.ts` (fmtBp sub-0.1bp rule,
  exception-first sort, input immutability), `GraphAttributionCard`
  (contribution rows/signs/β chips/others fold, gain×innovation tooltip,
  close/open wiring, empty-solve state), `QualityViewer` (tiles, exceptions
  filter, offline card + retry) — data hooks mocked; the HTTP contracts stay
  locked by the backend suites. Test files live in src/ and type-check under
  `tsc -b`.
- **Headless-Edge UI smoke** (`npm run smoke:ui` → `scripts/ui_smoke.mjs`,
  puppeteer-core): spawns `vite preview` on :4188 (via the vite JS bin —
  Node ≥20 EINVALs on .cmd spawns; strip ANSI before matching the banner),
  drives every workspace tab, fails on any pageerror / ErrorBoundary
  fallback / empty main, screenshots to `.smoke/` (gitignored).
- **The smoke caught a real production bug on its first run**: the Local Vol
  tab crashed (React #300) whenever the app ran WITHOUT a backend — its
  offline card early-returned BETWEEN hooks, so the hook count changed when
  the session flipped live→mock after mount. Fixed by moving the offline
  return below the last hook (`LocalVolViewer.tsx`); all 8 tabs now render
  offline.
- Follow-ups: hook-level tests with a mocked fetch layer, a smoke variant
  against a live synthetic backend (assert data actually renders), CI wiring
  when a CI exists.

**Quote-derived error bars SHIPPED (same evening; Phase-1 follow-up; suite
958 passed, 1 skipped — the `graph_update_1k` perf rail busted its budget
ONLY under the user's concurrent benchmark-sweep CPU load [dense-BLAS
contention; it passed both earlier full runs today; all other rails 1–52% of
budget under load] — RE-VERIFY `-m perf` after the sweep. Also found + killed
24 orphaned spawn workers accumulated by the racy `shutdown(wait=False)`;
fit_pool now joins on shutdown).** Every calibrated smile now shows "error bars from
the quotes" — the Vola-parity feature, and it was nearly free: the Note 15 §4
measurement machinery (solver Jacobian → R_x = G(JᵀWJ+Λ)⁺Gᵀ with the bid-ask
half-spread as stated noise) already existed; it just only ran with the
filter on.

- `solver_diag` is now retained on EVERY fit (`_slice_task` want_diag always;
  pure side-channel, fits byte-identical; the filter commit hook self-gates
  on mode so filter state is NOT created when off — test-locked). New
  `api/fit_uncertainty.py` computes + caches the measurement per fit key at
  commit (advisory, never raises); records without one (pre-feature cache)
  degrade to the factors route lazily on read.
- `SmileDiagnostics` gains `atmVolStd`/`skewStd`/`curvStd` (None-safe); the
  smile payload reports the DISPLAYED (frozen) fit's uncertainty — a stale
  node keeps its committed σ (keyed by the calibrated pointer).
- UI: SmileChart draws a subtle accent band = current fit ±1.96·σ_atm (level
  band; legend "±1.96σ quotes"); SmileAside shows "ATM 20.5% ±0.15%".
  `tests/test_fit_uncertainty.py` (5).
- Follow-ups: surface σ in the Quality dashboard + exports; per-model handle
  maps (today the LQD backbone prices the uncertainty for overlays too, like
  the filter); an Options toggle if anyone wants the band off.

### 🧭 SESSION WRAP (2026-07-05/06) — v2 verdict (F9–F11); F10 active gate; capture underway

All on **main** (through `a66b016`; suite **921 passed, 1 skipped**).

- **v2 full-regime run analyzed (39,190 steps; `4600c8e`;
  `FINDINGS_observation_filter.md`): F9 — ACTIVE MAP is the best denoiser on
  plain/contradiction days in every regime (beats raw AND the overlay
  posterior, e.g. high-vol contradiction 5.6 vs 9.8 bp raw; ζ std 0.4–1.4);
  F10 — its shock lag traced to the gate being overlay-only; F11 — adaptive Q
  validated at full scale (shock 39–79 bp → 5–8 bp, clean days untouched).**
- **F10 FIXED (`a66b016`):** active-path adaptive gate — a fit-free ATM probe
  of the prepared mids gates the level row, the previous step's innovation
  gates the shape rows; identical factors in the prior builder and the MAP
  bookkeeping. NB the harness's synthetic shock never touches the prepared
  mids, so scenario A/Bs under-report this fix (unit-locked); a v3 run (and a
  shock-the-prepared-chain scenario) can quantify it later.
- User confirmed the in-app visual pass; dark-node precision shipped earlier
  (`78a1fc5`). **25-asset capture COMPLETED 2026-07-06**
  (`run_capture_full.ps1` finished in the user's window — the full-universe
  fixtures are on disk; user-reported, contents not yet inventoried).

**Plan:** next session(s) = **augmenting app features** (user-directed;
productization arc underway, see the wrap above); the capture prerequisite is
now CLEARED for the **25-asset graph leave-one-out** (sector edges lit +
`DARK_BASE_SCALE` validation) *[DONE 2026-07-09 — see that wrap]* and the
temporal/ablation reruns — run those when the app-feature push pauses.

## STATUS — earlier (2026-07-03)

### 🧭 SESSION WRAP (2026-07-03, evening) — Observation Kalman filter Phases 0–3 SHIPPED

The Note 15 observation filter (`Docs/kalman_filtering.tex` — a per-node
temporal Kalman filter on the (ATM, skew, curvature) handles, strictly
separated from prior persistence) is built through its numerical + app layers,
all on **main** (commits `fddddda`, `be8b56f`, `160bd73`, `8a53990`; full
suite **905 passed, 1 skipped**; ruff + strict-TS green). Roadmap + phase log:
**`Docs/observation_filter_roadmap.md`** (read it first — 4 scope decisions
recorded there; the user explicitly confirmed the Jacobian R_t route).

- **Phase 0** — `observationFilterMode` off/overlay/active + knobs
  (`api/schemas.py`, `useOptions.ts`); `api/filter_mode.py` resolver; NEW
  lightweight `AppState._filter_version` (overlay knobs refresh the overlay
  WITHOUT busting fit caches; only off/overlay↔active transitions or knobs
  while active bump `options_version`).
- **Phase 1** — `calib/observation_filter.py`, pure numpy: Joseph-form
  `kalman_update` (+ gain cap, input PSD validation), eq.-Q `process_noise`
  with per-component breakdown, `should_reset`, whitened MAP rows
  (`prediction_prior_residual`, jitter REPORTED), first-order SSR
  `transport_handles`. GOLDEN cross-check: reproduces
  `graph/posterior.posterior_update` to 1e-12.
- **Phase 2** — `calib/observation_measurement.py`: **Jacobian R_t**
  (USER-CONFIRMED) `R = ρ·G·(JᵀWJ+Λ)⁺·Gᵀ` off the calibrators' new
  `solver_diag` seam (LQD/SVI/SIV retain `result.jac` — byte-identical when
  None); regularized eigen-inverse (clamps, never explodes/vanishes); χ²
  inflation; graph floors/caps envelope; factors fallback
  (`filterCovarianceMode`). **UNITS finding:** quote weights are RELATIVE, so
  the builder takes `noise_scale` = stated per-quote noise (bid-ask
  half-spread, floored) on the DATA rows only — R obeys the quadratic
  contract. Band semantics free (inactive hinges ⇒ zero rows).
- **Phase 3** — `api/observation_filter.py` + `GET /smiles/{t}/{e}/filter`
  (`FilterDiagnostics`): update-on-commit hooked into BOTH fit paths
  (`_compute_fit` + `fit_and_commit_slice`), idempotent per
  (data_version, session_version); seeds from `resolve_node_prior`;
  resets = quote-edit/stale reseed, source/as-of wipe
  (`_clear_chain_caches` + `_CHAIN_CACHE_ATTRS` round-trip survival;
  `recalibrate` deliberately keeps the state — a refetch is a new
  observation). Everything advisory — can never break a calibration.

- **Phase 4 (2026-07-04, `90588ab`) — overlay UI SHIPPED.** FilterDiagnostics
  now carries the drawable overlay (LQD backbone RETARGETED to m⁺ via the
  graph `build_atm_coordinates.retarget` seam + 1.96·sd(ATM) band + the m⁻
  prediction curve); frontend: `useObservationFilter.ts`, SmileChart teal
  filter overlay + legend, SmileViewer FILTER badge (gains/ρ/provenance/
  contamination), `ObservationFilterPanel.tsx` in Options (mode + knobs +
  per-expiry diagnostics table). strict-TS + Vite build green. NB SmileChart
  ~600 lines — a future-split candidate. Not yet visually smoked in-app —
  run `.\restart.ps1`, set Options→Observation filter→overlay, Calibrate.

- **Phase 5 harness (2026-07-04, `69caad1`) — temporal backtest BUILT +
  smoked.** `backend/backtest/observation_filter.py` (clones `temporal.py`,
  drives the PRODUCTION `on_fit_commit`): per (T-1,T) pair × expiry, carry the
  T-1 posterior into day T, commit a thinned measurement under scenarios
  thinned/contradiction/shock, score vs raw-measurement + gain-0 baselines +
  ζ + retargeted wing RMS; sweeps covariance route × process noise. SPX
  1-pair smoke (54 steps): **filter denoises (4bp vs 8bp raw) and the
  jacobian route dominates factors on shock pass-through (gain 0.957 vs
  0.57)** — but **ζ std ≈ 27 = posterior overconfidence** (partly
  methodological: score omits the truth fit's own noise R_heldout).
  `tests/test_filter_backtest.py` (5). Results:
  `backtest/results/spike_aug2024_observation_filter.json`.

- **Phase 5 verdict (2026-07-04, `6463668`) — the gate PASSES.** ζ now scores
  against `√(P⁺+R_truth)`; **DIAGONAL_UPDATE shipped** (production fix: the
  full-covariance update let a junk curvature innovation on coarse-strike
  EEM/EFA drag the ATM level through OFF-diagonal gains — 3–28 vol-point
  posterior errors, worse than both baselines); summary split ≤30d/>30d.
  8-asset pilot (666 steps, `FINDINGS_observation_filter.md`): at (jacobian,
  bp=30, >30d) the filter is a CALIBRATED denoiser — err 7.1bp vs 7.6 raw /
  26 gain-0, win 0.73, ζ ~ N(−0.3, 1.3); jacobian beats factors on
  contradiction + calibration. Open: shock lag (adaptive Q), short-dated
  (≤30d) policy, bp 10→30 default (Phase 7 after the full run).
- **Phase 6 (2026-07-04, `f844c15`) — active one-stage MAP SHIPPED,
  default-off.** `build_filter_prior` = the prediction as an UNGATED
  OperatorPriorTarget (stencil legs, λ = s_q²/P⁻ in the fit's unit-weight
  convention); hard-coded persistence auto-exclusion in `resolve_prior_mode`
  (only the deep-tail anchor survives); `service.prior_targets` injects the
  filter target independent of any saved prior; MAP posterior bookkeeping
  P⁺ = G(J_totalᵀJ_total)⁺Gᵀ (all rows unwhitened by the same s_q), capped at
  P⁻, NO second update (Prop. nodouble — the double-count guard test locks
  MAP ≡ Kalman to 1e-10 and detects the wrong architecture).

- **Phase 7 (2026-07-04, `4574af9`) — 3-regime verdict; bp default flipped.**
  Full run (38,181 steps; `run_filter_full.ps1`, resumable — NB tool-managed
  background jobs get killed, the user's own PowerShell window works):
  **F6 `filterProcessVolBpSqrtDay` 10→30 SHIPPED** (one-sided everywhere: ζ
  std → ~1, shock lag 3–8× smaller); **F7 jacobian stays default** (2–3×
  better contradiction rejection every regime; factors better on shocks —
  the adaptive-Q item closes that); **F8** the filter is ~neutral on clean
  liquid days and pays on the noisy tail (the note's success criterion). A
  live-perf fix landed the same day (`fce3341`): seed no longer runs a hidden
  mid fit per node; /filter curves memoized (29ms→0.06ms); FD Jacobian on the
  opt grid.

- **Phase 8 (2026-07-04, `80989e7`) — Note 15 in the series; THE FILTER ARC
  IS COMPLETE (8/8 phases).** `Docs/notes/15_kalman_filtering.tex` (19 pp,
  STYLE_GUIDE-hardened, shipped defaults, TWO case files incl. the EEM/EFA
  off-diagonal blow-up, the backtest-verdict section) + `gen_kalman.py`
  (production-code figures, 42 macros, Appendix C executed vs
  calib/observation_filter.py at 0.0e+00). `Docs/kalman_filtering.tex` kept
  with the SUPERSEDED banner (docstrings cite its labels) + LEGACY_MAP row.

**Next up:** F3/F4 SHIPPED 2026-07-04 (`83800b3` — `filterAdaptiveSigma=3`
innovation-gated Q, shock win → 1.0 without chasing noisy chains; √(30/DTE)
short-dated noise floor; harness `--adaptive`/`--tag`). `active` is now IN the
harness sweep (`c6147db`, `--modes overlay,active`; SPX pilot: the MAP even
edges the overlay posterior, 4.7 vs 5.5 bp, ζ ≈ 1.1 — NB err_post==err_meas
by construction there, baseline = the overlay run's raw column). Remaining
filter follow-ups: a small Note-15 addendum for F3/F4 + the mode sweep, a
full-regime `--modes overlay,active --adaptive` rerun (user's own PowerShell
window: `run_filter_full.ps1` needs those flags added or run per-asset),
visually smoke overlay/active in-app. **Dark-node baseline precision SHIPPED**
(`78a1fc5`: `DARK_BASE_SCALE=0.25` in `graph/precision.py` — the graph-LOO
"dark prior pins the posterior" fix; lit design point byte-identical;
validate/tune on the 25-asset capture). Then the rest of the pre-filter
backlog: the **25-asset capture** (overnight capture jobs, user's window +
flat-file creds), the temporal/ablation reruns on the other regimes, graph
Phase 10 sparse perf. Housekeeping: SmileChart.tsx ~600 lines (split
candidate).

### 🧭 SESSION WRAP (2026-07-03) — R6 on main; R3×R6 ablation; technical notes augmented

Docs + backtest session; all on **main** and pushed (through `fe5feb4`).

- **R6 landed on main.** The Multi-Core SIV 2-core cap + put-wing Durrleman
  regularizer (`sivWingPenaltyPct`, FINDINGS_calibration_arb R6) is now on main
  (cherry-pick `556cf64` + docs merge `45c8a4a`), completing the R1–R6 roadmap.
- **R3×R6 ablation — NEW** (`backend/backtest/ablation_arb.py` +
  `tests/test_ablation_arb.py` + `backtest/FINDINGS_ablation_arb.md`). R3 (convex
  de-Am of the call INPUTS) and R6 (put-wing penalty on the SIV OUTPUT) defend the
  same F4 put-wing butterfly from opposite ends, both default-on — redundant? Fits
  SIV-2 per American node under the 2×2 `{R3}×{R6}`, reads arb from the analytic
  Durrleman g on a grid extended ±2 ATM-std into the wing, scoped to the arb-prone
  population. `ablate_node` is fixture-independent (test drives it on a synthetic
  American chain; CLI `--no-oos` default + `--max-days` bound foreground runs —
  BACKGROUND JOBS GET KILLED on this box, so run foreground in ~2-day chunks,
  ~1.9 min/fixture). **VERDICT: COMPLEMENTARY, not redundant** (captured spike
  EEM/EFA 2d, 38 arb-prone; AAPL/NVDA/JPM contrast): R3 cuts arb ~3× AND *improves*
  in-RMS 92→25 bp (removes the arbitraged de-Am input the SIV chased), byte-identical
  on liquid names (gating confirmed on real data); R6 eliminates the arb but 749 bp
  alone; **`both` = R6's arb removal at 225 bp — R3 makes R6 affordable, validating
  both shipping default-on.** Caveat: 2-day slice; the ±2z grid is harsher than the
  R6 note's metric. Follow-up: sweep `sivWingPenaltyPct` on illiquid names now R3
  absorbs most of the need; rerun the ablation on `high_oct2022` / `low_jul2023`.
- **Technical notes (`Docs/notes/`) synced + augmented.** (1) Notes 03/05/09/00 now
  document R6 (cap + put-wing penalty + hybrid Jacobian), R3 (the convex de-Am wing
  repair), and the ablation verdict — fully cross-consistent (incl. the confinement-
  vs-intrinsic-constraint reconciliation in Note 09). (2) **Verified code snippets
  added to all 15 notes** — inline crux (≤15 lines) + a fuller Appendix C where
  warranted, each distilled from the production module and EXECUTED against it
  (agreement 1e-10…1e-15). All PDFs rebuilt clean with `latexmk`.

**Next up (unchanged priority):** the **25-asset capture** (lights the dormant
name→name / sector-ETF graph edges AND gives cross-asset extrapolation a fair test)
+ lower dark-node baseline precision in `graph/precision.py`; rerun temporal +
ablation across `high_oct2022` / `low_jul2023`; then graph Phase 10 sparse perf.

### 🧭 SESSION WRAP (2026-06-26) — graph leave-one-out backtest (Phase 6) BUILT

The headline differentiator — graph smile-extrapolation — now has a **temporal
leave-one-out harness** (`backend/backtest/graph_loo.py` + `graph_edges.py`;
additive, no production change beyond the already-shipped `capture_snapshot(lv=False)`).
Per consecutive captured pair (T-1, T): freeze T-1 as the active prior, transport it
under SSR R, form the lit innovation `d = calibrated_T − transported_prior`, propagate
through a **directed graph**, and compare the graph posterior for held-out nodes with
their ACTUAL day-T calibration — all 3 handles (ATM/skew/curvature) + reconstructed
full-smile wing RMS — and vs the pure transported-prior baseline (the graph's **skill**).

Design (confirmed with the user 2026-06-26):
- **SSR sweep R∈{0,1}** — R=0 (sticky-moneyness) leaves an underperformer's baseline
  vol unmoved → OVER-credits the graph; R=1 (sticky-strike) bakes in the full leverage
  → UNDER-credits it. The truth is bracketed; both reported. (R=2 omitted.)
- **Both designs** — full_loo (withhold each clean node) + liquid_split (lit=index/ETF,
  dark=single names = the product use case).
- **Directed vol-normalized edges** — calendar β=√(T_to/T_from) high-conductance,
  Index→name β=0.7, SectorETF→name β=0.8, name→name same-sector β=0.6, else 0;
  absolute β=β_vn·σ_from/σ_to. **Direction:** `w_ij`="j informs i" ⇒ a `GraphEdgeInput`
  flows to→from, so "index informs name" = `from=NAME,to=INDEX` (verified + test-locked).
- **Lit calibration runs in mode `off`** (pure market) so the innovation is the genuine
  market-vs-prior move, not a prior-anchored fit; the active prior still drives the
  graph *baseline* via `resolve_priors` (independent of the calibration anchor).

**VERDICT (full spike regime, 18 pairs, 4134 held-out nodes; tables in
`backtest/FINDINGS_graph_loo.md`):**
- **full_loo — the graph DECISIVELY beats transport: ATM skill +37 bp (R=0) / +26 bp
  (R=1), wing +3 to +7 bp, with ζ mean ≈ 0 (UNBIASED) and ζ std 0.72–0.90
  (well-calibrated, slightly conservative).** The "fill a sparse/missing node from its
  lit neighbours" use case works, driven by CALENDAR coupling. The R-sweep brackets
  the true skill at +26 to +37 bp exactly as posed (R=0 over-credits, R=1 under-).
- **liquid_split — cross-asset extrapolation to FULLY-dark names adds ~nothing (ATM
  skill ≈ 0, wing slightly negative).** Two measured causes: the transported prior is
  an excellent same-name predictor at very high baseline precision (a 96 bp SPX
  innovation moves the dark AAPL node 0.01 bp), AND the **8-asset pilot is starved** —
  no US sector ETF, AAPL/NVDA/JPM share no sector ⇒ `name→name`/`ETF→name` edges are
  DORMANT. NOT a verdict against the method — the experiment can't exercise it.
  *[SUPERSEDED 2026-07-09: both "measured causes" were symptoms of a harness
  topology defect (one-way cross edges → names transient → π=0 → conductance
  0 → dark names decoupled). Post-fix, dark-name skill is +7.9…+14.2 bp in
  the spike and +3.8…+7.2 bp out-of-sample in high_oct2022, ≈0 in the calm
  regime — see the 2026-07-09 wrap + FINDINGS_graph_loo.md.]*
- **Two concrete follow-ups** to give cross-asset a fair test: the **25-asset capture**
  (same-sector clusters + sector ETFs light the dormant edges), and a **lower baseline
  precision for DARK nodes** in `graph/precision.py` (a dark target is less certain than
  a lit prior, so it shouldn't pin the posterior — production change, validate on 25).
  *[Resolved 2026-07-09: the capture ran, `DARK_BASE_SCALE` proved a dead lever, and
  the real unlock was the reverse-edge topology fix + reach η.]*
Tests: `tests/test_graph_loo_backtest.py` (taxonomy + direction/√T/vol-norm edge logic).

### 🧭 SESSION WRAP (2026-06-25) — prior-persistence follow-ons DONE

The two open prior-persistence follow-ons (from the 7-mode menu wrap below) are
both closed on **main**:

- **Overlay-hide-on-`off`.** In persistence mode `off` no prior curve is drawn at
  all (pure current market) — `service._prior_overlay` / `_no_fit_prior` and
  `affine_transport.attach_affine_priors` now consult `resolve_prior_mode.draw_overlay`
  and return empty; the SmileChart legend drops the "Prior" entry when the curve is
  empty. `overlay` mode still draws the dotted transported prior (no penalty). The
  calibration was already inert in `off` (Phase 8); this is the matching display fix.
  Guard: `test_priors.test_off_mode_hides_prior_overlay`.
- **Empirical temporal mode-scoring harness** (`backend/backtest/temporal.py`, the
  Phase-8 follow-on flagged in `backtest/README.md`). The ≥2-day prerequisite is met
  — all 3 captured regimes have consecutive days. For every (asset, T-1→T) pair it
  fits T-1's full chain → freezes it as the active prior (`capture_snapshot(lv=False)`,
  a new backward-compatible flag), thins day T to its ATM region (`|k|≤c_atm·σ√τ`),
  refits under each `priorPersistenceMode`, and scores the reconstructed MODERATE wing
  (`c_atm·σ√τ<|k|≤c_wing·σ√τ`, held out) vs the true day-T quotes; `off` is the
  baseline. Sweeps the two flagged defaults (var-swap probe `_VARSWAP_PROBE_STD`,
  operator `priorOperatorBandwidth`); reports per-(mode,bw,probe) median wing RMS /
  median improvement-over-off / win-rate. `tests/test_temporal_backtest.py` (helpers
  + synthetic self-prior end-to-end). **VERDICT** (full spike regime, 1117 nodes +
  a bandwidth×probe sweep; numbers + tables in `backtest/FINDINGS_prior_temporal.md`):
  **`hybrid` (the shipped default) reconstructs the held-out wing ~32 bp better than
  no-prior, ~66% of the time, and wins at EVERY (bandwidth, probe)**; `strike_gap`
  close second; pure `quote_operator`/`smile_factor` never beat off at the median at
  any bandwidth — the reconstruction comes from the tail/strike anchor, not the signed
  RR/BF operators. **So `priorOperatorBandwidth` is NOT a productive lever and is left
  at 0.06; the var-swap probe stays 1.4σ** (probe 1.0 marginally edges it for hybrid —
  the one candidate to confirm cross-regime before flipping a shipped default). **No
  default changed** — the harness confirms the shipped config. Next: rerun across
  `high_oct2022` / `low_jul2023` for regime-robustness.

Full suite **827 passed, 1 skipped** (was 822/1; +4 `test_temporal_backtest.py`, +1
overlay test). ruff + strict-TS clean.

### 🧭 SESSION WRAP (2026-06-25) — short-dated Local-Vol fit FIXED (fixes #1–#2)

Short-dated LV smiles (a true 6-DTE SPY weekly) fit **catastrophically** — 108 bp
RMS / 249 bp max vs the parametric ~47 bp — while normal expiries fit well. Full
diagnose-then-fix arc, all on **main** (commits `5663a73`, `c096b21`; suite **822
passed, 1 skipped**):

- **Phase 0 — measure first** (`volfit/api/affine_diag.py`, a pure per-expiry
  side-channel; `lv_benchmark.py --fixture` prints it). The Bloomberg fixture has
  no expiry < 27 d, so a **true-weekly capture** was taken from Massive Live
  (`capture_massive_weekly.py` → `tests/fixtures/lv_weekly_massive.json`; SPY
  2026-07-01/07-06 weeklies + the long ladder). Root cause: the delta strike axis
  is sized to the LONGEST expiry and clipped to the GLOBAL range, so a narrow short
  smile lands only ~3 vertices on its sharpest curvature. **Ruled out** (measured,
  not guessed): vega floor (1.3× threshold, never triggers), PDE time steps (2→33 =
  no change), local-vol cap, prior/early-stop (inert without a loaded prior), and
  adding time slices ahead of the weekly (a single expiry pins only the time-
  *integral* — measured flat). The residual is short-end quote/de-Am noise the
  rigid parametric averages through but the flexible LV chases.
- **Fix #1 — short-expiry strike coverage floor.** `OptionsSettings.gridXMinPerExpiry`
  (default 8; 0 = legacy axis byte-identical). After the delta axis is built,
  `_augment_per_expiry_coverage` splits the widest IN-RANGE gaps until each expiry
  has ≥ m_min vertices inside ITS OWN traded range — adds nodes ONLY to under-covered
  short-front expiries (even gap-fill; clustering the expiry's own delta nodes left
  wing gaps and stalled at 37 bp). Added to `affine_key`.
- **Fix #2 — short-expiry-aware PDE strike step.** `_pde_dx(rows)` refines the
  shared uniform PDE x-step to 0.3 × the smallest ATM σ√τ, snapped to 1/N so x = 1
  stays a node, clamped to `[1/400, 0.01]`. Normal surfaces stay on 0.01 ⇒
  byte-identical.

**Result (default settings):** weekly 07-01 **108.2 → 23.5 bp** (now *better* than
the parametric 47 bp), 07-06 49 → 14.0 bp, surface 35.8 → 11.5 bp. Bloomberg NVDA
byte-identical, SPY 3.3 → 2.8 bp — **no regression to well-fitting names.** Method &
levers documented in `Docs/localvol_calibration_methodology.md` §4/§9.

**Open follow-on — Fix #3 (optional):** the residual ~23 bp on the 6-DTE is a
near-ATM data-noise outlier (a 20.8% IV spiking from a ~13% smile via de-Am/parity
on clean 1%-spread markets). A robust loss (Huber/Cauchy) on short-dated residuals,
or defaulting very short expiries to fit-to-band, would close the last gap to a
visually clean weekly. Touches the LSQ objective (not just the grid); the
catastrophic regime is already gone, so this is quality polish, not a blocker.

### 🧭 SESSION WRAP (2026-06-25) — prior-persistence 7-mode menu SHIPPED

The prior-persistence redesign of `Docs/prior_persistence_design_options.md` is
built end-to-end (plan + per-phase log in `Docs/prior_persistence_roadmap.md`).
All 7 modes are live (parametric + Local-Vol): **Off · Overlay · Strike gaps ·
Quote operators · Smile factors · Hybrid · Graph only**, selected by
`OptionsSettings.priorPersistenceMode` (the new single source of truth; the legacy
`autoLoadPrior` master was retired — mode=off is the off switch; existing desks
preserved by the store-load migration). Highlights:
- `calib/operators.py` (ATM/RR/BF signed σ-baskets + var-swap) + `calib/factors.py`
  (ATM-local level/skew/curvature) + shared `calib/precision.py` activation gate.
- Parametric (LQD/SVI/Multi-Core-SIV) get direct signed-operator residuals — this
  **fixed the long-standing asymmetry** (SVI/SIV overlays previously got no prior).
- Local-Vol keeps the RR/BF coupling via **signed-basket residuals**
  (`affine_calib.BasketQuote`, a linear functional of leg prices — not per-leg
  quotes that drop the coupling).
- Hybrid = operators + a residual deep-tail strike anchor; two-pass opt-in
  (`priorDataOnlyPrepass`); `GET /smiles/{t}/{e}/prior-diagnostics` + an Options
  mode selector & §9.4 audit panel (`PriorPersistencePanel.tsx`).
- Validated by `tests/test_prior_nodamp.py` (overnight ATM-jump no-damp check).
Full suite **798 passed, 1 skipped**; strict-TS + ruff green. Committed on `main`
(dddd163..); **not pushed to origin.** Open follow-ons: empirical temporal-fixture
mode scoring + tuning the var-swap probe / operator bandwidth (see
`backtest/README.md`); overlay-hide-on-`off` in the smile viewer.

### 🧭 SESSION WRAP (2026-06-22) — read this first

Two threads landed on **main** today (full suite **744 passed, 1 skipped**; ruff +
strict-TS green):

1. **Offline backtest harness** (`backend/backtest/`, see `SPEC.md` + `README.md`)
   — **3-regime pilot complete** (8 assets × 60 days: spike_aug2024, high_oct2022,
   low_jul2023). Capture via the per-contract **REST quotes API** (`rest_quotes.py`,
   `capture.py --source rest`, DEFAULT): ~4.4 min/day, ~65× the flat-file firehose
   (`--source flatfile` fallback), Options-Advanced = no rate limit, historical NBBO
   back to ≥2022. The scaled batches use `run_compute --models …` to drop the
   non-viable SIV-1/2/3.
   **Key results (robust across all 3 regimes):** LQD (8–12) **strictly dominates
   SVI-JW** — faster *and* 2–3× lower RMS, no overfit (LQD-12 in-RMS = 0.31×/0.37×/
   0.45× SVI in spike/high/low); the analytic Jacobian made LQD the speed leader
   too. **Multi-Core SIV cores overfit** (60–75% butterfly-arb; base SIV-0 ≈ SVI).
   The harness flagged a **real recurring LV bug** (`LinearizedJacobian` has no
   `.T`, in the matrix-free GN solver `affine_gn.py`) on 6 surfaces across regimes
   (NVDA, NDX) — worth fixing.
   **Next batches:** full **25-asset universe**; **graph leave-one-out** (Phase 6,
   runnable now — sticky-moneyness + SSR 1.0); **NN-dataset emit** (Phase 7, feeds
   off `volfit/data/columnar.py`). NB: the real `VOLFIT_MASSIVE_KEY` is shadowed by
   a stale 4-char env var (restart.local.ps1's `if (-not …)` guard) — force-set it.
2. **Structural perf backlog — COMPLETE** (#2–#6; details in that section below).

Workflow note: normal dev = edit JS/Python + `.\restart.ps1`; the PyInstaller `.exe`
(`build_exe.ps1` → `\dist`) is rebuilt ONLY on an explicit "compile to .exe".

### 🧪 OFFLINE BACKTEST HARNESS — pilot validated (2026-06-22, `backend/backtest/`)

A standalone harness (additive; imports `volfit`, changes nothing) to measure
calibration **precision / speed / breaks** across models & hyperparameters vs an
SVI-JW baseline, attribute end-to-end time (fetch / de-Am / fit), and (next) score
graph leave-one-out vs the transported-prior baseline. Full plan + every parameter:
**`backend/backtest/SPEC.md`**; how-to + module map: `backend/backtest/README.md`.

Two phases:
- **Capture** (`capture.py`) — reconstructs the **15:45-ET NBBO** chain per
  (asset, day) from the Massive/Polygon **`quotes_v1`** flat files (real bid/ask;
  new `quotes_store.py` reader — the live `FlatFileStore` reads only trade aggs).
  Writes immutable JSON fixtures; resumable; one daily firehose scan shared across
  the universe. **Nightly window 23:30–06:30** (`--window`) so the machine is free
  by day; a day in progress finishes (never killed mid-scan).
- **Compute** (`run_compute.py` → `dispatch.py`, `replay.py`) — replays fixtures
  offline through a `StaticProvider`/`AppState`; per node de-Am once then sweep
  **SVI-JW · LQD-6/8/10/12 · SIV-0/1/2/3** under **{mid, haircut(0.5)} × {equal,
  tv_density}**; uniform precision (in-sample + leave-3rd-out OOS + Durrleman
  no-butterfly g(k)), timing, arb. `analyze.py` → Pareto / time-attribution / break
  report.

**Sample set** (`universe.py`): pilot 8 / full 25 assets (SPX·NDX·RUT indices
European multi-root, EEM·EFA ETFs, mega-caps + sector breadth single names); 3
regimes — `spike_aug2024`, `high_oct2022`, `low_jul2023` (low/stable relaxed to
2023). Ladder = monthlies + 3 weeklies, DTE 7–400, ≤10/node, all strikes.

**Pilot findings (Aug-5-2024 spike):** end-to-end clean; **LQD-10/12 dominate
SVI-JW** (≈4 bp vs 25 bp mid on liquid SPX, **0% vs 50% butterfly-arb**, OOS ≤
in-sample); **Multi-Core SIV overfits + arb-breaks even at 1 core** (slow, dropped
SIV-4); de-Am ≈ 15% of an American node (fit dominates), 0 for European indices.

**Cost finding:** the `quotes_v1` day-file is the OPRA firehose — one non-splittable
gzip; **Aug-5 scan ≈ 8.85 h**. Paid once/day, shared across assets (reduced to a
~1.7 MB Parquet cache). So a 20-day window ≈ ~3 weeks of nights. A faster
per-contract REST-quotes path (`/v3/quotes` at the 15:45 timestamp) is the
mitigation to probe.

**Remaining:** graph leave-one-out (Phase 6 — runs once ≥2 nights captured; under
**sticky-moneyness + SSR 1.0** transport), the NN-training dataset emitter (Phase 7,
Parquet), LV `wall_ms_pde_*` timing wiring, and the REST-quotes feasibility probe.

### 🖥️ DESKTOP `.exe` — single-origin refactor SHIPPED (2026-06-21, branch `feature/desktop-exe`)

Bifurcated off `main` (main unchanged, continues independently). Makes FastAPI
serve the React build on **one origin** — the prerequisite for a PyInstaller
`.exe`. Additive only; `create_app` and the dev workflow (`restart.ps1`, Vite on
:5173 + CORS) are byte-identical. New: `backend/volfit/api/frontend.py`
(`mount_frontend`/`find_frontend_dist`), `backend/desktop.py` (single-origin
entry point — auto-picks a free port, opens the browser, app-data DB default),
`volfit.spec` + `build_exe.ps1` (PyInstaller scaffold), and `api.ts`'s
`API_BASE_URL` now relative in prod builds (`window.location.origin`). Verified
in-app: UI + `/assets/*` + API all serve from one origin with API routes taking
precedence; 4 new tests (`test_frontend_mount.py`), full suite green. **The
PyInstaller freeze succeeds** — `build_exe.ps1` → `dist\VolFitter.exe` (~135 MB
one-file). **Now a native windowed app**: `desktop.py` serves uvicorn on a daemon
thread and opens the UI in a pywebview WebView2 window (browser fallback;
`VOLFIT_DESKTOP_MODE=window|browser|server`); `console=False` so logs go to
`%LOCALAPPDATA%\VolFitter\desktop.log`. App icon = a volatility-smile tile
(`assets/make_icon.py` → `volfitter.ico` + `frontend/public/favicon.ico`); exe
`icon=` set; `tbb12.dll` bundled (no warning). Verified the frozen window renders
the app + drives live API calls. See `DESKTOP.md`. Remaining (optional):
code-signing, an installer for shortcuts.

### 🚀 GRAPH SMILE-EXTRAPOLATION — production path SHIPPED (2026-06-21, branch `feature/graph-extrapolation`)

The prior-anchored production extrapolator of
`Docs/graph_extrapolation_implementation_plan.md` is built end-to-end (v1 = the
plan's Phases 1–6, plus Phase 8 backtest). The manual-shift sandbox
(`/graph/solve`, `/graph/nodes`, `/graph/autotune`) is **untouched** (Amendment A);
the production path is entirely additive. The spine:

    transported prior → lit-calibration innovation → graph posterior increment
                      → dark reconstructed smile    → quote comparison

- **Phase 1** `api/graph_universe.py` — `build_selected_universe(state)` over the
  user-selected **lit+dark nodes only** (Amendment C); lattice topology reused.
- **Phase 2** `api/graph_nodes.py` — `resolve_node_prior` by the locked hierarchy
  (active_transported → nearest_expiry_transported → today_bootstrap → flat_atm),
  each carrying provenance + `valid_for_validation`. Handles read exactly off the
  LQD backbone at h=0, numerically off the transported curve otherwise.
- **Phase 3** `api/graph_extrapolation.py` + `POST /graph/extrapolate` — innovation
  `d = calibrated − transported_prior` on lit nodes; dark nodes never observations.
- **Phase 4** `graph/precision.py` — observation precision = 1/rms² × quote-density
  × bid-ask × freshness; baseline precision = provenance tier × age × transport;
  per-handle floors/caps; design point reproduces the legacy `[1e6,1e6,1e4]`.
  Factor breakdown surfaced in diagnostics (Amendment F).
- **Phase 5** `api/graph_reconstruct.py` + `GET /graph/extrapolate/nodes/{tk}/{exp}`
  — retarget posterior handles → arb-free smile + band + prior/lit overlays + quote
  metrics (weighted RMS, inside-spread hit rate, standardized residual for quoted
  DARK nodes only). Lazy per-node payload (Amendment E).
- **Phase 6** `graph/beta.py` — `L_dir^β = (I−K∘B)ᵀΠ(I−K∘B)`, PSD, per-handle;
  beta=1 byte-identical (golden guard). `crossBeta` + explicit `edgeBetas`
  (weight=trust and beta=amplitude are separate fields, Amendment D).
- **Phase 8** `api/graph_backtest.py` + `POST /graph/backtest` — leave-one-node-out
  over validation-clean nodes; residuals + standardized residuals + aggregate
  calibration (rmseBp, ζ mean/std); bootstrap priors excluded (Amendment B).
- **Frontend** — Sandbox/Extrapolate toggle in the Graph workspace
  (`useGraphExtrapolation.ts`, `ExtrapolatePanel.tsx`): runs the solve + backtest,
  lists per-node prior→posterior moves with provenance, flatAtm + crossBeta knobs,
  drill-in; the chart draws the full selected universe in Extrapolate mode.
- **Phase 5 live overlay (DONE)** — drilling into a node overlays its GET
  node-smile reconstruction (violet posterior curve + shaded credible band) on the
  live quotes in the Smile viewer, with a GRAPH provenance + quote-metrics badge
  (RMS / in-band hit / ζ) and a dismiss ✕ (`graphFocus.tsx`, `useGraphNodeSmile.ts`,
  `SmileChart` overlay props). Strict-TS green; verified in-app.

- **Phase 7 edge editor (DONE)** — user-supplied sparse bi-directed weighted graph
  with per-edge weight (trust) + beta (amplitude). `GraphEdgeInput`; an explicit
  edge list overrides the lattice over the selected node set; persisted overrides
  round-trip (`settings_persist` graph_edges, GET/PUT `/graph/edges`,
  `/graph/edges/lattice` seed); solve resolves request → persisted → lattice.
  `_stationary_distribution` gained a teleport-damped fallback so a sparse/
  disconnected (reducible) user graph no longer fails the singular solve
  (irreducible graphs byte-identical). Frontend: an Edge editor in the Extrapolate
  panel (`EdgeEditor.tsx`, `useGraphEdges.ts`) — seed/add/remove/edit + persist.

- **Phase 9 model-agnostic reconstruction (DONE for parametric)** — the node-smile
  reconstruction renders in the CHOSEN model (LQD/SVI/Multi-Core SIV), not always
  LQD: LQD is the exact target, SVI/Sig are fitted to it (`graph_reconstruct
  ._native_slice` via `build_display_fit`) so their ATM handles still match the
  propagated ones; band carried onto the native curve; metrics + lit overlay use
  the displayed model; `GraphNodeSmile.model` shown in the overlay badge.

- **Phase 9 LV projection (DONE)** — LV has no cheap 3-param transport, so the
  graph-extrapolated parametric smile is the projection TARGET: `graph_lv
  .project_to_lv` reuses each expiry's live strike grid + forward, swaps the target
  total variance for the graph reconstruction, and runs the standard affine LV
  calibration (via a minimal `affine_fit._fit(rows=)` seam). Arb-free (Dupire),
  reproduces the extrapolated smiles. `POST /graph/extrapolate/lv/{ticker}`; the
  LocalVol viewer has a "Graph-extrapolated" source toggle (`useAffine` swaps the
  endpoint).

Merged to **main** (`3cc909f`, Phases 1-9). Tests: `test_graph_{extrapolation,
node_priors,extrapolate_solve,precision,reconstruct,reconstruct_models,beta,
backtest,edges,lv}.py` (~68 new). **Full suite 718 passed, 1 skipped.**

**Next up (remaining):**
- **Phase 10** — sparse perf (deferred; only when selected universes ≫ 10³ nodes):
  `prior.py:67,72` dense N×N inverses, autotune O(7·n_obs·N³) → the note's §8
  matrix-free path (sparse solves + Hutchinson diagonal).
- **(optional) graph→LocalVol drill-in** — a direct UI jump; the source toggle
  already lets the user view the LV projection in the LocalVol workspace.
- **Pre-graph robustness fixes (2026-06-21)**: `/graph/nodes` iterates the ACTIVE
  universe (was provider watchlist → 500 on an inactive ticker); empty universe no
  longer 500s; `state.known_ticker` so read-path guards (market/history/massive-IV)
  accept user-added tickers; Save/Fetch priors flash a confirmation.

---

## STATUS — earlier (2026-06-20)

### ✅ CAPSTONE (2026-06-20) — LV calibration perf branch complete; see the methodology note

On branch **`perf/localvol-calibration`**. The Local-Vol (piecewise-affine) calibration
was re-engineered end-to-end for speed. **The full methodology + every optimisation +
everything shelved is now consolidated in
`Docs/localvol_calibration_methodology.md`** (the standalone reference; read it first).
Headline final state:

- **Default solver = matrix-free Gauss-Newton** (`OptionsSettings.lvSolver="gn"`,
  `affine_gn.py`): avoids scipy TRF's dense SVD (~52% of an eval). Gated to the smooth
  MID fit target + the Numba march; band/haircut/var-swap/banded-march fits keep TRF.
  ~1.3–1.65× over TRF; surface within ~0.25 vol-bp (a slightly different local optimum
  on stiff data — accepted at the default).
- **Compiled march** (`affine_march.py`, Stage 6′): a `@njit` no-pivot Thomas march with
  the sensitivity columns as the contiguous SIMD inner loop + fused source — **6.5× the
  scipy/LAPACK banded march**, numerically exact (≈1e-15). `numba` is a dependency with a
  graceful banded fallback. The default `lvFastKernel=True`.
- **Stall-based early-stop** (Stage 8, `lvEarlyStop=True`): stops the cold fit at the
  best iterate when the option-block misfit stalls — ~1.45× (SPY) to ~3.3× (NVDA),
  +0.1–0.25 bp. The lever that scales the whole fit.
- **Parametric Dupire cold-start seed** (Stage 2b / `#1`): seeds θ from the parametric
  surface's local variance — ~1.3–1.8× on cold fits.
- **Sparse reg block in the GN operator** (`#3`): ~1.29× at 440 vtx, negligible at 220.
- **Cumulative:** the LV cold fit is ~**3–6×** over the original banded baseline (scaling
  with grid size); recalibrations were already ~instant (Stage 2a warm start).
- **Shelved (documented in the note, §7):** Stage 3 coarse grid (biases θ), Stage 6 first
  Numba attempt (~1.2×, wrong loop order), Stage 7 Rannacher (~1.1× + arb risk, opt-in
  off), GN-for-band-mode (non-smooth), `tr_solver='lsmr'` in trf, thread/process
  parallelism (GIL).

Full suite **632 passed, 1 skipped**; ruff + strict-TS build green; golden byte-identical.
**Open levers (incremental only):** vectorise `sens_at`, a better GN preconditioner, the
future non-tensor bowtie grid (where the SVD genuinely dominates), a smoothed band
objective for GN. The order-of-magnitude wins are spent.

### 🛠 The journey (2026-06-20, kept for the reasoning trail) — Stage 5 GN first judged non-viable, then reversed

On branch **`perf/localvol-calibration`**. Stage 5 (matrix-free Gauss-Newton,
backlog #1) was built, benchmarked on real data, found **NOT a speed-up at
tensor-grid sizes, and shelved gated-off**. Honest finding (corrects an earlier
synthetic-only overclaim):

- **Built (correct, retained as a bowtie-regime seed):**
  `backend/volfit/models/localvol/affine_gn.py` — `LinearizedJacobian` (matrix-free
  `apply_jacobian`/`apply_jacobian_transpose` + column-equilibration preconditioner)
  + `gauss_newton`, a projected Levenberg–Marquardt loop whose step is solved by
  preconditioned `scipy.sparse.linalg.lsmr` (no JᵀJ, no SVD; bounds via active-set
  projection). `test_affine_gn.py` (8) — identities + golden/heavy agreement +
  fallback — all pass. Reachable only via `calibrate_affine(gn=True)`.
- **Why shelved (SPY/NVDA Bloomberg benchmark, cold-start, 143→440 vtx):** GN is
  **~1.4× SLOWER than TRF everywhere** and every run shows the TRF-fallback message —
  GN does NOT converge within the 200-eval cap. Pre-fallback (SPY 220 vtx) it
  converges only by ftol at **nfev≈339** (vs TRF's 200 cap) to the **same surface**
  (RMS 2.71 bp; 11/220 nodes at a bound). **Removing the SVD made fits slower**, so
  at ≤440 vtx the per-eval bottleneck is the **PDE sensitivity march**, not the SVD —
  the SVD-O(m³) wall is a ≳1000-vtx (future non-tensor bowtie) phenomenon. The clean
  synthetic rail (zero-residual, in-bounds, GN converges in 8 evals) hid this.
- **Disposition:** removed the `lvSolver` Options field + UI selector + `affine_fit`
  wiring (app always uses TRF); kept `affine_gn.py` + `calibrate_affine(gn=)` + tests
  + the synthetic perf rail (relabelled a correctness/bound guard, not a win).
- **Stage 6 (Numba march) ALSO REVERTED (~1.2×):** the compiled Thomas march is
  numerically exact (≈1e-15 vs banded) but only 1.1–1.26× at 220–440 vtx — the
  per-eval cost is the irreducible O(N_t·N_x·m) multi-RHS sensitivity solve, which
  LAPACK already does near-optimally, so compilation can't beat it. `affine_march.py`
  removed, `numba`/`llvmlite` uninstalled. Third dead-end on the "faster per eval"
  axis (with Stages 3 & 5) — all the same wall: the PDE march is inherent + efficient.
- **Stage 7 (Rannacher 2nd-order time stepping) BUILT but ~1.1× + arb risk → default
  OFF.** CN-after-implicit-startup with the full analytic CN sensitivity recurrence;
  validated 2nd-order (21× more accurate than implicit at dt=0.02; sens vs FD ~3e-11;
  golden byte-identical on the implicit default). But on SPY/NVDA it cut N_t 2.7×
  (102→37) yet only ran **~1.12× faster** — the CN sensitivity step is ~2× costlier
  per step (explicit-half matvec + dual-level sources), ~cancelling the fewer-steps
  win, and the N_t-independent assembly+SVD dilute the rest; CN also broke arb-freedom
  on NVDA gridX=12 (not monotone). Kept as a tested opt-in (`timeScheme`,
  `test_affine_time_scheme.py`), default implicit.
- **FOUR distributed-cost dead-ends (Stages 3, 5, 6, 7):** the cold-fit cost spreads
  ~evenly across the march, the Jacobian assembly, and the optimizer linear algebra,
  so no single per-eval/per-step lever moves the total.
- **Stage 5 (matrix-free GN) REVISITED & SHIPPED opt-in — viable now that the march
  is cheap.** Its first verdict (non-viable) was reversed: GN AVOIDS trf's dense SVD,
  which Stage 6′ showed is **52%** of an eval, and with the cheap Numba march GN's
  no-SVD evals win. Re-benchmarked (numba + early-stop): **GN ~1.3–1.65× faster than
  trf** (better surface on SPY g20). **Now the DEFAULT** (`lvSolver="gn"`), gated to the
  smooth MID fit target + Numba march; band/haircut (non-smooth objective), var-swap,
  and banded-march fits keep trf. The ~0.25 bp surface difference vs trf (a slightly
  different local optimum on stiff data; the NVDA +0.25 bp gap is inherent) is accepted
  at the default. Hardened the GN early-stop: track best among ACCEPTED iterates only,
  count rejects as no-progress, conservative window/rtol (18/3e-3) + looser lsmr (1e-6).
  `gn_lsmr_tol` threaded; `lvSolver` in `affine_key` + Options selector;
  `test_affine_gn.py` GN early-stop test.
- **Stage 6′ — Numba vectorized-Thomas march SHIPPED (6.5× the banded march).** The
  first Numba try (~1.2×) used a column-OUTER scalar Thomas; the real lever was the
  loop order. `affine_march.py`: no-pivot factor-once Thomas + the k sensitivity
  columns as the CONTIGUOUS INNER (SIMD) loop + fused source ⇒ **6.1–6.9× vs LAPACK
  `dgbsv`** on the march (220–440 vtx; numerically exact ≈1e-15). Wired
  `solve_affine_dupire(engine=)` / `calibrate_affine(engine=)` / `OptionsSettings
  .lvFastKernel` (default ON, in `affine_key`) + Options toggle; basis stored as one
  contiguous `(n_steps,n_int,m)` array (banded indexes views ⇒ golden byte-identical);
  `numba` added to deps with a graceful banded fallback. `test_affine_march.py` (5).
  **Amdahl:** the march is only ~32% of an eval (optimizer/SVD is 52%, assembly 14%),
  so 6.5× march → ~1.3× whole-fit alone, but **combined with early-stop the cold fit
  is 1.7× (SPY) – 3.8× (NVDA) faster**. New bottleneck = the optimizer SVD (52%).
- **Stage 8 — stall-based early-stop SHIPPED (the win that works).** `calibrate_affine`
  tracks the best option-block misfit and stops the cold fit once it stalls (returns
  the best-cost iterate); `OptionsSettings.lvEarlyStop` (default ON, window 12 /
  rtol 5e-3, in `affine_key`) + Options toggle; `stall_window=0` ⇒ byte-identical.
  Fewer evals multiply march + assembly + optimizer *together*, so it scales the whole
  fit: measured (SPY/NVDA gridX=20 vs full 200-eval) **3.3× on NVDA** (16.8→5.1 s, a
  convergence knee) at +0.25 bp and **1.45× on SPY** (31.2→21.5 s, no knee) at +0.10 bp
  — adaptive (stops when converged, runs while improving); warm recals unaffected.
  `test_affine_early_stop.py` (3). This is the one measured lever that actually works,
  and it stacks with the (opt-in) Rannacher scheme.

Separately, a strike-grid fix landed: `_delta_strike_nodes` now densifies by
splitting the single widest gap one node at a time (matching `_time_nodes`) instead
of doubling every gap — so SPY/NVDA land on the same `gridXNodes` floor (was 11×21 vs
11×37 from the doubling overshoot). Full suite green; ruff + strict-TS green.

### 🛠 LATEST (2026-06-20) — LV calibration perf branch + SPY regression FIXED

On branch **`perf/localvol-calibration`** (off main). Two threads, full
roadmap in `Docs/localvol_calibration_perf_roadmap.md` (Stages 0–6):

- **LV calibration perf — Stages 0/1/2a/4′ SHIPPED.** Stage 0 = instrumentation
  (`AffineFitDiagnostics`: counts, optimizer counters, wall-time split;
  `solve_affine_dupire(timing=)`; perf rails) — pure side metadata, golden
  byte-identical. Stage 1 = `calibrate_affine` `x_scale='jac'` + tols 1e-12→1e-8
  (two toggles), nfev 23→12 on golden, surface identical. Stage 2a = warm-start
  `theta0` from the previous surface (`affine_fit._seed_theta`, `theta_ref` pinned
  flat → flat seed byte-identical), recalibration nfev 19→1 / wall ~38× faster.
  Stage 4′ = backward **source-PDE variance swap** (`models/localvol/varswap_pde.py`,
  note eq. variance_swap_source_pde), analytic dI/dθ + dI/da vs FD, grid-robust;
  gated by `OptionsSettings.varSwapMethod` (default static → byte-identical).
- **SPY "26 bps RMSE" regression ROOT-CAUSED + FIXED (commit ff853be).** The
  convex-wing constraint selected EVERY vertex ≤5Δ regardless of data; at the
  user's saved `gridXNodes=20` it stacked convexity penalties onto densely-quoted
  put strikes and forced the wrong wing on low-vol SPY (NVDA's convex wing hid it).
  Fix: confine `convex_cols` to vertices below the deepest quote (the
  extrapolation tail only). SPY 25.7→2.6 bp. Diagnosed via a captured Bloomberg
  benchmark (the bug only reproduces with the persisted DB settings:
  fitMode=haircut + gridXNodes=20 + convexWing — read from
  `backend/data/volfit.sqlite`).
- **Bloomberg SPY+NVDA benchmark committed**: `backend/capture_benchmark.py` →
  `backend/tests/fixtures/lv_benchmark_bloomberg.json` (2534 quotes);
  `backend/lv_benchmark.py` replays it offline; `tests/test_lv_benchmark.py` guards
  the convex-wing regression (opt-in `-m perf`).
- **Stage 3 (coarse calibration grid) ATTEMPTED, NON-VIABLE — reverted.** Coarse
  calibration biases θ by up to ~26 vol points (≫ tolerance), SPY went nan, modest
  speedup. Re-confirms the prior rejection ([[calibration-perf]]). The per-eval
  win must come from Stage 5/6, not grid coarsening.

**Next (fresh session): Stage 5 — matrix-free Gauss-Newton** (= backlog item #1
below; the ~86 s heavy-grid dense-SVD wall). Then Stage 6 (Numba `nogil` march +
parallelism). Full suite **604 passed, 1 skipped** (ruff + strict-TS green).

### 🚀 STRUCTURAL PERF BACKLOG (added 2026-06-19) — ✅ COMPLETE (2026-06-22)

**All actionable items done** (see the ✅ tags on each below): #2 analytic LQD
Jacobian (~2.3–2.9×), #3 per-ticker version counters + chain-cache reconciliation
(A/B/C), #4 SSE status push, #5 GZip + payload slimming, #6 columnar Parquet/DuckDB
history (core). #1 (sparse GN) stays shelved (non-viable at tensor-grid sizes).
Deferred, non-blocking follow-ons: #5 per-expiry deltas, #6 live dual-write
integration, and the analytic Jacobian for the var-swap/prior LQD configs.

From an end-to-end perf review (two agents: data/architecture + calibration
compute). The localized **quick wins are already SHIPPED** on branch
`perf/quick-wins` (commits "perf(batch A)" + "perf(batch B)"): pooled provider
HTTP, concurrent multi-ticker fetch, SQLite open fast-path, leaner frontend
polling (idle backoff + tab-hidden pause + `useSurface` request coalescing +
stable density-refetch key); looser LQD trf tolerances (1e-15→1e-10),
deterministic warm-start of the independent surface sweep, and a version-keyed
prepared-(de-Am'd)-quotes cache. The **structural items below remain** (graph
sparse-linalg deliberately excluded for now). Ordered by expected wall-clock /
effort. The numbers tracked: a ~533-vertex affine LV fit ~86 s; LQD12 slice ~35 ms;
graph 1k-node ~700 ms.

1. **Sparse Gauss-Newton for the piecewise-affine LV surface** ⚠️ **ATTEMPTED,
   NON-VIABLE at tensor-grid sizes (2026-06-20, Stage 5 — shelved gated-off; see the
   LATEST entry + `affine_gn.py`).** The benchmark showed the dense SVD is NOT the
   bottleneck at ≤440 vtx (removing it made fits slower — the PDE march is), so the
   per-eval win must come from Stage 6 (Numba march), not the outer linear algebra;
   revisit GN only with the future ≳1000-vtx non-tensor bowtie. *The single
   heaviest path in the app* (~86 s @ 533 vertices, hits the 200-eval cap). The
   roughness / convex / front-tie Jacobian blocks are 3-nnz/row but stored dense
   and `np.vstack`'d (`models/localvol/affine_calib.py:425,441,443`), and trf's
   trust-region does a **dense SVD on an (n_res × ~1000) Jacobian**. Reformulate as
   Gauss-Newton on the **sparse-assembled** normal equations (`scipy.sparse` /
   `lsqr` — distinct from the rejected `tr_solver='lsmr'`), keeping the small dense
   data block. Target: 86 s → seconds. This is ROADMAP Stage 5 (non-tensor delta
   bowtie + adjoint gradient). **See the full implementation plan in
   `Docs/localvol_calibration_perf_note.md`** (written 2026-06-19, one-liners →
   structural rewrites, with file:line).

2. **Analytic Jacobian for the LQD slice fit** ✅ **DONE 2026-06-22.** Was a
   (P+1)-eval finite-difference Jacobian rebuilding the quadrature every column.
   `models/lqd/jacobian.py` propagates `dC/dθ` in one quadrature pass: the priced
   call's implicit `z_k` dependence cancels (`dA/dz = -e^k u(1-u)` at `z_k`), so
   `dC/dθ = ∂A/∂θ|_{z_k}` = `hermite_eval(z_k; ∂a_z/∂θ, ∂da_dz/∂θ)`, with every
   nodal sensitivity from differentiating the build_slice pipeline (g affine in θ;
   `dQ'/dθ = Q'·φ`). Covers mid + band fits, the reg block, the calendar slack, and
   the A_R barrier; var-swap / prior-anchor configs fall back to FD (not yet
   differentiated). `calibrate_slice` passes `jac=` when those are absent. Measured
   **~2.3× (order 6) → ~2.9× (order 12)**, same converged cost (≈1e-6). Validated
   vs 3-point FD (`test_lqd_jacobian.py`); golden LQD fits byte-unchanged.

3. **Per-ticker version counters + chain-cache reconciliation** ✅ **DONE
   2026-06-22.** (A) `forwards_version` and `events_version` were global
   (`api/state.py`), so one market-setting / event-calendar edit invalidated EVERY
   ticker's fits — worst case ~100 tickers × ~10 expiries = 1000 forced refits. Now
   **per-ticker dicts** (`forwards_version(ticker)` / `events_version(ticker)`),
   folded into `fit_key` / `affine_key` / the local-vol view key — a name's
   rate/dividend/forward-policy/event-calendar edit refits only that name.
   `settings_version` / `options_version` stay **global** (model / penalties / grid
   genuinely affect all tickers — correct to refit everyone); `data_version` /
   `active_prior_version` were already per-ticker. (B) Changing one expiry no longer
   re-pulls the whole ladder: `_reconcile_chain_selection` (`state_universe.py`)
   PRUNES the cached snapshot + forwards in place when the new selection is a subset
   of the cached chain (deselect / re-select) — **no provider fetch, surviving nodes
   keep warm fits** (per-node fit keys unchanged) — and only forces a full **atomic**
   re-fetch when a genuinely new expiry is added (so the chain never mixes
   spot/instants). Tests: `test_api_forwards.py` (cross-ticker isolation),
   `test_chain_cache.py` (subset-no-refetch + warm-fit reuse, add-refetches).
   (C) `spot_version` was also global, so one name's spot move re-transported every
   other name's derived grid (localvol extraction). Now split: the GLOBAL
   `spot_version` stays the client refresh signal in the status payload, and a new
   PER-TICKER `spot_version_for(ticker)` keys the derived-grid cache — a SPY move
   re-transports only SPY's grid. `test_spot_version.py` (per-ticker spot, global
   signal intact).

4. **SSE push for `{epoch, spotVersion}`** ✅ **DONE 2026-06-22.** The 500ms status
   poll + `refreshViews()` fan-out is replaced by a Server-Sent-Events stream
   `GET /calibration/stream` (`routers/workflow.py`) that pushes the
   `CalibrationStatus` payload only when it changes (250ms in-process watch +
   15s keep-alive; `text/event-stream` is auto-excluded from GZip so it flushes
   live). `useWorkflow.ts` consumes it via `EventSource` and runs the same
   idempotent `applyStatus` (epoch/spot diff → `refreshViews`); the poll stays as a
   fallback (relaxed to a 5s scheduler-only refresh while the stream is healthy,
   speeds back up if it drops), dropped when the tab is hidden, reconnected on
   fit-mode change. Worst case (no SSE / mock) = the prior polling exactly.
   `test_sse_status.py`; live-smoked under uvicorn. (SSE chosen over WS: one-way,
   native browser auto-reconnect, no upgrade/proxy quirks.)

5. **Slim + incrementalize payloads.** ✅ **DONE 2026-06-22 (GZip + downsampling).**
   `GZipMiddleware(minimum_size=1024, compresslevel=6)` added inside CORS
   (`api/app.py`) — ~2.4–2.6× on the dense payloads (stacked densities, surface),
   transparent, tiny polls uncompressed (`test_gzip.py`). Viewport downsampling was
   already in place (curves strided to ≤`MAX_CHART_POINTS`=241, surface 81/expiry,
   term 80), so the raw payloads were already modest. **Remaining (deferred):**
   per-expiry deltas — pairs with #4's "what changed" event, do alongside it.

6. **Columnar history (DuckDB/Parquet)** ✅ **CORE DONE 2026-06-22 (additive).**
   `volfit/data/columnar.py` — `ColumnarHistory`: snapshots written one Parquet
   file per `(ticker, date)`, queried via DuckDB with column pruning + `ts`
   predicate pushdown. Provides the VolStore-compatible analytical reads
   (`snapshot_at` / `latest_snapshot` / `list_snapshots`, round-trip-faithful) PLUS
   the capability SQLite is poor at — `scan_quotes(tickers, start, end)`, a
   multi-snapshot columnar scan (the feed for the Phase-7 neural-operator dataset /
   historical studies) — and `export_from_sqlite` to migrate existing capture
   (idempotent / de-duped). `test_columnar.py` (4). **Deliberately NOT wired into
   the live hot path:** SQLite stays the source of truth (its single-snapshot reads
   are already indexed/fast); the live dual-write + read-through-with-fallback is
   the separately-reviewable last mile. The columnar layer is shared with the
   backtest harness (Phase 7).

> (Graph sparse linear algebra — the two dense O(N³) inversions per coordinate in
> `graph/prior.py:67,72`, autotune O(7·n_obs·N³) — was identified but EXCLUDED from
> this backlog per the request. Revisit when the graph solver becomes a bottleneck.)


### 🛠 LATEST (2026-06-19) — Data-source reach + trigger-gated workflow + prior/UX fixes

A data-layer + workflow session. Headlines:

- **Non-US Bloomberg names (indices + stocks).** `BloombergProvider._security` now
  handles three shapes case-insensitively (the app uppercases every symbol, which
  had destroyed the yellow key): a full security re-cased (`"SPX INDEX"` →
  `"SPX Index"`, `"SAP GY EQUITY"` → `"SAP GY Equity"`), exchange-coded equity
  shorthand (`"SAP GY"`/`"VOD LN"`/`"7203 JT"` → `… Equity`), and bare → default
  `yellow_key`. Symbol search now covers **equities + indices** (was EQTY-only;
  `bloomberg_search` queries both yellow keys, indices first, de-duped). So "add
  underlying" works for non-US/index Bloomberg tickers end-to-end (frontend passes
  the symbol verbatim). **Massive (Polygon/OPRA) and Yahoo are US-options-only**
  (verified live: every non-US Yahoo listing returns 0 expiries) — no non-US
  underlyings available there beyond US-listed ADRs / US index options.

- **Bloomberg status light fixed (was stuck red "no Terminal" with the Terminal
  open).** xbbg 1.3.0's `is_connected()` is **lazy** — False until the first data
  request creates the engine, and `feed_status` deliberately issues no billable
  request. `session_connected` now brings the engine up first via the quota-free
  `_get_engine()` (a local bbcomm connect, NOT a reference request), so the light
  reads real-time green from a fresh process. Live-verified green.

- **Bloomberg daily-quota burn cut.** Bloomberg meters UNIQUE SECURITIES/day and
  an option chain is hundreds–thousands of contracts, so a few fetches tripped
  `DAILY_CAPACITY_REACHED`. Two amplifiers fixed: (1) `spot()` is **overridden** to
  one underlying `PX_LAST` (the base default re-pulled the WHOLE chain per spot
  poll); (2) **strike windowing** — live fetches keep only strikes within
  `[0.5,1.5]·spot` (ctor `strike_window`, `None` to disable), cutting the per-fetch
  security count several-fold (the far tails carry no liquidity anyway).

- **TRIGGER-GATED WORKFLOW (the live server; serve.py `gated=True`).** No fetch /
  no calibration until a button is pressed — on startup or universe selection the
  app stays quiet. Mechanism: a `gated` flag on `AppState` (tests stay ungated, so
  the suite is byte-identical). Gated: `snapshot()` is cached-only (only the Fetch
  button `refresh_chain` and Calibrate's `ensure_chain` hit the feed);
  `service.displayed_base` returns None instead of bootstrapping a fit; the smile
  shows **quotes-if-fetched → dotted prior-if-any → stale-fit-if-any → "No fit yet"**
  (`SmileData.hasFit`, `_no_fit_smile_payload`); every multi-node view skips
  uncalibrated nodes, single-node views degrade cleanly (no 500s); Calibrate
  **auto-fetches** the chain first (`_ensure_chains`); the LV/affine surface is
  gated the same way (`_empty_affine_response`, `AffineFitResponse.hasFit`).
  `GET /universe` + the **lit/dark map** + `resolve_expiry` now use the expiry
  **selection metadata** (not parity forwards), so the ladder and Lit/Dark panel
  populate and toggle immediately on a universe edit — before any fetch. Default
  **autoCalibrate OFF** in the gated server (set in AppState when no saved pref;
  schema default stays ON for tests). New `test_gated_workflow.py` (10 tests).

- **Universe expiry-picker: composable + optimistic + debounced.** Fast de-selects
  no longer clobber each other (each `toggle` read the same stale snapshot and PUT
  a full-set replacement → only one removed). Now a synchronous `selectedRef`
  composes edits, checkboxes/count update optimistically, and ONE debounced PUT
  carries the final set. `useSmile.refreshUniverse` got a monotonic sequence guard
  so out-of-order `GET /universe` responses can't freeze a stale count.

- **Smile charts: observed quotes in bright RED, bolder** (Parametric + LV), so the
  market stands out against the fitted curve.

- **Fetch priors fixed (was a no-op / wiped the live smile).** (1) The on-the-fly
  prior ladder switched the global as-of to a past close and back, and the restore
  cleared the live chain caches — which the gated workflow no longer re-bootstraps,
  so the live smile/quotes vanished. `fetch_all` now wraps the as-of round-trip in
  `AppState.capture_chain_state()`/`restore_chain_state()`, making it transparent
  to the live surface. (2) The freshness ladder bypassed a deliberately-past saved
  prior (used the saved snapshot only if newer than prev-close), so you never saw
  YOUR prior. Now a **saved snapshot always wins** (a prior IS a chosen past
  observation); recalc-at-prev-close is only the fallback when nothing is saved.
  The active prior is drawn dotted and **transported to current spot** (the
  transport machinery was already correct). 2 new prior regression tests.

Full suite green (584 + the new gated/prior tests; 1 live-optional skipped); ruff +
strict-TS build green. Verified via TestClient/HTTP; not visually smoked in-app
(the user holds :8000/:5173) — run `.\restart.ps1` to see it live.

### 🛠 PREVIOUS (2026-06-18) — Local-Vol grid redesign + put-wing fixes (user-confirmed in-app)

The biggest recent thread is a Local-Vol (affine surface) overhaul that fixed bad
short-dated RMSE and a diverging / under-priced deep put wing on high-vol names
(NVDA), all detailed in the "Done & verified" log below. In order: **delta-spaced
strike vertices** (Stage 1), **spacing-aware roughness** (Stage 2), a **convex-wing
constraint**, a **√T time axis with visible grid hyperparameters** (Stage 3), a
**short-end front tie** (Stage 4), an **adaptive local-vol cap** (the hard 60% cap
was starving high-vol put wings — user-confirmed fixed), and **left-wing linear
extrapolation below x_min** with the slope a free calibration variable when a
var-swap quote is set (so the LV var-swap matches LQD). All gated, byte-identical
when off; the note's golden example is untouched. **Still open from this thread:**
Stage 5 (non-tensor delta bowtie + adjoint gradient for the ~1000-vertex regime)
and the var-swap-from-parametric toggle (seed the LV var-swap target from the
prevailing parametric model and auto-fit the wing slope to it).

### ✅ RESOLVED (2026-06-17/18, user-confirmed in-app) — Backend↔Frontend calibration sync (was TOP PRIORITY)

The fragile, edge-triggered refresh is replaced by a **level-triggered calibration
epoch** — a real architectural fix, not another edge patch. `AppState._calib_epoch`
is a monotonic counter bumped in `set_calibrated_ptr` ONLY when an already-calibrated
node moves onto a new fit_key (a genuine recalibration that changes the displayed
fit); a first-ever bootstrap or an identical re-point does NOT bump it (so no churn /
no refetch loop under autoCalibrate ON). It is surfaced on `GET /calibration/status`
(`CalibrationStatus.epoch`). `useWorkflow.poll` now compares the polled epoch to the
last-seen value and `refreshViews()` whenever it advances — covering the explicit
Calibrate button, auto-calibrate-on-fetch, the streaming refit, AND progressive
per-node commits during a running job, for ALL mounted views regardless of which tab
is open. This is immune to missed running→idle edges, fast single-node jobs, and
background/scheduler calibrations. The old `wasRunning` edge is gone; `spotVersion`
still drives pure-transport refreshes. End-to-end verified (TestClient, the user's
exact autoCalibrate-OFF flow): Apply freezes the LQD fit (stale, epoch unchanged),
Calibrate advances epoch 0→1, `/smiles` then reports `sigmoid` with `stale=false`.
3 new tests in `test_calibration_workflow.py` (epoch advances only on real recal,
no churn on repeated reads under autoCal ON, model-info reflects the displayed model).

**Follow-up (2026-06-18) — the per-mode calibrated-pointer leak (the residual
"visualized smile stays stuck" bug).** After the epoch fix, a node viewed in a
NON-mid fit target (bid-ask / haircut) still stayed frozen/STALE forever while
never-visualized nodes updated fine. Root cause: the calibrated pointer is keyed by
`(ticker, ISO, MODE)`, but EVERY calibrate/status/fetch endpoint hardcoded
`fit_mode="mid"` (the function defaults) and the frontend `calibrate` sent no mode —
so Calibrate re-pointed the "mid" pointer while the viewed "bidask"/"haircut" pointer
was never touched. Fix: (1) the frontend `useWorkflow` now threads the VIEWED
`fitMode` as `?fit_mode=` on `/calibration/status`, `/calibrate` and `/fetch/options`
(TopBar passes `session.fitMode`); (2) the backend records the last-viewed mode
(`AppState.last_fit_mode`, set on every `GET /smiles`) and the workflow endpoints
resolve `fit_mode or state.last_fit_mode`, so even a bare `POST /calibrate`, the
scheduler's auto-fetch and `stream_refit` target the mode actually on screen, not
always mid. End-to-end verified (TestClient): a haircut smile goes stale on a model
switch and a bare `/calibrate` clears it + shows the new model. 2 new tests.

Shipped alongside: the Parametric **diagnostics aside now shows the displayed model
family + hyperparameters** (LQD Legendre degree N, Multi-Core SIV effective core
count R — capped by the quote budget, so faithful to what the chart draws; SVI-JW has
none) via `SmileData.modelInfo` (`service.model_info`, read off the actual displayed
slice so a frozen node names the model it was last calibrated with). A "Stale" pill
sits next to the model label.

---

**Done & verified (pytest green incl. 4 perf + 1 live-optional skipped, `git log --oneline` tells the story):**

- **[2026-06-18] Local-Vol fix — left-wing linear extrapolation below x_min
  (was flat-clamped → var-swap too cheap).** The P1 surface clamped σ(x,t) flat
  for x below the lowest strike vertex (`affine.basis` clipped to the hull), so
  the deep-put local variance stopped rising and the model var-swap came in below
  LQD. Now the left wing continues LINEARLY toward x=0 with slope `a` × the first
  cell's slope (`AffineVarianceSurface.left_extrap_a`; right wing stays flat, the
  cap does NOT apply in the extrapolation region — variance rises freely, positive
  by construction in the put wing). `a` is set by: **var-swap quote present → `a`
  is a FREE calibration variable** (the deep-put tail steepness is fitted to hit
  the var-swap, with an analytic dPrice/da PDE sensitivity — `basis_components`
  splits the basis into flat-base + linear-delta, `precompute_dupire_steps(...,
  with_left_lin=True)` + `solve_affine_dupire(left_a=, fit_left_a=)` append the
  da-column, `calibrate_affine(fit_left_a=)` optimises `[θ, a]` jointly);
  **else convex wing ON → fixed `a` = `leftWingSlopeMult`** (default 1.5, steeper
  rising wing); **else `a` = 0** (flat, the historical behavior — byte-identical,
  golden note test untouched). New tunable `OptionsSettings.leftWingSlopeMult`,
  folded into `affine_key`; Options "Left-wing slope ×" control. 5 new tests
  (flat/linear/steeper values; analytic da vs finite-difference; free-`a` reduces
  the var-swap error). ruff + strict-TS green. NB: verify in-app that NVDA's
  var-swap now matches LQD with a var-swap quote set.

- **[2026-06-18] Local-Vol fix — adaptive local-vol CAP (was a hard 60%).** The
  affine calibration box-bounded every nodal local vol to [5%, 60%]
  (`AffineFitRequest.varLo/varHi`), a hard constraint. On a high-vol name (NVDA)
  the deep-put LOCAL variance must run well above 60% (local vol in the wing is
  materially higher than implied), so the optimizer clamped and the put wing
  diverged for Δ<20 — while SPY stayed under the cap and matched LQD perfectly.
  The cap is now ADAPTIVE (`affine_fit._lv_bounds`): max(60%, `lvVolCapMult` ×
  the highest observed IV across the surface), capped at a 400% safety ceiling;
  the 5% floor is unchanged (low-vol names unaffected). New tunable
  `OptionsSettings.lvVolCapMult` (default 3.0), folded into `affine_key`. The
  resolved bounds are surfaced in `GridInfo.capVol`/`floorVol` and shown in the
  Options grid summary ("LV bounds 5%–270%") + an "LV cap ×" control. 4 new tests
  (`_lv_bounds` scales/floors/ceiling; grid-info cap tracks the multiplier).
  ruff + strict-TS green. NB: still to verify in-app on NVDA 17-Jul-26 (the deep
  put wing should now reach).

- **[2026-06-18] Local-Vol grid redesign — Stage 4 (short-end front tie).** The
  unconstrained `t = 0` vertex row had no quotes and leaked into the shortest,
  most-curved smile (it enters the Dupire integral over `[0, T₁]`). New soft
  penalty `sqrt(W)·(θ[0,:] − θ[1,:])` per strike column (`calibrate_affine`
  `front_tie_weight`) — a one-sided time difference pinning the `t = 0` row to the
  first (data-identified) row in the τ clock (so events are already handled). Gated
  by `OptionsSettings.frontTie` / `frontTieWeight`, **on by default** (a mild
  stabilizer, weight 1e-2); weight 0 / off ⇒ byte-identical (no extra residual
  rows, golden note test untouched). Folded into `affine_key`. Options UI: "Front
  tie (t=0 → first row)" toggle + weight. 2 new tests (`test_affine_grid_design.py`:
  off=byte-identical, the tie shrinks ‖θ₀ − θ₁‖ on a time-varying surface);
  option-defaults updated. ruff + strict-TS green; affine/options/golden green.

- **[2026-06-18] Local-Vol grid redesign — Stage 3 (sqrt(T) time axis) +
  visible/consistent grid hyperparameters.** Time vertices are now built by
  `affine_fit._time_nodes`: the base set is always 0 + a short-end node at the
  sqrt-T midpoint of [0, T₁] (= T₁/4, decoupling the unconstrained t=0 row from
  the first, most-curved smile) + every lit expiry; `gridTNodes` (default **10**)
  is a FLOOR on the positive time vertices — the widest sqrt(T) gaps are split
  until reached, never dropping an expiry (was: subsample/cap). Applies in both
  strike modes. The grid build was factored into one shared `_resolve_grid` used
  by BOTH the fit (`_fit`) and a new read-only `grid_info` / `GET /fit/affine/
  {ticker}/grid-info` (`GridInfo` schema), so the Options panel shows the ACTUAL
  resolved grid ("Resolved grid for SPY: 11×13 = 143 vertices (delta, N convex-
  wing) · 9 expiries", with an "Apply to refresh" hint while edits are pending) —
  the hyperparameters are now visible and provably consistent with what the fit
  builds. Options UI relabel: "Time nodes (floor; 0 = per expiry)". 5 new tests
  (`test_affine_grid_design.py` ×2 time-axis base/floor; `test_api_affine.py` ×2
  grid-info matches fit / tracks options; option-defaults updated). ruff +
  strict-TS green; affine/options/workflow/priors suite (68) green.

- **[2026-06-18] Local-Vol grid redesign — Stage 1 (delta-spaced strikes) +
  Stage 2 (spacing-aware roughness) + convex-wing constraint.** Fixes the two
  reported LV symptoms (left wing too concave; short-dated RMSE) at the vertex
  level. (1) **Delta strike axis** (`OptionsSettings.gridStrikeMode`, default
  `"delta"`): `affine_fit._delta_strike_nodes` places strike vertices at the
  symmetric `{1,2,5,10,25,40,50}Δ` set on a standardized-moneyness axis
  `k = ±σ*·√T*·Φ⁻¹(Δ)` (σ* = the longest expiry's ATM vol, T* = max lit tau),
  clipped to the OBSERVED `[k_lo,k_hi]` with `x=1` forced in — dense near ATM,
  controlled wing reach. `gridXNodes` becomes a FLOOR (default 12; midpoints
  inserted only to reach it); `"linear"` keeps the legacy uniform-in-x axis.
  (2) **Spacing-aware roughness** (`affine_calib.second_difference_rows_spacing`
  via the cell-width-normalized `_d2_coeffs`): the roughness operator now uses
  the REAL vertex positions (true curvature, exact for quadratics) instead of
  the index-space `(1,-2,1)` which over-smoothed the widely-spaced wings; reduces
  EXACTLY to the legacy stencil on a uniform grid, so the note's golden example
  is byte-identical (`calibrate_affine` falls back to the index form when
  `reg_nodes` is None). (3) **Convex-wing constraint**
  (`OptionsSettings.convexWing` / `convexWingWeight`, off by default): a soft
  hinge `√W·relu(−D²σ)` per time row penalizing concavity of the VOL row in x at
  the vertices at/left of the 5Δ-put strike (`wing_convexity_stencils`, analytic
  subgradient Jacobian); byte-identical when off (no extra residual rows). All
  three fold into `affine_key` so a change re-fits. Var-swap wiring in the affine
  path AUDITED and confirmed correct (gated by `varSwapEnabled`/`varSwapWeightPct`,
  uses the tau clock consistently with the parametric `service.varswap_target`,
  surfaces the model level, includes var-swap-only expiries) — locked with a
  regression test. Options UI: "Delta strike axis" + "Convex wing (< 5Δ)" toggles
  + weight, "Strike nodes (floor)" relabel. 10 new tests (`test_affine_grid_
  design.py` ×8: uniform-grid equivalence, exact-curvature on non-uniform grid,
  stencil math, off=byte-identical, penalty convexifies a concave wing;
  `test_api_affine.py` ×2: delta axis dense-near-ATM, var-swap pull) + the two
  grid-semantics tests updated. ruff + strict-TS build green.

  **Still to do (deferred from this redesign — the user's point 5):**
  * **Stage 5 — non-tensor delta bowtie + adjoint gradient.** Place true
    per-maturity delta vertices (a fanning point cloud, Delaunay-triangulated —
    the model already supports it) and switch the gradient to the note's adjoint
    (eq. (adjoint_grad), O(1) in vertex count) to make the max-vertex ceiling
    (~1000) tractable. Touches `second_difference_rows*`, the basis modes,
    transport, prior snapshots and the frontend tensor assumptions — large.
  * **Var-swap → parametric toggle.** A switch that seeds each node's default
    var-swap level from the prevailing PARAMETRIC model's fair variance and
    forces the LV surface to calibrate to it (so LV var-swaps inherit the
    parametric view unless overridden).

- **[2026-06-18] RMS error refined: calibration-consistent + smile AND surface,
  shown the same way in both workspaces.** New `volfit/calib/rms.py`
  `node_error_terms` returns `(Σ wᵢeᵢ², Σ wᵢ)` for a node, where the per-quote
  error eᵢ is the **distance to the chosen fit target** — `model − mid` in "mid"
  mode, else the band VIOLATION `max(model−hi,0)+max(lo−model,0)` (0 inside the
  bid-ask / haircut band, mirroring `calib.band`) — weighted by the **active
  scheme** (equal / TV-density), plus an optional **var-swap** term (model vs
  quoted var-swap vol at the var-swap penalty weight). Pooling the terms across a
  ticker's expiries gives the whole-surface RMS. Parametric: `service.
  weighted_rms_error` now takes `fit_mode` and routes through the helper, new
  `service.surface_rms_error`, `SmileData.surfaceRmsError`; `SmileAside` shows
  "RMS — smile" + "RMS — surface" (%). Local-Vol: `affine_fit` computes per-expiry
  `AffineSmile.rmsError` + `AffineFitResponse.surfaceRmsError` on the reconstructed
  surface's own IVs via the SAME helper (factored `_model_vol_at`, reusing
  `service.varswap_target` for the var-swap weight); the LV aside shows the same
  "RMS vol error — smile / surface" block. So bid-ask fits read ~0 RMS while the
  curve sits inside the band, and the number matches what the calibrator minimized.
  Verified over HTTP (mid 7bp / bidask ~0 / haircut ~1bp). 7 new tests
  (`test_rms.py`); the existing equal-weighting `rmsError == plain RMS vs mid`
  invariant (mid mode) still holds.

- **[2026-06-18] LV Smile gains the x-axis chooser + Densities reach k_min=-1.4.**
  (1) The Local-Vol **Smile** sub-tab now has the same strike-axis selector as the
  other views: `LocalVolSmile` plots its geometry in the chosen display coordinate
  (`axisTransform` per the single smile's forward / ATM vol / model, ticks via
  `axisDisplayTicks`), and `smile` joined the LV `AXIS_MODE_VIEWS`. (2) The stacked
  **Densities** overlay (both Parametric and Local-Vol) now extends its left tail
  to **k_min = -1.4** (matching the smile/surface range) in log-moneyness — and to
  the transform of -1.4 in the other axis modes. New `analytics.stacked_density_
  arrays(slice, k_min)` (Breeden-Litzenberger on a grid widened via a new
  `numeric_density(half_floor=)` arg, kept `k >= k_min` with the upper tail still
  central-mass trimmed); Parametric `stacked_densities` uses it, and `AffineSmile`
  gained a `densityExt` field (left-extended BL density on the reconstructed smile,
  allowed to taper to ~0 unlike the strictly-positive PDE `density`) that the LV
  overlay prefers. Hardened `numeric_density` to edge-fill non-finite wing variance
  (the LQD endpoint scales overflow past the data), so the wide grid stays finite.
  `DistributionArrays.u/quantile` are now optional (a density-only curve omits
  them). 1 new test (`test_stacked_densities_reach_k_min`); the stacked test's
  ≥0 + area∈(0.8,1] invariants still hold (0.99–1.00).

- **[2026-06-18] X-axis: wider display range + selectable coordinate on the
  overlay/surface views.** (1) Every drawn curve/mesh now extends to at least
  **k ∈ [-1.4, 1.0]** (asymmetric — the put wing reaches further) instead of the
  old symmetric ±1: shared `service.K_DISPLAY_LO/HI`, used by `model_curve`,
  `surface.surface_payload` and `run_scenario` (densities stay probability-mass
  trimmed). (2) The **strike-axis display mode** (ln(K/F) / Strike / %ATM / Δ /
  normalized) — previously only on the Smile — is now available on **Densities,
  Surface / IV Surface, and Stacked IV** in BOTH the Parametric and Local-Vol
  workspaces. Because those views span multiple expiries, the transform is
  per-curve: each expiry re-coordinates its own k by its own forward / ATM vol /
  smile (`lib/axisModes` gained `makeVolAt`, `axisTickLabel`, `axisModeLabel`).
  `OverlayCurvesChart` took a `formatX` prop (Densities + Stacked IV transform
  their series' xs and pass a mode-aware tick formatter); `SurfaceMesh` computes a
  **per-vertex** display-x (the 3D sheet shears under strike/Δ — still a valid
  rectangular-connectivity mesh) gated by an `axisMode` prop, with the k-brush
  unchanged. Backend payloads gained the per-expiry context the modes need:
  `SurfaceResponse` already had `forward`/`atmVol`; `StackedDensityItem` gained
  `forward`/`atmVol`/`vol` (IV at each x, for Δ); `AffineSmile` gained `forward`.
  All 529 tests green (the `>= -1.0` model-curve assertion still holds at -1.4);
  strict-TS build green. Not visually smoked (user's app holds :8000/:5173).

- **[2026-06-18] Local-Vol "Density" → "Densities" + Parametric "Stacked
  densities" → "Densities".** The Parametric sub-tab was relabeled; the Local-Vol
  one now overlays EVERY reconstructed expiry's Breeden-Litzenberger density
  (built client-side from each `AffineSmile.density`, like the LV Stacked IV /
  IV-surface), replacing the single-expiry chart.

- **[2026-06-18] Bottom STATUS BAR — narrates what the engine is doing.** Replaces
  the progress hints that crowded the TopBar buttons (per the user's "explicit what
  the engine is actually doing" request). New `volfit/api/activity.py`
  `ActivityReporter`: a thread-safe STACK of in-flight activities (most-recent
  shown, restores the outer frame on pop, monotonic `seq`), pushed only at COARSE
  boundaries so it never slows a fit. Instrumented: fetch (`workflow.fetch_options`/
  `fetch_spots`/`stream_refit` → "Fetching SPY quotes from Yahoo"), per-node
  calibration (`service._compute_fit`/`fit_and_commit_slice` → "Calibrating SPY
  2026-07-17 (LQD)", with a "de-americanizing"/"fitting <model> smile" detail),
  LV surface (`workflow._affine_thunk` → "Calibrating SPY local-vol surface"),
  and the read-path computations at the router level (term/density/surface →
  "Fitting … term structure" / "Computing … densities" / "Building … IV surface").
  Surfaced on `GET /calibration/status` as `ActivityInfo activity` (no new poll).
  Frontend: `state/workflowContext.tsx` lifts `useWorkflow`/`useDataSources`/
  `useAsOf` into ONE shared provider (App wraps TopBar + the new `StatusBar`), so a
  single poll loop feeds both surfaces; the poll is now adaptive (500ms while the
  engine is active, 1500ms idle). `components/StatusBar.tsx`: a thin footer that
  narrates the activity message + detail with a gauge (determinate node-count for
  the calibration job, indeterminate otherwise, per-stage accent colour) and, when
  idle, shows "Ready" + a summary (lit/stale nodes, next auto-fetch countdown,
  as-of, active source + status light). `WorkflowControls` trimmed to a MINIMAL
  CUE — static labels + a subtle indeterminate bar/disabled on the in-flight
  button (the detailed labels + the progress gauge moved to the bar). 7 new tests
  (`test_activity.py`: stack semantics, monotonic seq, thread-safety, status
  surfacing, fetch/calibrate narration); ruff + strict-TS build green. Verified
  end-to-end over HTTP (the activity field serializes; a concurrent reader sees
  every node's "Calibrating … (LQD)" narration mid-job). Not visually smoked in-app
  (the user's own app held :8000/:5173) — run `.\restart.ps1` to see it live.

- **[2026-06-18] Calendar-arbitrage constraint made MODEL-AGNOSTIC (was LQD-only).**
  The convex-order constraint lived only on the LQD backbone (`calib/calendar.py`
  asset-share curve `A(z)`, threaded into `calibrate_slice`); the SVI and Multi-Core
  SIV *display overlays* (`api/fit_models.build_display_fit`) were fit per-expiry with
  ZERO calendar awareness, so `enforceCalendar` did nothing for them (worked well on
  LQD, crossed freely on SVI/Sig). Now both overlay families enforce Gatheral's
  equivalent surface condition — total variance non-decreasing in maturity at every
  fixed k, `w_far(k) >= w_near(k)` — via a soft hinge `sqrt(calendarWeight)·max(floor −
  w_model(k), 0)` (`calibrate_svi`/`calibrate_sigmoid` gained `calendar_k`/
  `calendar_floor`/`calendar_weight`; sigmoid applies it only in the final refine
  stage). The previous (shorter-T) overlay is threaded ascending-T as `prev_display`
  through `service.display_overlay`/`fit_and_commit_slice`, the `fit_surface` loop, the
  WS route, and the coupled Calibrate job (`workflow._coupled_ticker_items`). Gated by
  the SAME `enforceCalendar` toggle + `calendarWeight` knob; byte-identical when OFF or
  on the first expiry (golden tests intact). Same documented caveat as LQD: a
  single-node `_compute_fit` has no cross-expiry context, so coupling holds until such
  a refit. **Fix (same day):** the floor was first evaluated on the fixed wide grid
  `k ∈ [-1, 1]`; SVI's linear wings make a steep short-dated slice extrapolate to far
  higher wing variance than a flatter long-dated one, so `w_near(±1) > w_far(±1)` read
  as a PHANTOM violation in a no-data region and (at weight 1e6) flattened the far SVI
  fits — reported live on NVDA (sep-26) and SPY (jun-27). The floor is now confined to
  the expiry's TRADED log-moneyness range (`calendar.variance_floor_grid_from(k)`, used
  by `display_overlay`): calendar arb is only meaningful where prices are observable.
  LQD/sigmoid math untouched. 11 new tests (`test_overlay_calendar.py` ×9 incl. the
  wide-grid regression + byte-identical no-ops for both families; `test_calibration_
  workflow.py` ×1 prev-overlay threading for non-LQD). **User-confirmed clean in-app
  (2026-06-18): the NVDA sep-26 and SPY jun-27 SVI fits come back clean with
  enforceCalendar ON.**

- **[2026-06-17] Fix: Parametric panel not refetching after Calibrate (model switch
  looked inert).** With autoCalibrate OFF, switching model → Apply → Calibrate left
  the smile + diagnostics byte-identical: the only post-Calibrate refresh was
  `useWorkflow.poll` catching the job's `running:true→false` EDGE (every 1500ms),
  which a fast single-node fit finishes between — so the chart kept showing the
  frozen pre-calibration fit. Fix: `calibrate` (and `fetchOptions`, which can
  auto-calibrate) now `awaitCalibration()` — poll `/calibration/status` to idle
  (bounded, with a startup grace) — THEN `refreshViews()`, guaranteeing the views
  refetch the finished fit regardless of job speed. Backend was correct throughout
  (raw `/smiles` already differed per model). Verified in-app: the A_L diagnostic
  flips 0.074 (LQD) → 0.000 (SVI) on switch+Apply+Calibrate. Frontend-only.

- **[2026-06-17] Local-Vol gains a "Stacked IV" sub-tab (Parametric parity).** The
  LV workspace now overlays every reconstructed expiry's total variance
  w(k)=σ²·τ on shared axes (built from the affine smiles' own `model` + `tau`,
  reusing `OverlayCurvesChart`), non-crossing ⟺ no calendar arb — exactly the
  Parametric "Stacked IV" view. Tab order: Smile · Density · Term · LV surface ·
  IV surface · Stacked IV · Table. Frontend-only; verified in-app (screenshot:
  4 nested non-crossing curves for ALPHA). Parametric's Stacked IV was already a
  static, always-present sub-tab (confirmed).

- **[2026-06-17] Surface tab quoted in the event-variance clock (t→tau fix).**
  `surface.py` built the 3D mesh as `sqrt(w / prepared.t)` (calendar) while the
  Smile/Term use `sqrt(w / prepared.tau)` (event-variance), so with an event
  calendar active the Surface tab's vols (and its own atmVol marker) disagreed with
  the Smile. Now the mesh uses `tau`; `SurfaceResponse` exposes `tau`, and
  `StackedVarianceChart` plots `sigma^2 * tau` (recovers the price total variance w,
  non-crossing ⟺ no calendar arb). No-event case unchanged (tau==t). Model
  consistency was already correct (every Parametric sub-tab uses `displayed_slice`/
  `displayed_*`, never defaulting to LQD under an SVI/Sig overlay). 1 new test.

- **[2026-06-17] Startup restores the last saved/loaded universe.** A new
  `last_universe` pointer in `app_settings` (set by `universe_service.save_current`
  + `load_saved`, cleared by `delete_saved`) is read in `create_app` via
  `universe_service.restore_last_universe`, which calls a new no-fetch
  `AppState.restore_universe(tickers, selections)` — the active ticker list is set
  directly (network-free, like the default watchlist) and any custom expiry picks
  are stashed in `_pending_selections`, applied lazily in `_ensure_selection` once
  each ladder resolves. Best-effort (missing store/pointer or a deleted universe ⇒
  the provider's default watchlist). Frontend unchanged (`GET /universe` just
  serves the restored set). 5 new tests.

- **[2026-06-17] Prior anchor delta-set widened + tunable (follow-up to the
  in-app verification finding).** The default delta-locations were 10/25/40Δ
  (span ≈ ±0.16 for a 3M node) — narrower than wide chains, so the anchor never
  reached the sparse wings. Now `DEFAULT_DELTAS = 2/5/10/25/40Δ` per side + ATM (11
  anchors), with the **var-swap prior carrying the aggregate tail below ~2Δ** (where
  the prior is only its own extrapolation and Black vega collapses). Added a vega-
  normalizer cap (`MAX_INV_VEGA_RATIO = 25×` the most-liquid anchor) so a deep point
  can't dominate. The delta set is now a tunable **`OptionsSettings.priorAnchorDeltas`**
  (per-side forward deltas in (0,0.5); ATM always added; bumps the options version)
  with an Options "Prior-anchor Δ (%, per side)" comma-list control. 3 new tests
  (deeper reach, vega cap, default count).

- **[2026-06-17] Prior framework Phase C — Bayesian data-gap anchor (DONE; the
  framework R1–R5 is complete).** `volfit/calib/prior.py` rewritten: the anchor now
  pulls the fit toward the **transported active prior** (R4: spot-consistent with
  the live quotes) at **delta-locations** (10/25/40Δ puts+calls + ATM, placed from
  the prior smile) plus a companion **var-swap** moment. Per-location precision =
  the **data gap** `λ·max(ρ_desired − ρ_observed, 0)·Δx` — ρ_observed a Gaussian
  KDE of the live quote log-moneyness, ρ_desired uniform or time-value (reuses
  `FitSettings.weightScheme`) spread over the wider delta span — so dense-quote
  zones ignore the prior and sparse wings lean on it; the var-swap weight fades
  with the unmet-coverage fraction. Works for ALL models (vega-normalized price
  residuals into `calibrate_slice` via `prior_anchor`/`prior_var_swap`) AND the LV
  surface (extra `OptionQuote`s + `VarSwapQuote` in `affine_fit._prior_anchor_quotes`,
  tol = vega·VOL_TOL/√precision). Gated by `autoLoadPrior` (λ = `priorAnchorWeightPct`).
  A fetch bumps a new `active_prior_version` folded into `fit_key`/`affine_key` so a
  fetched prior re-anchors instead of serving a stale cached fit. Byte-identical
  when no active prior (golden tests intact). 9 prior-anchor tests (data-gap
  concentrates in wings, mechanism pulls sparse wings to the prior, affine quotes
  gated, cache-bust). Supersedes the Phase-10 near-wing autoLoadPrior anchor.

- **[2026-06-17] Prior framework Phase B overlays — LocalVol + Term.** The dotted,
  spot-updated prior now also overlays the **LocalVol smile** (`AffineSmile.prior`/
  `priorTransported`, attached post-cache/post-transport in `affine_payload` via
  `affine_transport.attach_affine_priors`) and the **Term structure**
  (`TermPoint.priorVol` = the prior's transported ATM vol per expiry, dotted teal
  line in `TermChart`). Same `prior_transport` machinery as the parametric smile, so
  all three workspaces show a consistent prior. Phase B is complete (3D surface mesh
  overlay deferred as optional). 1 new test.

- **[2026-06-17] Prior framework Phase B (core) — fetch freshness ladder +
  transported dotted prior.** `POST /priors/fetch` (`priors.fetch_all`) resolves
  each ticker's prior by the ladder: **(1)** latest SAVED snapshot if its `dataTs`
  is posterior to the previous close, else **(2)** recalibrate on-the-fly from the
  **15-min-before-previous-close** chain, else **(3)** the actual previous close
  (on-the-fly branch mirrors `workflow.seed_priors`' as-of toggle). The result is
  the ticker's ACTIVE prior (`AppState.set_active_prior`/`active_prior`, not cleared
  by `_clear_chain_caches`). `prior_transport.py` rebuilds the prior's LQD backbone,
  transports it to the current forward (`h_T = log(F_live/F_prior)`) under
  `Options.dynamicsRegime` (`TransportedSlice`), and samples on the model k-grid —
  this same helper feeds the Phase-C anchor. `smile_payload` now draws the active
  prior as a **dotted teal, spot-updated** line (`SmileData.priorTransported`).
  Frontend: a TopBar **"Fetch priors"** button + the dotted rendering. 3 new tests.
  (LocalVol + Term overlays added in the follow-up entry above.)

- **[2026-06-17] Prior framework Phase A — calibration snapshots + persistence +
  Save-all (the first of a 3-phase build).** A *prior* is now a full, timestamped
  `PriorSurfaceSnapshot` per ticker (`api/schemas_prior.py`): ref spot, per-expiry
  forward/discount/τ, `MarketSettings` (rate + dividends), event calendar, per-node
  `{displayed model id+params, LQD backbone vector, atmVol/skew}`, and the affine
  **LV grid** (tNodes/xNodes/theta). Persisted to a new `prior_snapshots` SQLite
  table (schema v3→v4, history kept); `AppState` gained a DB-backed snapshot cache
  (`save_prior_snapshot`/`latest_prior_snapshot`). `api/priors.py` captures
  (`capture_snapshot`/`save_all`/`prior_status`); `POST /priors/save-all` +
  `GET /priors`; a TopBar **"Save priors"** button (`useWorkflow.savePriors`).
  `dataTs` (market moment, for the Phase-B freshness ladder) is stored separately
  from `savedTs`. The snapshot reproduces exact modelled prices (LQD backbone
  vector rebuilds the identical slice) and survives a restart. 5 new tests
  (`test_priors.py`). **Next: Phase B** = Fetch ladder (Saved→15min-before-prev-
  close→prev-close) + transported dotted prior overlays under the dynamics regime;
  **then Phase C** = the Bayesian data-gap anchor (delta-locations + var-swap,
  precision ∝ (ρ_desired−ρ_observed)⁺, all models + LV).

- **[2026-06-16] Phase 10 follow-up toggles wired (the three open Options
  switches)**: closes out the Phase 10 "stored-but-inert" controls.
  * **`enforceCalendar` now bites on the real calibration path.** It used to
    affect only the (UI-orphaned) `/fit/surface` endpoint; the live Calibrate
    button (`/calibrate` → `workflow.calibrate_all` → per-node `_compute_fit`)
    fit each expiry independently. When the toggle is ON, `calibrate_all` /
    `calibrate_ticker` now calendar-COUPLE each ticker's lit expiries: ascending-T,
    threading the previous (shorter) slice as the convex-order floor, via the new
    shared `service.fit_and_commit_slice` (which `fit_surface` + the WS route were
    refactored onto, so the coupling recipe lives in ONE place). Items stay
    per-expiry so progress keeps node granularity (`workflow._coupled_ticker_items`
    shares a per-ticker ctx that re-anchors spot + builds the prepared plan on first
    touch). OFF ⇒ independent per-node, as before. Caveat (documented follow-up): an
    autoCalibrate-ON single-node recompute via `_compute_fit` has no cross-expiry
    context, so coupling holds until such a refit; under the default trigger-gated
    workflow the coupled fit stays displayed until the next Calibrate.
  * **`autoLoadPrior` now feeds the saved prior into calibration** as a soft
    prior-anchor penalty (`volfit/calib/prior.py`): vega-normalized call-price
    residuals pulling the LQD fit toward the prior in the quote-free NEAR wings
    (span 0.25 in log-moneyness; the deep tail is left to the A_L/A_R asymptotics,
    where vega→0 would explode the normalizer). Anchored in total-variance shape
    (same node ⇒ ~same time scale, no fragile rescale). Strength =
    `priorAnchorWeightPct` (new OptionsSettings field, default 50%) as a % of the
    node's summed quote weights, spread across the wing points. `prior_anchor=None`
    (the default everywhere) leaves every calibrator byte-identical — golden tests
    untouched. Built in `service.prior_anchor_target`, wired into both
    `_compute_fit` and `fit_surface_slice`.
  * **`varSwapEnabled` confirmed already fully wired** (both penalty paths gated,
    every UI row keys off `VarSwapInfo.enabled`, covered by
    `test_disabling_varswap_drops_the_penalty`) — no code change, just verified.
  * Both new calibration-affecting fields (`enforceCalendar`, `autoLoadPrior`,
    `priorAnchorWeightPct`) now bump the options version in `set_options` so the
    fit cache invalidates. Frontend: `priorAnchorWeightPct` type + default + an
    Options "Prior-anchor weight (%)" input (gated by Auto-load prior); refreshed
    the Arbitrage-fix / Auto-load-prior hints. 9 new tests (2 calendar-coupling in
    `test_calibration_workflow`, 7 in new `test_prior_anchor`). ruff + strict-TS
    build green.

**Done & verified (earlier — `git log --oneline` tells the story):**

- **[2026-06-15] Fit target persisted as an Options default**: the Fit target
  (Mid / Bid-Ask / Haircut) was session-only (`useSmile.fitMode`), so "Save as
  default" never captured it and it reverted to Mid on reload (making the Haircut
  value, which only bites in haircut mode, look un-persisted too — it was always
  on `FitSettings`). `OptionsSettings.fitMode` (default "mid") is now the persisted
  default (stored only — each fit still gets its mode per request — so it never
  bumps the options version); the session seeds it from `/settings/options` once
  on load (ref-guarded so reloads don't clobber an in-session change), and the
  Options "Fit target" control updates both the session and the OptionsSettings
  draft so Apply / Save-as-default persist it.

- **[2026-06-15] Local-Vol calibration master switch (Options)**: new
  `OptionsSettings.localVolEnabled` (default on) to speed up test cycles. OFF ⇒ the
  background Calibrate job skips every ticker's LV (affine) surface (only the
  parametric nodes fit) AND the **Local Vol tab is greyed out / inaccessible** (it
  bounces to Parametric if active when disabled; the flag rides on the polled
  `SchedulerStatus`). Pure workflow/UI gate — does not touch parametric fits, so it
  never busts caches. Calibration work items now carry a coarse `phase`, so the
  Calibrate button shows **"Calibrating Parametric"** then **"Calibrating LV"**
  (`jobs.start` items are `(label, phase, thunk)` 3-tuples).

- **[2026-06-15] Massive feed Tier 3 — REST gap-fill (DONE, live-verified)**:
  closes the 3-tier source router. `MassiveProvider.historical_aggregate()` =
  single-contract minute-bar lookup via `/v2/aggs` (close-based; live-verified).
  **Today's intraday serves the live REST snapshot** (the bulk, entitled
  "now/pre-connect" chain) — a per-contract aggregate crawl over a full expiry
  times out, and there's no whole-chain historical snapshot endpoint.
  `_fetch_agg_chain` (bounded ThreadPool, per-contract try/except resilient)
  remains the rare flat-empty past-day fallback. Routing: TODAY→live snapshot,
  past-day→flat (Tier 2) / capped legacy NBBO when no flat. 3 new tests; ruff +
  full suite green. Live: single-contract close 1.61 @14:00Z; today-intraday →
  376 quotes / 297 two-sided / 1.7s. The Massive feed track (Tier 0/1/2/3) is
  complete + verified.

- **[2026-06-15] Massive feed Tier 2 — flat-file history (LIVE-VERIFIED)**: the
  long-deferred columnar history. **Verified end-to-end** with the user's S3 key
  against `files.massive.com` (bucket `flatfiles`, prefix `us_options_opra`,
  products `day_aggs_v1`/`minute_aggs_v1`, `…/YYYY/MM/YYYY-MM-DD.csv.gz`): day-aggs
  rebuilt a 6,319-quote / 35-expiry SPY close chain (parity spot 741.56) in ~3s,
  minute-aggs a 6,240-quote chain at 15:55 ET, and a full-pipeline fit of SPY
  2026-07-17 as-of EOD 2026-06-12 gave atmVol 15.62% / skew −0.79 / rms 35bp. Two
  real-S3 bugs fixed in the process: DuckDB only binds a `?` parameter in the LAST
  statement of an execute (each `SET …=?` is now its own call), and the endpoint is
  normalized to DuckDB's bare-host + `s3_use_ssl` form (`_split_endpoint`). Default
  endpoint is now `files.massive.com`.
  `data/occ.py` parses OCC/OPRA option tickers (the flat files carry only the
  `O:` symbol → strike/expiry/type). `data/flatfiles.py` `FlatFileStore` uses
  DuckDB (+bundled httpfs) to read the gzipped daily aggregate CSV from the S3
  bucket, filter to the watchlist roots, cache the day to local Parquet, and
  reconstruct a `ChainSnapshot` at an instant (minute aggs = past intraday, day
  aggs = official Close; zero-spread close, parity spot). It belongs to
  `MassiveProvider` (`flat_store=`), so the as-of layer is untouched:
  `historical_modes` gains `eod`, `available_history` lists ~20 recent weekdays,
  and `fetch_chain(as_of=)` routes eod→day-aggs / past-day-intraday→minute-aggs
  (today-intraday stays REST). serve.py `_flat_store()` builds it from env
  (`VOLFIT_FLATFILES_KEY`/`_SECRET` +optional endpoint/bucket/prefix/cache); duckdb
  is an optional `flatfiles` extra, imported lazily. 19 new offline tests (occ ×11,
  flatfiles ×5 via a local gzip-CSV fixture duckdb reads for real, Massive wiring
  ×3). See the priority-track Tier 2 entry for what live-verify still needs.

- **[2026-06-15] Massive feed Tier 0+1 LIVE-VERIFIED + delayed-cluster WS
  fallback**: with the user's key, `massive_diag.py SPY` confirmed the REST feed
  end-to-end on both hosts (api.massive.com / api.polygon.io): contracts+snapshot
  HTTP 200, two-sided NBBO (`fetch_chain` → 376 quotes / 308 two-sided),
  `underlying_asset.price`=755.21, and the **stocks plan is entitled** (so the
  IV-fallback isn't needed here). **WS finding:** the real-time cluster
  `wss://socket.massive.com/options` connects+auths but is **silent** (no
  subscribe-ack, no quotes) — this key is a **delayed** tier; the delayed cluster
  `wss://delayed.polygon.io/options` auths, acks the subscribe, and streams live
  SPY NBBO. So `MassiveWebSocket` now takes a **candidate URL list** and
  auto-advances past a silent cluster (per-frame `quote_grace`, default 6s) to one
  that streams — works for both real-time and delayed keys.
  `MassiveProvider._ws_urls()` = `[override-or-derived primary,
  wss://delayed.polygon.io/options]`; override via `VOLFIT_MASSIVE_WS_URL` (read by
  serve.py) — **set it to the delayed URL on this key to skip the ~6s warmup on the
  dead real-time cluster.** Live-verified: the book fills from the delayed cluster
  and `fetch_chain(live)` serves REST while the book is cold. 2 more tests (candidate
  list + silent-cluster advance).

- **[2026-06-15] Massive feed Tier 1 finish (the three code sub-tasks of the WS
  live book)**: (1)
  **Contract-listing cache** — `MassiveProvider._intraday_contracts` is cached per
  `(ticker, frozenset(expiries))` (`refresh_contracts()` invalidates), so the WS
  read path (`_chain_from_book`/`option_tickers`) and the per-tick resubscribe diff
  no longer re-paginate the contracts reference each call. (2) **Resubscribe on
  universe change** — `AppState.sync_streaming` now diffs the desired contract set
  (`_desired_stream_contracts`) against the provider's live subscription
  (`MassiveProvider.streaming_contracts()` / `MassiveWebSocket.contracts`) and
  restarts the stream when a ticker/expiry edit changes it (was source/mode-change
  only); providers that can't report their subscription are never thrash-restarted.
  (3) **Throttled full-refit loop** — a new `Scheduler.tick` branch gated by
  `AppState.is_streaming()` **AND `autoCalibrate`** calls `workflow.stream_refit`
  every `OptionsSettings.streamRefitSeconds` (default 5s, frontend type seeded)
  while a live book streams: refetch chains from the book + recalibrate ALL lit
  nodes in the background. **`autoCalibrate` is the master switch for unattended
  refits** — with it OFF the streaming loop is a no-op (the surface still tracks
  spot via the transport poll; nodes stay frozen/stale until an explicit Calibrate),
  matching `fetch_options`. [Corrected 2026-06-15: an earlier cut wrongly bypassed
  `autoCalibrate`, so realtime kept recalibrating with the toggle off.] Distinct
  from the minutes-cadence `optionsFetchMode=="auto"` REST refetch. 5 new offline
  tests (cache hit/invalidate, sync_streaming resubscribe, scheduler
  refit-only-while-streaming, stream_refit refetch+calibrate). ruff + strict-TS
  build green. **Live-unverified** (no Massive key in this environment).

- **[2026-06-15] UI crash hardening (error boundary + null-safe diagnostics)**: a
  per-view **ErrorBoundary** (`components/ErrorBoundary.tsx`, keyed by tab) so a
  render crash shows a recoverable card + logs the stack instead of white-screening
  the app. It pinpointed the real-time-spot crash: a **transported** slice is
  finite near ATM but non-finite at the far wings (±6) where the numeric Lee-slope
  / var-swap diagnostics evaluate it → NaN → JSON `null` → `null.toFixed()` crashed
  `SmileAside`. Fixed both layers — backend `numeric_handles`/`numeric_lee_slopes`/
  `numeric_var_swap_w`/`_max_iv_error` coerce non-finite → finite; frontend
  `SmileAside` renders "—" for null/NaN and `formatPct` is null-safe. Massive spot
  now resolves via the upgraded stock plan (`underlying_asset.price` / stocks
  endpoint), with parity-forward as fallback.

- **[2026-06-15] Massive real-time WebSocket live book (feed workflow phase 1)**:
  first tier of the Massive feed design (3 tiers: **WS live book** for RT · **S3
  flat files** [minute/day aggregates → DuckDB/Parquet] for past days · **REST**
  gap-fill). `volfit/data/massive_ws.py`: a pure thread-safe `LiveBook`
  (`{O:ticker → bid/ask}`, parses Polygon `Q` events) + `MassiveWebSocket` — a
  daemon thread running an asyncio client (`websockets` 16, already installed)
  that connects to the options cluster, auths, subscribes to the active
  universe's `Q.O:…` channels and folds quotes into the book; injectable
  `connect` for offline tests; capped-backoff reconnect. `MassiveProvider`:
  `start_streaming`/`stop_streaming`/`is_streaming`, `option_tickers`, and
  `fetch_chain(live)` now serves from the book (`_chain_from_book`, spot via
  parity) with a REST fallback until the book warms. `AppState.sync_streaming()`
  (called each scheduler tick) starts the stream when Massive is active in
  realtime mode and stops any orphaned stream on source/mode change. 7 tests
  (book parsing, the asyncio session via a fake conn, book-served chain, ws-url,
  sync_streaming). **Live-unverified** (needs the user's key); throttled full-
  refit cadence + flat-file history are the next steps. The surface updates on
  the existing realtime spot-poll (reads the book) between Calibrates.

- **[2026-06-15] Massive fits on the base tier (IV fallback) + As-of Prev-Close
  discoverability**:
  * **Fit Massive from its IVs without the paid NBBO add-on.** When the live
    snapshot has no two-sided `last_quote` (gated) but still carries Massive's
    per-contract `implied_volatility` (entitled), `MassiveProvider.fetch_chain`
    auto-falls-back to `_chain_from_iv`: each contract is priced from its IV with
    `core.black.black_call` at forward = spot, DF = 1 (`_price_from_iv`, puts by
    parity), quoted bid = ask = price and marked **european** (no de-Am of a clean
    Black value). The fitter re-inverts those prices and recovers exactly Massive's
    IV smile (exact at zero carry; a tiny shift otherwise) — verified end-to-end
    (atmVol 0.2003 vs 0.20 input). Toggle `iv_fallback` (default on). Needs the
    underlying price (present in the option snapshot) + ≥3 strikes paired call/put
    (real chains have both). 2 tests. NB this fits *Massive's reported* IVs, not an
    independent inversion.
  * **As-of "Previous Close" explicit again**: the day→moment dropdown now shows a
    top-level **Previous Close** row when the source supports `prev_close`
    (Bloomberg/Massive), plus a "this source serves live data only" hint for
    live-only sources (**Yahoo** — it has no option-chain history, so it never
    offered closes; that was not a regression). `useAsOf` gained `setPrevClose`.

- **[2026-06-15] As-of selector reworked to day → moment**: the As-of dropdown is
  now a two-level pick — choose a recent business **day**, then a **moment** within
  it: **Close** (official EOD), **Latest snapshot**, or **N min before close**
  (preset 15/30/60). Backend (`api/asof.py`): `asof_payload` returns the recent
  business days that have data, each flagging `hasClose` / `hasCaptures` /
  `intraday`; `set_moment` + `_resolve_moment` map a (day, moment) to a concrete
  selection — close→`eod`/`prev_close`, latest→newest capture, before_close→the
  capture nearest at-or-before `market_close_utc(day) − N` (16:00 ET via zoneinfo,
  DST-correct, with a fixed-offset fallback). `AsOfSelection` gained display
  metadata (`day`/`moment`/`offset`); `AsOf` + state gained an `intraday` mode.
  Intraday moments come from captured snapshots for Yahoo/Bloomberg; **Massive
  fetches the instant from Polygon `/v3/quotes`** (`intraday_capable`,
  `_fetch_intraday` — per-contract historical NBBO + underlying mid; offline-tested
  via injected `http_get`). POST `/asof` accepts the new `{mode:"moment", on,
  moment, offsetMinutes}` and still the legacy `{mode:"eod"|"captured"|…}`.
  Frontend: `useAsOf` (days + `setLive`/`setPrevClose`/`setMoment`) and a TopBar
  accordion (Live · **Previous Close** when the source supports it · then each day
  expands to its available moments; a "live data only" hint when the source has no
  closes — e.g. Yahoo). 6 new tests (resolution, DST close, Massive intraday).
  Verified end-to-end over HTTP. NB historical/close moments need a provider that
  serves them: **Yahoo is live-only** (no option-chain history), **Bloomberg** does
  live+prev_close+eod (needs an open Terminal), **Massive** does prev_close + the
  intraday fetch but its chain quotes need the paid NBBO entitlement (the contracts
  reference that fills the expiry picker is free, so the picker can list expiries
  the fitter then can't price → "0 selected").

- **[2026-06-15] False "Mock Data" — the actual root cause + ROBUST fallback**:
  the decisive trigger was a backend **500 on `/smiles`**, not a connectivity
  problem. `models/lqd/basis.lee_slopes` did `1/A_R` where a degenerate
  sparse-data fit (a far-dated QQQ node with the stale custom expiry picks carried
  over from a source switch) drove `R≈-1000`, **underflowing `A_R = exp(R+…)` to
  exactly 0.0** → `ZeroDivisionError` → `/smiles` 500. The universe loaded ("Live"
  for a moment), then the first smile fetch 500'd and the old frontend dropped to
  mock. Fix: `lee_slopes` guards the reciprocals and takes the finite limits
  (`psi(1/A−…) → 0` as `A → 0`; verified live — the two far-dated QQQ nodes now
  return 200). `test_lee_slopes_handle_underflowed_endpoint_scales`.
  Plus the mock payload is now reserved for a genuinely UNREACHABLE backend; a
  reachable backend with no data / a node-level error never trips it:
  * **Smile fetch never mocks (`useSmile.ts`)**: a failed `/smiles` retries a few
    times (chain may be warming) then, if still failing, stays LIVE and surfaces
    the error in the chart ("Couldn't load this smile: …") — never the mock badge.
  Three more layers (already this day):
  * **Frontend never latches onto mock (`state/useSmile.ts`)**: the mount path
    became a *retry loop*. `/universe` 200-but-all-ladders-empty (active provider
    warming up / Yahoo throttling a fresh process / a momentarily capped feed) is
    treated as "reachable, no data yet" — stay on the live source, show a
    "Connecting to market data…" state, and re-poll every `UNIVERSE_RETRY_MS`
    (2.5 s) until a ladder appears. Only a thrown request (connection refused)
    falls to mock, and even then it keeps polling so a backend that comes up
    reconnects automatically. The old code dropped to mock the instant the first
    payload was empty and never re-checked — the root of the recurring restart
    bug. (`sourceRef` lets the poll read the live source without restarting.)
  * **Backend serves 200 under provider failure** (already landed earlier this
    day): `AppState.snapshot()` degrades a raised provider fetch to an empty
    uncached snapshot, so `/universe` never 500s.
  * **Startup auto-pick lands on a source that SERVES** (`serve._pick_active` +
    new `_can_serve`/`_bounded`): now that `feed_status` is a cheap connectivity
    check (the Bloomberg quota fix), a connected-but-capped Bloomberg would read
    green and be auto-picked → empty surface. `_pick_active` now additionally
    verifies each non-synthetic candidate can resolve a non-empty ladder for its
    first ticker (retried a few times to tolerate a transient Yahoo throttle; a
    hard cap/gate fails every attempt and is skipped), falling through to the
    next source and finally synthetic. The probe shares the app's provider
    instance, so a successful enumeration warms its chain cache (no extra call).
    4 tests (`test_serve_pick.py`).

- **[2026-06-15] Bloomberg daily-cap drain + Fetch-button gauges**:
  * **Status light no longer burns the Bloomberg quota.** The Data Source
    selector polls `GET /datasources` every 30 s, and Bloomberg's `feed_status()`
    was firing a real `bdp(PX_LAST)` on every probe → ~120 billable ref-data
    hits/hour purely for the light, independent of the On-demand fetch settings —
    that drained the daily cap. `feed_status()` is now a CHEAP, quota-free probe:
    it reads the blpapi session (`session_connected()` / `is_connected()`, no data
    request) and the cached outcome of the last *on-demand* fetch. New
    `BloombergProvider._last_error` + `_record(exc)`: `fetch_chain` (the on-demand
    path, covering the spot probe via `provider.spot`) records a connected-but-
    refused reason (entitlement / *workflow review* / *daily capacity reached*) and
    clears it on success; benign ValueErrors (no contracts/spot for a selection)
    are ignored. So the light still shows a real account gate — established by an
    actual fetch, never by a poll. 3 bloomberg tests updated/added (green w/o
    billable probe, refusal surfaced from last fetch, success clears refusal).
  * **Fetch buttons show an indeterminate gauge while fetching.** `useWorkflow`
    now exposes `pending: "spots"|"options"|"calibrate"|null` (per-action, was a
    shared `busy`); `WorkflowControls` overlays an animated indeterminate bar
    (`@keyframes volfit-indeterminate` in index.css) + "Fetching spots…/quotes…"
    label on the active button. Calibrate keeps its existing determinate
    progress gauge (it's a real background job with done/total).

- **[2026-06-15] False "Mock Data" round 2 — provider failing mid-session**: the
  earlier fix (411e29c) stopped a *transient empty* ladder from freezing, but
  `AppState.snapshot()` still let a *raised* provider `fetch_chain` error escape
  unhandled → `/universe` 500 → frontend falls to mock. Hit in the wild when the
  active source was **Bloomberg** and it went red ("daily capacity reached")
  *after* startup auto-pick had selected it (`_AUTO_ORDER` prefers bloomberg;
  the active source is never re-evaluated at runtime). Fix: `snapshot()` now
  treats any provider fetch exception (UnknownNodeError excepted, still a 404)
  as a transient miss → returns an empty, UNCACHED snapshot via new
  `_empty_snapshot()` helper, so `/universe` and all downstream views degrade to
  "no data" (HTTP 200) and re-probe once the feed recovers. Regression test
  `test_provider_chain_failure_degrades_not_500` (CappedProvider). To get live
  data back when a source is capped, switch the TopBar Data Source selector to a
  reachable feed (Yahoo) — `POST /datasource/{id}` keeps the watchlist, clears
  caches and re-resolves on the new feed.

- **[2026-06-15] Save current selection as default (Options + View)**: both tabs
  gained an explicit **"Save as default"** + **"Reset to defaults"** bar.
  * **Options/Fit** persist to the app store (SQLite, VOLFIT_DB): new
    `app_settings(key, value_json)` table (VolStore schema **v2 → v3**,
    `save_setting`/`load_setting`/`delete_setting`); `volfit/api/settings_persist.py`
    serializes the live `FitSettings` + `OptionsSettings` under keys
    `fit_settings`/`options_settings` (best-effort: no store = no-op, stale blob
    discarded). `AppState.__init__` restores them at startup (a backend restart
    boots on the saved defaults, not code defaults); `save_settings_defaults` /
    `reset_settings_defaults` / `settings_defaults_saved` / `store_enabled` on
    AppState. Endpoints `GET/POST/DELETE /settings/defaults`
    (`SettingsDefaultsStatus` / `SettingsDefaultsReset`) — POST 422s when no
    store. Frontend: `state/useSettingsDefaults.ts`; `OptionsViewer` sticky bar
    now Reset · Save as default · Apply (Save first applies pending edits then
    persists; Reset adopts the reverted code-defaults into both drafts + reloads).
    `useOptions`/`useFitSettings` `apply()` now returns a Promise + an `adopt()`
    setter. 3 new API tests (`test_api_settings_defaults.py`): no-store disables
    Save, save survives a fresh app on the same DB, reset clears + reverts.
  * **View** stays localStorage but switched to the **explicit-save** model:
    `viewSettings`/`expiryFormat` apply changes live (instant preview) but only
    `saveDefault()` persists; both expose `dirty`. `ViewSettingsViewer` got the
    same Save/Reset bar (covers scheme + contrast/brightness + expiry format);
    the per-card Reset button was removed. NB the chart-header ↻ expiry cycle no
    longer auto-persists — persistence is now via the View tab's Save button.

- **[2026-06-15] Calibration compute speed-ups** (branch `perf/calibration-speedups`,
  all byte-identical or within golden tolerances):
  * **LQD slice fit 96 → 35 ms (2.7x)** — the atom of every parametric
    calibration (smile/surface/term/graph baseline all inherit it). (1) Cache
    the parameter-independent quadrature grid and Legendre basis in
    `models/lqd/quadrature.py` (`build_slice` runs ~900x/fit; it was recomputing
    `linspace`/`expit` + the order-6 Legendre matrix every call) and pass `dx=`
    (not `x=`) to `cumulative_simpson` (uniform fast path). (2) Optimize on a
    2001-node grid (`OPT_N_POINTS`), rebuild the accepted slice at the full 8001
    nodes for the result/diagnostics (converged params agree to ~1e-6). The
    calendar constraint moved from grid-index- to z-VALUE-based (new
    `LQDSlice.asset_share_at` Hermite eval + `calendar.calendar_floor_targets`),
    bit-identical at native resolution and correct on the coarse grid; threaded
    through `calibrate_surface` + `service.fit_surface_slice`.
  * **Affine local-vol Dupire fit** (`models/localvol/affine.py`): hoisted the
    theta-INDEPENDENT hat basis out of the per-eval solve (`precompute_dupire_steps`
    / `DupireSteps`, reused across all trial thetas) and sliced the multi-RHS
    sensitivity solve to its active (non-zero) column prefix (`active_k`, derived
    from the real basis sparsity). ~1.15x at optimal-grid scale; PDE-solve 2.05x /
    total fit ~1.6x at large grids (533 vertices). Sensitivity output diff exactly 0.0.
  * **Vectorized `implied_total_variance`** (`core/black.py`): replaced the
    per-strike `scipy.brentq` Python loop with one vectorized safeguarded Newton
    (`rtsafe`, analytic `black_vega_w`, bisection fallback). ~39x on a 241-pt
    curve render (27 → 0.7 ms); matches Brent to ~1e-13 with identical nan
    behaviour. Speeds every smile/affine render, term overlay and `max_iv_error`
    (full-suite wall-clock ~130s → 75s as a side effect). `brentq` no longer used
    in black.py.
  * **Parallelism (roadmap "parallelize slice fits") — measured & rejected.**
    Threads are GIL-negative for both LQD (0.5x) and affine (0.75x) fits;
    process-parallelism gives ~3.9x on LQD but is not worth the live-backend
    integration risk (persistent pool, Windows spawn, large-object serialization,
    cancellation) for a benefit that lands on the already-non-blocking background
    Calibrate job. Coarse-grid-during-opt is viable for LQD but NOT affine
    (it shifts the calibrated nodal variances 30x over the golden tolerance — the
    LV surface is the product output). Kept sequential.

- **[2026-06-14] UX/viewer batch — theming, layout, zoom, true-coordinate axis,
  Forwards chart**:
  * **View tab + full theming** (7th top tab): a `state/viewSettings.tsx`
    provider (localStorage) drives `data-theme` on `<html>` + a CSS
    contrast/brightness filter on `#root`. Tailwind v4 compiles colour utilities
    to `var(--color-*)`, so `index.css` re-skins the whole palette per
    `[data-theme]` scope with **no per-component migration** — four schemes
    **Dark / Light / High-contrast / Warm** (dark's dim text tiers lifted to fix
    "too dimmed"). New `views/ViewSettingsViewer.tsx` (scheme picker + contrast /
    brightness sliders + expiry format + live preview). Chart hardcoded hexes
    routed through tokens so charts flip too. Light mode verified end-to-end.
  * **Options tab reorganized by theme** (`OptionsViewer` 307 lines): Model &
    hyperparameters (model + N/damping/cores, model penalties, the local-vol
    grid) · Calibration (fit target, haircut, quote weighting, band mid anchor,
    var-swap weight, normalize events, calendar weight, calibration penalties,
    graph prior) · Workflow & engine features · Spot-vol dynamics. FitSettings
    lifted into `state/useFitSettings.ts` so its controls span two cards sharing
    one draft; `HyperparamPanel`/`PenaltyCoefficients` are now controlled +
    group-aware; one **Apply** bar commits both `/settings/fit` + `/settings/options`.
    Shared controls extracted to `components/OptionsControls.tsx`.
  * **Calibration gauge** in TopBar `WorkflowControls` (progress bar + current
    item label while a job runs). **As-of dropdown split into date → time** for
    captured snapshots, **weekday-only** (no weekend captures). **Local-Vol
    expiry selector → dropdown** (parity with Parametric). **Universe tab**:
    Active set and Lit/Dark matrix side by side.
  * **Zoom on every chart** (`lib/useZoom.ts`: base-relative wheel-zoom +
    drag-pan + dbl-click/⌂ reset, zoom-out beyond data): Smile (x+y, x beyond
    data), Stacked densities (x), Stacked IV (x+y), 3D Surface (scene scale),
    LocalVol Smile, Density / Log-Q-density. The Smile brush is kept as the
    coarse control.
  * **Smile true-coordinate x-axis** (`SmileChart` rewrite): geometry is plotted
    in the SELECTED coordinate (ln(K/F) / strike / %ATM / Δ / normalized), so the
    smile genuinely reshapes when switching (delta runs high→low) — no longer a
    fixed log axis. `axisModes.axisDisplayTicks` ticks the display domain.
  * **Curves drawn to k ∈ [-1, 1]** (`service.model_curve` 241 pts, `surface`
    81 pts extended to ±1; brush/default `kMin/kMax` stay the OBSERVED range, so
    zoom/pan out reveals the wings). New `service.fill_nonfinite` keeps the
    extreme-wing arrays finite (NaN would serialize to JSON null). 4 grid tests
    updated to the new semantics.
  * **T / √T toggle** on `TermChart`, the Forwards chart, and `SurfaceMesh`
    (`lib/timeAxis.ts`); **Surface coarse k-brush** (shrinks the strike axis,
    Parametric + LV IV-surface).
  * **Forwards-curve chart** (`components/ForwardCurveChart.tsx`): active-forward
    curve + dashed dividend ex-date verticals (amount labels), click-to-add a
    dividend, slider/numeric to set the amount, Apply (PUT `/settings/market`;
    continuous tickers switch to discrete cash so manual divs bite). Verified
    live on a throwaway synthetic backend.
  * Hardened `chartScale.niceTicks` against a sub-ULP step on flat domains
    (was an "Invalid array length" infinite-push crash). No new backend tests
    (existing grid tests updated); frontend strict-TS build green.

- **[2026-06-14] Local-Vol (affine) workspace overhaul**: (1) the vertex grid +
  roughness (λ, ρ) are now GLOBAL hyperparameters in Options only (the LV
  workspace's own sliders are gone); the affine fit reads them directly and they
  are in its cache key. Strike-node max raised to 200; **time vertices default to
  the observed expiries** (`gridTNodes = 0` = auto, one per expiry; > 0 caps).
  (2) An **"Optimal size"** button (Options) sizes the grid to the observed quotes
  (`GET /fit/affine/{t}/optimal-size`: strike nodes ≈ avg quotes/expiry, capped to
  ~160 total vertices so the heavy LSQ stays tractable). (3) The lowest strike
  vertex is placed strictly **between the lowest and 2nd-lowest observed strike**
  (no vertex below the data) — `_lowest_vertex_x`. (4) **LV joins the trigger
  model**: a per-ticker affine calibrated-pointer freezes the surface and reports
  `stale` (a STALE chip in the LV header) until Calibrate; the read path
  (`affine_payload`) NEVER recalibrates synchronously (the affine LSQ scales with
  vertex count — SPY ~minute) — it bootstraps once then serves frozen. The global
  background **Calibrate job now includes each lit ticker's LV surface** as
  labelled work items (`"TICKER · LV surface"`) so progress covers them
  (`workflow.calibrate_all`, jobs take `(label, thunk)` items); fetch-options
  auto-calibrate rebuilds them too. `calibrate_affine_surface` is the force path.
  Frontend: `useAffine`/`useAffineView` drop the grid params (POST `{fitMode}`
  only). 5 tests updated for the trigger model + new affine-grid/optimal-size
  tests; live-verified on SPY (optimal-size 977 quotes/8 expiries → capped grid,
  arb-free fit).

- **[2026-06-14] Trigger-gated calibration workflow** (what calibrates, on what,
  when): calibration is now decoupled from input changes. **Stale model** — each
  node carries a CALIBRATED pointer (the fit-key + spot it was last calibrated at)
  on AppState; `service.fit_or_get` bootstraps one fit, then with
  `Options.autoCalibrate` ON refits on any input change (old behaviour) and OFF
  *freezes* the last fit, reporting `SmileData.stale=True` until an explicit
  Calibrate (`node_dirty`/`calibrate_node`; a per-ticker `data_version` in the fit
  key bumps on a fresh options fetch). The spot-move transport anchors on the
  *calibration* spot (`anchor_spot`), not the live snapshot. **Actions**
  (`api/workflow.py` + `routers/workflow.py`): `POST /fetch/spots` (probe live spot
  → transport, no refit), `POST /fetch/options` (refetch chains + auto-calibrate
  when enabled), `POST /calibrate` (BACKGROUND job over all lit nodes via
  `api/jobs.CalibrationJobs`, `GET /calibration/status` for progress + lit/stale
  counts), `POST /calibrate/{ticker}[/{expiry}]` (sync), `POST /priors/seed`
  (explicit prev-close → calibrate → save). **Backend scheduler**
  (`api/scheduler.py`, opt-in `create_app(enable_scheduler=True)`; serve.py turns
  it on): a daemon thread polls live spots every `spotPollSeconds` when
  `spotMode=realtime` and refetches chains every `optionsFetchMinutes` when
  `optionsFetchMode=auto` (then auto-calibrates if enabled); `GET /scheduler` gives
  modes + countdowns. New OptionsSettings fields `spotPollSeconds`,
  `optionsFetchMode`, `optionsFetchMinutes` (autoCalibrate/spotMode now wired, not
  stubbed). **Frontend**: `state/useWorkflow.ts` (polls status, edge-reloads all
  views on job-completion / backend RT spot move) drives TopBar `WorkflowControls`
  (Fetch spots / Real-time Spots · Fetch Options Quotes / auto-countdown ·
  Calibrate with progress + stale-count badge); a STALE chip on the Parametric
  header; a "Calibration & data workflow" Options card; `useSmile` owns a single
  view-refresh counter (`spotVersion`/`refreshViews`) threaded into every
  workspace's fetchers; `useSpot` slimmed to the manual slider (backend owns RT).
  13 new tests (stale model, workflow endpoints, scheduler ticks); live-verified
  over HTTP (stale↔calibrate↔fetch cycle, scheduler thread running).

- **[2026-06-14] Fast spot-move transport (no recalibration)** per
  `Docs/spot_move_vol_surface_note_updated.tex`: a spot change — the user sliding
  the spot level OR a real-time spot tick — refreshes the calibrated smile / term
  / LV-grid **analytically**, never refitting (full recalibration only on the
  explicit Calibrate button). New `volfit/dynamics/transport.py`: the SSR
  horizontal total-variance transport `w₁ᴿ(k)=w₀(k+R·h_T)` (recovers
  sticky-moneyness/strike exactly at R=0/1), the exact sticky-local-vol `ℓ_T(k,h)`
  displacement (R=2 double-skew), an optional finite-move ATM re-anchor, and the
  LV-grid node rule `Kᵢ¹=Kᵢ⁰e^{(1−R/2)h_t}` (`TransportedSlice` SmileModel +
  `transport_grid_logk/strikes`). `h_T` comes from the FORWARD per the note
  (multiplicative under continuous yield, additive `ΔF=ΔS·e^{rt}` under discrete
  cash divs, so h differs per expiry). Integration: AppState holds a per-ticker
  spot SHIFT + `spot_version` (NOT in the slice fit-cache key — the anchor stays
  warm and is transported on read); `service.fit_or_get` wraps the cached
  `_anchor_fit` with `transport_record` (new forward, quotes re-indexed to new
  moneyness k−h, transported slice as a DisplayFit so EVERY view — smile, term,
  surface, density, var-swap, table, and the Dupire `/localvol` extraction —
  follows). The affine Local-Vol surface transports at the `affine_payload`
  boundary (`affine_transport.py`: per-expiry smile transport + grid relabel),
  `spot_version` busting the two derived caches. New endpoints
  `GET/PUT /spot/{ticker}`, `POST /spot/{ticker}/calibrate` (re-anchor: clear
  shift + drop chain caches + refit at live spot), `GET /spot/{ticker}/live`
  (provider spot re-probe for RT polling; cheap Yahoo override). Frontend:
  `state/useSpot.ts` (debounced PUT, RT poll when Options.spotMode='realtime',
  `spotVersion` folded into every workspace's fetchers), the aside "Spot scenario"
  slider repurposed into a live `SpotPanel` (slider moves the surface +
  anchor→shifted readout + regime·R + Calibrate button). 25 new tests
  (engine golden + service integration + API); live-verified over HTTP
  (synthetic +3%: fwd ×1.03, ATM 21.87%→21.73%, LV grid recenters, calibrate
  restores). The graph universe deliberately still reads the un-transported LQD
  anchor.

- **[2026-06-14] Auto-calibrate Events (Term)**: a horizon drop-list (an expiry T)
  plus a Calibrate button solve — all at once — one candidate event before each
  expiry up to T so the event-time forward variance `Δw/Δτ` is as flat and
  monotone-increasing as possible with events as small and sparse as possible
  (`volfit/calib/event_autocalibrate`: bounded L-BFGS-B over per-interval extra
  days, jaggedness + asymmetric non-monotonicity penalty + L1/ridge, tiny events
  thresholded out, the first post-T interval anchors the tail). Events only move
  the weighted clock, so the optimizer targets the *dilated* forward variance (the
  real-time one is event-invariant). `POST /events/{ticker}/autocalibrate`
  installs the result as the shared calendar. 4 tests.

- **[2026-06-14] Event-weighted VARIANCE CLOCK**: events are now a real variance
  clock (not just term interpolation). Each calendar day weighs 1; an event adds N
  *extra equivalent days* to its day (`volfit/calib/weighted_time.py`); the smile
  is calibrated/quoted in weighted years τ. Total variance is price-derived (clock-
  invariant), so the working IV = √(w/τ) **drops when an event sits before the
  expiry** (verified exact: ATM 0.2187→0.1980 = ×√(T/τ)) — quote bands, ATM,
  var-swap, table, term and the Local-Vol reconstruction all follow. Dual clock:
  calendar `t` still drives discounting / forwards / de-Americanization / the
  maturity axis; `prepared.tau` drives every vol↔variance conversion. An Options
  **Normalize events** toggle (default off) rescales all days so the 1Y weight
  budget stays 365 — 1Y vols unchanged, events redistribute variance within the
  year (verified). `eventsEnabled` is the master switch; the per-ticker calendar +
  `eventsEnabled`/`normalizeEvents` are folded into the fit-cache keys. Event
  weight is now *extra days* (was years); the Term editor labels it "days" and the
  master on/off lives in Options (the local checkbox is gone). No events ⇒ τ = t,
  byte-identical to before. 11 new tests.

- **[2026-06-14] Variance-swap quotes (Smile · Term · Table, Parametric + Local
  Vol)**: gated by the Options "Variance-swaps" toggle. A node carries at most one
  var-swap quote (the var-swap is a single log-contract scalar per smile),
  model-independent and SHARED across the Parametric (LQD/SVI/sigmoid) and
  Local-Vol (affine) fits, with its OWN undo/redo/reset history separate from the
  option-quote edits (`volfit/api/varswap_session.py` + AppState registry +
  `varswap_version` in the fit-cache key). Adding a quote adds a soft calibration
  penalty pulling the model's own fair var-swap toward the quote
  (`volfit/calib/varswap.py`, vol-space residual `sqrt(u)·(σ_vs_model−σ_vs_quote)`):
  threaded into all three parametric calibrators (scipy numerical Jacobian, so no
  analytic gradient) and the affine surface fit (reusing its existing
  `VarSwapQuote`). **Perf gotcha**: LQD's `implied_w` solves a per-point root, so
  the generic replication made one fit ~158 s under the FD Jacobian — LQD now uses
  its exact closed form `LQDSlice.var_swap_strike()` (≈0.7 s, vs 0.087 s
  unpenalized); SVI/sigmoid keep the cheap arithmetic-curve replication. The
  penalty weight is `OptionsSettings.varSwapWeightPct` (% of the node's summed
  option-quote weights; default 10%), so the var-swap competes with the options at
  a chosen relative strength regardless of quote count; `varSwapEnabled` /
  `varSwapWeightPct` now bump the options version. New endpoints
  `POST /smiles/{t}/{e}/varswap[/undo|/redo]` (shared by both workspaces). `SmileData`
  /`AffineSmile` gain `varSwap: VarSwapInfo`; `TermPoint` gains the per-expiry
  quote. Frontend: reusable `VarSwapPanel` (entry + slider + Exclude/Undo/Redo/Reset,
  Options-gated), a horizontal teal line on the Smile & Local-Vol smile charts, a
  Table footer row, and a Term overlay (hollow teal rings, click a rung to edit +
  a per-expiry panel/ladder column). 10 new backend tests; strict-TS build green.

- **[2026-06-14] All calibration/optimization coefficients exposed in Options**:
  every previously-hardcoded calibration constant is now a tunable parameter
  (each default = the historical constant, so default fits stay byte-identical
  and all golden tests pass) and surfaced explicitly in the Options tab —
  **LQD** A_R soft-barrier centre/scale, **SVI** no-arb penalty weight + Lee-slope
  bound, **Multi-Core SIV** hat-amplitude ridge, the **band** mid-anchor weight
  (threaded through `band_residuals` into LQD/SVI/sigmoid/affine), the **affine**
  roughness ρ, and the **graph** prior strength κ + η/λ/ν. Added to FitSettings
  (per-model, bumps the settings version) and OptionsSettings (graph-prior
  defaults + gridRegRho). Frontend: a `PenaltyCoefficients` sub-panel (grouped by
  model, greyed off-family) in HyperparamPanel + a "Graph prior (defaults)"
  section in OptionsViewer; `useAffine`/`useGraph` seed ρ and κ/η/λ/ν from the
  Options defaults. 1 new test (coefficients reach the calibrators).

- **[2026-06-14] Phase 10 viewer refinements** (third request batch):
  * **Local Vol IV surface is now 3D** (not a heatmap): the 3D renderer was
    extracted from SurfaceChart into a presentational `SurfaceMesh`; SurfaceChart
    is a thin fetching wrapper and the LV "IV surface" sub-tab builds a (T×k→σ_IV)
    mesh from the reconstructed affine smiles and renders it through SurfaceMesh,
    matching the Parametric Surface.
  * **Global expiry-format toggle** (`lib/expiryFormat.formatExpiry`): five
    formats — `dd-mmm-yy`, `(dd)mmmyy` (**smart-day**: the day is shown only on
    non-3rd-Friday listings, so monthlies read "Dec26", weeklies "11Dec26"),
    `1.25y`, `15.0m`, `15m 0d`. One global preference via a lightweight
    `ExpiryFormatProvider` context (localStorage-persisted), a full selector in
    the Options "Display" card + a ↻ cycle toggle in the Parametric/Local-Vol
    headers, applied across the expiry dropdown, chart titles, Local-Vol
    chips/diagnostics, Forwards & Term ladders, the lit/dark matrix and the
    stacked-chart legends.

- **[2026-06-14] Phase 10 viewer refinements** (second request batch):
  * **Aside/header slimmed**: the Parametric expiry-class chips (D/W/M/Q/All) are
    gone (the Expiry dropdown lists every selected expiry); the aside keeps only
    diagnostics + the spot-scenario *slider* — the **dynamics regime moved
    entirely to Options** (Mny / Strike / LV / LV-grid / custom-SSR; backend
    `dynamicsRegime` widened to a string literal incl. `custom`), and the **model
    selector moved to Options** too (ModelPanel retired). `useSmile` sources the
    scenario regime from `/settings/options` and re-pulls it on reload, so an
    Options change propagates.
  * **Stacked views (Parametric)**: the single-node Density tab is replaced by
    **Stacked densities** — every selected expiry's risk-neutral density overlaid
    (all ≥ 0 ⇒ no butterfly arb), new `GET /smiles/{ticker}/densities`
    (model-aware; declared before `/{expiry}`). A **Stacked IV** tab beside
    Surface overlays **total variance** w(k)=σ²·T per expiry (the correct space:
    non-crossing ⇔ no calendar arb), from the existing `/surface` mesh. New
    zero-dep `OverlayCurvesChart` (maturity-graded).
  * **Local Vol IV surface**: the Surface sub-tab is now **LV surface**; a new
    **IV surface** sub-tab shows the reconstructed implied-vol heatmap (per-expiry
    affine smiles resampled on a shared intersection grid). `LocalVolHeatmap`
    generalized with a legend label.
  * **Lit/dark nodes**: per-(ticker,expiry) lit/dark designation on AppState
    (lit by default; lit = observed source, dark = extrapolation target),
    `GET /universe/lit` + `PUT /universe/lit/{ticker}[/{expiry}]`, `GraphNodeInfo`
    reports `lit`. New `LitDarkMatrix` in the Universe tab; `useGraph` seeds its
    observed set from the designation on load and persists toggles back, so the
    Universe and Graph tabs stay in sync. 11 new backend tests (options/custom,
    stacked-densities, lit/dark); strict-TS build green; endpoints live-verified.

- **[2026-06-14] Phase 10 — workspace restructuring (tabs, Forwards & Options)**:
  top tabs are now **Parametric · Local Vol · Forwards · Options · Graph ·
  Universe** (Smile → Parametric; Term-Structure is no longer a top tab).
  * **Parametric**: Term-Structure embedded as a chart sub-tab next to Density
    (`components/TermPanel.tsx`, reuses useTerm + TermChart; aside hidden on it);
    the standalone `TermStructureViewer` is retired. The aside is slimmed to its
    live per-node controls — new `ModelPanel` (smile-family selector that PUTs
    the *full* FitSettings so other fields survive) + ScenarioPanel.
  * **Local Vol**: Parametric-style sub-tabs Smile / Density / Term / Surface
    (heatmap) / Table, every view DERIVED from the calibrated affine LV surface.
    Backend `api/affine_views.py` reconstructs them from the cached fit (wrap
    each reconstructed (k,vol) smile in an interpolating SmileModel, reuse the
    Breeden-Litzenberger density / log-contract var-swap / Black-price pipeline);
    `POST /fit/affine/{ticker}/{density,term,table}` share the AffineFitRequest
    body → same cache key. Frontend `state/useAffineView.ts` (only the active
    sub-tab fetches) + presentational `LocalVolTable`.
  * **Forwards** tab (`views/ForwardsViewer.tsx`): per-ticker forwards table
    across the ladder (parity/theo/manual/active) + the per-expiry ForwardPanel
    reused verbatim; edits refit both Parametric & Local Vol via the forwards
    version. (ForwardPanel left the aside.)
  * **Options** tab (`views/OptionsViewer.tsx` + `state/useOptions.ts`): new
    global `OptionsSettings` (GET/PUT /settings/options on AppState; options
    version folded into the fit-cache key, bumped only by the calibration-
    affecting `calendarWeight`). Hybrid meta page: calibration defaults (reuses
    HyperparamPanel + fit-mode), engine toggles (arb-fix / events / var-swap /
    auto-load-prior), spot-vol dynamics default (regime + SSR), local-vol grid
    defaults, the **penalty catalogue** (descriptions + formulas verified
    against the calibrators, editable `calendarWeight`), and the stubbed
    workflow toggles (auto-on-demand calibration, real-time/static spot).
  * **Wiring (per the "wire cheap / stub new" decision)**: `calendarWeight`
    fully affects surface slice fits (threaded into calibrate_slice, tested);
    `useAffine` seeds the LV grid from Options (untouched-only) and `useTerm`
    seeds the events default. The remaining toggles (enforceCalendar,
    varSwapEnabled, dynamicsRegime/ssr, autoLoadPrior) are persisted global
    defaults surfaced in the UI — deeper per-view consumption is the Phase 10
    follow-up; auto-calibrate + spot mode stay stubbed. 10 new backend tests
    (`test_api_options.py` ×6, `test_api_affine_views.py` ×4); strict-TS build
    green; new endpoints live-verified on uvicorn (synthetic ALPHA: options
    round-trip, /term 4 points, /density 169 pts, /table 14 rows, F 87.80).

- **[2026-06-14] "Quantile" chart replaced by the log quantile density**: the
  Smile Viewer's distribution tab now plots the LQD model's own backbone,
  ℓ(u) = log q(u) = −log f_X(Q(u)) = −log(pdf) vs u (Docs/lqd_model_note.tex eq
  lqd_main), with the y-axis **capped at ymax = 2.5** (ℓ is a bowl that diverges
  at the tails; the divergent tails are clipped to the plot box). Computed
  frontend-side from the existing `density` array (so it follows the chosen
  model, like density/quantile already do — no backend change). Tab renamed
  Quantile → "Log Q-density" (`logqd` view), legend/hover/hint updated, SVG
  clipPath added. Frontend strict-TS build green.

- **[2026-06-13] Weighted RMS fit error in the diagnostics**: every calibrated
  smile now reports its RMS vol error using the active weighting scheme —
  `sqrt(sum u_i (sigma_model - sigma_mid)^2 / sum u_i)` over the edited quotes,
  with u_i the equal/TV-density weights actually used by the fit (pure helper
  `models.diagnostics.weighted_rms_vol`; `service.weighted_rms_error` gathers the
  displayed slice + scheme weights). New `SmileDiagnostics.rmsError` (decimal
  vol) shown as a "RMS error" % row in the Smile aside. 2 new tests.

- **[2026-06-13] Time-value density quote weighting (all models, per maturity)**
  per `Docs/iv_time_value_density_weights.tex`: new `volfit/calib/weights.py` —
  `w_i = max(TV_i, eps) * s_i / s_bar` where TV_i is the OTM quote's time value
  (its normalized forward option price, `otm_time_value`) and s_i is the 1-D
  Voronoi cell width in log-moneyness, so the *aggregate* weight density follows
  TV(x) with the strike oversampling divided out (dense regions down-, sparse
  wings up-weighted; uniform grid → w_i = TV_i exactly). New FitSettings
  `weightScheme` ("equal" = historical unit weights | "tv_density"; room for a
  third) drives `resolve_weights(scheme, k, w)` — mean-normalized so the
  data-vs-regularization balance is identical to equal weighting. Applies to
  EVERY model and EVERY fit mode: SVI/Sigmoid/LQD multiply the (IV-space)
  residual by sqrt(w), LV-affine folds sqrt(w) into the vega tolerance, and the
  band objective scales its violation+anchor by it too. Computed on the *edited*
  slice quotes (exclusions define the Voronoi cells, amends move TV). Refactor:
  `fit_weights`/`fit_band` removed; `surface_inputs` returns (iso, prepared) and
  weights/band are derived per slice at fit time. New "Quote weighting"
  segmented control in HyperparamPanel. 9 new tests incl. the note's exact
  5-quote golden example + uniform-grid benchmark + per-model effect.

- **[2026-06-13] Term-structure & local-vol now follow the chosen model too**
  (correcting an earlier overstatement that they "need" LQD): neither has a
  structural LQD dependency. **Term-structure** only reports per-expiry ATM vol /
  ATM total variance / var-swap — all model-agnostic and already computed for
  overlays — so `analytics.term_structure` now reads them from the *displayed*
  fit (bitwise-equal to GET /smiles' diagnostics for the same model).
  **Local-vol** (`GET /localvol`) is a Dupire extraction that only uses the
  `implied_w(k)` SmileModel interface, so it now extracts from the displayed
  surface (`displayed_slice`); the SSR scenario uses the displayed skew. Caveat
  documented: Dupire's denominator is ill-conditioned and assumes an arb-free
  smooth input — LQD/SVI are arb-free by construction, the signed MC-SIV cores
  can violate butterfly, in which case the extraction clips and the no-arb
  diagnostics flag it. Only the **graph universe** genuinely stays LQD (it needs
  exact ATM-orthogonal coordinates + Newton retargeting). Refactor: the
  `displayed_*` accessors moved to `api/displayed.py` (service.py back to 379
  lines); added `displayed_var_swap_w`/`displayed_max_iv_error`. 2 new tests.

- **[2026-06-13] Density / Quantile views now follow the chosen model**: the
  density chart was hard-wired to the LQD backbone (`record.result.slice`) even
  when SVI/sigmoid was displayed. Added a model-agnostic Breeden-Litzenberger /
  Durrleman-Gatheral density `numeric_density(slice_)` in `models/diagnostics.py`
  (`p(k) = g(k)/sqrt(2πw) e^{-d_-^2/2}` from `implied_w(k)` alone, FD w'/w'',
  pdf floored at 0 + renormalized for non-arb-free overlays). `density_payload`
  now uses the displayed slice's own density for a non-LQD overlay (LQD keeps its
  exact closed form; saved prior stays the LQD snapshot). Validated: integrates
  to 1, matches the exact LQD pdf to <0.4% over the central mass, and exactly
  reproduces the flat-smile Gaussian N(-a/2, a). 3 new tests. (Frontend already
  labels the curve "Current fit" — no UI change.)

- **[2026-06-13] Bid-ask / haircut band fitting objective for ALL models**:
  the band fit modes no longer fit |mid - model|; they penalize the model
  *leaving the quoted band* — `max(model-ask,0)^2 + max(bid-model,0)^2` — plus a
  small `MID_ANCHOR_WEIGHT=0.05` |mid-model| anchor (new `volfit/calib/band.py`:
  `resolve_band`/`band_residuals`). "haircut" tightens each side toward mid by a
  tunable `haircut` (default 0.5 vol pts = 0.005, clamped never to cross mid:
  `modified_bid=min(bid+h,mid)`, `modified_ask=max(mid,ask-h)`), replacing the
  old HAIRCUT_SHRINK weight factor. The hinge is monotone so each model keeps
  its native residual space: **SVI/Sigmoid** vol-space hinge, **LQD** vega-
  normalized price hinge (band vols → call-price edges), **LV-affine** price
  hinge with the analytic Jacobian preserved (subgradient 0 inside band;
  `OptionQuote` gained `price_lo`/`price_hi`). Band-only weighting (no inverse-
  spread on top — the band encodes the spread; `fit_weights` now returns unit).
  "mid" mode is byte-identical (golden tests untouched). `haircut` added to
  FitSettings + a "Haircut (vol pts)" control in HyperparamPanel; threaded
  through fit_or_get / surface / WS / display-overlay / affine fit
  (`apply_band_edits`/`edited_band`, aligned to quote edits). Fixed a latent
  calib/__init__ import cycle (lazy `surface` via PEP 562). 13 new tests
  (band core + per-model in-band/smoothing/outside-pull + LV band modes).

- **[2026-06-13] Multi-Core SIV ("sigmoid") model rewrite** per
  `Docs/Multi_Core_SIV_Technical_Note.tex`: the legacy 4-param monotone sigmoid
  is replaced by `v_R(z) = v_SIV(z;theta) + sum_r alpha_r B_{c_r,h_r,kappa_r}(z)`
  — a one-core SIV base (level/skew/convexity/asymmetric wings, 6 params) plus R
  signed **zero-wing hat kernels** (eq B-def) that reshape the body for WW /
  dual-hat smiles WITHOUT moving the Lee wing slopes (eq model-wing-preservation).
  `models/sigmoid/kernels.py` (Phi primitive, base SIV, hat B + derivatives,
  Durrleman/Gatheral g diagnostic), `sigmoid.py` (`MultiCoreSiv` SmileModel,
  `SigmoidSmile` kept as alias), `calibrate.py` (base fit → greedy hat seeding on
  residuals → bounded trf joint refine + amplitude ridge; cores capped so
  6+4R ≤ N). **R is a slider** (`nCores` on FitSettings, 0–6, the analogue of the
  LQD Legendre order) threaded through `build_display_fit`/service → a "SIV cores
  R" range control in HyperparamPanel (active only for the sigmoid family).
  Golden tests reproduce the note's Table 1 coefficients, RMSE (8.62e-4), feature
  table, min v (0.03824) and min g (0.1553) to published precision; the slider
  monotonically buys fit (WW smile: R=0 base 105 bp → R=3 0.4 bp). 14 sigmoid
  tests + 2 settings tests; ruff + strict-TS build green.


- **[2026-06-13] As-of (timestamp) selector under Data Source**: choose the
  observation time — **Live / Real-time**, **Previous Close**, a provider **EOD
  trading day** (~30 days), or a **captured intraday** snapshot replayed from the
  store. Everything re-prices because it all flows through
  `AppState.snapshot()`. Provider contract gained `AsOf` + `fetch_chain(as_of=)`
  + `historical_modes()`/`available_history()` (`data/provider.py`, default
  live-only). Bloomberg does eod/prev-close via `bdh` (`data/bloomberg_history.py`,
  narwhals long `ticker/date/field/value`; ~30 trading-day list); Massive does
  prev-close from the snapshot `day.close` (zero-spread); Yahoo/Synthetic
  live-only. AppState `set_as_of` clears chain caches + routes live(+auto-capture
  to VolStore, dedup ~60 s) / provider-EOD / captured-replay
  (`store.snapshot_at`); `data/store.py` gained `list_snapshots`/`snapshot_at`/
  `last_snapshot_ts`. `api/asof.py` + `routers/asof.py` (GET/POST /asof).
  Frontend `state/useAsOf.ts` + a TopBar "As of" dropdown (amber when
  historical). 7 new tests. Live-verified: Bloomberg eod 2026-06-11 fits a real
  historical SPY smile (ATM 16.27%).

- **[2026-06-13] In-app Data Source selector** (Yahoo / Bloomberg / Massive /
  Synthetic) with a per-source status light (green=real-time, amber=delayed,
  red=unavailable). `AppState` now holds a **provider registry** instead of one
  provider (`self.provider` is a property over `_active_source`);
  `set_active_source` switches at runtime — keeps the watchlist + custom expiry
  picks, clears data caches, refetches on the new feed (auto selections
  re-resolve lazily, custom picks intersect the new available list). Each
  provider gains a cheap `feed_status()` probe (`data/provider.py` default +
  yahoo/bloomberg/massive overrides; Massive's is two single-page GETs, never
  full pagination). New `api/datasource.py` (concurrent probing + 30 s TTL
  cache) + `routers/datasource.py` (GET /datasources, POST /datasource/{id}).
  `serve.py` registers ALL sources and auto-picks the best-reachable active one
  (bloomberg→yahoo→massive→synthetic; `VOLFIT_PROVIDER` forces one). Frontend
  `state/useDataSources.ts` + a TopBar dropdown selector with status dots;
  switching fires the session's refreshUniverse()+reload(). `restart.ps1` now
  brings all sources up by default (flags only force the active one). 13 new
  tests. Live-verified: lights = bloomberg green / yahoo amber / synthetic
  green / massive amber, switch + 404 work end-to-end.

- **[2026-06-13] Bloomberg + Massive market-data providers** (CLAUDE.md data
  layer; ROADMAP Phase 3 + "Next up" #2). Both implement the
  `OptionChainProvider` contract so the whole stack runs on them unchanged.
  * **Bloomberg** (`data/bloomberg.py` + `data/bloomberg_parse.py`): via xbbg
    against a live Terminal. `available_expiries` parses the OPT_CHAIN
    descriptor strings (one cheap `bds`, no per-contract `bdp`); `fetch_chain`
    bulk-`bdp`s only the selected expiries' contracts (liquid names list 1000s).
    Reads xbbg's **narwhals long-format** frames column-wise (they lack
    `index`/`itertuples`). Real `OPT_EXER_TYP` sets `exercise_style`.
    `search_symbols` uses the blpapi `//blp/instruments` service so the Universe
    picker resolves "Nvidia"/"NVDA" -> "NVDA US Equity" (Massive search hits
    `/v3/reference/tickers`); the picker is source-aware via the active provider.
    `dividend_schedule()` imports `DVD_HIST_ALL` (future-declared rows, else
    projects the trailing quarterly cadence forward) → seeded into per-ticker
    MarketSettings at startup (`serve._seed_bloomberg_dividends`).
    Live-verified: SPY 13 expiries, 1026 quotes, spot+american+forwards+divs.
  * **Massive** (`data/massive.py`): Massive.com = rebranded Polygon.io
    (`api.massive.com`, Bearer auth, `/v3/...`). `available_expiries` via the
    contracts reference; `fetch_chain` via the chain snapshot (last_quote
    bid/ask + day OHLC + OI + underlying price); `NOT_AUTHORIZED` →
    actionable `RuntimeError`. **The supplied key's tier DOES return snapshot
    quotes + spot**, so Massive is a fully-working fitter source today
    (live-verified: 32 expiries, spot 741.75, 291/366 usable mids).
  * **Massive IV overlay** (`api/routers/massive_iv.py`, GET
    /massive/iv/{ticker}): Massive's own American IV/greeks per contract as a
    read-only comparison (entitled without quotes). Frontend toggle in the
    Smile Viewer (`state/useMassiveIv.ts` + cyan OTM scatter on SmileChart).
  * Wiring: `serve.py`/`snapshot.py`/`restart.ps1` gain `bloomberg`/`massive`
    selection (`VOLFIT_PROVIDER`, `VOLFIT_MASSIVE_KEY`; `restart.ps1
    -Bloomberg`/`-Massive`). Shared `data/fieldmap.py` (price/int coercion,
    also adopted by yahoo). Optional `providers` extra in pyproject (xbbg,
    blpapi, httpx, yfinance — not in CI). 16 new offline tests (injected
    `blp_module` / `http_get`); both providers live-verified end-to-end.

- **[2026-06-13] Per-ticker expiry-depth/window selection**: the Universe tab
  now picks each ticker's expiries from the FULL provider list. Provider
  exposes `available_expiries` (cheap — Yahoo `Ticker.options`, no chain fetch;
  horizon raised to ~2Y) and `fetch_chain(ticker, expiries)` fetches only the
  selected rungs. `data/expiry_select.py`: buckets (0dte / weekly = M/W/F /
  monthly = 3rd Fri / quarterly / daily), the **default rule** (first 2 M/W/F
  weeklies >=2 days + first 2 monthlies + quarterlies <=18M; sparse ladders
  <=8 take all), and bulk-filter resolution. AppState gains per-ticker
  available/selected/mode (auto vs custom), lazily applied to watchlist
  tickers; selection changes re-fetch the chosen expiries (extracted to
  `api/state_universe.UniverseMixin` to keep state.py <400). Endpoints: GET
  /universe/{t}/expiries (full list + buckets + selected flags), PUT (set),
  POST .../reset (default rule). Named universes now persist per-ticker
  selection ("auto" re-resolves the rule, "custom" re-applies explicit picks).
  Frontend `ExpiryPicker.tsx` in the Universe tab: bulk chips (0DTE/Weeklies/
  Monthly/Quarterly/<=1Y/<=2Y/All) + per-expiry checkboxes + Reset; edits
  refit every workspace via the shared session. 11 new tests; verified
  end-to-end on live SPY (29 available -> 8 default-selected; picker + chips).

- **[2026-06-13] Universe-selection UI**: a dedicated "Universe" tab (5th
  workspace) to curate the working set of underlyings. Backend: AppState now
  holds a mutable active-ticker set (`add_ticker` validates by fetching the
  chain + a parity forward, `remove_ticker` keeps >=1 and drops the ticker's
  caches, `set_active_tickers` for loading a saved set); `snapshot()` gates on
  the active set so dynamically-added symbols work. Symbol search
  (`provider.search_symbols`: default substring+echo, **YahooProvider override
  hits Yahoo's autocomplete** via httpx with offline fallback). New endpoints
  (`api/universe_service.py` + router): GET /universe (active), GET
  /universe/search, POST/DELETE /universe/tickers, and named universes wired to
  the existing SQLite persistence (`data/universe.py`) — GET/POST/DELETE
  /universes + POST /universe/load/{name} (no-op without VOLFIT_DB). Frontend:
  `views/UniverseManager.tsx` + `state/useUniverse.ts` (debounced search,
  add/remove, save/load/delete named) + `useSmile.refreshUniverse()` so edits
  propagate to every workspace's selectors. 7 API tests; verified end-to-end in
  headless Edge (search → add DELTA → save named universe).

- **[2026-06-13] Discrete cash-dividend de-Americanization**: the proper cure
  for the residual ATM kink on dividend-straddling expiries (the continuous-
  yield de-Am smears a discrete cash dividend into an average yield and
  mis-models the call/put early-exercise asymmetry near the ex-date). New
  escrowed-Hull cash schedule in the CRR tree (`core/american.py`: `_escrow` +
  `div_times`/`div_amounts` on `binomial_price`/`_batch`/`deamericanize`/
  `_batch`; recombining, base lattice on S-PV, actual spot = lattice + remaining
  dividend PV). Consistency: the tree uses the ticker's physical `rate` and the
  schedule's ex-date timing, with cash amounts SCALED so the escrowed forward
  reproduces the resolved forward exactly (`data/dividends.forward_consistent_
  cash_schedule`, alpha=(S-F e^{-rt})/PV) — the IV level is untouched, only the
  ex-date EEP asymmetry is corrected. Wired opt-in through quote prep
  (`api/quotes.prepare_quotes` + state `cash_dividend_schedule`): activates when
  the ticker has a discrete/mixed dividend mode with a cash leg in (0,t] and a
  rate high enough to admit positive dividends (else falls back to continuous-q,
  unchanged). Golden test: flat-vol American chain with a mid-period cash
  dividend — continuous-q leaves a 62 vol-bp ATM kink, discrete de-Am brings it
  to 1.5 bp and recovers the flat 20% smile (tests/test_discrete_deam.py).

- **[bugfix 2026-06-13] American parity-forward ATM kink**: put-call parity is
  an equality only for European options, so a forward implied from raw American
  C - P is biased (~40 bp), and quote prep then de-Americanized OTM puts/calls
  under that biased carry in opposite directions → a visible IV jump at the
  money (reproduced flat-vol: 93 vol bp; live SPY: 22-308 bp per expiry). Fix in
  `data/forwards.py`: when a reference date is supplied for an American snapshot,
  de-bias **only the forward** (iterating the carry q via de-Americanized
  European-equivalent mids to the fixed point that reconciles the two OTM sides)
  while **holding the discount at its raw parity value** — re-implying the
  discount (the fragile regression slope) drifted to absurd rates on short-dated
  / dividend chains and shifted the IV level through 1/(D F). Threaded
  `reference_date` through `implied_forwards` (api/state, snapshot.py); coarse
  near-ATM de-Am keeps it ~0.1 s/expiry (cached). Live SPY now joins smoothly
  across ATM with sane discounts. Discrete-dividend chains can keep a small
  residual kink (continuous-yield tree); **now cured opt-in by discrete cash-
  dividend de-Americanization — see the dated entry above**.
  4 golden tests (tests/test_forward_debias.py).
- Phase 0 scaffold (no CI yet), Phase 1 complete (LQD engine reproduces both
  paper benchmarks; ATM-orthogonal coordinates with exact Newton retargeting).
- **Phase 2 complete**: calendar constraint = elementwise asset-share
  comparison; local-vol grid model done (`models/localvol/`): bilinear/pw_t
  grid, Crank–Nicolson Dupire forward PDE pricer (adaptive 7.5-sd mesh,
  <0.5 vol bp flat round trip in ~20 ms), Dupire extraction with butterfly
  gating, no-arb diagnostics. Not yet exposed via the API.
- Phase 3 near-complete (M3 reached): synthetic + **Yahoo provider**
  (`data/yahoo.py`, yfinance, sqrt-time expiry thinning, 0-bid→None mapping),
  parity forwards, SQLite VolStore, snapshot CLI (`backend/snapshot.py`).
  Live-verified 2026-06-12: SPY/QQQ/AAPL chains fitted end-to-end in the UI
  (SPY 5.5M: ATM 17.2%, skew -0.41; clean monotone variance term structure).
  Run live: `$env:VOLFIT_PROVIDER='yahoo'; $env:VOLFIT_TICKERS='SPY,QQQ,AAPL'`
  before serve.py. (Bloomberg/Massive providers + DuckDB/Parquet history TODO)
- Phase 4 complete (dense path): 6-node golden example reproduced exactly;
  smile-universe round trip works (graph posterior on (atm_vol, skew, curv)
  handles → exact arbitrage-free LQD smiles + credible bands); 1k nodes < 1 s.
  Matrix-free/Hutchinson large-N path deferred to Phase 9.
- Phase 5 core: FastAPI backend live (`volfit/api`): /universe, /smiles
  (3 fit modes, prior save), /fit/surface (POST + WebSocket per-expiry
  progress), /graph/solve (12-node universe), /scenario/ssr. Quote prep with
  parity normalization + 4-sd wing filter (`api/quotes.py`). Run it:
  `.venv\Scripts\python backend\serve.py` (port 8000, CORS for Vite).
- Phase 5 fit sessions: per-(ticker, expiry) quote edits (exclude/include/
  amend/reset) with bounded undo/redo (`api/session.py`), instant refit via
  POST /smiles/{t}/{e}/edits|undo|redo; edits shared across fit modes via a
  version-stamped fit-cache key.
- Phase 6 partial: SmileViewer wired to the live API (`state/useSmile.ts` +
  `state/smileSession.tsx` context): universe-driven selectors, fit-mode
  refetch, mock fallback when offline, TopBar live/mock/connecting status.
  Quote interaction done: click-select quotes, Del exclude/restore, arrow-key
  mid amend (Shift = coarse), Ctrl+Z/Y undo/redo, excluded quotes dimmed,
  amended mids amber (drag-to-amend not implemented; keyboard-first per spec).
- Phase 7 core: Graph Viewer live (`views/GraphViewer.tsx` + `useGraph.ts` +
  `GraphChart.tsx`): SVG lattice (tickers × expiries, calendar/cross edges),
  click to light nodes, per-node dAtmVol inputs, η slider, solve via
  /graph/solve (+ new GET /graph/nodes baseline endpoint), shift coloring +
  sd halos + tooltips, double-click drills into the Smile tab. Verified in
  headless Edge (screenshots: 2 observed → 10 extrapolated, sane decay).
- Phase 6 near-complete: Term-Structure view live (POST /term + `useTerm` +
  `TermChart`: vol & variance vs T, real/event-dilated clock toggle, editable
  event markers, expiry ladder table); density & quantile chart views
  (GET /smiles/{t}/{e}/density + `DistributionChart`, prior overlay once
  saved); Save-prior button (priors now store LQDParams via `PriorRecord`).
- Phase 8 complete: SSR scenario engine + frontend regime selector
  (Mny/Strike/LV) with spot-return slider and dotted overlay on the smile
  chart. (true sticky-local-vol-grid mode still awaits localvol API wiring)
- API slice fits use gentle high-order damping (default REG_LAMBDA=1e-6) —
  without it, slices left with ~7 quotes after the wing filter interpolate
  exactly with wild handles (GAMMA 1M fitted skew +0.78). Now user-tunable:
  **fit-settings hyperparameters** (GET/PUT /settings/fit: nOrder, regLambda,
  regPower) held on AppState with a settings version folded into every
  fit-cache key; HyperparamPanel in the Smile Viewer aside drives it.
- **[REQ done] Piecewise-affine local-variance calibration** per
  `Docs/piecewise_affine_local_variance_calibration.tex`:
  `models/localvol/affine.py` (P1 hat-function surface; **scipy Delaunay
  triangulation reproduces the note's quote table to every published
  decimal** — fixed-diagonal splits land ~2e-5 off; implicit-Euler forward
  Dupire in normalized strike with analytic multi-RHS forward sensitivities)
  + `affine_calib.py` (option + var-swap LSQ per eq. calibration_objective;
  log-contract replication; second-difference roughness **lambda=50**
  reproduces the note's calibrated nodal table to 1.5e-3 and all fit
  metrics). 10 golden tests in tests/test_localvol_affine.py.
- **Local-vol grid exposed via API** (`api/localvol.py`, GET /localvol/{t}):
  pw_t forward-variance buckets extracted at bucket midpoints from the
  fitted surface, session/settings-aware cache, no-arb diagnostics in the
  payload. **Sticky-local-vol-grid SSR regime** (exact: grid fixed in
  absolute strike, Dupire reprice, realized SSR reported; "LV grid" button
  in ScenarioPanel). Caveat documented in api/localvol.py: the shortest
  bucket's ATM slope is ill-conditioned (bp-level fit wiggles amplified by
  the small-w Dupire denominator) — realized short-expiry SSR can sit well
  below the theoretical ~2; mid/long buckets land in 1.5-2.5.

- **Realism block, part 1 done**: `core/american.py` (CRR binomial
  American/European pricer + `deamericanize()` → European-equivalent IV by
  Brent inversion) and the **stale parity-pair filter** in `data/forwards.py`
  (iterative 4-robust-sigma MAD trim floored at 1bp of spot, `n_outliers`
  reported).
- **[REQ done] Realism block, part 2 (complete)**:
  * **Dividends model** (`data/dividends.py`): continuous yield / discrete
    absolute (escrowed) / discrete proportional / mixed (cash near-dated
    switching to proportional past `switch_years` — desk practice);
    `theoretical_forward()` + `equivalent_yield()`, golden-tested.
  * **Forward mode per expiry** (`api/market.py`, `routers/forwards.py`):
    parity-implied (default) / theoretical (rate + dividend model, per-ticker
    `MarketSettings` via GET/PUT /settings/market/{ticker}) / manual override
    — GET /forwards/{ticker} shows all three side by side, PUT
    /forwards/{t}/{e} sets the policy; a `forwards_version` on AppState is
    folded into every fit-cache key so policy changes refit cleanly. Frontend
    `ForwardPanel` in the Smile Viewer aside (mode segmented control, manual
    input, carry r/q inputs); verified in headless Edge (manual override
    89.56 vs parity 87.80 refits the smile end-to-end).
  * **De-Americanization wired into quote prep** (`api/quotes.py`):
    `ChainSnapshot.exercise_style` flag (Yahoo heuristic: `^`-prefixed
    indices European, stocks/ETFs American; VolStore schema v2 persists it);
    American mids inverted via vectorized-bisection `deamericanize_batch`
    (one (n_quotes × steps) CRR sweep per iteration — chain-scale, ~50 ms vs
    seconds scalar), early-exercise premium subtracted from bid/mid/ask alike
    (spread preserved in price space); carry derived from the resolved
    forward (r = -ln D/t, q = r - ln(F/S)/t). Golden round trip: CRR-priced
    American chain at known σ(k) recovered within 30 vol bp.

- **[REQ done] Chart & UX block (2026-06-13)**:
  * **Strike-axis modes** on the smile chart (`lib/axisModes.ts` +
    SmileChart): k / fixed strike / %ATM / delta (numeric-bisection inverse,
    "25Δ"-style ticks) / normalized / log-normalized — geometry stays in
    k-space, only ticks/crosshair labels transform; selector in the chart
    header.
  * **3D vol-surface view** (`components/SurfaceChart.tsx`, zero-dep SVG:
    painter-sorted quads, drag-to-rotate yaw, vol colormap + legend) fed by
    GET /surface/{ticker} (`api/surface.py`: shared 61-pt union k grid over
    the fitted ladder, cached slice fits).
  * **Table export**: GET /smiles/{t}/{e}/table (JSON) + /table.csv
    (attachment download; `api/table.py`, prices reconstructed via
    normalized Black) and a Table chart-card view (`QuoteTable.tsx`) with
    Copy-TSV / CSV-download.
  * **Expiry classification** (`data/expiries.py`: leaps > quarterly >
    monthly (3rd Friday) > weekly (Friday) > daily; `expiryType` on
    /universe) + class filter chips next to the expiry selector (only
    classes present render; auto-reselects when the current rung filters
    out). **Full universe-selection UI now done** (the Universe tab: provider
    symbol search, add/remove, named universes); the chips still cover bulk
    expiry selection within a ladder.
  * SmileViewer split into UniverseHeader / SmileAside / useSmileShortcuts
    to stay under the 400-line policy. All verified in headless Edge
    (surface mesh, delta ticks, table grid, CSV Content-Disposition).

- **[REQ done] Fit time-series scaffold (2026-06-13)**: every calibrated
  slice (POST/GET/WS paths alike) persists into the VolStore `fits` table
  keyed by SNAPSHOT timestamp (`api/history.py`: fresh WAL connection per
  write for thread safety, dedupe on (ticker, expiry, ts, fitMode),
  exception-safe — persistence can never fail a fit; opt-in via env
  `VOLFIT_DB=path`, off by default). Query: GET /history/{ticker}/{tenorDays}
  ?fit_mode= — per snapshot picks the expiry nearest the tenor, returns
  {ts, expiry, t, atmVol, skew, curvature, varSwapVol, maxIvErrorBp,
  forward} ascending. Charting UI deferred.

- **[REQ done] CI + perf benchmarks (2026-06-13)**:
  * **GitHub Actions** (`.github/workflows/ci.yml`): three jobs — `backend`
    (py3.11/3.12 matrix: `ruff check .` + `pytest -m "not live and not perf"`),
    `perf` (single 3.11 runner: `pytest -m perf -s`), `frontend`
    (`npm ci` + `npm run build` strict-TS gate). Per-branch `concurrency`
    cancels superseded runs; pip + npm caches keyed on lockfiles.
  * **Perf budget suite** (`tests/test_perf.py`, `@pytest.mark.perf`): a
    `BUDGET_MS` table enforced by warmup-then-median timing of the four hot
    paths — LQD slice fit (~95 ms local), 1k-node graph update (~700 ms),
    local-vol CN forward solve (~20 ms), ~80-quote de-Am batch (~630 ms);
    budgets sit ~2.5-3.5x above local medians for slow-runner headroom.
  * Registered `perf`/`live` pytest markers + a `test` extra (httpx, pandas)
    in pyproject; tagged the live Yahoo test `@pytest.mark.live`; cleaned the
    6 pre-existing ruff findings so lint gates clean. Generated
    `frontend/package-lock.json` for reproducible `npm ci`.
    (process-pool for parallel slice fits still deferred — single fit ~95 ms,
    instant-refit target already met.)

- **[REQ done] Graph Viewer remainder (2026-06-13)**:
  * **Full solver panel**: GraphSolveRequest now carries the prior knobs —
    kappaScale (local stiffness), etaScale (reach), lambdaScale (OT flux, 0 =
    off, preserves the legacy regime), nu (source allowance) — plus
    calendarWeight/crossWeight edge overrides. Wired in the new
    `api/graph_service.py` (extracted from service.py to keep both under the
    400-line policy): `_reweighted_universe` rebuilds only the cheap graph from
    the cached handles when weights change; `_build_priors` applies the scales
    per handle coordinate. SolverPanel.tsx (η/κ log sliders, λ slider, ν +
    edge-weight inputs) drives it via useGraph; default solve unchanged.
  * **Auto-tune η** (POST /graph/autotune, `autotune_graph`): leave-one-out
    cross-validation over the lit observations across a geometric η grid,
    minimizing held-out ATM-vol RMSE; returns the chosen η + scored grid
    (rendered as bars in the panel, ≥2 lit nodes required).
  * **Lasso selection** in GraphChart: drag a rectangle on the lattice
    background to light every enclosed node (node groups stop mousedown so a
    plain click still toggles). 7 new graph API tests; verified end-to-end in
    headless Edge (lasso lit all 12 nodes, solve propagated, auto-tune adopted
    η=10×).

- **Model choice in the hyperparameter panel (2026-06-13)**: the Smile
  Viewer can now fit the displayed smile with **LQD** (default, arbitrage-free
  quantile density + the analytic backbone), **SVI** (raw-SVI own calibration,
  new `models/svi_jw/calibrate.py`: reparametrized LM fit, data-driven init,
  soft Lee-wing + min-variance no-arb penalties; recovers the note's SPX
  benchmark to machine precision — 7 golden tests) or **sigmoid** (existing
  `calibrate_sigmoid`). LQD is *always* fitted under the hood; a non-LQD choice
  attaches a `DisplayFit` overlay (`api/fit_models.py`) read by the smile
  chart, diagnostics, quote table, 3D surface and SSR scenario, while density,
  term-structure, local-vol and the graph universe stay LQD-based (they need
  the exact LQD coordinates). Overlay diagnostics (ATM handles, var-swap by
  log-contract replication, Lee wing slopes) come from the new model-agnostic
  `models/diagnostics.py` (matches the LQD closed forms on an LQD slice — 4
  tests); A_L/A_R report 0 (no endpoint-scale analogue off LQD). FitSettings
  `model` is now `lqd|svi|sigmoid`; the LQD-only N/damping knobs grey out off
  LQD in HyperparamPanel. Frontend strict-TS build green.

- **Direct local-vol-affine fit + Local Vol view (2026-06-13)**: the
  model-choice bullet is now fully closed. `POST /fit/affine/{ticker}`
  (`api/affine_fit.py` + `schemas_affine.py` + `routers/affine.py`) calibrates
  the piecewise-affine local-VARIANCE surface of the Docs note straight to a
  ticker's option quotes — gathers every expiry's edited quotes, converts mid
  IVs to normalized forward call prices with vega-scaled tolerances, builds a
  tensor vertex grid (0 + a spread of expiries × a strike grid incl. x=1) and
  the fine PDE x/t grids (t hits every quoted expiry), runs
  `calibrate_affine`, and reconstructs each expiry's arbitrage-free smile by
  inverting the Dupire PDE call prices through Black. Distinct from
  GET /localvol (Dupire *extraction* from the LQD fit). Cached per request
  hyperparameters. New frontend **Local Vol tab** (`views/LocalVolViewer.tsx`
  + `state/useAffine.ts` + `LocalVolHeatmap.tsx` nodal σ heatmap +
  `LocalVolSmile.tsx` reconstructed-smile-vs-quotes chart): vertex-grid /
  roughness controls, per-expiry fit + butterfly (min φ) diagnostics, arb-free
  badge. 6 API tests; verified end-to-end in headless Edge (ALPHA: arb-free,
  21 bp max error, 4×8 vertex heatmap, 0.5 s fit).

- **Realism leftovers done (2026-06-13)**: the last [REQ] bullet is closed.
  * **Dividend ex-date markers in the Term view**: POST /term now returns a
    `dividends` list (`DividendMarker`: exDate, real-time t, dilated tau,
    amount) for the ticker's discrete schedule within the curve range, emitted
    only under the discrete/mixed dividend modes (`api/analytics.py`
    `_dividend_markers`). TermChart draws them as emerald dashed verticals with
    a $amount label on both the real-time and event-dilated clocks (the
    per-expiry forward already drops across each ex-date; these are
    informational). 3 API tests.
  * **Dividend-schedule editor**: new `DividendEditor.tsx` embedded in the
    ForwardPanel — a mode picker (continuous / discrete cash / discrete
    proportional / mixed), an editable (ex-date, amount) row list with
    add/remove, and the mixed-mode switch horizon. ForwardPanel now PUTs the
    full MarketSettings (mode + schedule + switchYears, not just r/q), so the
    smile refits via the forwards version. Verified end-to-end in headless
    Edge (cash dividend → Term marker at t≈0.12y; editor shows the schedule).

**>>> MASSIVE FEED ROADMAP (the priority track — 3-tier source router) <<<**

The design (agreed 2026-06-15): all three tiers sit behind the as-of `(day →
moment)` model so the fitter never sees the difference.

0. **[DONE — verified 2026-06-15] Live REST feed confirmed end-to-end.**
   `massive_diag.py SPY` on both hosts: two-sided NBBO (376 quotes / 308
   two-sided), `underlying_asset.price` populated, stocks plan entitled. See the
   dated STATUS entry.
1. **[Tier 1 finish — CODE DONE + LIVE-VERIFIED 2026-06-15]** The three code
   sub-tasks of the live book are shipped (451 tests green), and the WS book is
   live-verified — but only via the **delayed cluster** (`wss://delayed.polygon.io/
   options`): the real-time cluster is silent on this (delayed-tier) key, so
   `MassiveWebSocket` now auto-advances a candidate URL list to the cluster that
   actually streams (`VOLFIT_MASSIVE_WS_URL` to override; set it to the delayed URL
   here to skip the ~6s warmup). The three sub-tasks:
   * **Contract-listing cache** (`MassiveProvider._intraday_contracts` keyed by
     `(ticker, frozenset(expiries))`, `refresh_contracts()` to invalidate) — the
     WS read (`_chain_from_book`/`option_tickers`) and the per-tick resubscribe
     diff no longer re-paginate the contracts reference every call.
   * **Resubscribe on universe change** (`AppState.sync_streaming` +
     `_desired_stream_contracts` + `MassiveProvider.streaming_contracts()` /
     `MassiveWebSocket.contracts`): a ticker added/removed or an expiry-selection
     edit while streaming now restarts the WS on the new subscription (was
     source/mode-change only). Providers that can't report their subscription are
     never thrash-restarted.
   * **Throttled full-refit loop** while a live book streams: a new scheduler
     branch (`Scheduler.tick`, gated by `AppState.is_streaming()` AND
     `autoCalibrate`) calls `workflow.stream_refit` every
     `OptionsSettings.streamRefitSeconds` (default 5s) — refetch chains from the
     book + recalibrate ALL lit nodes (background). `autoCalibrate` is the master
     switch: OFF ⇒ the loop is a no-op (surface still tracks spot via the transport
     poll; nodes stay stale until explicit Calibrate). Distinct from the
     minutes-cadence `optionsFetchMode == "auto"` REST refetch.
   **Remaining (optional) live-UI check:** drive the running app (Massive +
   Real-time) to confirm the throttled refit + resubscribe paths end-to-end in the
   scheduler thread (the engine paths are verified by the probe + tests).
2. **[Tier 2 — flat-file history — BACKEND DONE 2026-06-15, live-verify pending
   S3 creds]** S3 flat files → DuckDB/Parquet local store (the long-deferred
   columnar history). Shipped:
   * `volfit/data/occ.py` — OCC/OPRA option-symbol parse/format (the flat files
     carry only the `O:` ticker, which encodes strike/expiry/type). 11 tests.
   * `volfit/data/flatfiles.py` — `FlatFileStore`: DuckDB (+bundled `httpfs`)
     reads the gzipped daily aggregate CSV straight from S3, filters to the
     watchlist roots, caches the day to local **Parquet** (lazy, once per
     date×product), and reconstructs a `ChainSnapshot` at a target instant —
     **minute aggregates** for a past intraday moment, **day aggregates** for the
     official Close — quoting `close` as a zero-spread bid=ask=close, spot by
     parity. Injectable `source_uri` ⇒ offline tests run the real duckdb read of
     a local gzip CSV fixture. 5 tests.
   * Wiring: the store belongs to `MassiveProvider` (`flat_store=`), so the as-of
     layer is unchanged — `historical_modes()` gains **`eod`**,
     `available_history()` lists the last ~20 weekdays, and `fetch_chain(as_of=)`
     routes `eod`→day-aggs and a **past-day** `intraday` instant→minute-aggs
     (today-intraday still the REST `/v3/quotes` path). serve.py `_flat_store()`
     builds it from env `VOLFIT_FLATFILES_KEY`/`_SECRET` (+ optional
     `_ENDPOINT`/`_BUCKET`/`_PREFIX`/`_CACHE`); None without creds. 3 tests.
   `duckdb` is an optional `flatfiles` extra, imported lazily (core runs without
   it; tests `importorskip`). **LIVE-VERIFIED 2026-06-15** against `files.massive.com`
   (see the dated STATUS entry): bucket/layout confirmed, day + minute aggs
   reconstruct real SPY chains, full-pipeline EOD fit lands atmVol 15.6% / rms 35bp.
   Set `VOLFIT_FLATFILES_KEY`/`_SECRET` (+ `_ENDPOINT=files.massive.com`) to enable.
   Quote-level flat files only if true historical NBBO depth is needed (heavy).
3. **[Tier 3 — REST gap-fill — DONE + LIVE-VERIFIED 2026-06-15]** Closes the
   3-tier router. `MassiveProvider.historical_aggregate(contract, ts)` does a
   single-contract minute-bar lookup via `/v2/aggs` (close-based, broadly
   entitled) — live-verified (O:SPY…C00755000 @14:00Z → close 1.61). **TODAY's
   intraday serves the live REST snapshot** (the "now / pre-connect" chain) rather
   than a per-contract crawl — the whole-chain historical snapshot isn't
   bulk-available via REST, and a per-contract aggregate crawl over a full expiry
   times out (verified). `_fetch_agg_chain` (bounded-concurrency, per-contract
   try/except resilient) remains the rare flat-empty past-day fallback. Past days
   use the flat files (Tier 2); past-day-without-flat keeps the capped legacy NBBO.
   Live-verified: today-intraday → live snapshot (376 quotes, 297 two-sided, 1.7s).
4. **Spot source**: now that the stock plan is live, prefer the real
   `underlying_asset.price` / stocks spot; keep parity-forward as the fallback.
   Consider streaming the underlying quote channel for a true live spot.

**Then (general, in order):**
0. **🔴 Backend↔Frontend calibration sync consistency** — see the TOP PRIORITY
   block at the head of STATUS. Smiles stick on STALE / don't follow the latest
   calibrated model under Auto-calibrate-OFF + RT spot; backend is correct, the
   frontend refresh/STALE-flag is racy. Design a clean sync model (calibration
   epoch) rather than patching refetch edges. **Do this first.**
1. ~~Phase 10 follow-ups (`enforceCalendar` per-view, `varSwapEnabled` rows,
   `autoLoadPrior`)~~ — DONE 2026-06-16 (see the dated STATUS entry). Remaining
   smaller Phase 10 idea: a prior load/diff UI (the anchor exists; surfacing the
   prior overlay + a "load prior" affordance per node is still open).
2. Phase 9 hardening: arbitrage invariants as property tests, fuzzed quote
   sets, provider-failure injection; UX polish (skeletons, layout persistence;
   the error boundary + null-safe diagnostics now landed); Docker-compose
   packaging + user/API docs.
3. Smaller leftovers: process-pool for parallel slice fits; editable ATM handles
   + prior load/diff UI; cross-ticker "apply expiries to all" in the picker.

**Environment notes:**
- venv at repo root `.venv`; run tests: `cd backend; ..\.venv\Scripts\python -m pytest tests -q`
  (487 green as of 2026-06-16, incl. 4 perf-budget tests; opt-in live Yahoo
  test via `$env:VOLFIT_LIVE="1"`). Run only perf: `pytest -m perf -s`.
- Data sources: `restart.ps1` registers ALL feeds and auto-picks the best
  reachable as active; switch live via the TopBar **Data Source** selector
  (status light per source). Force one active on launch with
  `-Live`/`-Bloomberg`/`-Massive`/`-Synthetic`. Set `$env:VOLFIT_MASSIVE_KEY`
  to light up Massive (else it shows Red; the rest still work). Bloomberg needs
  an open Terminal (xbbg+blpapi are in .venv).
- API server: `.venv\Scripts\python backend\serve.py` (uvicorn :8000, CORS for
  Vite). Live data: set `$env:VOLFIT_PROVIDER='yahoo'` and
  `$env:VOLFIT_TICKERS='SPY,QQQ,AAPL'` first (yfinance installed).
- Snapshot CLI: `.venv\Scripts\python backend\snapshot.py SPY QQQ` → SQLite
  (`backend/data/snapshots.sqlite`, gitignored) + parity-forward diagnostics.
- Frontend: `cd frontend; npm run dev` — talks to :8000 when up, else mock
  fallback with an amber MOCK badge; `npm run build` is the strict-TS gate.
- Engine demo: `.venv\Scripts\python backend\demo.py`.
- PyPI is **intermittently flaky** on this machine (TLS resets toward Fastly;
  npm/Cloudflare fine). pip is configured with retries=15 in pip.ini — installs
  succeed with patience. Suspected AV/router TLS filtering.
- Sub-agents have no shell access here: they write code, the lead runs/verifies.
- UI smoke-testing recipe: `npm i --no-save puppeteer-core` in frontend, drive
  headless Edge (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`)
  against the Vite dev server, screenshot and inspect; delete the throwaway
  driver script afterwards.

---

## Architecture overview

```
┌─────────────────────────────── Frontend (React + TS) ───────────────────────────────┐
│  Smile Viewer        Surface/Term-Structure Viewer        Graph Viewer              │
│  (Plotly/visx)       (vol & variance, event time)         (force-directed, WebGL)   │
└───────────────▲──────────────────────────▲──────────────────────────▲───────────────┘
                │ REST (FastAPI) + WebSocket (live fit progress)      │
┌───────────────┴──────────────────────────┴──────────────────────────┴───────────────┐
│                              Python backend (FastAPI)                               │
│  ┌────────────┐  ┌──────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │ data layer │  │  quant core      │  │ calibration     │  │ graph solver       │  │
│  │ providers, │  │  models: LQD,    │  │ slice fits,     │  │ Gaussian update,   │  │
│  │ universe,  │  │  SVI-JW, sigmoid,│  │ calendar/no-arb │  │ OT mobility,       │  │
│  │ storage    │  │  local-vol grid  │  │ event dilation  │  │ marginal precision │  │
│  └────────────┘  └──────────────────┘  └─────────────────┘  └────────────────────┘  │
└──────────────────────────────────────┬───────────────────────────────────────────────┘
                                       │
                            SQLite (quotes, fits, priors, graphs)
```

**Package layout** (Python monorepo, each file ≤ 400 lines):

```
backend/
  volfit/
    core/        # Black/Bachelier pricing, implied vol inversion, quadrature, Lee bounds
    models/      # lqd/, svi_jw/, sigmoid/, localvol/  — one model = one subpackage
    calib/       # objectives, weights, constraints (butterfly/calendar), event time
    graph/       # operators (L_rev, L_dir, A_rho), prior, posterior, hyperparam calib
    dynamics/    # SSR, sticky-strike, sticky-local-vol scenario engine
    data/        # providers (yahoo, bloomberg, massive), dividends, universe, db
    api/         # FastAPI routers, schemas (pydantic), websocket fit-progress
frontend/
  src/
    views/       # SmileViewer, TermStructure, GraphViewer, UniverseSelector
    components/  # charts, sliders, quote-table, parameter panels
    state/       # zustand stores, API client, websocket hook
tests/           # pytest (unit + golden-number + arbitrage invariants), vitest/playwright
Docs/            # technical notes (existing)
```

**Tech decisions** (answering the open questions in CLAUDE.md):

| Question | Recommendation | Why |
|---|---|---|
| Front-end | **React + TypeScript + Vite**, Plotly.js (charts) + Sienna/visx or regl for graph view | Mature, fast iteration, professional look with Tailwind + Radix; nothing materially better for this use case |
| Storage | **SQLite for app state** (universes, fits, priors, graph configs) + **Parquet via DuckDB for quote history** | SQLite is perfect for transactional app data; columnar Parquet/DuckDB is far better for bulk option-chain snapshots and backtests |
| Compute | **NumPy vectorized + Numba JIT** for hot loops (LQD quadrature, graph solves via `scipy.sparse` + CHOLMOD/`sksparse`), optional JAX later for autodiff gradients | "Lightning-fast" target: one slice fit < 50 ms, full surface < 1 s, graph update on 10k nodes < 1 s |
| API | **FastAPI + WebSockets** | Async, pydantic schemas shared with frontend via OpenAPI codegen |

---

## Phase 0 — Foundations (week 1)

- [x] Git init, `pyproject.toml` (setuptools), pytest; frontend scaffold (Vite + TS + Tailwind v4). (ruff configured, mypy not yet)
- [x] CI: lint (ruff) + unit/golden tests + perf budgets + frontend build
  (`.github/workflows/ci.yml`). Type-check (mypy) still TODO.
- [x] Shared conventions: ≤400-line files, module docstrings referencing Doc equation numbers (established in code).
- [x] React shell with tab routing (Smile / Term Structure / Graph); FastAPI skeleton pending (deps installed late due to network).

**Exit criteria:** `make dev` runs backend + frontend hot-reload; CI green.

## Phase 1 — Quant core: pricing & LQD slice engine (weeks 2–4)

The LQD note (`Docs/lqd_model_note.tex`) is the centerpiece; implement it first
since other models are standard.

- [x] `core/black.py`: normalized Black formula B(k,w), vega, robust implied-variance inversion (Brent; closed-form ATM).
- [x] `models/lqd/basis.py`: Legendre recursion, endpoint scales A_L/A_R, Lee slopes.
- [x] `models/lqd/quadrature.py`: logit quadrature, martingale shift μ, asset-share A(z), analytic tail corrections (NumPy-vectorized; Numba not needed — slice fit ≈ 30 ms).
- [x] Pricing via cubic-Hermite interpolation on exact nodal derivatives (`models/lqd/interp.py`) — required for clean FD Greeks; density/quantile extraction in `LQDSlice`.
- [x] `models/lqd/atm.py` exact ATM functionals + `models/lqd/ortho.py` (Jacobian, least-norm primary directions, kernel shape modes, exact Newton retargeting).
- [x] `models/lqd/calibrate.py`: vega-weighted LSQ, A_R barrier, n^{2r} regularization, logistic initializer. (wing-aware & quantile-projection initializers still TODO)
- [x] Golden tests: both note benchmarks reproduced (μ to 4e-8; SVI fit < 2 vol bp; double-hat bimodal).

**Exit criteria:** both paper benchmarks reproduced to stated accuracy; slice fit < 50 ms.

## Phase 2 — Quant core: remaining models & no-arbitrage (weeks 4–6)

- [x] `models/svi_jw/`: raw-SVI + JW conversion (Appendix A) + **own
  calibration** (`calibrate.py`: reparametrized LM, data-driven init, soft Lee
  wing-slope & min-variance penalties; recovers the benchmark to machine
  precision). (full Gatheral–Jacquier butterfly conditions still TODO)
- [x] `models/sigmoid/`: 4-param sigmoid curve + LM fit (round-trip exact).
- [x] `models/localvol/`: bilinear (continuous piecewise-affine) and pw-const-in-t grid variants; CN Dupire forward PDE pricer (Rannacher startup, adaptive span); Dupire extraction with butterfly-gated denominator; round-trip + consistency tests. Exposed via the API (GET /localvol extraction + POST /fit/affine direct calibration) and the Local Vol view.
- [x] [REQ 2026-06-12] Local-vol calibration per `Docs/piecewise_affine_local_variance_calibration.tex`: `models/localvol/affine.py` + `affine_calib.py`, golden tests vs every table of the note (Delaunay triangulation is the note's convention; lambda=50 roughness reproduces the calibrated nodal table). **Exposed via the API** (POST /fit/affine/{ticker}, `api/affine_fit.py`) and the **Local Vol frontend view** (direct surface fit + reconstructed arbitrage-free smiles + no-arb diagnostics).
- [x] [REQ 2026-06-12] American-options handling, de-Americanization first: `core/american.py` CRR binomial + `deamericanize()` scalar and `deamericanize_batch()` (vectorized bisection, chain-scale). **Wired into quote prep**: `ChainSnapshot.exercise_style` flag (Yahoo heuristic + VolStore v2), EEP stripped from bid/mid/ask in `api/quotes.py`, carry from the resolved forward.
- [x] Common `SmileModel` protocol (`models/base.py`): `implied_w(k)`, `implied_vol(k, t)` — satisfied by LQD/SVI/sigmoid. (richer `density()`/`diagnostics()` surface TBD)
- [x] Calendar check via G_i(α) ≤ G_j(α): implemented as elementwise asset-share comparison on the shared logit grid (`calib/calendar.py`), soft-slack penalty in `calibrate_slice`, **toggleable**. (model-free butterfly check for non-LQD models TODO)
- [x] `calib/event_time.py`: dilated clock + variance-lumping term-structure interpolation; toggleable.
- [x] Surface construction: sequential nearest-to-farthest with warm starts and violation diagnostics (`calib/surface.py`).

**Exit criteria:** all 4 model families fit a test surface; arbitrage diagnostics (A_L, A_R, Lee slopes, μ, calendar residuals) reported for every fit.

## Phase 3 — Data layer (weeks 5–7, parallel with Phase 2)

- [x] Provider interface `OptionChainProvider` + deterministic `SyntheticProvider` (offline dev/tests) + `yahoo.py` (yfinance, lazy import, injectable factory, sqrt-time expiry thinning) + **`bloomberg.py`** (xbbg, OPT_CHAIN descriptor parse for cheap `available_expiries`, bulk `bdp` for the selected expiries, real `OPT_EXER_TYP` exercise style, `DVD_HIST_ALL` dividend import w/ forward projection) + **`massive.py`** (Massive/Polygon REST, contracts-reference expiries, chain snapshot quotes/greeks/IV, `NOT_AUTHORIZED` -> clear upgrade error, `iv_surface` overlay). Shared field coercion in `data/fieldmap.py`. Both live-verified.
- [x] Implied forwards by put-call parity regression (`data/forwards.py`, recovers F to <0.1% on synthetic).
- [x] [REQ 2026-06-12] Dividends model selection: continuous yield, discrete absolute (escrowed), discrete proportional, or mixed (absolute short-dated switching to proportional long-dated — standard desk practice) — `data/dividends.py`, feeds the theoretical forward. **Discrete schedule editable in the UI** (DividendEditor in the ForwardPanel) and **ex-dates surfaced as markers in the Term view** (event-time clock).
- [x] [REQ 2026-06-12] Forward fitting mode per expiry: **theoretical** (spot + carry from rate/dividend model), **parity-implied** (default), or **manually adjusted** (ForwardPanel UI override, held on AppState with a forwards version in fit keys); GET /forwards/{ticker} shows the three side by side.
- [x] [REQ 2026-06-12] Fit time-series scaffold: every calibration persists (params, ATM handles, diagnostics) keyed by snapshot timestamp into VolStore `fits` (`api/history.py`, opt-in via VOLFIT_DB) + GET /history/{ticker}/{tenorDays}; charting UI deferred.
- [x] Quote prep: mid/bid/ask + haircut modes, spread-based weights, 4-sd wing filter (`volfit/api/quotes.py`). (per-quote liquidity haircuts and richer outlier rules TODO)
- [x] Storage: SQLite `VolStore` (instruments, snapshots, quotes, fits, priors, universes; WAL, versioned schema). Parquet/DuckDB history TODO.
- [x] Universe dataclass + persistence, **now wired to the API and a dedicated
  Universe tab** (add/remove tickers via provider symbol search, save/load named
  universes). AppState holds the mutable active set.
- [x] [REQ 2026-06-12] Expiries bulk selection by type: `data/expiries.py` classification (`expiryType` on /universe) + class filter chips in the Smile header. (Full provider-driven universe-selection UI still TODO.)

**Exit criteria:** one command snapshots a 20-ticker universe from Yahoo into storage; forwards implied; quotes ready for calibration.

## Phase 4 — Graph extrapolation engine (weeks 7–10)

Direct implementation of `Docs/ot_bayesian_graph_extrapolation_expanded.tex`.
Nodes = smiles `(underlying, T)`; node scalar field = smile parameters in
**ATM-orthogonal coordinates** (level w₀, skew s₀, curvature κ₀, shape modes ξ)
— this is what makes the LQD ATM orthogonalization load-bearing: each
coordinate is propagated as its own graph signal `z = x¹ − x⁰`.

- [x] `graph/build.py`: node registry, row-normalized K, stationary π (dense solve), reversibilized conductances. (default-weight rules from sector/maturity proximity TODO)
- [x] `graph/operators.py`: L_rev, L_dir, mobility Laplacian A_ρ (log + arithmetic means).
- [x] `graph/prior.py`: Q_Δ = D_κ + ηL_dir + λ(A_ρ+νI)⁻¹ — **dense path** (fine to ~2k nodes; matrix-free/sparse deferred to Phase 9).
- [x] `graph/posterior.py`: covariance-form update, marginal precisions 1/K⁺_ii. (Hutchinson/selected-inverse large-N path deferred)
- [x] `graph/hyper.py`: marginal likelihood ℓ(θ) (Cholesky), standardized residuals ζ_i. (analytic gradient + auto-tune optimizer TODO)
- [x] Round trip (`graph/smile_universe.py`): handles (atm_vol, skew, curv) propagated per-coordinate → exact ATM retargeting → arbitrage-free LQD smiles + credible bands. Tuning insight: η such that smoothness residual ≈ 1/3 of increment scale gives ~75% same-ticker / ~6% cross-ticker propagation.
- [ ] Validation harness: hide x% of liquid smiles, extrapolate, score vs truth; calibration plots. (basic version exists in tests; systematic harness TODO)

**Exit criteria:** 6-node running example of the note reproduced exactly (μ⁺, π⁺ tables); 1k-node synthetic universe updates < 1 s; held-out validation report.

## Phase 5 — Backend API (weeks 9–11)

- [x] Routers: `/universe`, `/smiles/{ticker}/{expiry}` (fit_mode=mid/bidask/haircut, prior save), `/fit/surface` (POST + WS per-expiry progress), `/graph/solve`, `/scenario/ssr`, `/smiles/{t}/{e}/edits|undo|redo`.
- [x] Fit session model: edited quote set per smile (exclude/include/amend/reset), bounded undo/redo, version-stamped fit cache (`api/session.py`).
- [x] Var-swap level computation per slice (exact integral; in `SmileDiagnostics.varSwapVol`).
- [ ] Performance: process-pool for parallel slice fits across expiries/assets; cache quadrature grids. (in-process fit cache exists; pool TODO)

**Exit criteria:** full fit-edit-refit loop driveable from HTTP/WS; OpenAPI schema published for frontend codegen.

## Phase 6 — Smile Viewer frontend (weeks 10–14)

Professional, commercial, sleek (dark theme default, dense layouts, keyboard-first).

- [x] Smile chart (pure SVG, zero deps): prior vs current vs bid/ask I-beams, log-moneyness axis (fixed-strike mode designed in via `axisMode` prop), strike-range brush, crosshair readout. **Wired to live fits** via `useSmile` (universe selectors, fit-mode refetch, mock fallback when backend offline).
- [x] Quote interaction: click to select, Del to exclude/restore, arrow-key mid amend, Ctrl+Z/Y undo/redo; fit-to-bid-ask / mid / haircut toggle; instant refit on edit (~30 ms server-side). (drag-to-amend TODO if wanted)
- [x] Quantile-function & LQD density chart: prior vs current (`DistributionChart`, GET /smiles/{t}/{e}/density).
- [x] Term-structure view: vol and total variance vs T, calendar in real time **and** event-dilated time; event markers editable (POST /term).
- [ ] Diagnostics panel: A_L/A_R, Lee slopes, var-swap level shown; directly *editable* ATM handles (w₀, s₀, κ₀ via exact retargeting) TODO.
- [x] Prior management: save current fit as prior (button + PriorRecord with params); load/diff UI TODO.
- [x] Hyperparameter panel: **model choice** (LQD/SVI/sigmoid overlays, the
  N/damping knobs grey out off LQD), Legendre N, penalty coefficients.
  (arbitrage/event toggles in the panel still TODO)
- [x] [REQ 2026-06-12] Strike-axis modes on the smile chart: all six modes via `lib/axisModes.ts` (geometry stays in k-space; ticks/crosshair labels transform; delta inverted numerically).
- [x] [REQ 2026-06-12] 3D vol-surface chart: `SurfaceChart.tsx` zero-dep SVG mesh (painter-sorted quads, drag-rotate, colormap) on GET /surface/{ticker}.
- [x] [REQ 2026-06-12] Table export: GET /smiles/{t}/{e}/table + /table.csv attachment; QuoteTable grid view with Copy-TSV and CSV-download.

**Exit criteria:** trader workflow demo — load universe, inspect smile, drag ATM skew, erase a bad quote, refit, save prior — all fluid.

## Phase 7 — Graph Viewer frontend (weeks 13–16)

- [x] Graph visualization: structured SVG lattice (ticker columns × expiry rows, calendar + cross-ticker edges) — chosen over force-directed for legibility at current scale; WebGL/pan-zoom deferred to large-universe work.
- [x] Node states: **lit** (observed) vs **dark** (extrapolated), toggled by click or **lasso** (drag-rectangle lights all enclosed nodes), with per-node dAtmVol inputs. (ticker/expiry filters TODO)
- [x] Edge-weight input: calendar (same-ticker) and cross-ticker weight overrides in SolverPanel (rebuild only the cheap graph, fits cached). (per-edge matrix editor + sector rules + CSV upload TODO)
- [x] Solver panel: κ, η, λ, ν controls (SolverPanel.tsx) + leave-one-out "Auto-tune η" with a scored-grid readout. (live re-solve on every drag still manual via Solve; per-edge κ/λ TODO)
- [x] Result overlay: posterior shift as diverging node color, marginal sd as halo size/fade, hover tooltip with base→post + credible band; double-click → jump to that smile in the Smile Viewer.

**Exit criteria:** end-to-end demo — observe 5 smiles, light them, solve, watch 200 dark smiles update with uncertainty, drill into any one.

## Phase 8 — Vol-spot dynamics & scenarios (weeks 15–17)

- [x] `dynamics/ssr.py`: SSR on ATM vol, configurable; sticky-moneyness / sticky-strike / sticky-local-vol (SSR=2 short-maturity rule) regimes with exact shape-preservation invariant. (true sticky-local-vol-grid mode awaits the localvol model)
- [x] Frontend: regime selector + spot-shift slider with live re-render of shifted smile (ScenarioPanel + dotted overlay).

**Exit criteria:** spot ±5% scenario renders all three regimes consistently for any fitted surface.

## Phase 9 — Hardening, performance & polish (weeks 17–20)

- [x] Perf pass: budget table (`tests/test_perf.py`) enforced in the CI `perf` job — slice fit, local-vol forward solve, 1k-node graph update, de-Am batch. (Profiling-driven Numba/JAX tuning not needed yet; all paths inside budget.)
- [ ] Test depth: arbitrage invariants as property tests (every LQD iterate butterfly-free; calendar residuals ≤ τ), fuzzed quote sets, provider failure injection.
- [ ] UX polish: loading/skeleton states, error surfaces, layout persistence, theming, onboarding tour.
- [ ] Packaging: Docker compose (backend + frontend), one-line local install; user guide + API docs.

---

## Phase 10 — Workspace restructuring: tabs, Forwards & Options (SHIPPED 2026-06-14)

> Shipped — see the dated STATUS entry at the top for what landed. The checklist
> below is the original plan. The deferred "wire cheap" consumers
> (enforceCalendar/varSwap per-view, autoLoadPrior) were completed 2026-06-16
> (dated STATUS entry). Still open: the scenario auto-seed and the two stubs
> (autoCalibrate/spot), tracked as Phase 10 follow-ups in "Next up".

Reorganize the top-level tabs and consolidate the global / meta controls into a
single **Options** workspace, so the per-workspace asides only carry the live
controls a trader touches per node. No new quant math — this is an
information-architecture + settings-plumbing phase that surfaces engine switches
that already exist (and stubs the two that do not yet).

**Decisions locked in the 2026-06-14 planning Q&A (do not re-litigate):**
- **Options is hybrid**: it holds meta/UX + *defaults* + the penalty catalogue.
  The Parametric aside keeps only the live per-node controls (model, fit-mode,
  scenario). The Forward / Dividend panels *leave* the aside for a dedicated
  Forwards tab.
- **Wiring scope = "wire cheap, stub new."** Wire the toggles that map to an
  existing engine switch now (calendar/arb-fix, event-time dilation, var-swap,
  quote weighting, fit-mode + haircut, dynamics regime + SSR, all defaults).
  **Stub** the genuinely new ones as persisted UI state with a clear TODO:
  *auto-on-demand calibration* and *real-time spot streaming*.
- **auto-on-demand calibration** = a toggle between auto-refit on every edit
  (default ON, today's behavior) and a manual **Calibrate** button that gates
  refits (OFF). **Real-time / static spot** = stream live spot and re-price
  (real-time) vs freeze spot at load (static); pairs with the existing As-of
  selector. Both are stubbed this phase (UI + persisted flag; behavior TODO).
- **Local Vol sub-tabs mirror Parametric**, every view derived from the
  calibrated piecewise-affine LV surface (new backend derivations).
- **sticky-delta** maps to the existing `sticky_moneyness` regime (delta-space ≈
  moneyness-space); the UI labels it "sticky-delta", the `Regime` enum is
  unchanged (`sticky_moneyness` | `sticky_strike` | `sticky_local_vol`).

**Top-level tabs (before → after):**
```
before:  Smile · Term Structure · Local Vol · Graph · Universe
after:   Parametric · Local Vol · Forwards · Options · Graph · Universe
```
Term Structure ceases to be a top tab (it becomes a Parametric/Local-Vol
sub-tab). `App.tsx` `TabId`/`TABS` updated; `TopBar` unchanged structurally.

### 10A — Parametric workspace (rename Smile → Parametric, embed Term)
- [ ] Rename the tab **label** to "Parametric" (`App.tsx`). Keep the `smile`
  route id and `SmileViewer` component to minimize churn (or rename to
  `parametric` if cheap — label is what the user sees).
- [ ] Chart-card sub-tabs become **Smile · Density · Log Q-density · Term ·
  Surface · Table** — i.e. embed Term-Structure *alongside Density*. Add a
  `term` case to `ChartView` + `VIEW_HINTS` in `SmileViewer.tsx`; render
  `TermChart` (existing) in the chart body for the current ticker.
- [ ] Move the Term-Structure controls (event markers + real-time/dilated-clock
  toggle + expiry ladder table from `TermStructureViewer.tsx`) into a compact
  **TermControls** aside panel shown only when the Term sub-tab is active
  (mirrors how the strike-axis `select` shows only for the Smile view). The
  global Events ON/OFF *default* lives in Options; live per-session event
  editing stays here.
- [ ] Retire the standalone `TermStructureViewer.tsx` top-level view (its parts
  are reused: `TermChart` in the sub-tab, the controls in TermControls).
- [ ] Slim the aside (`SmileAside.tsx`) to **diagnostics + live model/fit-mode +
  scenario** only; remove `ForwardPanel` (→ Forwards tab) and the
  defaults-y knobs of `HyperparamPanel` (→ Options). Keep a minimal live
  model + fit-mode selector seeded from the Options defaults.

### 10B — Local Vol workspace (model-aware sub-tabs, derived from the LV surface)
- [ ] Add Parametric-style chart-card sub-tabs to `LocalVolViewer.tsx`:
  **Smile (reconstructed) · Density · Term · Surface (heatmap) · Table**, every
  view derived from the calibrated piecewise-affine local-vol surface (the
  existing `POST /fit/affine/{ticker}` result), not from the LQD backbone.
- [ ] Backend derivations from the cached affine fit (each ≤ 400 lines, new
  helpers next to `api/affine_fit.py`):
  - **Density**: Breeden–Litzenberger on the reconstructed arbitrage-free call
    prices per expiry (reuse `models/diagnostics.numeric_density` on the
    reconstructed slice).
  - **Term**: ATM vol / total variance / var-swap per expiry from the
    reconstructed smiles (same shape as `POST /term`).
  - **Table**: per-strike reconstructed prices/IVs (same shape as
    `GET /smiles/{t}/{e}/table`).
  Expose either as fields on the affine response or sibling GET endpoints that
  read the per-request affine cache; keep the response under the size policy.
- [ ] Frontend: reuse `DistributionChart` / `TermChart` / `QuoteTable` against
  the LV-derived payloads; the heatmap stays the "Surface" sub-tab.

### 10C — Forwards tab (new top-level, shared by Parametric + Local Vol)
- [ ] New `views/ForwardsViewer.tsx`: a per-ticker **forwards table** across all
  listed expiries (`GET /forwards/{ticker}` already returns every entry) — one
  row per expiry with the parity / theo / active columns and an inline
  mode selector + manual override (`PUT /forwards/{t}/{e}`), plus the
  ticker-level **carry (r/q)** and **dividend schedule** editor (reuse
  `DividendEditor`; `PUT /settings/market/{ticker}`).
- [ ] No engine change: both Parametric and Local Vol already read the active
  forward through the `forwards_version` fit-cache key, so edits here refit both
  workspaces automatically. Removing `ForwardPanel` from the aside is pure UI
  relocation.

### 10D — Options tab (new top-level: meta + defaults + penalties)
A preferences workspace (`views/OptionsViewer.tsx`, split into section
components to stay ≤ 400 lines). Sections:

1. **Calibration defaults** — seed every new fit/ticker/session:
   - Vol-surface model default (LQD / SVI / Sigmoid).
   - LQD: Legendre order N, damping λ + power r.
   - Sigmoid: SIV cores R + the MC-SIV defaults.
   - "Default parameters for LQD and Sigmoid" (initial-guess / bounds presets).
   - Quote weighting scheme (equal | tv_density).
   - Fit mode (Mid / Bid-Ask / Haircut) + Haircut value.
   - Local-vol **grid-size default** (nXNodes, nTNodes) + roughness λ.
   - **Prior default** (auto-load the saved prior as the fit prior on node load,
     on/off + behavior).
2. **Penalty catalogue** — each row: description + coefficient knob + formula +
   source module (formulas verified against the code 2026-06-14):

   | Penalty | Coefficient (knob) | Penalty term | Module |
   |---|---|---|---|
   | LQD high-order damping | `regLambda` λ, `regPower` r | λ · n^{2r} · a_n² (n ≥ 4; modes a₂,a₃ free) | `models/lqd/calibrate.py` |
   | Calendar slack (arb-fix) | `calendar_weight` (1e6) | w · Σ max(floor − Gᵢ(α), 0)² | `calib/calendar.py`, `lqd/calibrate.py` |
   | SVI min-variance | `_PENALTY_WEIGHT` P | P · max(−(a + bσ√(1−ρ²)), 0)² | `models/svi_jw/calibrate.py` |
   | SVI Lee wing | `_PENALTY_WEIGHT` P | P · max(b(1+|ρ|) − 2, 0)² | `models/svi_jw/calibrate.py` |
   | Band hinge + mid anchor | `haircut` h, `MID_ANCHOR_WEIGHT` (0.05) | max(model−ask,0)² + max(bid−model,0)² + 0.05·(model−mid)² | `calib/band.py` |
   | Affine LV roughness | `regLambda` (note λ=50) | √λ · L(θ − θ_ref), L = 2nd diff in (t, x) | `models/localvol/affine_calib.py` |
   | Sigmoid amplitude ridge | `_RIDGE` | ridge · Σ α_r² (hat amplitudes) | `models/sigmoid/calibrate.py` |

   Editable where a coefficient is a real knob (λ, r, haircut, calendar_weight,
   roughness); the others render formula + description read-only.
3. **Toggles — wired this phase** (map to existing engine switches):
   - **Arbitrage fix** ON/OFF → `enforceCalendar` (promote the per-request
     `SurfaceFitRequest.enforceCalendar` to a global default on `AppState`).
   - **Events** ON/OFF default → `eventsEnabled` (promote from
     `TermStructureRequest.eventsEnabled`).
   - **Variance-Swaps** ON/OFF → compute/show the var-swap level + column.
   - **Spot-Vol dynamics** default → regime (sticky-strike / sticky-delta /
     sticky-LV) + **SSR value** (feeds the Scenario panel's default).
4. **Toggles — stubbed this phase** (persisted UI state + behavior TODO):
   - **Auto-on-demand calibration**: auto-refit on edit (ON, current) vs manual
     **Calibrate** button (OFF). Persist the flag; gating behavior is TODO.
   - **Real-time / static spot prices**: stream live spot + re-price vs freeze
     at load. Persist the flag; streaming behavior is TODO (pairs with As-of).

### Backend — global settings plumbing
- [ ] New global **app/meta settings** on `AppState` (extend `FitSettings` or add
  a sibling `OptionsSettings` schema; keep schema files ≤ 400 lines) covering:
  model/N/damping/haircut/weighting (already in `FitSettings`) + grid-size
  default, var-swap on/off, prior default, events default, arb-fix default,
  dynamics regime + SSR default, spot mode (stub), auto-calibration (stub).
- [ ] `GET/PUT /settings/options` (or extend `GET/PUT /settings/fit`); fold the
  fit-affecting fields into the existing **fit-cache version** so every view
  refits consistently (same pattern as `settings_version` / `forwards_version`).
- [ ] Thread the promoted globals (`enforceCalendar`, `eventsEnabled`, var-swap,
  regime/SSR, grid-size) into the surface/term/affine/scenario call sites as the
  *default*, with any live per-node control still overriding.

### Tests & exit criteria
- [ ] Backend: settings round-trip + cache-version bump tests; LV-derived
  density/term/table golden tests (match the Parametric-shape payloads on an
  arbitrage-free affine fit); arb-fix/events/var-swap default propagation tests.
- [ ] Frontend: strict-TS build green; the six top tabs render; Parametric shows
  the Term sub-tab next to Density; Local Vol shows the five derived sub-tabs;
  Forwards edits refit both workspaces; Options persists and refits.
- [ ] Headless-Edge smoke: rename verified (Parametric), Term embedded, Forwards
  table edits a forward end-to-end, Options toggles persist across reload.
- **Exit:** tabs reorganized to Parametric · Local Vol · Forwards · Options ·
  Graph · Universe; Term embedded; Local Vol mirrors Parametric off the LV
  surface; Forwards & dividends live in one shared tab; Options drives all
  defaults/penalties/toggles (two stubbed) with a single global settings round
  trip; all tests green; files ≤ 400 lines.

---

## Execution policy (per CLAUDE.md)

- **Sub-agents:** parallelize by vertical — quant-core agent, data agent, graph agent, frontend agent — coordinated through the `SmileModel` and API interface contracts frozen at end of Phase 1/5 respectively. Spawn review agents for arbitrage-math correctness on every quant PR.
- **File size:** hard cap 400 lines; split by responsibility (basis/quadrature/pricing/calibrate pattern above).
- **Speed:** every quant function vectorized; benchmarks in CI with regression gates.
- **Comments:** every module gets a header docstring linking to the equation numbers of the relevant Doc note (e.g. "implements eq. (mu_norm) of lqd_model_note").

## Key risks & mitigations

1. **Yahoo scraping fragility** → cache snapshots, provider abstraction, fall back to stored data; treat Bloomberg/Massive as optional plug-ins.
2. **Dividends/forwards quality** → parity-implied forwards first (robust), explicit dividend curves later; sanity-check vs spot-carry.
3. **Graph hyperparameter opacity** → empirical Bayes + held-out ζ calibration baked in from day one (note §9); never ship point estimates without marginal precision.
4. **Local-vol grid arbitrage** → grid model is the hardest to keep arbitrage-free; gate it behind diagnostics and ship it last within Phase 2.
5. **Performance creep in UI** → WebSocket incremental updates, debounced refits, WebGL graph rendering from the start.

## Milestone summary

| Milestone | Content | Target |
|---|---|---|
| M1 | LQD engine reproduces both paper benchmarks | end W4 |
| M2 | 4 model families + no-arb surface construction | end W6 |
| M3 | Live Yahoo universe snapshot → calibrated surfaces | end W7 |
| M4 | Graph solver reproduces 6-node example; 1k-node < 1 s | end W10 |
| M5 | Smile Viewer trader-workflow demo | end W14 |
| M6 | Graph Viewer end-to-end extrapolation demo | end W16 |
| M7 | Vol-spot dynamics scenarios | end W17 |
| M8 | v1.0: packaged, benchmarked, documented | end W20 |

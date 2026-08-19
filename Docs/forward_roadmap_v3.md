# Forward Roadmap v3 — proposals + phased plan (drafted 2026-08-20)

Fifteen user-listed items, surveyed against the codebase as of commit 2cf1d11
(tails+calendar arc Phase 3), detailed into precise proposals, and ordered into
implementation phases. Conventions throughout: golden tests citing the Docs/book
equations, files ≤ 400 lines, byte-identity for every default-off path, commit per green
batch, captures/benchmarks in the user's window.

**Item → section map** (the user's numbering):

| # | Item | Group | Phase |
|---|------|-------|-------|
| 1 | Hard constraints, LQD calendar | A | V3.0 |
| 2 | Evolve MCS (calendar, tails) + re-emphasis vs SVI | A | V3.1 |
| 12 | Comparison UI LQD / SVI-JW / MCS | A | V3.2 |
| 3 | LV stacked variance untruncated | C | V3.3 |
| 10 | Stacked variance: visualize the cross | C | V3.3 |
| 11 | Densities: visualize sub-zero | B | V3.3 |
| 4 | Fit-target overlay (mid / band / haircut) | B | V3.4 |
| 5 | Weighting-scheme histogram | B | V3.4 |
| 9 | Separate Calibrate LV / parametric | C | V3.5 |
| 13 | Animate the LV compute | C | V3.5 |
| 14 | Var-swap setting improvements | B | V3.6 |
| 15 | Unified fetch + auto-roll prior | D | V3.7 |
| 6 | Full-day 15-min replay + LOO scenarios | D | V3.8 |
| 7 | Kalman filtering evidence | D | V3.9 |
| 8 | Prior persistence evidence | D | V3.9 |

Terminology notes (resolved during survey, veto here if wrong):
- "MQS" = **MCS, the Multi-Core Sigmoid** (volfit\models\sigmoid\, book ch. 3).
- "Graph option 1 / option 2" (item 6) = **precision_messages** (production default,
  best measured intraday) / **layered_dynamic_harmonic, H=0.1d** (the adjudicated
  interior optimum). smooth_field is kept as the control column.
- "Dark, spot-only" (item 6) = the transported-prior baseline (the base_* columns the
  LOO scorer already computes on every row).
- Basket for item 6 = **NVDA, AAPL, MSFT + SPY** (SPY stands in for the index — the
  intraday REST path lacks SPX/SPXW multi-root discovery; recorded as a rider).

---

# Group A — model core (items 1, 2, 12)

## Item 1 — Hard constraints for LQD calendar arbitrage (tails+calendar arc Phase 4)

**This is the standing green-lit arc's final phase** — the spec already exists
(Docs\generalized_tails_calendar_roadmap.md §Phase 4; book ch. 2, eq.
globalledgerconstraint + the B_implementation.tex exchange pseudocode). This proposal
pins the open implementation decisions.

**Current reality.** The exact full-line certificate (calendar_certificate.py) is live as
the acceptance/publish authority but is called ONLY from quality.py — nothing in the
solver consumes it. The joint stack (symmetric_stack.py) enforces calendar order via a
soft price-space hinge on a 33-node tapered strike grid + penalty escalation
(symmetric.py: ×10 up to 3 escalations, 4 growth passes) — violations that survive are
"irreducible slack", never a refusal. Row layout is frozen at build time; the analytic
dA/dθ evaluation the new rows need is inlined inside residual_jacobian, not exported.

**Proposal.**
1. **Export `asset_share_rows(slice_, d_az, d_dadz, z)`** from models\lqd\jacobian.py —
   the ledger-space analogue of `call_price_rows` (the eq. pass1–pass3 sensitivities
   evaluated at arbitrary ranks; today inlined at jacobian.py:257-259).
2. **Per-rank calendar-G interface rows** in symmetric_stack: for each adjacent pair, an
   active rank set {z_r}; rows `sqrt(w_cal)·max(G_near(z_r) − G_far(z_r), 0)` in LEDGER
   space (the book's constraint object, replacing nothing — the existing price-space
   hinge rows stay as the smooth in-loop screen). Analytic Jacobian: active mask ×
   (+dA_near into the near block, −dA_far into the far block), mirroring the existing
   interface-row writes. Row layout rebuilt per exchange round (stacked_functions is
   already rebuilt per escalation attempt — same cost class).
3. **Exchange driver**: new module `calib\symmetric_exchange.py` (new file — the 400-line
   policy) implementing the book loop:
   `active = {}` → joint_refit with current rank rows → rebuild each slice at the FULL
   quadrature grid (N_POINTS=8001) → ledger_certificate per adjacent pair (the Phase 0
   authority — certifying at the acceptance grid closes the 2001-vs-8001 exit-gate
   mismatch; the certificate is ~0.2 ms/pair) → if all certified(_CAL_TOL) accept; else
   add each failing pair's minimizer z* to its active set → repeat, MAX_EXCHANGE_ROUNDS
   (default 8; the book: "the active ranks are few").
   Seed: empty active set (round 1 = today's behavior); the certificate minimizer IS
   initial_calendar_ranks for round 2.
4. **Wiring**: surface_symmetric.phase_b_repair runs the existing penalty+escalation
   pass first (it repairs most cases and its locks stay untouched), then the exchange
   loop ONLY for pairs whose full-line certificate still fails. Non-convergence after
   MAX_EXCHANGE_ROUNDS: keep the best iterate, report through SurfaceRepair
   (violations_after/max_slack — existing semantics), publish stays blocked by the
   certificate downstream (existing). The book's "smallest quote-band relaxation needed
   for feasibility" infeasibility diagnostic is recorded as a rider, not v1.
5. **Perf**: new perf rail on the exchange driver (2-slice standard fixture, budget set
   from measurement); the existing calendar_certificate 25 ms rail untouched.
6. **Tail-order clause stays advisory in v1** (the λ± seam rows already ARE the
   monotonicity rows at common α; promoting ledgerTailOrderOk to a gate is recorded as a
   Phase-4 rider pending a repair path for it).

**Exit gates (from the arc spec).** No accepted surface fails the certificate on the
suite's ladders + the rigged-dip fixtures; clean ladder byte-identical to independent
fits (fast path untouched — exchange enters only on certificate failure); the FD-vs-
analytic stacked Jacobian lock extended to the new rank rows; benchmark-pack fit-quality
regression bounded (user-window run); certification case updated; full suite green.

## Item 2 — Evolve MCS (Multi-Core Sigmoid): calendar arbitrage, tails, re-emphasis vs SVI

**Current reality.** MCS is wing-NEUTRAL, not wing-admissible: kernels preserve base
slopes but nothing caps them (Lee slopes are numeric FDs at k=±6, diagnostic-only, no
buffer/cap/chart). Calendar is a 41-node sampled w_far ≥ w_near hinge confined to the
common quote support — the "sampled screen" class Phase 0 retired for LQD; the exact
certificate runs on the LQD backbone, never on the published MCS curve. Belly: MCS is
certificate-GATED (publish blocker) but has NO repair path — display.py gates repair on
model=="svi" (the roadmap's "MCS belly repair" rider names exactly this asymmetry, and
the book measures the failure: MCS at M=2 fails the dense-grid check on most SPY
expiries). Kernel non-uniqueness is unmanaged beyond an amplitude ridge. The adjudication
instrument exists (backtest\dispatch.py sweeps SIV-0/1/2 vs SVI variants vs LQD) but has
no calendar columns and no certificate-gated verdict.

**Proposal (mirrors the ratified SVI committee arc, leg by leg).**
1. **Analytic k-space Lee slopes** for MCS (closed form from the base's z-space wing
   slopes s0 ∓ 2k0/κ and the z=k/(σ_ref√T) chart; kernels contribute zero by
   lem:zerowing) — replaces numeric_lee_slopes in diagnostics, quality leeOk, and the
   extrap slope-order row for the sigmoid family. Golden vs the numeric values.
2. **MCS belly repair**: the sigmoid branch of build_display_fit runs belly_certificate
   on the traded range; on failure, ONE hinge refit (rows sqrt(W)·max(−g + 2e-4, 0) via
   _eval_g on the traded grid — the machinery already exists for the wing penalty),
   kept only if re-certified; DisplayFit.belly_repaired flows through (field exists).
   OverlaySettings (the pool-worker pickle contract) gains the MCS flags.
3. **Lee admissibility — structural chart port**: `models\sigmoid\structural.py` —
   chart (β_L, β_R, v*, z*, κ_p, κ_c) with logistic wing lifts against the buffered
   leeSlopeMax cap so every finite optimizer vector is admissible, + closed-form chart
   chain for the analytic Jacobian (the svi_jw\structural.py pattern, incl. the two
   float-boundary saturation guards that arc found). `FitSettings.mcsChart:
   Literal["raw","structural"] = "raw"` — flip only after adjudication (the sviChart
   precedent: pre-registered benchmark, then ratified flip).
4. **MCS calendar upgrade** (two legs):
   a. In-fit: extend the variance floor/ceiling grid beyond the common quote support
      (wing crossings are exactly what a support-confined grid misses), density matched
      to the current 41-node budget.
   b. Certificate: `mcs_calendar_certificate(near, far)` — dense-grid scan of
      w_far − w_near + Newton-polish of each local minimum (smooth closed-form curves —
      polished minima are exact to tolerance) + the analytic wing-order clause from (1)
      deciding the far field. Honest labeling: polished-dense, not sample-free like the
      LQD ledger object. Wired into quality for sigmoid-displayed nodes as overlay
      fields (the backbone ledger certificate stays; today MCS calendar order is
      certified only for the backbone that shadows it).
5. **Kernel governance**: prune kernels with |α| under quote-noise resolution after the
   fit (re-fit once without them), report effective cores; the book's "governed dial".
6. **Re-emphasis vs SVI — adjudicated, not asserted**: extend backtest\dispatch.py with
   calendar columns + certificate-gated verdicts (a fit that fails its certificate
   scores as invalid regardless of rms); run the sweep on the stored regime fixtures;
   FINDINGS_mcs.md with a pre-registered gate; if MCS-structural beats SVI-structural
   under the gated protocol, re-emphasis lands as (i) HyperparamPanel ordering/copy,
   (ii) the compare view (item 12) defaulting MCS on, (iii) an Options default proposal
   recorded for user ratification — never auto-flipped.
7. **File split**: sigmoid\calibrate.py (432 lines) splits into seeding / residual
   assembly / entry (≤400 each).

**Exit gates.** All byte-identity locks green unmodified (no-floor/no-penalty/no-prior
fits bit-identical; nCores=2 default untouched); analytic-vs-FD Jacobian locks extended
to the chart; belly repair: clean fits never refit, repaired fits re-certify, cert case
extended; adjudication artifact produced with pre-registered gates; suite + frontend
green.

## Item 12 — UI: model comparison LQD / SVI-JW / MCS

**Current reality.** One model per fit globally (FitSettings.model bumps
settings_version → whole-universe refit; the previous family's record is orphaned — no
way to hold two models' fits simultaneously, no model in fit_key). The comparator exists
offline (backtest\dispatch.fit_node: prepare once, fit every family, one metrics row
each, per-family analytic validity signal). SmileChart already supports multiple named
overlay curves; OverlayCurvesChart is a generic multi-series chart; useLooComparison is
the client-side comparison-table pattern; the book's model palette is LQD green / SVI
blue / MCS violet.

**Proposal.**
1. **Endpoint**: `GET /smiles/{ticker}/{expiry}/compare?models=lqd,svi,sigmoid&fit_mode=…`
   — read-only relative to the committed record (STRICTLY no fit_or_get, no pointer
   moves, no spot mutation — the quality.py rule): prepares the node once
   (dispatch.fit_node pattern), fits each requested family ad hoc via build_display_fit
   (pure function; fan out through fit_pool when workers available), caches under its own
   (fit_key, model) side map (invalidation = fit_key change, for free). Response per
   model: curve (SmilePoints on the display grid), rmsBp, maxIvBp, atmVol, skew,
   leeLeft/Right, varSwapVol, validity {kind: density|g, minValue, certified}, nParams,
   fitMs. `_analytic_butterfly` lifts from backtest\dispatch.py into
   models\diagnostics.py (one protocol, three families — never reimplemented).
2. **Schemas**: new `schemas_compare.py` (the schemas_quality/schemas_affine split
   convention) + router registered in ALL_ROUTERS.
3. **Frontend**: new "compare" ChartView in SmileViewer: model-coloured
   OverlayCurvesChart (palette module lib\modelColor.ts: LQD green / SVI blue / MCS
   violet — the book convention) over the quote I-beams, + a metrics table
   (useModelComparison.ts hook mirroring useLooComparison; null metric = not defined for
   that family), fetched lazily when the tab opens (2 extra fits per node, on demand
   only). Mock fallback in mockData.ts (the app must work backendless). Smoke: the
   8-tab headless-Edge pass gains the sub-tab.
4. **Explicitly NOT v1** (recorded riders): fit_key gaining a model dimension /
   FitRecord.displays dict (invasive across displayed.py, quality, export, graph — no
   consumer needs it once the compare endpoint has its own cache); eSSVI comparator
   column (rides its existing R0 rider).

**Exit gates.** Compare read provably does not move the calibrated pointer (lock);
byte-identity of the committed record across a compare call; per-family validity fields
match the lifted diagnostics on rigged fixtures; vitest for the hook/table; smoke green
with the new tab.

# Draft proposals — items 4, 5, 11, 14 (smile-viewer UI group)

## Item 4 — Fit-target overlay on the smile (mid line / bid-ask band / haircut band)

**Problem.** The fitter supports three objectives (`FitMode = mid | bidask | haircut`,
schemas.py:38) but the chart draws only per-quote I-beams (SmileChart.tsx:447-497) — a
haircut fit looks identical on screen to a bid-ask fit. The haircut band
(`lo = min(bid+h, mid)`, `hi = max(mid, ask−h)`, band.py:69-73, h absolute vol points,
default 0.005) is computed backend-side and never serialized.

**Proposal.**
- Backend: attach optional per-quote target fields to `QuoteBand` (frozen-contract-safe
  optional additions, pattern = SmileData.stale?): `targetLo`, `targetHi`, resolved by the
  SAME `resolve_band` call used by the fit (band.py:51) with the request's `fit_mode` and
  `FitSettings.haircut` — so amended-mid recentering and the collapse-to-mid clamp are
  inherited, never re-implemented. `fit_mode="mid"` ⇒ fields omitted (target is the mid
  polyline). Attach at service.py:1394-1409 (fitted path) and :1259-1272 (no-fit path).
- Frontend: new helper `lib/smileTarget.ts` (SmileChart.tsx is 632 lines — over the
  400-line policy; all new geometry goes in the helper):
  - **mid line**: thin polyline through non-excluded `mid`s in display coords (through
    `tx()` = axisTransform, SmileChart.tsx:173) — shown in all modes (it is the target in
    mid mode, the anchor term elsewhere, weight `midAnchorWeight` 0.05).
  - **bid-ask band**: translucent ribbon through (bid, ask) of non-excluded quotes —
    interpolated between strikes, low opacity, drawn UNDER curves.
  - **haircut band**: darker ribbon through (targetLo, targetHi) inside the bid-ask
    ribbon — the "compressed band". Only when fit_mode="haircut".
  - Excluded strikes: ribbon gap (skip segment), so exclusions stay visible.
  - Legend entries + one segmented toggle "Target: off / mode / all" in the chart header
    (there is no toggle framework; keep it a single local state like showMassiveIv,
    SmileViewer.tsx:374-387).
- The active band shown always matches the CURRENT `fitMode` from the session
  (useSmile.ts:181) passed down as a new SmileChart prop.

**Tests/gates.** Backend lock: targetLo/Hi under all 3 modes × amended mid × excluded ×
tight-quote collapse (lo=hi=mid when spread < 2h). Frontend vitest on the ribbon-path
builder (gap at exclusions, display-coord mapping). α=0/no behavior change to fits —
pure additive payload.

## Item 5 — Weighting-scheme histogram (original distribution vs rescaled weights)

**Problem.** Weights are invisible: `resolve_weights` (weights.py:92) returns None for
"equal" and mean-1 `max(TV,eps)·s_i/s̄` for "tv_density"; no API exposes per-quote
weights; QuoteTable has no weight column; the scheme control is two unexplained buttons
(HyperparamPanel.tsx:112-119).

**Proposal.**
- Backend: new read-only, poll-safe endpoint `GET /smiles/{ticker}/{expiry}/weights`
  (quality.py precedent: reading never triggers a fit; build from prepare_slice +
  edited_fit_inputs, NOT fit_or_get). Response per included quote, aligned to
  `QuoteBand.index` (explicit remap — weights are computed on the post-edit shorter
  array, service.py:586-587):
  - `k`, `index`
  - `spacing` s_i (Voronoi cell width in k — the "original distribution" is its inverse:
    quote crowding)
  - `weightRaw` (pre-normalization: max(TV_i, eps) for tv_density; 1.0 for equal)
  - `weight` (final mean-1 value the LSQ actually uses; ones materialized for "equal")
  plus header fields: `scheme`, `maxMult` (10.0 cap), `meanNormalized: true`.
- Frontend: collapsible **weight strip** mounted under SmileChart above the RangeBrush
  (SmileChart.tsx:620-629), sharing the x-axis transform:
  - bars series 1 "quote density" = 1/s_i (normalized to max 1) — where quotes crowd;
  - bars series 2 "effective weight" = mean-1 `weight` — what the fitter actually sees;
  - hover ties into the smile hover; excluded quotes shown as empty outlines.
  - A weight column in QuoteTable (231 lines — room) with the same numbers.
- Updates on quote edit / scheme change (same triggers as smile refetch).

**Tests/gates.** Backend: endpoint lock for both schemes (equal ⇒ ones; tv_density
matches resolve_weights exactly incl. cap + mean-1), exclusion remap, poll-safety (no
fit-cache entry created). Frontend vitest on the strip's binning/alignment.

## Item 11 — Sub-zero density evidence

**Problem.** Negative density (butterfly arb in SVI/MCS overlays) is destroyed before
serialization: diagnostics.py:151 clips `pdf = max(g,0)·…` then RENORMALIZES (:152-154),
so both density endpoints ship a curve that cannot dip and whose area-normalization
differs from the model's true pdf. The signed diagnostics exist (belly_certificate:
min_g, argmin_k, neg_share — diagnostics.py:182-231) but bellyMinG/bellyArgminK never
reach the UI (useQuality.ts:9-44 lacks them) and neg_share is computed then dropped
(quality.py:312-314).

**Proposal.**
- Backend: `numeric_density` returns the raw signed pdf alongside the clipped one; new
  OPTIONAL fields `densityRaw` (signed, un-clipped; same grid) on `DistributionArrays`
  and `minDensity`/`minDensityX` on `StackedDensityItem`. Guard: only attached when a
  negative region exists (LQD is structurally positive — quadrature.py:247 — so the
  fields appear only for SVI/MCS overlays; document that). Fix the stride hazard: the
  argmin/min are computed on the FULL grid BEFORE `_trim` striding (analytics.py:196),
  so a narrow dip can't be sampled away even if the plotted curve misses it.
- Also surface the already-computed certificate numbers: add `bellyMinG`, `bellyArgminK`,
  `butterflyCertified`, `bellyRepaired`, `negShare` to the quality payload consumption in
  useQuality.ts + a QualityViewer chip (backend already emits most at quality.py:308-318;
  add negShare there).
- Frontend:
  - StackedDensityChart (OverlayCurvesChart is READY: zero baseline + negatives visible,
    OverlayCurvesChart.tsx:131, :210-212): fill the sub-zero excursion in red and draw a
    **circle marker at (minDensityX, minDensity)** with a hover readout (mirrors item 10's
    calendar-cross circle).
  - DistributionChart.tsx:112: `yLo = Math.min(0, dataMin)` instead of hard 0; same red
    sub-zero fill; show BOTH curves when they diverge (raw signed vs clipped-renormalized,
    clipped dashed) so the renormalization contamination is explicit, not hidden.
- Chart hint text (SmileViewer.tsx:65) and analytics.py:278-279 docstring rewritten: the
  non-negativity claim is only structural for LQD.

**Tests/gates.** Backend: a rigged SVI slice with a known g<0 dip — densityRaw dips,
clipped doesn't, minDensityX within tolerance of belly argmin_k mapped to x; LQD slice ⇒
fields absent; stride-hazard lock (dip narrower than the display stride still reported).
Threshold discipline: UI flags negativity iff min_g < −CERT_G_TOL (1e-4,
diagnostics.py:179) — never invent a new threshold.

## Item 14 — Var-swap setting improvements

**Problem.** The panel edits one scalar with heuristic slider bounds, shows no weight, no
basis, no staleness; TermPanel hardcodes canUndo/canRedo=true (TermPanel.tsx:91-92);
LocalVolViewer wires the Parametric node's var-swap while showing the LV surface
(LocalVolViewer.tsx:539-550); no term-structure editing; the penalty strength is
invisible at the point of use.

**Proposal (scoped package, one node = one scalar stays the invariant).**
1. **Payload**: optional `VarSwapInfo` additions — `basisBp` (quote − model, vol bp),
   `weightPct` (the options value) + `weightAbs` (resolved sum-share, service.py:336),
   `stale` (mirror SmileData.stale), `rmsShare` (the _varswap_rms_term contribution,
   service.py:1047-1061). Term payload gains real per-node `canUndo`/`canRedo`.
2. **Panel**: show "model X% · quote Y% · basis +Z bp"; a weight readout with a link-out
   to Options ▸ Calibration; stale badge; slider bounds derived from data — center =
   quote∪model envelope padded by max(2 vol pts, 2·|basis|), consistent 0.05 step and
   display precision; keep commit-on-release (one refit per gesture).
3. **Term editor**: in TermPanel, a compact per-expiry var-swap row (level, set/exclude,
   basis chip) — N independent sessions, N refits, batch "shift all by +x bp" issuing
   sequential edits (explicitly acknowledged N-refit cost; no new session object).
4. **Wiring fixes**: LocalVolViewer mounts the LV surface's own var-swap
   (_affine_varswap_info, affine_fit.py:817) instead of the parametric node's; TermPanel
   fake undo/redo replaced by real state.
5. NOT in scope (recorded as riders): hard var-swap pinning (equality constraint), strip
   vs tail decomposition of the replication (varswap.py truncates at ±6), per-node weight
   overrides (breaks the global options-version refit model, state.py:916-917).

**Tests/gates.** Backend: VarSwapInfo field locks (basis sign convention, weight
resolution, stale propagation); term payload undo-state lock; LV wiring lock (LV panel
model == PDE/static value from the affine payload, not the LQD one). Frontend: panel
renders basis/weight; term rows dispatch to the right node sessions.

# Draft proposals — items 3, 9, 10, 13 (Local-Vol group)

## Item 3 — LV stacked variance: untruncated tails for all expiries (LQD-like)

**Problem.** The parametric stacked-variance view is already full-width: surface.py:54-56
evaluates every expiry on one union grid [min(−1.4,·), max(1.0,·)] and LQD extrapolates
arb-free wings. The LV view is not: each expiry's `model` curve is reconstructed only on
its own quoted range ±0.02 (affine_fit.py:1229 → _reconstruct_smile :905-916), so short
expiries are stubs. The PDE lattice is NOT the constraint on the left (x=0 … x_max covers
k=−1.4 for free); on the right it caps at k=ln(x_max) (typically ln(2.5)=0.916), and
`price_at` np.interp-clamps beyond it → garbage inversions.

**Proposal.**
- New per-expiry field `AffineSmile.modelExt` (optional; mirrors the existing
  `density`/`densityExt` template at affine_fit.py:71-81, :1261): reconstruct each expiry
  on the SHARED display grid `[min(K_DISPLAY_LO, k_obs_lo−pad), min(max(K_DISPLAY_HI,
  k_obs_hi+pad), ln(x_grid[-1])−ε)]` — the right edge clamped to the PDE lattice so we
  never invert clamped prices. Inversion guarded by a normalized time-value floor (the
  alpha_law_wings pattern, service.py:978); points below the floor extend with the last
  reliable w linearly in k (the _InterpSlice doctrine) rather than being dropped.
- Do NOT touch `model` — five consumers couple to it (LocalVolSmile x-domain, client-side
  IV surface intersection, stacked IV, densityExt, smileAxisContext.kRange); widening it
  would zoom the per-expiry smile chart out to ±1.4.
- LocalVolViewer stacked IV (:200-215) prefers `modelExt` when present (same pattern as
  densityExt at :225-237).
- Display-grid-only change: no PDE lattice change (byte-identity of fits preserved), no
  perf-rail impact (rails call calibrate_affine directly).
- Rider (recorded, NOT in scope): raising `_X_MAX_MIN` to reach k=+1.0 on the right —
  changes the lattice, breaks byte-identity, costs O(n_x) in the march.

**Tests/gates.** Lock: modelExt spans ≥ [−1.4, ln(x_max)−ε] for every expiry; every point
finite with 0.01<vol<2.0 (the test_api_affine.py:52-53 discipline); modelExt ≡ model on
the quoted range (same grid points ⇒ same values); `model` payload byte-identical.

## Item 9 — Separate "Calibrate parametric" / "Calibrate LV"

**Problem.** One /calibrate endpoint runs parametric then LV gated by the persisted
Options toggle `localVolEnabled` (workflow.py:332-338; LocalVolSection.tsx:41-46 "On:
Calibrate also fits each ticker's Local-Vol surface (slow)"). Running just one stage
requires Options round-trips; the toggle also gates the LV tab.

**Proposal.**
- Backend: factor calibrate_all into `_parametric_stage` / `_lv_stage` builders; add
  `POST /calibrate/parametric` and `POST /calibrate/lv` (same _mode() resolution,
  returning CalibrationStatus; "one job at a time" contract preserved — jobs.py:85-87).
  LV-only runs without the parametric barrier: `_parametric_seed` is best-effort (falls
  back to flat seed when <2 parametric slices are warm — same converged optimum by the
  theta_ref decoupling, affine_fit.py:242-257; iterate counts may differ, recorded).
  Add `lvStaleTickers` to CalibrationStatus (per-ticker affine_dirty count) for badging.
- Wire compat: `POST /calibrate` keeps its exact current semantics (both stages, toggle
  gate) — tests test_api_workflow / test_calibration_workflow / test_gated_workflow stay
  untouched.
- Frontend: WorkflowControls Calibrate becomes a split-button (MenuPanel pattern already
  used by Fetch :81-107): primary click = "Parametric" (fast, the common loop) with its
  stale count; menu = "Parametric + LV" and "Local-Vol only", each with its own badge
  (staleNodes / lvStaleTickers). WorkflowAction union + StatusBar.PENDING_LABEL gain
  `calibrateParametric` / `calibrateLv` (total Record — TS enforces).
- `localVolEnabled` semantics narrowed: it remains ONLY the workspace/tab gate
  (TopBar.tsx:29-32, NavMenus.tsx:110); the "Calibrate also does LV" clause leaves the
  hint text. /calibrate (combined) still respects it for wire compat.

**Tests/gates.** New endpoint locks (parametric-only leaves affine ptr stale; LV-only
completes with warm and with cold parametric fits; job-already-running returns False for
all three endpoints); byte-identity: per-ticker item ORDER inside groups unchanged
(warm-start + calendar chains depend on ascending-T from lit_nodes); status badge counts.

## Item 10 — Visualize the calendar cross in Stacked Variance

**Problem.** The exact crossing location is computed and served for parametric pairs
(ledgerGapMin/Z/K + ledgerCertified, quality.py:297-307) but useQuality.ts never declares
the fields and no chart consumes them; the LV side has only a violation COUNT with no
location (affine_fit.py:953-962).

**Proposal.**
- Type the wire: add ledgerGapMin/ledgerGapZ/ledgerGapK/ledgerCertified/
  ledgerTailOrderOk/calendarWorstStrike to QualityNode in useQuality.ts (data already
  arrives — FastAPI serializes the full model).
- OverlayCurvesChart gains an optional additive `markers?: {x, y, label, severity}[]`
  prop (no behavior change when absent — Densities view untouched) + an optional
  `differences` mode is NOT built into it; instead:
- StackedVarianceChart (parametric): consume quality rows, map each far-expiry node row
  to its adjacent (near, far) series pair; when ledgerGapMin < −tol draw a **circle at
  x=tx(ledgerGapK)**, y = the two curves' interpolated midpoint, hover = "ΔG min
  {bp} at K {}, pair {near}→{far}, certified: no". Tol = the certificate's own gate
  (−1e-6, _CAL_TOL) — never invent a new threshold. Refetch quality on calibration epoch
  (add reload key — today it refetches on spotVersion only, useQuality.ts:121-138).
- **Difference chart**: a header toggle "levels / Δ" on StackedVarianceChart; Δ mode
  plots w_far(k) − w_near(k) per adjacent pair on the shared grid (client-side subtraction
  — the series already share data.k), zero baseline on; sub-zero excursions filled red.
  This is the "chart of differences" form and needs no new endpoint.
- LV: extend _diagnostics with the argmin location (np.unravel_index over
  np.diff(prices,axis=0)) → optional AffineFitResponse fields `calendarWorstPair`,
  `calendarWorstK`, mirrored in TS; LV stacked IV places the same circle; the header
  badge "N cal. viol." gains the location in its tooltip.

**Tests/gates.** Backend: LV argmin lock on a rigged crossing pair; quality fields
already locked (test_quality.py:165-188 — untouched). Frontend vitest: marker mapping
(node row → series pair), Δ-mode series algebra, no-marker when certified. Perf: no
per-render recomputation of the certificate (test_perf.py:141 rail untouched — read from
quality cache only).

## Item 13 — Animate the LV compute (surface and prices)

**Problem.** The LV fit is one opaque blocking LSQ in a process pool (fit_pool.execute →
calibrate_affine); nothing between "Calibrating {ticker}" and the finished surface. No
iterates escape; Phase-0 diagnostics are deliberately off-wire.

**Proposal — post-hoc replay (design path (a): zero solver risk, honest numbers).**
- Solver: `calibrate_affine(..., trace_every=None)` records CHECKPOINTS at accepted
  steps only (not `evaluate` — memoization makes eval cadence ≠ step cadence): a copy of
  theta (the nodal variance grid), cost, n_evals, and the per-expiry residual RMS vector
  (already computed in the residual assembly — a cheap slice). Cap ~24 frames
  (subsample accepted steps uniformly if more). Default None ⇒ byte-identical, zero
  overhead on the perf rails (rails call with default).
- Transport: the trace rides the AffineFitTask result as pure data (~20-30 KB), stored
  main-side in a side channel (the last_affine_expiry_diagnostics pattern,
  affine_fit.py:371-379) and served by a NEW read-only endpoint
  `GET /fit/affine/{ticker}/trace` — the main AffineFitResponse payload stays lean.
- Frontend: `state/useLvTrace.ts` + a replay driver on the LV workspace:
  - **surface**: LocalVolHeatmap / SurfaceMesh re-rendered per frame (mesh is memoized on
    `data` — new matrix per frame is the natural driver), with a scrubber + play/pause
    (useWaveTimeline pacing doctrine: epoch-keyed, prefers-reduced-motion short-circuits
    to the final frame, terminal state = Infinity).
  - **prices**: per-frame per-expiry RMS bars descending + the cost curve tracing — the
    honest "prices converging" view without re-running the PDE per frame (no per-frame
    reprice: that would be N extra solves).
  - Auto-plays once when a fresh calibration lands (epoch = fit key), replayable from a
    small ⏵ button next to the "N PDE solves · rms" readout (LocalVolViewer.tsx:592-595).
- New UI state lives in a hook + component (LocalVolViewer is 657 lines — over policy;
  no inline additions).

**Tests/gates.** Solver: trace off ⇒ byte-identical result object (hash lock);
trace on ⇒ frames monotone in n_evals, last frame == converged theta; frame cap honored.
API: trace endpoint 404 before first fit, poll-safe (never triggers a fit). Perf rails
untouched by construction (default off). Frontend vitest: scrubber/pacer honors
reduced-motion, epoch re-key restarts replay.

# Draft proposals — items 6, 7, 8, 15 (replay / temporal / prior / fetch group)

## Item 6 — Full-day 15-min replay campaign + scripted leave-out scenarios

**Current reality.** Intraday capture exists (flat-file + REST twins) but on a 13-instant
30-min grid starting 10:00 with a 0-7 DTE + 2-monthly ladder; the replay spine exists
(graph_intraday.py: per-instant AppState via _StoredChains, solve(now_day, obs_ages_days,
hold_out) seams, per-node LOO scoring via graph_loo._score_node); per-(ticker,expiry)
lit/dark exists (state.set_node_lit + LitDarkMatrix); leave-k-out is one hold_out call.
Missing: a 15-min grid generator, a ≥5-expiry shared ladder intraday, a fixture→VolStore
loader, scripted scenario definitions, per-scenario reports.

**Proposal.**
1. **Capture upgrades** (both capture_intraday.py and capture_intraday_rest.py):
   `--step 15 [--from 09:45 --to 15:45]` regular-grid generator beside `--times`
   (session_instants already clips at session close / half-days); `--ladder term`
   option = front weeklies + monthlies to ~120 DTE capped at 6 expiries (the daily
   capture.py ladder shape, made intraday) beside the default 0DTE ladder. New CLI
   `-m backtest.load_fixtures --db <path> <fixture.json>...` re-persisting existing
   fixture JSONs through _persist_db (no network; closes the "re-run = re-hit network"
   gap; keeps the settlement/tick stamps that the QQQ cent-lottery bug made load-bearing).
2. **Campaign recipe** (runs in the USER'S window, per the standing constraint): ship
   `backend\backtest\run_replay_day.ps1` — basket default SPY (the index; avoids SPX
   multi-root) + NVDA, AAPL, MSFT, `--step 15`, `--ladder term`, REST source, per-instant
   checkpointing → `results\replay_day.sqlite`. Estimated wall clock 15-25 min/ticker-day
   (measured REST costs from the 0DTE campaign log; names are far cheaper than ETFs).
3. **Scenario harness**: new module `backend\backtest\scenarios.py` (new file — the
   400-line policy: graph_intraday.py is at 415) with a declarative scenario schema:
   `{name, tickers, maturityFilter, litMap: {(ticker, rung|iso): bool}, design:
   loo|dark, modes: [...], halfLife?, targets}`. Driver reuses instant_state / solve /
   _score_node; parts per (scenario, day) → resumable. Five NAMED scenarios shipped:
   - `loo_basket_1mat`: 3 names + SPY, one shared maturity rung, full LOO (each node
     held out via hold_out in turn).
   - `dark_spot_only`: the transported-prior baseline — REPORTED as its own arm from the
     base_* columns already computed in every scored row; no separate solve pass.
   - `dark_graph_msg`: names dark all day, mode=precision_messages (graph option 1 —
     the production default, best measured intraday: 65.8bp).
   - `dark_graph_layered`: same, mode=layered_dynamic_harmonic with
     residualHalfLifeDays=0.1 (graph option 2 — the interior-optimum arm; pinned
     residualConfigVersion so the store isn't purged per instant).
   - `leave3out_5exp`: 5-expiry ladder per ticker, rungs 2 and 4 lit, extrapolate
     1, 3, 5 (interpolation rung 3 vs extrapolation rungs 1 and 5 reported separately)
     — per-(ticker,expiry) lit via the same flags graph_intraday already sets.
4. **Report**: `-m backtest.scenarios report` merges parts → JSON + client-facing HTML
   (benchmark_pack precedent), grouped by scenario × held-out node/rung × mode, columns:
   handle RMS vs dark baseline, smile ATM/wing/full RMS, ζ std + cov95, persistence
   buckets. Served read-only like the benchmark artifact if desired (rider).

**Ambiguity resolved (flagged for veto).** "3 names + 1 index" = NVDA/AAPL/MSFT + SPY
(SPY stands in for the index — index roots SPX/SPXW need multi-root discovery the
intraday REST path lacks; recorded as a rider, not blocking). "Graph option 1/2" =
precision_messages / layered_dynamic_harmonic(H=0.1); smooth_field recorded as control
column. "Dark, spot-only" = transported-prior baseline column.

**Tests/gates.** Grid generator unit locks (15-min grid, half-day clip); ladder selector
lock; load_fixtures round-trip == _persist_db output byte-identical; scenario schema
validation + a 2-instant synthetic end-to-end (fixture-driven, offline) per scenario
family; replay seams byte-identity lock untouched (test_graph_intraday_replay.py:140).
The real capture + full campaign run in the user's window; harness must be green offline.

## Item 7 — Kalman filtering: evidence + visualization

**Current reality.** The observation filter is complete numerically (Joseph-form update,
Q breakdown, adaptive inflation, transport, reset ladder) and FilterDiagnostics already
ships prediction/observation/posterior ± std, innovation, gain, breakdowns — but ONLY the
last step (NodeFilter holds one step; each commit overwrites). No history, no ζ on the
wire, χ² untyped, panel = snapshot table capped at 8 expiries. The offline intraday sweep
scores the pure core, bypassing the production app layer.

**Proposal.**
1. **Wire, current step**: add typed `zeta` (per-handle ν/√(P⁻+R), pre-inflation) and
   `chi2` to FilterDiagnostics (server-computed; today derivable but unnamed).
2. **Filter history ring**: per node key, keep the last 64 committed steps as compact
   records (ts, dt charged by the ACTIVE clock, m⁻/√P⁻, z/√R, ν, ζ, K, m⁺/√P⁺,
   Q-breakdown incl. adaptive, transportDistance, provenance, resetReason,
   contaminated) in AppState beside the NodeFilter holder. In-memory v1 (advisory
   doctrine: commit_hook never raises); workspace persistence recorded as a rider, NOT
   in v1 (avoids new workspace round-trip locks). New endpoint
   `GET /smiles/{t}/{e}/filter/history` (read-only, poll-safe).
3. **Replay evidence artifact**: new offline module `backtest\filter_replay.py` driving
   the PRODUCTION app layer (on_fit_commit, reset policy, active-MAP, adaptive factors)
   per instant over intraday.sqlite via the _StoredChains provider pattern (NOT as-of
   flips — those wipe filter state via _clear_chain_caches), emitting a per-instant
   series JSON + HTML. This closes the "sweep bypasses the app layer" gap and gives the
   full-day evidence on real data.
4. **UI — FilterTimeline** (new component + hook; ObservationFilterPanel keeps config):
   per handle: prediction band (m⁻±σ), observation band (z±σR), posterior line — the
   three-band chart; a ζ strip with ±1/±2 guides (std(ζ)≈1 = healthy); gain K
   evolution; stacked Q-breakdown area (the adaptive component is where surprises
   show); reset/provenance/contamination markers. Fed by /filter/history live, or by a
   replay artifact file for a captured day.

**Tests/gates.** History ring: bounded length, idempotent per (data_version,
session_version) like the commit itself, cleared on the same cache-clear events as
filter state; endpoint lock. Replay module: byte-identity of production defaults
(the test_graph_intraday_replay discipline applied to the filter path: driving commits
with the store provider changes nothing vs live sequence on a fixture). ζ/chi2 fields:
numeric lock vs hand-computed values. No new FitSettings fields (no defaults-snapshot
churn). commit_hook stays advisory (failure ⇒ no history, never an error).

## Item 8 — Prior persistence: evidence + visualization

**Current reality.** Three distinct mechanisms (calibration prior-anchoring config;
prior surface snapshots with transport; graph residual store). The panel shows
configuration + activation, nothing temporal. Prior AGE is computed
(_prior_age_days) but never emitted; GET /graph/nodes drops prior provenance; the
per-(ticker,day,expiry) ATM innovation store (record_graph_innovations — literally
"prior vs market over time") is persisted for the idio floor and never surfaced; the
§16.2 persistence-decay curve exists only offline; prior snapshot history is written
but only `latest` is readable.

**Proposal.**
1. **Wire promotions (all already-computed quantities):**
   - GraphExtrapolateNode: `priorAgeDays` (from _prior_age_days).
   - GraphNodeInfo: `priorSource`, `priorAsOf`, `priorAgeDays`, `transportDistance`,
     `priorPrecision` (from NodePrior — currently dropped at the wire).
   - GET /priors: explicit `ageDays`/`ageMinutes` per ticker beside dataTs.
   - New `GET /priors/history/{ticker}`: list of saved snapshots (savedTs, dataTs,
     nodeCount, asOfLabel) — the store already keeps history; only `latest` is exposed.
   - New `GET /graph/innovations/{ticker}`: the persisted ATM innovation series per
     (day, expiry) — prior-vs-market distance over time, straight from state._graph_idio.
2. **UI — Prior Evidence tab** on PriorPersistencePanel (config stays where it is):
   - per-ticker prior age + source tier + snapshot history sparkline;
   - per-expiry table gains age / source / transport-distance columns;
   - innovation time-series chart (|calibrated − transported prior| ATM bp per day,
     per expiry) — the honest "does the prior persist?" evidence;
   - residual decay curve: φ(dt)=2^(−dt/H) from residualHalfLifeDays with the node's
     residualAgeDays marked on it, plus the χ chip (data already on
     GraphExtrapolateNode in layered mode); labeled clearly as the GRAPH residual
     (distinct object from the Kalman filter — the filter_mode.py:20-25 doctrine, and
     the two must not read as one thing).
3. **Replay tie-in**: the item-6 scenario report already emits persistence buckets
   (elapsed-since-lit vs error) — link the panel to the latest artifact when present
   (benchmark-artifact serving precedent). No new campaign machinery here.

**Tests/gates.** Wire locks for each promoted field (values == the internal quantities);
priors history endpoint lock (order, fields; latest == history[0]); innovations endpoint
lock vs record_graph_innovations writes; PriorNode/PriorSurfaceSnapshot old key set
byte-identical (the 2026-08-13a wire rule); capture_snapshot's calibrated-record filter
untouched (certification-locked).

## Item 15 — Unified fetch (quotes+spot) + auto-roll prior before calibration

**Current reality.** Two independent fetch verbs (spots = pure transport, options =
chain refresh, both prior-blind); three independent scheduler timers; "auto-roll prior"
absent from the codebase. refresh_chain deliberately preserves the spot shift +
calibrated pointers (frozen-until-Calibrate contract, test-locked);
test_fetch_spots_transports_without_recal pins spot-fetch-never-recalibrates.

**Proposal.**
1. **New `POST /fetch/snapshot`** (workflow.py; /fetch/spots + /fetch/options preserved
   verbatim — their locks stay untouched): sequence =
   (i) refresh chains (fetch_options body, ≤8-wide pool);
   (ii) spot re-anchor (fetch_spots logic — sets shift to live/anchor−1; still no refit:
        the frozen-until-Calibrate contract holds);
   (iii) **prior auto-roll (cheap path ONLY)**: for each ticker with a saved snapshot
        and no fresher active one: set_active_prior(latest_prior_snapshot, "saved") —
        O(1), never enters the _recalibrate_at_prev_close ladder, no as-of flip.
        Skip when already active (avoids governance-event flood). Bumps
        _active_prior_version ⇒ the NEXT calibration sees the rolled prior through the
        fit-cache key with zero extra machinery. Spot-level re-anchoring of the prior
        itself stays READ-TIME transport (transported_prior_slice recomputes h each
        read) — no stored mutation, no new invariant.
   (iv) optional autoCalibrate (existing flag semantics).
2. **Gating**: new `OptionsSettings.autoRollPriorOnFetch: bool = False` (default False =
   current behavior byte-identical; the settings-defaults snapshot + workspace snapshot
   tests updated in the same commit — the known one-commit rule from the tails arc).
3. **Frontend**: Fetch menu gains primary item "Snapshot (quotes + spot)"
   (awaitJob=true); legacy "Spots" / "Options quotes" kept beneath. WorkflowAction union
   + StatusBar.PENDING_LABEL extended. The SpotPanel slider is untouched (hypothetical
   shifts stay a separate concept from fetching).
4. **Scheduler**: timers unchanged in v1; the unified endpoint is a UI verb. A
   "scheduler uses unified fetch" consolidation is a rider (needs double-fire guard
   between the spot timer and options timer).
5. Recorded rider (NOT v1): retiring /fetch/spots from the UI entirely once the unified
   verb has lived a while ("maybe stop fetching quotes and spots separately" — the
   endpoint split stays server-side for the locks; the UI consolidation answers the
   user's intent).

**Tests/gates.** New endpoint lock: chains refreshed + shift set + prior rolled +
data_version bumped + NOTHING recalibrated when autoCalibrate off; roll no-ops when no
saved snapshot / already active; flag off ⇒ byte-identical to fetch_options+fetch_spots
sequence; all five gated-workflow locks + test_fetch_spots_transports_without_recal stay
green untouched.


---

# THE ROADMAP — phases V3.0 … V3.9

Ordering rationale: solver/model core first (the standing arc's final phase, then MCS,
then the comparison view that consumes it), then the visualization truth pack (cheap,
additive, high value), then LV workflow/animation, var-swap, the workflow unification,
and finally the replay + evidence arc (whose campaigns run in the user's window and
whose UI rides the captured data). Within a phase, items are independent unless noted.

## V3.0 — LQD hard calendar constraints (item 1) ← START HERE
The green-lit tails+calendar arc Phase 4. Backend-only, solver core.
Deliverables: asset_share_rows export; per-rank ledger-gap rows + analytic Jacobian in
symmetric_stack; calib\symmetric_exchange.py exchange driver certifying at the 8001
acceptance grid; phase_b_repair wiring (escalation first, exchange on certificate
failure); perf rail; FD locks extended; cert case updated.
Exit gate: no accepted surface fails the certificate; clean-ladder byte-identity; suite
green; benchmark regression bounded (user-window run, recorded as a rider to execute).

## V3.1 — MCS evolution (item 2)
Model layer. Deliverables: analytic k-space Lee slopes; MCS belly repair (one hinge
refit, kept only if re-certified); structural chart port behind mcsChart="raw" default;
calendar floor grid beyond common support + mcs_calendar_certificate (polished-dense +
wing-order clause) into quality overlay fields; kernel pruning + effective-cores report;
dispatch.py calendar columns + certificate-gated verdict; calibrate.py file split.
Exit gate: all byte-identity locks green unmodified; Jacobian FD locks extended;
adjudication artifact (FINDINGS_mcs.md) with pre-registered gates; re-emphasis decisions
recorded for user ratification, never auto-flipped.

## V3.2 — Model comparison UI (item 12)
Backend: /compare endpoint (read-only vs committed record, own (fit_key, model) cache,
_analytic_butterfly lifted into models\diagnostics.py), schemas_compare.py.
Frontend: "compare" ChartView, useModelComparison hook, model palette (LQD green / SVI
blue / MCS violet), metrics table, mock fallback, smoke tab.
Exit gate: compare never moves the calibrated pointer (lock); vitest + smoke green.

## V3.3 — Arb-evidence visualization pack (items 3, 10, 11)
- 3: AffineSmile.modelExt on the shared display grid (right edge clamped at the PDE
  lattice; time-value-floor guarded inversion); LV stacked IV prefers it.
- 10: type the ledger fields in useQuality; OverlayCurvesChart markers prop; crossing
  circle at ledgerGapK + "levels/Δ" difference mode; LV calendar argmin location
  (calendarWorstPair/K) + circle.
- 11: densityRaw (signed, unclipped) + minDensity/minDensityX computed pre-stride;
  belly fields typed through to QualityViewer; sub-zero red fill + circle marker;
  DistributionChart yLo unclamped; docstring/hint honesty pass.
Exit gate: fits byte-identical everywhere (display/payload-only changes); rigged-fixture
locks for each new field; vitest for markers/Δ-mode.

## V3.4 — Fit-target + weights visualization (items 4, 5)
- 4: QuoteBand.targetLo/Hi resolved by the fit's own resolve_band; lib\smileTarget.ts
  ribbons (mid line / bid-ask band / haircut band), legend + toggle.
- 5: GET /smiles/{t}/{e}/weights (poll-safe, no fit); weight strip under SmileChart
  (quote-density bars vs effective mean-1 weights); QuoteTable weight column.
Exit gate: target fields lock under 3 modes × amended × excluded × collapse; weights
endpoint matches resolve_weights exactly; no fit-cache entries created on read.

## V3.5 — LV workflow + animation (items 9, 13)
- 9: POST /calibrate/parametric + /calibrate/lv (stage builders factored; /calibrate
  untouched); lvStaleTickers badge; split-button UI; localVolEnabled narrowed to the
  tab gate.
- 13: calibrate_affine trace checkpoints (accepted steps, ≤24 frames, default off =
  byte-identical); GET /fit/affine/{ticker}/trace; useLvTrace + replay driver
  (heatmap/mesh morph + per-expiry rms bars + cost curve; reduced-motion respected).
Exit gate: perf rails untouched (default-off construction); one-job-at-a-time contract
holds; trace-off hash lock; vitest for the pacer.

## V3.6 — Var-swap package (item 14)
VarSwapInfo optional fields (basisBp, weightPct/weightAbs, stale, rmsShare); real
canUndo/canRedo in the term payload; LocalVolViewer wired to the LV surface's own
var-swap; panel readouts (model/quote/basis, weight, stale badge, data-derived slider
bounds); TermPanel per-expiry var-swap rows + batch shift (N refits acknowledged).
Riders (recorded, not v1): hard pinning, strip/tail decomposition, per-node weights.
Exit gate: field locks; wiring locks (LV panel shows the affine value); frontend green.

## V3.7 — Unified fetch + auto-roll prior (item 15)
POST /fetch/snapshot (chains → spot re-anchor → cheap-path prior roll behind
autoRollPriorOnFetch=False → optional autoCalibrate); legacy endpoints verbatim; Fetch
menu gains the unified verb; settings-defaults + workspace snapshots updated in the same
commit. Riders: scheduler consolidation (double-fire guard), UI retirement of the split
verbs.
Exit gate: flag-off byte-identity; all five gated-workflow locks +
test_fetch_spots_transports_without_recal green untouched; roll no-op semantics locked.

## V3.8 — Replay campaign + LOO scenarios (item 6)
Capture --step/--from/--to grid + --ladder term (both capture twins);
-m backtest.load_fixtures; backtest\scenarios.py declarative harness with the five named
scenarios (loo_basket_1mat / dark_spot_only / dark_graph_msg / dark_graph_layered /
leave3out_5exp); run_replay_day.ps1 launcher; scenario report (JSON + HTML, grouped by
scenario × node/rung × mode, ζ/cov95/persistence columns).
Exit gate: offline synthetic end-to-end green per scenario family; replay-seam
byte-identity locks untouched; THE CAPTURE ITSELF runs in the user's window (recipe
documented; report regenerated after).

## V3.9 — Kalman + prior persistence evidence (items 7, 8)
- 7: zeta/chi2 typed on FilterDiagnostics; 64-step in-memory filter history ring +
  /filter/history endpoint; backtest\filter_replay.py driving the PRODUCTION app layer
  over intraday.sqlite via _StoredChains; FilterTimeline UI (prediction/observation/
  posterior bands, ζ strip, gain, Q-breakdown stack, reset markers).
- 8: wire promotions (priorAgeDays; GraphNodeInfo prior provenance; /priors ages;
  /priors/history/{ticker}; /graph/innovations/{ticker}); Prior Evidence tab (age +
  history + innovation series + residual decay curve with the filter-vs-residual
  distinction kept explicit).
Exit gate: commit_hook stays advisory; history ring bounded + idempotent; wire locks for
every promoted field; PriorNode old key set byte-identical; panel renders from live data
AND from a V3.8 artifact.

---

# Standing constraints (apply to every phase)

- **Byte-identity**: every new capability defaults OFF/absent with a test asserting the
  default path is bit-identical. α=0, smooth_field wire default, calibrated-pointer
  no-fit-on-read, PriorNode key set, /calibrate semantics — all locked already; keep them
  locked.
- **The settings-snapshot rule**: any new FitSettings/OptionsSettings field updates
  test_api_settings_defaults + workspace snapshot in the SAME commit.
- **400-line policy**: new machinery = new modules; the named over-limit files
  (SmileChart.tsx 632, LocalVolViewer.tsx 657, api\observation_filter.py 744, sigmoid
  calibrate.py 432, graph_intraday.py 415) must not grow — split or helper-module.
- **User-window work**: benchmark-pack regression runs (V3.0, V3.1 adjudication) and the
  V3.8 capture campaign are launched by the user; the session ships launchers + specs.
- **Restart reminder**: the long-running :8000 must be restarted after each phase that
  adds API fields.
- Commit per green batch with the arc prefix `feat(v3.N):` / `docs(app):`; SESSION WRAP
  entries in ROADMAP.md STATUS per phase.

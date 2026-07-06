# Observation Kalman Filter — Implementation Roadmap

> **STATUS 2026-07-06: COMPLETE.** All 8 phases + follow-ups shipped on main
> (Phases 0–3 2026-07-03; 4–8 2026-07-04; F3/F4 `83800b3`, active-in-sweep
> `c6147db`, F10 active gate `a66b016`). Verdicts F1–F11 in
> `backend/backtest/FINDINGS_observation_filter.md`; the note is
> `Docs/notes/15_kalman_filtering.tex`. This file is the historical plan +
> phase log.

Companion to `Docs/kalman_filtering.tex` (Note 15, the design note). That note
defines the *what* (a per-node temporal Kalman filter on smile handles, strictly
separated from Note 13's prior-persistence gap regularizer); this file is the
*how* — the phased build plan, file touch-points, and acceptance tests. Written
2026-07-03 after verifying every code anchor the note cites.

## Goal

Add a temporal state estimator over compact arbitrage-safe smile handles
`x = (σ_atm, skew, curvature)`:

    prediction  = SSR-transported previous filtered state  + process noise Q_t
    measurement = data-only fit handles z_t                + covariance R_t
    update      = covariance-form Kalman (Joseph form), per node

with three modes — `off` (byte-identical to today) · `overlay` (compute,
display, never steer calibration) · `active` (one-stage MAP: the prediction
prior is a residual block in the existing fit; quotes are never counted twice).

The two invariants that must survive every phase (Note 15 §1):

1. **Persistence ≠ filtering.** Prior persistence answers "where did the market
   not speak" (gap gate, Note 13); the filter answers "how noisy is what it
   said" (covariance). A quote used to build the filtered posterior is never
   also an independent calibration datum (Prop. `nodouble`).
2. **The filter state is handles, never a raw IV curve, and never native LV
   parameters** (LV consumes the filtered smile as a projection target only).

## Decisions (2, 3, 4 proposed while user AFK; 2 since USER-CONFIRMED as Jacobian)

- **Scope: overlay → active in one arc.** Core + overlay + temporal backtest
  first; active MAP is built afterwards and stays **default-off until the
  Phase-5 backtest shows denoising without signal damping** (same gating
  pattern as the prior-persistence arc).
- **R_t route: Jacobian-propagated covariance from the start**
  (**USER-CONFIRMED 2026-07-03**, overriding the original cheap-first
  proposal). `R_t = ρ · G (JᵀWJ + Λ_intrinsic)⁺ Gᵀ` per note eq. `cov-delta` +
  `resid-inflation`. Cheaper than first estimated: every parametric calibrator
  solves via `scipy.optimize.least_squares` and `result.jac` at the solution
  already carries the weight/vega scaling in its rows, so the information
  matrix is nearly free; the only genuinely new object is the handle Jacobian
  `G = ∂handles/∂θ` (v1 = model-agnostic central FD of the handle map — no
  fitting, d×2P slice evaluations). The cheap precision-factor builder (eq.
  `cheapR`) is demoted to a fallback + A/B diagnostic mode
  (`filterCovarianceMode="factors"`).
- **Active-mode coordinate split: hard-coded auto-exclusion.** When
  `observationFilterMode="active"`, persistence operators/factors overlapping
  the filter state (ATM level + shape factors) are dropped by
  `resolve_prior_mode`; the deep-tail strike anchor, var-swap companion and
  dark graph nodes keep persistence. No knob, no way to double-anchor.
- **Doc placement: adopt as Note 15.** Final phase moves
  `Docs/kalman_filtering.tex` → `Docs/notes/15_kalman_filtering.tex` with
  STYLE_GUIDE hardening (generated figures/macros, verified Appendix C snippet,
  traceability table).
- **State vector v1 = the 3 ATM handles.** RR25/BF25/var-swap extension is
  deferred (the machinery is dimension-agnostic; extend after the pilot).

## What already exists (verified 2026-07-03 — reuse, don't rebuild)

| Need | Existing anchor |
|---|---|
| Covariance-form Gaussian update + innovation + marginal variance | `graph/posterior.py` `posterior_update` (the per-node filter is a strict specialization); ζ in `graph/hyper.py` `standardized_residuals` |
| Cheap measurement precision (rms/density/spread/freshness, per-handle confidence, floors/caps) | `graph/precision.py` `observation_precision`; shared vocabulary in `calib/precision.py` |
| Prediction-side precision by provenance tier + age + transport | `graph/precision.py` `baseline_precision`, `SOURCE_BASE` |
| SSR transport + transported-prior handles with provenance | `dynamics/transport.py` `transported_w`; `api/graph_nodes.py` `resolve_node_prior` / `_prior_handles` |
| Handle extraction (exact LQD / numeric any-model) | `models/lqd/atm.py` `atm_handles`; `models/diagnostics.py` `numeric_handles` |
| Residual-block injection into ALL parametric fits | `calibrate_slice`/`calibrate_svi`/`calibrate_sigmoid` already accept `operator_prior`-style targets; `build_display_fit` threads them; LV via `prior_lv` basket conversion |
| ATM-local level/skew/curvature as σ-baskets (the active-MAP residual rows) | `calib/factors.py` `build_factor_prior` (`OperatorPriorTarget`) |
| Mode resolver pattern | `api/prior_mode.py` `resolve_prior_mode` |
| Per-node state store + reset machinery | `api/state.py` `_calibrated`/`_priors` pattern; `_clear_chain_caches`, `recalibrate`, `_CHAIN_CACHE_ATTRS` |
| Temporal validation harness template | `backend/backtest/temporal.py` (consecutive captured pairs, thinning, per-mode sweep) |
| Frontend overlay + panel patterns | `useGraphNodeSmile.ts` + `SmileChart` `graphPost`/band props; `PriorPersistencePanel.tsx` |

Greenfield: `calib/observation_filter.py`, `api/observation_filter.py`, the
`observationFilter*` settings, the `AppState` filter store, the handle
Jacobian `G = ∂handles/∂θ` (Phase 2 — the only new numerical object the
Jacobian covariance needs; `result.jac` from `least_squares` supplies JᵀWJ),
and the backtest module.

---

## Phases

### Phase 0 — Schema, mode resolver, versioning
*Foundation; no behaviour change; `off` byte-identical.*

- `api/schemas.py` `OptionsSettings`: `observationFilterMode`
  (`Literal["off","overlay","active"]`, default `"off"`) + surfaced knobs from
  the note's atlas: `filterProcessVolBpSqrtDay` (10), `filterProcessSkewSqrtDay`
  (0.02), `filterProcessCurvSqrtDay` (0.05), `filterTransportNoiseScale` (0.10),
  `filterResidualInflation` (True), `filterMaxGain` (1.0), `filterResetHours`
  (source-dependent default, stored as float hours), `filterDataOnlyPrepass`
  (False — see Phase 2 contamination note), `filterCovarianceMode`
  (`Literal["jacobian","factors"]`, default `"jacobian"` — factors is the
  fallback/A-B diagnostic route). Hidden constants live in the module
  (`HANDLE_CONFIDENCE`, `RESID_INFLATION_CAP`, `SOURCE_RESET_POLICY="strict"`).
- **Version-bump rule:** filter fields bump the global `options_version`
  **only when they affect fits** — i.e. `observationFilterMode` transitions
  to/from `"active"`, and the process/measurement knobs while in `active`.
  Overlay-only changes bump a new lightweight `_filter_version` (refreshes the
  overlay payload without invalidating any fit cache).
- New `api/filter_mode.py`: `resolve_filter_mode(opts) -> FilterModePlan`
  (`enabled`, `active`, `owned_handles`, `draw_overlay`) mirroring
  `prior_mode.py`. In `active`, `resolve_prior_mode` consumes the plan and
  drops overlapping persistence coordinates (the auto-exclusion; tail anchor,
  var-swap and graph-only survive).
- Frontend `useOptions.ts` type + defaults; `settings_persist` needs no
  migration (Pydantic defaults fill missing fields).
- Tests: options round-trip; `off` ⇒ golden fits byte-identical; version-bump
  matrix (overlay knob ⇒ no options_version bump; active knob ⇒ bump).

### Phase 1 — Numerical core (`calib/observation_filter.py`)
*Pure numpy; no app state, no provider calls; ≤400 lines.*

- Frozen dataclasses per the note §7.1: `FilterState` (node key, as-of/source
  key, handle names, m⁺, P⁺, timestamp, provenance, reset reason),
  `FilterPrediction` (m⁻, P⁻, transport distance, per-component Q breakdown),
  `FilterMeasurement` (z, R, quote-count/spread/RMS/inflation breakdown),
  `FilterUpdate` (innovation, S, K, posterior).
- `kalman_update(mean_pred, cov_pred, obs, obs_cov, H=None)` — Joseph form,
  symmetrized, PSD guard raising `FloatingPointError` (the note's Appendix C
  listing verbatim); Cholesky jitter is *reported* in diagnostics, never
  silent.
- `process_noise(dt_days, transport_h, event_pending, source_changed,
  model_changed, knobs) -> diag Q` per eq. `Q`: √t clock noise per handle,
  `filterTransportNoiseScale·|h|` transport term, event widening (read off the
  event calendar between the two snapshots), source/model widening.
- `predict(prev, transported_handles, Q)` with `A_t = I` (v1: the state is
  re-extracted after transport, so the Jacobian is deferred);
  `apply_gain_cap(K, filterMaxGain)` as a diagonalized clip;
  `should_reset(prev_key, new_key, dt_hours, knobs) -> reason | None`.
- Tests (`test_observation_filter.py`, core section): the scalar shrinkage
  proposition `K = p/(p+r)` exactly; Joseph-form PSD under an ill-conditioned
  P; gain cap; **golden cross-check: on a single-node problem the update
  reproduces `graph/posterior.py.posterior_update` to 1e-12** (the two
  implementations must agree — this is also the Note 15 Appendix C
  verification target).

### Phase 2 — Measurement builder (Jacobian-propagated R_t)
*USER-CONFIRMED 2026-07-03: full covariance from the start (note eq.
`cov-delta`); the factor builder survives only as fallback + A/B diagnostic.*

- **Information matrix `I_θ = JᵀWJ + Λ_intrinsic` — nearly free.** All three
  parametric calibrators solve via `scipy.optimize.least_squares` and hold the
  result (`models/lqd/calibrate.py:245`, `models/svi_jw/calibrate.py:218`,
  `models/sigmoid/calibrate.py:240`); `result.jac` is the residual Jacobian at
  the solution with the sqrt-weight/inv-vega scaling already folded into its
  rows (Note 07 vega-normalization ⇒ vol units), so
  `result.jac.T @ result.jac` **is** `I_θ`. In a data-only measurement pass
  the stacked rows are exactly fit + intrinsic regularization
  (reg/calendar/barrier) — the note's `Λ_intrinsic` — with no temporal-prior
  rows to exclude. Plumbing: each calibrator gains an opt-in diagnostics seam
  retaining `result.jac` (pure side-channel; golden fits byte-identical).
- **Handle Jacobian `G = ∂g/∂θ` — the one genuinely new object.** v1 is
  model-agnostic central FD of the handle map: perturb θ per-parameter,
  rebuild the slice, read `numeric_handles` — d×2P slice *evaluations* (no
  fitting; microseconds), FD step scaled to each parameter's magnitude.
  Analytic G for LQD (differentiating `atm_handles`' closed form through the
  build_slice pipeline) is optional hardening once FD is test-locked
  (validate analytic vs FD ≤ 1e-6, the `test_lqd_jacobian.py` pattern).
- **`R_x = G I_θ⁺ Gᵀ`** via eigendecomposition pseudo-inverse with a relative
  rank cutoff: sparse chains make `I_θ` ill-conditioned, and near-null
  directions (θ combinations the quotes do not identify) must inflate R, not
  explode it. Per-handle variance floors/caps from `graph/precision.py` stay
  as the sanity envelope; `HANDLE_CONFIDENCE` is *retired on this route* —
  weak curvature identification now emerges from the geometry instead of a
  hand-set 0.01.
- **χ² residual inflation** (eq. `resid-inflation`): `ρ = clip(χ²/(m−d), 1,
  RESID_INFLATION_CAP)` with `χ² = rᵀWr` from the same solution residuals
  (`calib/rms.node_error_terms` semantics); `R_t = ρ·R_x`. This carries the
  note's contradictory-cluster case file.
- **UNITS (discovered in implementation, shipped):** production quote weights
  are RELATIVE (equal/tv-density), not 1/noise², so `JᵀWJ` alone is the
  information under an implied noise of one full vol point — R saturates the
  envelope. The builder therefore takes `noise_scale` = the stated per-quote
  noise std in vol units (bid-ask half-spread / haircut, floored) and divides
  the DATA rows only (intrinsic reg rows keep their prior scale). R then obeys
  the quadratic contract (2× stated noise ⇒ 4× covariance) and is tied to the
  market's stated uncertainty, exactly the note's §4 intent. The app layer
  (Phase 3) supplies the per-quote half-spreads from the prepared chain.
- **Band semantics come for free on this route:** in `bidask`/`haircut` modes
  the inactive hinge rows have `band_sign = 0` inside the band ⇒ they
  contribute nothing to `JᵀWJ`; only the small mid anchor remains — exactly
  the note's remark ("inside the spread the market is a set, not a point"),
  with no special-casing. This is a concrete advantage over the factor route,
  which had to proxy band width through a spread factor.
- **Fallback route (`filterCovarianceMode="factors"`):** the cheap builder
  (note eq. `cheapR`: `HANDLE_CONFIDENCE · (1/max(rms,floor)²) · density ·
  spread · freshness` via `graph/precision.observation_precision`) kept for
  (a) fits where no solution Jacobian is available, (b) an A/B diagnostic
  column, (c) the Phase-5 backtest sweep, so the Jacobian route's
  ζ-calibration advantage is *measured*, not assumed.
- `measurement_from_fit(slice_, t, prepared, weights, fit_mode, jac=None) ->
  FilterMeasurement` — `z_t` via `numeric_handles` (exact `atm_handles` when
  the displayed model is LQD), R by the mode above, breakdown recorded.
- **Measurement contamination.** The default persistence mode is `hybrid`, so
  the committed fit is potentially prior-anchored. v1 policy: reuse the
  committed fit's handles as `z_t` and set a `measurementContaminated`
  diagnostic flag when any active persistence λ>0 overlaps the handle set
  (Note 13's no-damp guarantee makes contamination ≈0 exactly where the filter
  has signal — dense quotes ⇒ gate closed). The clean alternative is the
  opt-in `filterDataOnlyPrepass` (one extra data-only fit per node, the same
  cost trade-off as `priorDataOnlyPrepass`). In `active` mode the question
  dissolves: the auto-exclusion means the handle block of the committed fit is
  filter-owned by construction. Note the synergy: a data-only pass is exactly
  the configuration where the LQD *analytic* residual Jacobian is valid
  (`use_analytic` gates off when prior terms are present), so the prepass
  yields the highest-quality `I_θ` at the same time it decontaminates `z_t`.
- Tests: `R_x` vs a brute-force FD covariance on a synthetic linear model
  (exact agreement); contradictory close-strike cluster ⇒ curvature variance
  inflates, level/skew stay tight (the note's case file, made executable);
  band mode widens R vs mid on the same chain with zero special-case code;
  rank-deficient chain (3 quotes) ⇒ pseudo-inverse cutoff + floors bind, no
  explosion; jacobian-vs-factors A/B smoke; contamination flag truth table.

### Phase 3 — App layer + state store (`api/observation_filter.py`)

- **Node key** `(ticker, iso, fitMode, source, asOf)`; store
  `AppState._filter_states: dict[key, FilterState]` alongside `_calibrated`.
  Wire into `_clear_chain_caches` (source/as-of changes ⇒ strict reset) and
  `recalibrate` (per-ticker eviction). **Add the store to
  `_CHAIN_CACHE_ATTRS`** so the Fetch-priors transient as-of round-trip
  (`capture_chain_state`/`restore_chain_state`) does not silently destroy the
  filter — a real reset is a policy decision, not a side effect.
- **Reset matrix** (each stored as `reset_reason`): source/as-of change ·
  fit-mode change · manual quote edit (session version moved) · calendar gap >
  `filterResetHours` · first-ever node. Model change does **not** reset (the
  handle state is model-agnostic); it widens Q via the model-noise term.
- **Prediction:** previous `FilterState` handles transported under the current
  SSR regime (reuse the `graph_nodes._prior_handles` transport path);
  `P⁻ = P⁺ + Q_t`. **Seeding:** no previous state ⇒ seed from
  `resolve_node_prior` (active transported prior) with `P` from
  `baseline_precision` provenance tiers; provenance recorded.
- **Update trigger:** the filter is sequential — one update per genuinely new
  observation, not per view. Hook the update into the fit-commit path
  (`fit_and_commit_slice` / `_compute_fit` post-commit, gated `mode != off`),
  idempotent per `(node, data_version)`: recalibrating the same snapshot twice
  must not double-update. `dt` comes from snapshot timestamps
  (`data/types.py`), never wall clock.
- **Endpoint:** `GET /smiles/{ticker}/{expiry}/filter` — prediction,
  observation, innovation, per-handle gain, posterior mean/σ, Q and R
  breakdowns, reset reason, contamination flag. Advisory; never 500s (the
  `prior-diagnostics` pattern).
- Tests: reset matrix; idempotency; seed-from-prior provenance; as-of
  round-trip survival; per-ticker eviction isolation.

### Phase 4 — Overlay frontend

- `useObservationFilter.ts` (clone of `useGraphNodeSmile.ts`) fetching the
  Phase-3 endpoint, keyed on `_filter_version` + calib epoch.
- `SmileChart`: `filterPost` / `filterBandLo` / `filterBandHi` props drawn like
  the graph posterior overlay (distinct colour; the filtered *curve* is the
  displayed model retargeted to m⁺ — reuse the `graph_reconstruct` retarget
  seam), plus a badge: per-handle gain, innovation, ρ. Hidden when `off`.
- `ObservationFilterPanel.tsx` in the Options tab (clone of
  `PriorPersistencePanel.tsx`): mode selector, the Phase-0 knobs grouped, and a
  per-expiry diagnostics table (innovation · gain · √P⁺ · ρ · reset reason).
- strict-TS green; `off` renders nothing (legend entry dropped, the
  overlay-hide-on-off precedent).

### Phase 5 — Temporal backtest (`backend/backtest/observation_filter.py`)
*The acceptance gate for active mode. Clone `backtest/temporal.py` structure.*

Per consecutive captured pair (T-1, T) per asset/expiry: fit T-1 full chain ⇒
filter state; day T full-chain fit = truth; a **thinned/perturbed** day-T chain
= the measurement. Score filtered posterior vs two baselines: the data-only fit
(no filter) and the pure transported prediction (gain 0). The note's §9
protocol, made executable:

1. **Held-out scoring** — filtered handles + reconstructed smile vs held-out
   day-T quotes (the `temporal.py` wing-RMS machinery).
2. **Contradiction injection** — perturb 1–2 close strikes inside the spread:
   curvature noise must be rejected (low K_κ) with level moves preserved.
3. **Shock pass-through** — true ATM jump with tight spreads: gain must be
   high; report the lag in bp.
4. **Gap preservation** — remove wings: the filter must not invent tail
   information (that is persistence/graph territory); assert the tail handles'
   posterior ≈ prediction.
5. **ζ calibration** — `(heldout − m⁺)/√(P⁺+R_heldout)`: mean ≈ 0, std ≤ 1
   (the Note 14 diagnostic, same reporting style as FINDINGS_graph_loo).
6. Sweep the Q knobs (`filterProcessVolBpSqrtDay`, `filterTransportNoiseScale`),
   the R inflation cap, and **both covariance modes** (`jacobian` vs
   `factors`) — the ζ-calibration comparison is the empirical verdict on the
   Jacobian route; this tuning is the overlay pilot's purpose.

Run on `spike_aug2024` first (then `high_oct2022`/`low_jul2023` for regime
robustness); findings → `backend/backtest/FINDINGS_observation_filter.md`.
**Success = lower held-out error on noisy snapshots + lower refresh jitter +
no meaningful lag on clean moves — not "lower every RMS".**

### Phase 6 — Active mode: one-stage MAP
*Gated on the Phase-5 verdict; ships default-off.*

- **The residual block** (note eq. `active-map`): per-handle whitened rows
  `L⁻¹(H(θ) − m⁻)` with `L = chol(P⁻)`; v1 uses the diagonal (independent
  rows), full-covariance whitening behind a constant. Route it through the
  **existing factor machinery**: an `OperatorPriorTarget` built by a new
  `build_filter_prior(prediction, …)` whose targets are m⁻ and whose λ come
  from `(P⁻)⁻¹` — because `calib/factors.py` level/skew/curvature σ-baskets
  ARE the handle extractor, this flows to LQD/SVI/SIV via the existing
  `operator_prior` plumbing and to LV via the `prior_lv` basket conversion
  with **zero new per-model wiring**. Crucially the gate is **not** applied to
  this target — the Kalman prior is always on at its covariance weight; that
  is exactly the persistence/filter distinction.
- `service.prior_targets` grows a `filter_target` member routed by
  `resolve_filter_mode`; the auto-exclusion in `resolve_prior_mode` drops the
  overlapping persistence coordinates (tail anchor + var-swap + graph-only
  survive untouched).
- **Posterior bookkeeping:** after the MAP fit commits, the stored `FilterState`
  is the MAP handle solution with P⁺ from the covariance update evaluated at
  the MAP point (the EKF convention).
- **Double-count guard test** (the note's validation item 5): on a
  linear-Gaussian synthetic, the active MAP minimizer must equal
  `kalman_update`'s posterior mean to 1e-10 (Prop. `nodouble`); a companion
  test constructs the *wrong* architecture (posterior-as-prior + quotes again)
  and asserts the guard distinguishes them.
- Tests: MAP ≡ Kalman; `off`/`overlay` fits byte-identical to Phase-5 state;
  auto-exclusion truth table (which persistence rows survive per mode); LV
  projection path.

### Phase 7 — Validation flip + defaults

- Rerun the Phase-5 harness with `active` in the mode sweep (add to
  `DEFAULT_MODES`, set `observationFilterMode` in the options loop exactly as
  the persistence sweep does).
- Tune the shipped defaults from the sweep; decide the default mode (stay
  `off` unless the evidence is one-sided — the persistence arc's precedent).
- Update `ROADMAP.md` STATUS + `backtest/README.md`.

### Phase 8 — Note 15 adoption + docs

- Move `Docs/kalman_filtering.tex` → `Docs/notes/15_kalman_filtering.tex`;
  STYLE_GUIDE hardening: one `\boxed{}` (eq. `kalman` — already so), quiet
  boxes audit, `figures/gen_kalman.py` (case-file gain chart + backtest ζ
  calibration panel, run against production code, macros →
  `figures/kalman_tables.tex`), Appendix C snippet **executed against
  `calib/observation_filter.py`** with the agreement level stated, traceability
  table with the real anchors (the note's §10 table already names the correct
  modules — verify lines exist), cross-refs to Notes 01/07/12/13/14.
- Update `Docs/notes/LEGACY_MAP.md` + the notes-hardening memory.

---

## Deferred (explicitly out of this arc)

- **Analytic handle Jacobians for SVI / Multi-Core SIV** — the FD `G` is the
  v1 route for all models; analytic G (LQD first, per Phase 2) is hardening,
  extended to the other families only if the FD step choice proves fragile.
- **Extended state** — RR25/BF25/var-swap handles (the machinery is
  dimension-agnostic; extend after the 3-handle pilot is trusted).
- **Graph-coupled Kalman** — block covariance over the universe = Note 14's
  posterior + time dynamics; only after the single-node filter is validated
  (note App. B item 5).
- **Live streaming updates** — per-snapshot filter updates under the
  trigger-gated workflow; overlay mode makes this observable safely, but the
  cadence/reset policy needs its own design pass.

## Cross-cutting

- Files ≤ 400 lines (split the calib module into `observation_filter.py` +
  `observation_measurement.py` if needed). Docstrings cite Note 15 equation
  labels (`eq:kalman`, `eq:Q`, `eq:resid-inflation`, `eq:active-map`).
- Every phase carries an "`off` ⇒ byte-identical" golden guard.
- Perf: the update is a d≤3 dense solve — invisible. The Jacobian covariance
  adds no fitting cost: `JᵀWJ` comes from the retained `result.jac`, and the
  FD handle Jacobian is d×2P slice *evaluations* (no optimizer). The only real
  cost lever is the optional data-only prepass (opt-in, mirrors
  `priorDataOnlyPrepass`). No second fit pass by default. Overlay knob changes
  must not invalidate fit caches (`_filter_version`, Phase 0).
- Commit after each green test batch, on `main` per current convention.

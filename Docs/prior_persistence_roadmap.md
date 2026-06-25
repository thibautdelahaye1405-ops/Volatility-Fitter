# Prior Persistence — Implementation Roadmap

Companion to `Docs/prior_persistence_design_options.md` (the design note). That note
defines the *what* (7 persistence modes, the precision vocabulary, two-pass
activation, diagnostics); this file is the *how* — the phased build plan, file
touch-points, and acceptance tests.

## Goal

Turn today's single opinionated strike-gap anchor into the design note's full
7-mode menu and make every persisted prior auditable:

    Off · Overlay only · Strike gaps · Quote operators · Smile factors · Hybrid · Graph only

…while keeping the existing strike-gap machinery intact (golden byte-identical
when off) and fixing the current asymmetry where LQD/LV get the prior anchor but
the SVI / Multi-Core-SIV display overlays do not.

## Locked decisions (from the planning Q&A, 2026-06-24)

- **Scope:** all 7 modes, including Graph-only.
- **Two-pass "don't damp the signal":** heuristic single-pass is the DEFAULT;
  the data-only prepass is an opt-in toggle (`priorDataOnlyPrepass`, default off).
  Single-pass gates priors by quote-support precision with no extra fit; two-pass
  fits data-only first, measures operator precision, then refits with only the
  under-observed operator priors (~2x per-node fit cost).
- **Default mode:** ship with legacy behaviour preserved (a persisted
  `autoLoadPrior=on` migrates to `strike_gap`, byte-identical); flip the schema
  default for NEW installs to `hybrid` and the recommended default to `hybrid`
  in the final phase, after the backtest confirms it.
- **Operator → optimizer route (decided here):**
  - LQD / SVI-JW / Multi-Core SIV → **direct signed-basket operator residuals**
    `sqrt(λ_j)·(O_j(model) − O_prior_j)/scale_j` (RR/BF are signed baskets of
    model vols, not option prices — cleanest as residuals; this also fixes the
    SVI/SIV asymmetry).
  - Affine LV → **signed-basket residuals** (`BasketQuote`), NOT per-leg quotes.
    The coupling IS kept: on the PDE surface `σ_model(x_a) ≈ σ_prior(x_a) +
    (P_model − P_prior)/vega_a`, so the signed basket `O = Σ c_a σ(x_a)` is a
    linear functional of the leg call prices — one residual per operator that pins
    skew/curvature without pinning the absolute wing level. Reuses the forward
    sensitivities (no extra PDE solve), like a var-swap row. (Earlier note said
    "synthetic leg quotes"; superseded — the per-leg projection dropped the
    coupling and quietly re-introduced "ATM moved, wings persisted" for LV.)

## The residual object (shared across modes)

    sqrt(λ_j) · (O_j(model) − O_j(prior)) / scale_j

where `O_j` is a strike price, an operator (ATM/RR/BF/var-swap), or a factor, and

    gap_j = max(1 − obs_precision_j / required_precision_j, 0) ^ gamma
    λ_j   = global_strength · base_prior_precision_j · gap_j

so a well-observed operator (`obs ≥ required`) receives **zero** prior weight.

---

## Phases

### Phase 0 — Schema, mode resolver, migration, version-bumping
*Foundation; no behaviour change.*
- `api/schemas.py` `OptionsSettings`: add `priorPersistenceMode` + operator/factor/
  tail knobs (`priorOperatorSet`, `priorOperatorStrengthPct`,
  `priorOperatorRequiredPrecision`, `priorOperatorGapExponent`,
  `priorOperatorBandwidth`, `priorOperatorCovarianceMode`, `priorDataOnlyPrepass`,
  `priorFactorSet`, `priorFactorStrengthPct`, `priorTailAnchorStrengthPct`,
  `collarSign`). Keep `autoLoadPrior` / `priorAnchorWeightPct` / `priorAnchorDeltas`
  (now strike-gap / hybrid-tail specific).
- `api/state.py` `set_options`: fold every new calibration-affecting field into the
  `affects_fit` predicate (global `options_version`).
- Migration: a persisted blob predating the mode field derives
  `autoLoadPrior=True → "strike_gap"`, else `"off"`; new installs default `hybrid`.
- New `api/prior_mode.py`: `resolve_prior_mode(opts)` → which builders are live.
- Tests: options round-trip; migration; `off`/`overlay` byte-identical to
  `autoLoadPrior=False`.

### Phase 1 — Shared precision vocabulary
- New `calib/precision.py`: lift the generic factor functions + activation gate out
  of `graph/precision.py`; `graph/precision.py` re-imports (byte-identical, golden
  design-point guard).
- Tests: gate monotonic, gap=0 when obs≥req, graph design point unchanged.

### Phase 2 — Operator library
- New `calib/operators.py` (+ `operator_precision.py` if >400 lines): operator
  registry (ATM/RR_d/BF_d/VarSwapVol, optional wing slopes) with legs + signed
  coefficients honouring `collarSign`; `delta_strikes` (shared with `prior.py`);
  `evaluate_operators(smile_w_fn, …)` (model-agnostic); `operator_scales`;
  heuristic `observation_precision` (the §5.3 harmonic leg aggregation);
  `build_operator_prior(...) → OperatorPriorTarget`; `operator_residuals(...)`.
  `OperatorPriorTarget` carries the per-operator diagnostics payload.
- Tests: delta placement vs Black, RR/BF signs, gate behaviour, residual length.

### Phase 3 — Parametric calibrators (+ asymmetry fix)
- `calibrate_slice` (LQD), `calibrate_svi`, `calibrate_sigmoid`: accept
  `operator_prior` (and `prior_anchor` for SVI/SIG — the asymmetry fix); stack
  residuals. `build_display_fit` threads them through.

### Phase 4 — Affine LV (signed-basket residuals, Option A)
- `affine_calib.BasketQuote` + `calibrate_affine(baskets=...)`: dense
  linear-functional residuals of the leg call prices (reuse the forward
  sensitivities), one row per operator — keeps the RR/BF coupling. GN runs via the
  dense operator (baskets excluded from the sparse-reg fast path). Empty ⇒
  byte-identical.
- `api/prior_lv.build_operator_lv_targets`: operator prior → `BasketQuote`s (ATM
  1-leg, RR 2-leg, BF 3-leg) + a `VarSwapQuote`. Pure builder; Phase 5 wires it
  into `_fit` and keeps the legacy strike-gap path.

### Phase 5 — Mode dispatch + two-pass prepass  ✅ DONE
- `service.prior_anchor_targets` → `prior_targets` returning a `PriorTargets` struct
  (strike_anchor | operator_prior + companion prior_var_swap), routed by
  `resolve_prior_mode`. Threaded into BOTH `calibrate_slice` AND `build_display_fit`
  in `_compute_fit` AND `fit_surface_slice`/`display_overlay` (so SVI/Multi-Core-SIV
  overlays get the prior in every path — asymmetry fixed end-to-end).
- `affine_fit._prior_lv_targets` routes the LV path: strike_gap → legacy
  `_prior_anchor_quotes`; operator/hybrid → `prior_lv.build_operator_lv_targets`
  → `calibrate_affine(baskets=..., varswaps=...)`.
- Completed the parametric prior surface: `prior_var_swap` added to `calibrate_svi`
  / `calibrate_sigmoid` + `build_display_fit` (the operator var-swap companion).
- **Two-pass** (`priorDataOnlyPrepass`, opt-in): implemented in `_compute_fit`
  (single-node path) — data-only fit seeds the prior refit. The warm-started surface
  sweep keeps its previous-expiry seed (coupled-path two-pass deferred).
- **Gating decision:** `autoLoadPrior` is the TRANSITION master-enable (default
  False ⇒ byte-identical everywhere); the mode selects the builder when it is on.
  Phase 8 retires `autoLoadPrior` in favour of the mode once hybrid is backtested.
  (NB schema default mode=hybrid means `OptionsSettings(autoLoadPrior=True)` now
  resolves to operator/hybrid, not strike_gap — prior-specific tests set the mode
  explicitly.)

### Phase 6 — Factor mode, Hybrid, Graph-only  ✅ DONE
- **Smile factors** (`calib/factors.py`): ATM-local signed σ-baskets (level / skew /
  curvature / optional wing slopes + var-swap) via FD stencils, returning the SAME
  `OperatorPriorTarget` so every consumer is unchanged. Shares the operators'
  `assemble_target` / `varswap_rec` (refactored out of `operators.py`).
- **Hybrid** = operators + a residual deep-tail strike anchor at the deltas below
  the shallowest wing operator (`operators.hybrid_tail_deltas`,
  `priorTailAnchorStrengthPct`). `prior_targets` sets BOTH `operator_prior` and the
  tail `prior_anchor`; the calibrators stack both blocks.
- LV path: `prior_lv.build_factor_lv_targets` + the shared
  `lv_targets_from_operator_prior` converter; `_prior_lv_targets` routes factor /
  hybrid (hybrid adds the deep-tail quotes via a parametrized `_prior_anchor_quotes`).
- **Graph-only** short-circuits all calibration anchors (already inert from Phase 5;
  lit nodes pure data, graph carries the dark-node prior).

### Phase 7 — Diagnostics + frontend  ✅ DONE
- Backend: `PriorDiagnostics` / `PriorOperatorDiag` schemas + `service.prior_diagnostics`
  (reads `OperatorPriorTarget.diagnostics`: operator · priorValue · obsPrecision ·
  requiredPrecision · gap · λ) + `GET /smiles/{t}/{e}/prior-diagnostics` (advisory,
  never 500s). `test_prior_diagnostics.py`.
- Frontend: `useOptions` gains the mode + all knobs; new `PriorPersistencePanel.tsx`
  (the §10 mode selector + mode-grouped knobs — strike / operator / factor / hybrid
  with a ChipSet operator/factor set, collar sign, gate knobs, two-pass toggle) +
  the §9.4 diagnostics table (per-expiry active factors with gap + λ). Wired into
  `OptionsViewer` Calibration card; the Workflow "Auto-load prior" toggle relabelled
  as the master enable. strict-TS green.
- (Overlay-visibility hiding of the dotted prior in `off` mode is a small follow-on;
  the dotted prior currently always draws when a prior is active.)

### Phase 8 — Validation & default flip  ✅ DONE
- **Synthetic no-damp validation** (`tests/test_prior_nodamp.py`): an overnight
  ATM-jump / shape-unchanged / wings-unquoted scenario — operators & factors follow
  the level and reconstruct the jumped wing (shape is level-invariant) while the
  strike-gap anchor clings to yesterday's absolute level. The runnable mode
  comparison (the precision harness scores single-snapshot fits, not temporal
  persistence — the empirical temporal axis is documented in `backtest/README.md`
  as a ≥2-day-fixture follow-on).
- **Tuned** the over-eager var-swap coverage probe `2.0σ → 1.4σ`
  (`operators._VARSWAP_PROBE_STD`); operator bandwidth `0.06` left as-is (flagged
  for the temporal backtest to tune).
- **Flipped the default + retired the `autoLoadPrior` master:** the MODE is now the
  single source of truth (`prior_targets` / `_prior_lv_targets` / `_prior_anchor_quotes`
  no longer gate on `autoLoadPrior`); the schema default mode is `hybrid` (Phase 0),
  so new installs get hybrid persistence while existing desks are preserved by the
  store-load migration (legacy off → mode `off`). `autoLoadPrior` kept as a legacy
  field for migration + round-trip only; the frontend toggle removed (mode=off is
  the off switch). Full suite 798 passed / 1 skipped; strict-TS + ruff green.

## Cross-cutting

- Perf: operator residuals are a few rows; two-pass is opt-in; new knobs bump the
  global options version (one refit on change). No new O(N^3).
- Files ≤ 400 lines (split operators if needed). Every phase carries an
  "off ⇒ byte-identical" golden guard. Docstrings cite the design-note sections.

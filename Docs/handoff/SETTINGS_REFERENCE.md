# Settings reference — every tunable, its default, unit, and activation condition

**Companion to `VOL_FITTER_CLEAN_ROOM_REBUILD.md`. Extracted from the reference
implementation's validated settings schemas on 2026-07-29. This is the exact,
exhaustive control surface of the working application: the rebuild must expose
an equivalent set (names may differ; semantics, defaults, ranges, and
activation conditions must be preserved or consciously re-decided and logged.)**

Three schema groups exist:

1. **Fit settings** — per-fit hyperparameters. Any change bumps a *fit-settings
   version* folded into every fit-cache key, so all views (smile, term,
   density, local vol) refit consistently without per-endpoint threading.
2. **Options (engine/meta) settings** — app-wide toggles, penalty strengths and
   defaults the workspaces read. Only *calibration-affecting* fields bump the
   *options version* in the cache key; display/report-policy fields never do.
   Local-vol-only fields fold into a separate *LV affine key* so they never
   invalidate parametric fits. Observation-filter overlay changes bump a
   lightweight *filter version* only.
3. **Market settings** — per-ticker carry inputs.

The version/cache-key discipline is itself a requirement: a knob's docstring
must state whether it invalidates or calibrates anything (see the rebuild
spec, "State and invalidation").

---

## 1. Fit settings (17 fields)

| Field | Type / range | Default | Role |
|---|---|---|---|
| `model` | `lqd` \| `svi` \| `sigmoid` | `lqd` | Smile family charted by the Parametric workspace. LQD is *always* fitted under the hood so density/term/local-vol/graph views stay LQD-based; SVI and Multi-Core SIV ("sigmoid") are overlays calibrated to the same quotes. |
| `nOrder` | int 4–24 | 16 | LQD Legendre body order N. Raised from 6/cap 16 (2026-07-30): N≤12 leaves an equioscillating truncation residual (±20bp) at the smile shoulder on low-vol names whose quoted strip spans ±4σ (SPY LEAPs); at 24 the shoulder error reaches spread level. The *effective* per-slice order is additionally capped by the quote count (two quotes per parameter: N+1 ≤ quotes/2, never below min(nOrder, 6)): thin books keep their historical N=6 fits, stay data-identified (error bars never saturate), and avoid the measured trf latency meander of over-parameterized short-dated books (seconds at N≥12 on a 19-quote 0DTE book). |
| `lqdCoords` | `lr` \| `endpoint` \| `logistic` | `logistic` | LQD optimization chart. `logistic` = endpoint chart with the right tail scale mapped through a logistic, so the admissibility wall is unreachable and the chart covers exactly the admissible set (production default). `endpoint` = (log A_L, log A_R, a) with body modes endpoint-neutral. `lr` = historical raw vector. Same family/objective in all three — the fitted optimum is chart-independent to solver tolerance. |
| `regLambda` | float 0–1 | 1e-6 | LQD high-order ridge: penalty λ·n^{2r}·a_n². |
| `regPower` | float 0–4 | 1.0 | The r in n^{2r}. |
| `nCores` | int 0–2 (validator clamps >2) | 2 | Multi-Core SIV hat-core count R. Hard-capped at 2: measured finding — 3+ cores overfit and manufacture wing arbitrage. A persisted config with more is *clamped, not rejected*, so old saves still load. |
| `haircut` | float 0–0.05 | 0.005 | Band tightening of the "haircut" fit mode, in absolute vol (0.005 = 0.5 vol points). Only affects `fitMode="haircut"`. |
| `weightScheme` | `equal` \| `tv_density` | `equal` | Per-quote calibration weights: unit weights, or time-value-density weights (economic time-value shape with strike oversampling divided out). Applies in every fit mode, every model. |
| `barrierCenter` | float (0,1) | 0.90 | LQD right-tail-scale soft-barrier centre. |
| `barrierScale` | float >0 | 50.0 | LQD right-tail-scale soft-barrier steepness. |
| `sviPenaltyWeight` | float ≥0 | 1e3 | SVI no-arbitrage soft-penalty weight. |
| `leeSlopeMax` | float >0 | **1.95** | SVI Lee wing-slope cap, *strictly buffered under* Lee's bound of 2: β = 2 itself admits negative tail density (the penalty hinge was zero exactly on the broken boundary — a live production trap). 2.0 is reachable only as explicit configuration. |
| `sviChart` | `raw` \| `structural` | `structural` | SVI optimization chart. `structural` = (β_L, β_R, k*, w*, κ*) with lifts: every finite iterate is strictly positive-floor and strictly Lee-clean, so the penalties are inert. Default since a two-round pre-registered benchmark: equal/better precision on all 12 regime medians, zero breaks, ~3× faster, and the raw chart's lower headline arb rate was proven a survivorship artifact of its non-converged third. `raw` = rollback. |
| `bellyRepair` | bool | true | When a displayed fit fails the dense-grid belly butterfly certificate, refit ONCE with a belly hinge and keep the repair only if it certifies. Clean first fits never see a second solve. |
| `sigmoidRidge` | float ≥0 | 1e-2 | Multi-Core SIV hat-amplitude ridge. |
| `mcsChart` | `raw` \| `structural` | `raw` | Multi-Core SIV optimization chart (V3.1 rider). `raw` = the historical base + kernels vector with soft feasibility penalties (byte-identical default). `structural` = the wing-admissible chart (the base's Lee wing slopes lifted logistically against the buffered slope cap, so every iterate has Lee-clean base wings by construction — the `sviChart` committee-arc precedent) but ~20× slower at R=2. The flip waits on the MCS benchmark adjudication sweep. |
| `midAnchorWeight` | float ≥0 | 0.05 | Band-mode mid anchor (all models). |

---

## 2. Options / engine settings (78 fields)

### 2.1 Fit target and data freshness

| Field | Type / range | Default | Role |
|---|---|---|---|
| `fitMode` | `mid` \| `bidask` \| `haircut` | `mid` | Persisted *default* fit target the frontend seeds the session from; the live target is a per-request parameter, so this never bumps the options version. |
| `dataAgeAmberMin` | float 1–1440 | 20.0 | Live-chain age (minutes) past which the market pill turns amber (advisory; e.g. a delayed feed's 15-min lag). Display/report policy only. |
| `dataAgeRedMin` | float 5–10080 | 120.0 | Age past which the pill turns red and the quality report **fails the node's publish-readiness** — a premarket fetch of yesterday's book must not read "13/13 ready". Never touches a fit. |
| `asOfMismatchGate` | bool | **false** | As-of mismatch gate (per-node effective as-of, `node_asof`): a node whose served chain is NOT in the requested as-of session (`asOfExact == false` — a live-only source ignoring a close request, a feed stamping another session) gets the Quality readiness issue "as-of mismatch: chain stamped <ISO> vs the requested <day>" and the publish export blocks on it. Off = advisory only (the Nodes pane still flags "≠ as-of"). A data issue, never an arb flag. Display/report policy — never bumps the options version. |

### 2.2 Calendar and surface solver

| Field | Type / range | Default | Role |
|---|---|---|---|
| `enforceCalendar` | bool | true | Calendar-arbitrage control: background Calibrate couples each ticker's lit expiries. |
| `surfaceSolver` | `symmetric` \| `sequential` | `symmetric` | `symmetric` (production): fit every expiry independently, screen each adjacent interface for an **identified** violation (normalized-call order on common quote support), then jointly Gauss–Newton-repair only the violation-connected components — no traversal-order bias; corrections allocated by data information. `sequential` = historical near-to-far pass threading the previous slice as a one-sided floor. Calibration-affecting. |
| `calendarWeight` | float ≥0 | 1e6 | Quadratic calendar-slack penalty weight folded into surface slice fits. Calibration-affecting. |
| `extrapEnforce` | bool | **false** | Tapered no-arb enforcement in the *extrapolated* strike region: SVI/MCS overlays gain a butterfly hinge on the time-value envelope, a tapered calendar hinge vs the previous displayed slice, and a wing-slope-order hinge; with the symmetric solver it also arms the LQD **tail contract** (per-interface seam price ordering + linear wing-slope ordering rows in the joint repair). Off = byte-identical. The advisory *measurement* of extrapolated-region arb is always on in Quality. |
| `ledgerTailOrderGate` | bool | **false** | Promote the full-line calendar certificate's **tail-order clause** (`ledgerTailOrderOk`, the limiting tail order of adjacent slices) from advisory to a gate: the active-set exchange repairs tail-order failures (λ± seam rows at common α; unequal α is irreducible), Quality lists the issue, the publish export blocks on it. Off = the Phase-0 advisory policy, byte-identical. Bumps the options version. |
| `bandRelaxationDiagnostic` | bool | **false** | After a surface pass, for each adjacent pair the exchange could NOT certify, bisect the smallest symmetric quote-band widening (vol) under which the pair certifies → `QualityNode.bandRelaxationVol` + export notes. Advisory (the accepted surface is untouched); band fit modes only. |

### 2.3 Carry / borrow

| Field | Type / range | Default | Role |
|---|---|---|---|
| `jointCarry` | bool | false | Route the joint borrow/de-Americanization fixed point's converged (forward, discount) into the resolved forwards fits consume — American chains only, engaged **per expiry**. |
| `jointCarryEngageBp` | float 0–10000 | 25.0 | Materiality gate: engage only when converged \|borrow\| ≥ this many bp; below it the parity forward is kept EXACTLY, so ordinary names stay byte-identical even with the toggle on. |

### 2.4 Event and intraday clocks

| Field | Type / range | Default | Role |
|---|---|---|---|
| `eventsEnabled` | bool | true | Event-weighted variance clock: a ticker's event calendar augments day-weights so an event before expiry lowers working IV at fixed price. Calibration-affecting. |
| `normalizeEvents` | bool | false | Rescale ALL day weights so the 1Y budget stays 365: events redistribute variance within the year, 1Y vols unchanged. |
| `intradayClock` | bool | **false** | 0DTE research clock: value each sub-day node from the snapshot timestamp to the expiry's exact **settlement instant** (settlement map; exchange session rules as fallback) instead of integer days, and accrue variance through the session-weighted intraday profile. Off = byte-identical. |
| `sessionVarShare` | float 0–1 | 6.5/24 ≈ 0.2708 | Fraction of a trading day's variance accrued during the exchange session (09:30 ET–close; half-days scale). Default is the flat-density share that nests the legacy day convention; research values ~0.7–0.9 make a live 0DTE's clock "remaining trading minutes". Read only while `intradayClock` is on. |
| `nonTradingWeight` | float 0–1 | 1.0 | Day-weight of a non-trading day on the intraday clock (weekend-effect lever). 1.0 keeps the legacy 3-day-weekend-costs-3-days convention. |

### 2.5 Variance swaps

| Field | Type / range | Default | Role |
|---|---|---|---|
| `varSwapEnabled` | bool | true | Whether var-swap levels are surfaced and penalized. |
| `varSwapWeightPct` | float 0–1000 | 10.0 | Var-swap penalty weight as a **percentage of the node's summed option-quote weights** (100 = the quote weighs as much as all options combined). |
| `varSwapMethod` | `static` \| `source_pde` | `static` | How the LV fit prices the model variance swap: static log-contract strike replication (k⁻²-weighted integral), or the backward source-PDE value — a *local* quantity, far less sensitive to coarsening/truncating the strike grid. Parametric models always use their native/static routes. |

### 2.6 Prior persistence (Note 13)

| Field | Type / range | Default | Role |
|---|---|---|---|
| `priorPersistenceMode` | `off` \| `overlay` \| `strike_gap` \| `quote_operator` \| `smile_factor` \| `hybrid` \| `graph_only` | `hybrid` | The single source of truth for prior gating. `strike_gap` = legacy data-gap anchor; operator/factor/hybrid persist trader-readable shape features ONLY where live quotes do not identify them (activation gate); `graph_only` keeps lit calibration market-pure; `off`/`overlay` add no penalty (overlay still draws the dotted transported prior). |
| `autoLoadPrior` | bool | false | LEGACY. Retained only to migrate pre-mode persisted blobs; no longer gates calibration. |
| `priorAnchorWeightPct` | float 0–1000 | 50.0 | Strike-gap anchor budget, percent of summed quote weights, distributed across delta locations by observed-vs-desired quote-density deficit. |
| `priorAnchorDeltas` | list floats in (0,0.5) | [0.02, 0.05, 0.10, 0.25, 0.40] | Per-side forward-Black-delta anchor placements; ATM always added; var-swap prior carries the aggregate tail below the smallest delta. Validator dedups/sorts and falls back to the default when empty. |
| `priorOperatorSet` | subset of ATM, RR25, BF25, RR10, BF10, VarSwap | [ATM, RR25, BF25, VarSwap] | Quote operators the prior may persist (operator/hybrid modes). Unknown names dropped; empty → default. |
| `priorOperatorStrengthPct` | float 0–1000 | 50.0 | Base operator-prior budget (percent of summed quote weights). |
| `priorOperatorRequiredPrecision` | float ≥0 | 1.0 | Observation-precision threshold above which an operator's prior row turns OFF exactly (per-operator multipliers live in code). |
| `priorOperatorGapExponent` | float 0–10 | 1.0 | Gate sharpness γ: gap = max(1 − obs/req, 0)^γ. |
| `priorOperatorBandwidth` | float (0,2] | 0.06 | Quote-support kernel bandwidth (log-moneyness) around each operator leg. |
| `priorOperatorCovarianceMode` | `diagonal` \| `full` | `diagonal` | Per-operator covariance, or Jacobian-propagated full covariance (later upgrade). |
| `priorDataOnlyPrepass` | bool | false | Two-pass activation: fit data-only, measure operator precision, refit with only under-observed priors — a well-observed move is never damped. Off = cheaper single-pass quote-support gate. |
| `collarSign` | `call_put` \| `put_call` | `call_put` | Risk-reversal sign convention (desk choice). |
| `priorFactorSet` | subset of ATM, skew, curvature, leftWing, rightWing, VarSwap | [ATM, skew, curvature, VarSwap] | Smile factors persisted in `smile_factor` mode. |
| `priorFactorStrengthPct` | float 0–1000 | 50.0 | Factor-prior budget. |
| `priorTailAnchorStrengthPct` | float 0–1000 | 20.0 | Hybrid-mode residual deep-tail strike-anchor budget — only where no operator/quote covers the tail (uses `priorAnchorDeltas` deep placements). |
| `wingOperatorsUnderActiveFilter` | bool | false | Note 15 §6.3 carve-out: under an ACTIVE observation filter the WingL/WingR deep-wing slope rows of `priorOperatorSet` persist *alongside* the Kalman MAP rows — they measure a quantity disjoint from the filtered ATM/skew/curvature handles, so nothing is counted twice. Off = the historical switch (wings drop with ATM/RR/BF). Inert without a Wing op in the set; calibration-affecting. |

### 2.7 Observation filter (Note 15)

| Field | Type / range | Default | Role |
|---|---|---|---|
| `observationFilterMode` | `off` \| `overlay` \| `active` | `off` | `off` = feature absent (byte-identical). `overlay` = predict/update per snapshot and DRAW the filtered state; calibration untouched (pilot mode). `active` = the Kalman prediction enters the fit as a one-stage MAP residual block — never a second pass over the same quotes. Only the off↔active transition affects fits. |
| `filterCovarianceMode` | `jacobian` \| `factors` | `jacobian` | Measurement covariance from the fit's solution Jacobian, R = ρ·G(JᵀWJ)⁺Gᵀ (default), or the cheap precision-factor fallback (kept as A/B diagnostic). |
| `filterProcessVolBpSqrtDay` | float 0–1000 | **30.0** | ATM-level process noise, vol bp per √(calendar day). Raised from the design note's 10 after a 3-regime backtest: at 30 the posterior is calibrated (ζ std 0.8–1.9 vs 1.3–6.2) and shock lag drops 3–8×. |
| `filterProcessSkewSqrtDay` | float 0–10 | 0.02 | Skew process noise per √day. |
| `filterProcessCurvSqrtDay` | float 0–10 | 0.05 | Curvature process noise per √day. |
| `filterTransportNoiseScale` | float 0–10 | 0.10 | Extra process std per unit \|log-forward\| transport distance. |
| `filterResidualInflation` | bool | true | Inflate R by realized fit inconsistency ρ = clip(χ²/(m−d), 1, cap) so a dense-but-contradictory cluster reads as noise. |
| `filterAdaptiveSigma` | float 0–20 | 3.0 | Innovation-gated adaptive process noise (the shock-lag fix): when a handle's standardized innovation exceeds this many σ, the prior covariance is inflated so the surprise reads at ~this level and the gain rises toward the data. 0 = off. In active mode the level row is gated by a *fit-free ATM probe* of prepared mids; shape rows by the previous step's innovation. |
| `filterMaxGain` | float 0–1 | 1.0 | Pilot safety cap on diagonalized per-handle gains (non-binding in normal operation). |
| `filterResetHours` | float (0,720] | 96.0 | Maximum data gap the filter will PREDICT across; longer gaps reset the state (reset_reason "stale"). Default spans a weekend + holiday. |
| `filterClock` | `calendar` \| `session` | `calendar` | Clock the process noise accrues on. `session` = intraday variance clock; measured on a 936-measurement 0DTE campaign: 30-min steps move ATM 19.5 bp, one overnight 55 bp, a whole weekend also 55 bp — no calendar q calibrates all three; share 0.60/weight 0.0 at q=90 bp gives ζ 0.95/0.89/0.84. Reset stays on calendar hours (staleness is data age, not variance). |
| `filterSessionShare` | float 0–1 | 0.60 | Session share of a day's process variance (session clock). |
| `filterNonTradingWeight` | float 0–1 | 0.0 | Non-trading-day weight (session clock). |
| `filterDataOnlyPrepass` | bool | false | Fit data-only first so the measurement is a clean market observation; off = reuse committed fit's handles and flag contamination. |

### 2.8 Local-vol (affine) grid and solver

These fold into the LV *affine key* only — they never invalidate parametric fits.

| Field | Type / range | Default | Role |
|---|---|---|---|
| `gridStrikeMode` | `delta` \| `linear` | `delta` | Strike-vertex placement: symmetric delta axis (dense near ATM, controlled wing reach — fixes the under-resolved put wing) or legacy uniform-in-x. |
| `gridXNodes` | int 3–200 | 12 | Strike vertices. In delta mode a FLOOR (the ~13-node delta set drives placement; midpoints inserted only to reach the count); in linear mode exact. |
| `gridXMinPerExpiry` | int 0–60 | 8 | Minimum strike vertices guaranteed inside each expiry's OWN traded range. The shared axis is sized to the longest expiry, so a narrow short-dated smile can land only ~3 vertices on its sharpest curvature (measured: a 6-DTE weekly at 3 vertices fit 108 bp LV RMS vs ~28 bp at ~8). Widest in-range gaps are split until each expiry reaches the floor; well-covered expiries are untouched (often byte-identical). 0 = off. |
| `gridTNodes` | int 0–120 | 10 | Floor on POSITIVE time vertices over the base set (0 + pre-front node + every lit expiry); widest √T gaps split until reached. 0 = base set only. |
| `gridRegLambda` | float 0–1e4 | 1e-2 | Roughness regularization. |
| `gridRegRho` | float 0–10 | 1.0 | Time-vs-strike roughness ratio. |
| `convexWing` | bool | false | Force local VOL σ(x,t) convex in x below the 5Δ-put strike (soft hinge per time row at deep-put vertices) so the sparse left wing can't fit too concave. Off = byte-identical. **Authority confined to the unquoted extrapolation tail** (a fine-grid version fighting dense quotes cost 26 bp — certification case). |
| `convexWingWeight` | float ≥0 | 1e3 | Hinge strength. |
| `frontTie` | bool | true | Pull the unconstrained t=0 vertex row toward the first data-identified row via a soft one-sided difference per strike column, so the free front can't leak into the shortest smile. Weight 0/off = byte-identical. |
| `frontTieWeight` | float ≥0 | 1e-2 | Front-tie strength. |
| `lvVolCapMult` | float 1–20 | 3.0 | Adaptive nodal local-vol cap: max(60%, mult × highest observed implied vol), capped 400%. A fixed 60% cap starved high-vol names' put wings (local variance in the wing runs well above implied). Cap does not apply in the extrapolation region. |
| `timeScheme` | `implicit` \| `rannacher` | `implicit` | LV PDE time discretisation. Rannacher (CN after implicit start-up) reaches equal accuracy at ~3× dt but benchmarked only ~1.1× net (heavier sensitivity step) AND is not monotone — an arbitrage violation appeared on a coarse grid — so implicit Euler stays the default; Rannacher is opt-in. Var-swap fits keep implicit either way. |
| `lvEarlyStop` | bool | true | Early-stop the COLD fit when the DATA misfit (option + var-swap + basket rows) stalls (otherwise it runs to the 200-eval cap with tail evals barely moving the surface). Measured ~1.45× (slow-converging, +0.10 bp) to ~3.3× (fast-converging, +0.25 bp); warm restarts whose data rows already fit converge before the stall window. **Fix 2026-08-27:** the stall used to watch the OPTION rows only, so a warm-started fit whose options already fit stopped at its start point without moving toward a var-swap quote — the LV var-swap row (soft AND hard pin) was inert under early stop. Fits without var-swap / basket rows (the perf rails included) are byte-identical, so the measured speed-ups stand; a fit carrying such rows now keeps going while they improve. |
| `lvFastKernel` | bool | true | Compiled vectorized-Thomas Dupire march for the hot path: ~6× the LAPACK banded march (no-pivot Thomas, SIMD across sensitivity columns, fused source), matching banded to ~1e-15; automatic fallback when the compiler is unavailable or for var-swap/Rannacher paths. |
| `lvSolver` | `trf` \| `gn` | `gn` | Matrix-free Gauss–Newton avoids the trust-region solver's dense SVD (~52% of an eval): ~1.3–1.65× faster. Engages ONLY for the smooth MID target with the fast kernel active; falls back to trust-region for band objectives, var-swap fits, or the banded march. Accepted trade-off: GN can land a slightly different local optimum (≤~0.25 vol bp, often better). |
| `lvXMaxMin` | float [2.5, 10] | 2.5 | FLOOR on the LV PDE lattice's right edge in x = K/F (x_max = max(1.4 × highest quoted x, floor)); every LV view's right wing is capped at k = ln(x_max). 2.5 (k ≈ +0.92) = the historical constant, byte-identical; 2.72 reaches k = +1.0. O(n_x) march cost. LV-only (affine key). |
| `leftWingSlopeMult` | float 0–20 | 1.5 | Left-wing (x < x_min) LINEAR extrapolation slope as a multiple of the first cell's slope — deep-put local variance keeps rising instead of clamping flat. Fixed multiple when convex wing is on (else flat); becomes a FREE calibration variable when a var-swap quote is set (this is its init). |

### 2.9 Model penalties (cross-model)

| Field | Type / range | Default | Role |
|---|---|---|---|
| `sivWingPenaltyPct` | float 0–1000 | 100.0 | Multi-Core SIV put-wing no-butterfly regularizer strength (percent of base weight): pushes Durrleman g ≥ 0 in unquoted wings; 0 = off (byte-identical); zero on an arb-free slice, so liquid names are untouched regardless. |

### 2.10 Graph solver

| Field | Type / range | Default | Role |
|---|---|---|---|
| `graphKappaScale` | float >0 | 1.0 | Prior strength (local precision toward baseline). |
| `graphEtaScale` | float ≥0 | 1.0 | Reach (smooth-field edge strength scale). |
| `graphLambdaScale` | float ≥0 | 0.0 | Optimal-transport flux weight (0 = off — the adjudicated default). |
| `graphNu` | float >0 | 0.1 | OT source allowance. |
| `graphPropagationMode` | `smooth_field` \| `precision_messages` \| `hybrid` | **`precision_messages`** | Default propagation operator for the production solve; the frontend seeds its mode selector from this. Flipped by explicit user ratification on measured evidence (intraday: messages 65.8 bp vs transported prior 172.7; the legacy smooth-field operator nearly inert at 168.6). `smooth_field` remains explicit configuration/rollback and remains the **wire default** on the solve request itself, so replay, byte-identity locks, and the backtest harness are untouched. Persisted saves pin their explicit value until re-saved. |

### 2.11 Spot-vol dynamics

| Field | Type / range | Default | Role |
|---|---|---|---|
| `dynamicsRegime` | `sticky_moneyness` \| `sticky_strike` \| `sticky_local_vol` \| `sticky_local_vol_grid` \| `custom` | `sticky_strike` | Spot-scenario transport regime (selector lives in Options; the Parametric spot scenario reads it). |
| `ssr` | float ≥0 | 2.0 | Skew-stickiness ratio used by the `custom` regime. |

### 2.12 Workflow, scheduler, streaming

| Field | Type / range | Default | Role |
|---|---|---|---|
| `autoCalibrate` | bool | true (code) / **false when the gated live server boots with no saved preference** | ON: calibrate all lit nodes in the background after an options fetch, and refit on quote edits/parameter changes. OFF: mark stale and wait for the explicit Calibrate trigger. The live server deliberately defaults OFF so expensive fitting happens only on the button; the code default stays ON for the ungated test/dev app. |
| `localVolEnabled` | bool | true | LV master switch: OFF = background Calibrate skips every ticker's LV surface and the Local Vol workspace tab is disabled. Pure workflow/UI gate — never busts caches. |
| `autoUpdate` | `off` \| `spot` \| `snapshot` | `off` | The request-path timer WITHOUT a live stream (2026-09-02g model). `off` = manual Fetch only; `spot` = probe the provider spot every `autoUpdateSeconds` and transport the surface (`POST /fetch/spots` — never a refit); `snapshot` = the unified Snapshot sequence every `autoUpdateSeconds` (chains → spot transport → optional prior roll → auto-calibrate when on, exactly `POST /fetch/snapshot`). Inert while a book streams. A calibration always prices spot and quotes from ONE snapshot; a spot-only update only transports. Replaces `spotMode` / `spotPollSeconds` / `optionsFetchMode` / `optionsFetchMinutes` / `schedulerUnifiedFetch` (accepted on input and migrated: an auto chain timer → `snapshot` at its minutes cadence, a realtime spot poll → `spot`, else `off`). |
| `autoUpdateSeconds` | float (0,86400] | 5.0 | Auto-update cadence. Floored at 15 s by the model when `autoUpdate` is `snapshot` (every tick downloads a full chain on a request-path source). |
| `streamRefitSeconds` | float (0,600] | 5.0 | While a live book streams and `autoCalibrate` is on, rebuild the chains from the in-memory book and recalibrate the lit nodes at this cadence — the stream's own quotes + spot tick. Held by `streamFreezeFit`. |
| `streamFreezeFit` | bool | false | While a book streams, hold the fit where it was calibrated: the book still feeds Fetch / Calibrate and the live quote layer, but the surface is not transported to the book spot and the streaming refit does not run (the Spot card's dial stays free). Off = live transport + refit. |
| `autoStream` | bool | true | The one switch that opens the real-time book on a streaming-capable source (Massive WebSocket, Bloomberg //blp/mktdata): fetch / calibrate / spot serve from the fast in-memory book, spot and quotes flow continuously (the scheduler's streaming branch: book-spot sync every 5 s, the refit above), `autoUpdate` is inert. No effect on non-streaming sources. |

---

## 3. Market settings (per ticker)

| Field | Type | Default | Role |
|---|---|---|---|
| `rate` | float | 0.0 | Flat risk-free rate override. |
| `dividendMode` | `continuous` \| `discrete` \| `mixed` \| (manual policies) | `continuous` | Dividend policy. |
| `dividendYield` | float | 0.0 | Continuous yield. |
| `dividends` | list | [] | Discrete dividend schedule (ex-date, amount). |
| `switchYears` | float | 1.0 | Mixed-mode horizon: discrete before, continuous after. |

Per-expiry forward policy (parity / theoretical / manual, with provenance) is a
separate per-node endpoint, not a global setting.

---

## 4. Rules the rebuild must keep

1. **Every knob documents:** unit, valid range, default, activation condition
   ("only read while X is on"), and whether it bumps a cache version. The
   settings schema with field docstrings is the single source of truth; the
   Options workspace renders it.
2. **Feature-off = byte-identical.** Fields marked "off = byte-identical" above
   are locked by tests in the reference implementation; the rebuild needs the
   same locks.
3. **Version scoping.** Fit-settings version ≠ options version ≠ LV affine key
   ≠ filter version. A display-only field must never invalidate a fit; an
   LV-only field must never invalidate a parametric fit.
4. **Persisted-blob migration.** Old saved settings blobs missing new fields
   coerce to defaults; legacy fields (e.g. the pre-mode prior toggle) migrate
   on load; out-of-range persisted values clamp rather than reject, so a saved
   desk always loads.
5. **Defaults changed only through recorded adjudication.** Several defaults
   above (Lee cap 1.95, structural chart, GN solver, process noise 30, message
   mode) are the outcome of pre-registered benchmarks or committee review —
   see `PITFALLS_AND_ADJUDICATIONS.md`.

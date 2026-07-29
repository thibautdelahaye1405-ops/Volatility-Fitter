# Vol-Fitter — clean-room rebuild specification

**Purpose:** rebuild a professional implied-volatility surface fitting
application from first principles, using the accompanying Markdown technical
notes as the mathematical specification and this document as the product and
engineering contract.

**Target:** capability-equivalent to the reference application — same economic
questions answerable, same invariants, same failure visibility, same order of
latency — but not a source-compatible or pixel-identical clone. Improvements
are welcome wherever the contracts below are preserved.

**Version:** 2 (2026-07-29). Supersedes the 2026-07-27 draft.

**Audience:** a strong coding model (e.g. driven through GitHub Copilot) and
its human reviewer.

---

## 1. Instructions to the implementing model

You are building a new Vol-Fitter in a new repository. You do not have, and
must not request, the previous source tree. This document pack is the complete
design input: it was deliberately distilled so that nothing else is needed.

The objective is not to guess how the old application was written. It is to
produce an independently designed application with comparable quant
capabilities, numerical quality, latency, auditability, and desk usability.
Choose clean interfaces and current, well-supported libraries. It is
acceptable — encouraged — to improve the architecture, API, storage model, or
UI when the externally visible capability and the mathematical contracts are
preserved.

Non-negotiable working rules:

1. Read this document completely before writing code.
2. Read the relevant note completely before implementing its subject. The
   notes are lectures: they derive everything and state exactly what is
   *structural* (guaranteed by construction), *certified* (independently
   checked), *measured*, or *experimental*. Preserve those labels.
3. Convert every mathematical claim into an independent test before relying on
   it in a higher layer.
4. Keep a requirements-to-tests matrix and a short decision log in the new
   repository from day one.
5. Deliver a working, tested vertical slice at the end of every phase
   (Section 15). Never attempt the whole application in one pass.
6. Never call a feature complete because its UI exists. Completion requires
   the numerical tests, the failure semantics, the diagnostics, and the
   performance rail.
7. Never silently weaken a guarantee, and never silently change a default that
   Section 4.5 or `SETTINGS_REFERENCE.md` states — several of them are the
   outcome of pre-registered benchmarks (`PITFALLS_AND_ADJUDICATIONS.md`).
   Re-deciding one requires a recorded decision with evidence.
8. Report outcomes faithfully: failed tests with output, skipped steps named
   as skipped, measured numbers instead of "should work".

This is a clean-room *capability* specification, not a request to reproduce
source text. The algorithm specifications inside the notes are mathematical
oracles and test aids; write new production code around independently chosen
interfaces.

---

## 2. The document pack

The pack is entirely Markdown (transfer constraint: no PDFs, no images, no
source code, no executables). It has two layers.

### 2.1 Engineering layer (this folder)

| File | Role |
|---|---|
| `VOL_FITTER_CLEAN_ROOM_REBUILD.md` | This contract: scope, invariants, architecture, phases, acceptance. |
| `SETTINGS_REFERENCE.md` | The exhaustive control surface: every tunable with type, range, default, unit, activation condition, and cache-version semantics. |
| `API_AND_UI_INVENTORY.md` | The reference app's 107-route API surface and eight-workspace UI, as a completeness checklist. |
| `PITFALLS_AND_ADJUDICATIONS.md` | Every named production failure (as certification-test material) and every pre-registered benchmark verdict behind today's defaults. |
| `README.md` | Pack manifest, reading order, transfer notes. |

### 2.2 Mathematical layer (`notes/`)

The notes are the *prevailing lecture editions* of the reference project's
technical series — as of 2026-07-27 each was audited line-by-line against the
working code, so their equations, defaults, and measured numbers are current.
Figures could not be shipped; each figure was replaced by a caption plus a
panel-by-panel description, and every measured number is inlined. Reference
implementations were converted to precise algorithm specifications (no code).

One **primary** note per topic; supplements retell the same material from a
different angle (content-parity is guaranteed — read them when the primary's
angle doesn't land, or for their distinct case files).

| Topic | Primary | Supplements |
|---|---|---|
| System map + control index | `00_system_overview.md` | — |
| 01 LQD smile model | `01_lqd_model_coordinates.md` (charts; where no-arb is free) | `01_lqd_model_lecture.md` (distribution-first), `01_lqd_model_percentile_ruler.md` (fresh audit) |
| 02 SVI / SVI-JW | `02_svi_jw_rewrite.md` (raw vs JW charts, structural chart) | `02_svi_jw_moments.md` (wings, belly, Lee bound as a tail statement, certificates) |
| 03 Multi-Core SIV | `03_multicore_mcs_corrections.md` (base + correction, capacity control) | — |
| 04 Local volatility | `04_local_volatility_forward.md` (Dupire read backward, parameters up) | — |
| 05 De-Americanization | `05_deamericanization_stopping.md` (optimal stopping; subtracting the unobservable premium) | — |
| 06 Forwards / dividends | `06_forwards_dividends_inference.md` (inference on one straight line; identifiability ladder) | — |
| 07 Calibration objective | `07_calibration_objective_measure.md` (units, measure, tolerance) | — |
| 08 Variance swaps | `08_varswap_representations.md` (one number, three integrals) | — |
| 09 Wings | `09_wings_last_quote.md` (beyond the last quote: prove / choose / police) | — |
| 10 Calendar | `10_calendar_unnamed_martingale.md` (Kellerer as the organizing theorem; who pays to restore order) | — |
| 11 Event / intraday clock | `11_event_market_clock.md` (the market keeps its own clock) | — |
| 12 Spot-vol dynamics | `12_spotvol_missing_derivative.md` (dynamics unidentified by a snapshot; SSR as the one dial) | — |
| 13 Prior persistence | `13_prior_flat_directions.md` (the prior confined to the null space of today's data) | — |
| 14 Graph propagation | `14_graph_three_priors.md` (three priors for a dark universe; the mode fork as an assertion dial) | `14_graph_messages.md` (the precision-message system, standalone deep spec) |
| 15 Observation filter | `15_kalman_computed_trust.md` (trust is computed, not configured) | — |

### 2.3 Precedence when documents disagree

1. This rebuild specification for scope, product defaults, sequencing, and
   acceptance.
2. `SETTINGS_REFERENCE.md` for exact default values and ranges (it was
   machine-extracted from the running application and is the freshest).
3. The primary note for mathematics and numerical contracts; its supplements
   are equal in authority on shared content.
4. A note's *measured result* over its earlier *design intention* (notes state
   both; e.g. the filter process noise was designed at 10 and measured to 30).
5. A simpler, better-tested implementation over a speculative extension.

The most important current-default decisions (details and evidence in
`PITFALLS_AND_ADJUDICATIONS.md`):

- **LQD is the default parametric family** and the reconstruction backbone;
  its production chart is the logistic endpoint chart.
- **SVI fits through its structural chart** by default, with a strict Lee
  slope cap of **1.95** (2.0 is the broken boundary, explicit config only),
  and a one-shot belly repair followed by an independent certificate.
- **Multi-Core SIV is hard-capped at two hat cores** (3+ overfit and
  manufacture wing arbitrage).
- The graph UI defaults to **precision messages** (desk amplitude 1.0,
  calendar beta exponent 1); **smooth-field** remains the wire default on the
  solve request, an explicit rollback, and the validation comparison arm.
- **Layered dynamic-harmonic propagation stays opt-in**: its residual-memory
  mechanism is validated intraday (optimal half-life ≈ 0.1 day) but the full
  layered carrier has not beaten static messages; infinite residual
  persistence is measurably harmful.
- The **optimal-transport graph term** exists but ships at weight 0; learned
  graph betas remain diagnostic-only.
- **Observation filtering is off by default**; overlay mode is the safe first
  activation; process noise 30 bp/√day.
- The **symmetric calendar solver** is the default; sequential is a
  comparison/fallback mode.
- **Calendar/butterfly enforcement is confined to identified support**;
  extrapolated-region enforcement is opt-in with always-on advisory
  measurement.

---

## 3. Definition of success

The rebuild succeeds when a desk user can:

1. Select an asset/expiry universe and a market-data source, and save/load it
   by name.
2. Fetch or replay option chains, spots, carry inputs, and dividends, with a
   global as-of selector and visible data age.
3. Infer or override forwards and discounts with explicit provenance per
   expiry.
4. Prepare European and American chains robustly, retaining a typed reason for
   every quarantined quote.
5. Fit each smile with LQD, SVI, or Multi-Core SIV under mid, bid/ask-band, or
   haircut-band objectives, with equal or time-value-density weights.
6. Jointly fit a positive piecewise-affine local-variance surface through a
   forward Dupire PDE.
7. Apply variance-swap targets, calendar controls, event time, prior
   persistence, and optional observation filtering — each additive, each with
   exact off-behavior.
8. Transport a calibrated surface after a spot move analytically, without
   recalibration, under a chosen stickiness regime.
9. Mark dark smiles from lit innovations through a configurable graph, with
   credible bands, provenance, attribution, preflight, what-if, observation
   planning, and leave-one-out validation.
10. Inspect smiles, densities, term structures, local vol, forwards, settings,
    graph relationships, universe membership, and publish quality in a
    professional eight-workspace UI.
11. Run calibration in the background with progress streaming, cancellation,
    stale-state handling, scoped invalidation, and deterministic replay.
12. Export and publish only surfaces that pass explicit data, fit, and
    arbitrage gates; recall a publication as a lifecycle transition.
13. Re-run a named certification suite and a historical benchmark pack that
    report precision, uncertainty calibration, breaks, and speed.

"Comparable" does not mean identical floating-point values, HTTP routes, or
pixels. It means the same economic questions can be answered, the central
mathematical invariants hold, failures are visible, and the latency is of the
same order.

---

## 4. Scope and priorities

### 4.1 Required for the first full release

- Forward-normalized option-pricing primitives and robust vectorized IV
  inversion.
- Deterministic synthetic offline provider plus at least one real provider
  adapter appropriate to the environment.
- Typed market snapshots, exact timestamps, settlement semantics, tick sizes,
  and as-of replay.
- Parity forwards/discounts, dividend policies, manual overrides, provenance,
  and the zero-carry-chain pin.
- De-Americanization with a compiled fast path and a deterministic fallback.
- The three parametric slice models: LQD, SVI, Multi-Core SIV.
- The piecewise-affine local-variance surface with its full diagnostic set.
- Mid, bid/ask, and haircut objectives; equal and tv-density weights.
- Static-arbitrage diagnostics and independent publish certification.
- Symmetric calendar control, event variance time, variance-swap targets, and
  spot transport.
- Saved/transported priors and hybrid prior persistence with activation gates.
- Static precision-message graph propagation, smooth-field comparison mode,
  functional uncertainty bands with the idiosyncratic ATM floor, attribution,
  and observation planning.
- The eight workspaces of Section 12.
- Persistent settings (with defaults save/reset), named universes, prior
  snapshots, fit history, quote and var-swap edit sessions with undo/redo,
  publish manifests, and an append-only audit/event log.
- Background calibration with a bounded process pool, SSE progress,
  cancellation, stale-state semantics, and cached read-only views.
- Unit, golden, derivative, integration, API, UI, certification, and
  performance tests.

### 4.2 Required as an explicit advanced mode

- Local-vol variance-swap source-PDE route.
- Extrapolated-region tapered enforcement and the LQD tail contract.
- Joint borrow/de-Americanization fixed point behind its materiality gate.
- Prior operator/factor two-pass activation; full operator covariance.
- Observation-filter overlay and active one-stage MAP modes; session clock.
- Graph config lifecycle (draft/preview/activate/diff/revert), preflight,
  non-persisting what-if pulses, LOO comparison, next-observation ranking,
  smooth-field autotune, graph-to-LV projection.
- Research/replay-grade 0DTE intraday clock and degraded-market behavior.
- Client-readable HTML certification and quality reports.

### 4.3 Experimental or opt-in

- Layered dynamic-harmonic graph mode (directed state, residual half-life,
  exact zero reverse influence, harmonic completion, persistent residual
  store).
- Smooth-field/message hybrid mode and optimal-transport regularization.
- Learned graph amplitudes (diagnostic surface only).
- Full cross-handle covariance in prior and observation filters.
- Rannacher/CN local-vol time stepping (kept opt-in: not monotone).

Experimental features must never be the only path to a publishable surface,
and must be removable without changing the baseline result except for
documented setting/version metadata.

### 4.4 Non-goals

- Exotic pricing or risk management; order routing or execution.
- Forecasting dividends, borrow, volatility, or returns.
- Redistributing market data.
- A hyperscale multi-tenant platform in the first release (single-desk,
  single-tenant hosted is the settled posture; keep interfaces that allow
  more later).
- Bit-for-bit reproduction of the reference implementation.
- Neural models whose behavior cannot be explained or benchmarked against the
  mathematical models.

### 4.5 Reference starting profile

The first coherent configuration. `SETTINGS_REFERENCE.md` is exhaustive and
exact; this table is the orientation summary. A later benchmark may change a
default, but only through an explicit, recorded decision.

| Area | Starting choice |
|---|---|
| Parametric family | LQD, order 6, logistic endpoint chart, ridge 1e-6 power 1, tail barrier centre 0.90 scale 50 |
| SVI | structural chart; penalty 1e3; Lee cap 1.95; belly repair on; 801-point certificate at g ≥ −1e-4 |
| Multi-Core SIV | 2 cores max; amplitude ridge 1e-2; put-wing penalty 100% |
| Objective | mid; equal weights; haircut 0.005 vol; band mid-anchor 0.05 |
| Variance swap | enabled; 10% information budget; static replication route |
| Calendar | enabled; symmetric violation-block repair; penalty 1e6 |
| Extrapolated-region enforcement | off; advisory diagnostics always on |
| Event clock | enabled; one-year normalization off; intraday/0DTE clock off (session share 6.5/24, non-trading weight 1.0 when on) |
| Prior persistence | hybrid; operators ATM/RR25/BF25/VarSwap; strengths 50/50/20%; bandwidth 0.06; required precision 1.0; single-pass gate |
| Observation filter | off; jacobian covariance when on; process noise 30 bp/√day (skew 0.02, curv 0.05); adaptive σ 3; reset 96 h; calendar clock (session clock: share 0.60, non-trading 0.0) |
| Local-variance grid | delta strike axis; 12-vertex floor; ≥8 in-range vertices per expiry; 10 positive-time-node floor; roughness 1e-2 / ρ 1.0 |
| Local-variance solver | positive variance; implicit time step; compiled fast kernel; early stop; matrix-free GN where eligible; adaptive vol cap 3× (floor 60%, cap 400%); left-wing slope 1.5×; front tie on at 1e-2; convex wing off |
| Spot dynamics | sticky strike; custom SSR 2.0 available |
| Graph | precision messages; desk amplitude 1.0; calendar exponent α_T = 1; κ scale 1.0; η scale 1.0; OT λ 0 (ν 0.1); functional band + idiosyncratic ATM floor on |
| Data freshness | amber at 20 min, red (publish-blocking) at 120 min |
| Workflow | trigger-gated calibration on the live server (auto-calibrate off until the user opts in); LV enabled; spots static/on-demand; options on-demand; stream-refit 5 s and auto-stream on where a streaming source exists |

---

## 5. System-wide invariants

These rules outrank convenience.

### 5.1 Normalization and units

- Use the expiry forward $F_T$ and log-moneyness $k=\log(K/F_T)$.
- Work in forward-normalized, undiscounted option prices inside the quant
  core.
- Treat total variance $w$ as the clock-independent quantity implied by price.
- Keep calendar time $t$, event/working variance time $\tau$, market IV
  $\sqrt{w/t}$, and working IV $\sqrt{w/\tau}$ distinct. Switching clocks
  preserves price and total variance.
- Store volatility as a decimal; one vol point is 0.01; one vol basis point is
  1e-4.
- Use timezone-aware valuation, quote, last-trading, exercise, and settlement
  timestamps. Never represent a sub-day expiry with an integer day count.
- Label every precision and variance with the units of the handle it governs.

### 5.2 Guarantees are graded

**Structural** (by construction) > **certified** (independently checked on the
finished artifact, publish-gating) > **measured** (reported) >
**experimental** (labeled, comparable, removable). Examples:

- LQD slice butterfly freedom: structural.
- Positive-local-variance Dupire surface: structural, given the verified
  monotone scheme.
- SVI/MCS penalty satisfaction: measured; the dense-grid belly certificate:
  certified.
- Calendar order outside common identified support: measured, unless the
  explicit tail contract is armed.
- Graph uncertainty calibration: measured by held-out standardized residuals
  and coverage.

### 5.3 Features are additive

Turning a feature off must recover the feature-absent calculation to floating
point, and where practical byte-identically. Lock this with tests for: bands
and haircut; variance-swap targets; calendar coupling; event time; priors;
observation filtering; graph extras (OT, betas); local-vol fast kernels, early
stop, front tie, convex wing; extrapolated-region penalties; joint carry
below its materiality gate. A disabled feature must not alter initialization,
cache keys, seeds, or iteration limits unless its absence is itself part of
the key.

### 5.4 No hidden evidence

- Dark-node quotes never influence the graph solve; they may score it
  afterwards.
- A graph prediction is never recycled as a later market observation.
- A filtered posterior is never counted again as an independent quote; active
  filtering is ONE MAP problem, not "fit, filter, refit on the same
  evidence".
- A saved prior carries an as-of timestamp and provenance; transported priors
  state their transport.
- No unsupported graph component invents an innovation.
- Holdout/what-if/preflight solves never write state; replay freshness gates
  read the scenario clock, not the wall clock.

### 5.5 Fail visibly

Every failed or omitted datum needs a typed reason. At minimum distinguish:
source unavailable/delayed; stale snapshot; crossed or one-sided market;
below price/intrinsic/tick tolerance; no parity forward; American inversion
failure; IV inversion failure; quarantined wing; no fittable market;
optimizer non-convergence; uncertified butterfly; calendar failure;
unsupported graph component; missing or stale prior; stale filter state.
Fallbacks may keep the application usable but must never masquerade as fresh
market calibration.

---

## 6. Recommended architecture

Directory names are free; the dependency direction is not:

```text
pure numerical core
    -> market preparation and calibration
        -> stateful application services
            -> HTTP/streaming API
                -> web UI

persistence and audit sit beside services
backtest/certification call the same production core
```

A sensible layout:

```text
backend/
  volfit/
    core/            Black pricing, IV inversion, grids, linear algebra
    data/            providers, snapshots, symbols, expiry/settlement metadata
    market/          carry, forwards, dividends, de-Americanization
    models/          lqd, svi, mcs, local_variance
    calibration/     objectives, weights, calendars, priors, filters, clocks
    dynamics/        spot/forward transport
    graph/           messages, smooth field, dynamic-harmonic, uncertainty
    services/        workflows, sessions, cache, quality, publishing
    api/             typed schemas and routers
    persistence/     repositories, migrations, manifests, event log
  tests/
  backtest/
frontend/
  src/  (workspaces, components, charts, state, api client)
```

Keep the numerical packages independent of HTTP, UI, databases, and live
data: immutable arrays/domain objects in, typed results plus diagnostics out.
Keep source files small and single-purpose (the reference project held a
400-line-per-file discipline and it paid off for review and agent
navigation).

### 6.1 Suggested technology

- Python 3.11+; NumPy/SciPy for numerics.
- Numba (or an equivalent compiled-array route) for the CRR and local-vol hot
  loops, always behind a tested pure-NumPy/LAPACK fallback — the app must be
  correct without the compiler.
- FastAPI (or equivalent typed async framework); SSE for progress push.
- SQLite behind repository interfaces for the single-desk release; columnar
  files (Parquet) for bulk historical quotes.
- React + TypeScript (Vite) or an equivalently mature typed web stack;
  SVG/canvas/WebGL charts chosen by data size; charting never bleeds into the
  quant core.
- Pytest; vitest (or equivalent) for components; a headless-browser smoke
  runner over a production build.
- A bounded process pool for parallel fits: default `min(cpu_count − 1, 8)`
  workers, 0/1 = serial with byte-identical results, and the test suite pins
  serial.

Avoid a distributed system until measurement requires it.

### 6.2 Domain objects

Define typed, serializable objects early:

- `NodeKey` — ticker + exact expiry/settlement identity (AM/PM settlement
  matters; do not key sub-day expiries by date alone).
- `MarketSnapshot` — source, as-of, spot, raw quotes, tick size, data-age and
  provenance.
- `OptionQuote` — type, strike, expiry metadata, bid/ask, sizes, quote time,
  exercise style.
- `CarryCurve` — versioned discounts, forwards, dividends, borrow; per
  component source and confidence.
- `PreparedQuote` — normalized price/IV/total variance, $k$, band, weight,
  original identity, quarantine status + typed reason.
- `FitSettings` / `EngineSettings` — versioned, validated, explicit units
  (see `SETTINGS_REFERENCE.md`).
- `FittedSlice` — family, parameters, curve, handles, diagnostics,
  uncertainty, input/settings hashes, timestamps, stale state, certificate
  state.
- `FittedSurface` — ordered slices + calendar/LV diagnostics.
- `PriorSnapshot` — fitted state, original forward, as-of, provenance.
- `HandleState` — ATM level/skew/curvature and covariance.
- `GraphRelation` — informer, receiver, relation class, per-handle beta,
  precision, semantics, version.
- `SurfaceManifest` — parent hashes, inputs, settings, model version, quality,
  lifecycle status, wing-projection audit.

Use stable content hashes for expensive derived artifacts; never mutable
object identity as a cache key. Exports embed all inputs, so an export is
replayable standalone.

---

## 7. End-to-end compute pipeline

Implement and test these stages independently:

```text
provider snapshot
  -> exact expiry/settlement clock
  -> forward, discount, dividends, optional borrow
  -> OTM selection and quote preparation (screens, tick floor, quarantine)
  -> American-to-European conversion where needed
  -> price/IV inversion, weights
  -> parametric slice fits and joint local-variance fit
  -> independent certificates and quality gates
  -> saved fit + manifest
  -> views and exports
  -> transported prior + lit innovations
  -> graph posterior for dark nodes
  -> reconstructed smile + uncertainty + validation
```

Cache keys are separate per stage: changing a model penalty must not fetch
data or rerun de-Americanization; changing one ticker's dividends must not
invalidate other tickers; a spot-only move uses analytic transport, not
recalibration.

Background "Calibrate": snapshot the requested inputs and settings; fit lit
slices in parallel across the process pool; fit each enabled ticker's
local-vol surface as a separate task; stream progress (SSE); allow
cancellation between bounded work units; atomically commit successes; keep
the previous good fit visible when a new fit fails; mark affected artifacts
stale until replaced.

---

## 8. Quantitative requirements

The notes carry the derivations; this section fixes each subsystem's product
role and integration contract.

### 8.1 Shared pricing core

Vectorized normalized Black calls/puts, derivatives, total-variance
conversion, robust IV inversion. Tests: put-call parity in normalized units;
zero-variance intrinsic limits; deep ITM/OTM and very short maturity;
monotonicity in variance; finite-difference checks of analytic derivatives;
price→IV→price round trips over a wide deterministic grid. Prefer array-wide
bracketing/Newton with safe fallbacks over per-quote scalar root solving.

### 8.2 Forwards, discounts, dividends, carry (Note 06)

- Infer $F_T$ and the discount from put-call parity via robust, near-ATM-aware
  regression; keep the forward level robust to noisy slope identification;
  clamp or reject implausible discounts explicitly.
- Support proportional, discrete, mixed, and manual dividend policies; a
  theoretical/manual forward override carries provenance.
- **Zero-carry pin:** recognize provider chains synthesized at F = spot with
  zero spreads and pin F = spot, D = 1 (persisted) instead of regressing
  invented carry; legitimate zero-spread EOD closes must still resolve.
- Joint borrow/de-Americanization only behind the advanced toggle with its
  per-expiry 25 bp materiality gate; know its limits: a flat rate biases
  borrow 1:1, so unbiased borrow needs a rate curve.
- Every downstream object reports which forward/discount it used.

### 8.3 De-Americanization and quote preparation (Notes 05, 07)

- Apply only to American-style contracts; invert a validated American pricer
  (CRR class, ~192 steps minimum — cutting depth was measured harmful) to
  recover European-equivalent bid AND ask, not just a mid.
- Deterministic bracketing, explicit static bounds, typed failure reasons;
  batch the chain and compile the hot loop; cache by full content digest +
  carry + tree controls + clock.
- Repair authority is confined to the wing convexity defect the method exists
  for; a global repair that can move the ATM core is forbidden (this shipped
  once and had to be reverted — see the pitfalls file).
- Handle duplicate strikes across listings (nearest strictly-distinct-strike
  slopes).
- OTM-side selection; price/intrinsic/vega screens; a 3-tick OTM floor tested
  against the bid on real feeds; every dropped row retained with its reason.
- Price/band-space authority near zero vega, especially 0DTE.

### 8.4 Calibration objectives (Note 07)

All models expose the same user choices: mid; bid/ask band (zero residual
inside the band); haircut band (each side shrunk toward mid by a stated vol
amount, default 0.005); optional small mid anchor in band modes (0.05);
equal or time-value-density weights; weighted RMS and max error in stable
desk units. LQD and local variance normally use vega-normalized price
residuals; SVI/MCS may use IV residuals — a shared product choice does not
force a single internal residual on every model.

### 8.5 LQD (Note 01)

- Valid risk-neutral density and martingale normalization **by
  construction**; stable logit/quantile coordinates; endpoint tail scales;
  Legendre body modes with ridge regularization.
- Prices, IVs, density, log-quantile density, quantiles, tail moments, Lee
  slopes; exact ATM level/skew/curvature handles.
- The logistic endpoint chart as production default: the admissibility wall
  is unreachable, so the chart covers exactly the admissible set.
- Analytic residual Jacobians (including the var-swap row).
- Native variance-swap route (closed form/quadrature).
- Calendar constraints in the appropriate LQD object, in **price space at
  fixed strike** — never in the quantile-domain ledger, which integrates the
  whole upper tail (this mis-space cost 1000+ bp once; see pitfalls).
- LQD is the default family and the backbone for graph handle retargeting.

### 8.6 SVI / SVI-JW (Note 02)

- Raw SVI and exact JW handle maps with guarded domains; symmetric/degenerate
  chart singularities explicit; the guarded JW→raw map returns structured
  domain-error reasons, never case-dependent NaNs.
- Fit through the **structural chart** $(\beta_L, \beta_R, k^*, w^*,
  \kappa^*)$ by default: every finite iterate respects positivity and the
  strict Lee fence, so penalties are inert; the raw chart stays as rollback.
- Lee cap **1.95**; analytic Jacobians for both charts (the structural chain
  is 5×5 and made identical smiles 2.1–2.4× faster); guard the float
  boundaries (ρ → ±1, logistic → 1) with interior clipping.
- Exact Durrleman butterfly functional from model derivatives; certify the
  finished displayed slice on a dense in-range grid (801 points) with
  tolerance $g \ge -10^{-4}$; on failure allow ONE targeted belly-repair
  refit, kept only if it certifies.
- An uncertified SVI slice can never become a published mark (hard 409).
- Deterministic refusal below 3 quotes; the full adversarial battery of the
  pitfalls file must pass on both charts.

### 8.7 Multi-Core SIV (Notes 03, 09)

- Six-parameter sigmoid base plus zero-wing hat cores; the curve is the
  contract (hat decomposition need not be unique); 0–2 cores, hard-capped.
- Deterministic seeding; hat-amplitude ridge 1e-2; measure Durrleman $g$
  beyond the observed wing; the put-wing penalty/repair targets the observed
  failure mode and is zero on arb-free slices.
- Input-side de-Am repair and output-side model wing penalty stay separate,
  composable protections.

### 8.8 Piecewise-affine local variance (Note 04)

- Unknowns: positive nodal local variances on a maturity×strike grid,
  piecewise-affine interpolation, priced by the forward Dupire PDE.
- Time stepping monotone and stable; fully implicit is the default (CN-class
  schemes are opt-in only: measured ~1.1× net and not monotone).
- Delta-aware strike grid; √T-aware time grid; every lit expiry a node; the
  per-expiry in-range vertex floor (≥8) — the single most important grid rule
  (108 → 24 bp on a true weekly); pre-front time row with a mild front tie.
- Adaptive local-vol cap (3× max observed IV, floor 60%, cap 400%);
  controlled left-wing linear extrapolation (1.5× first-cell slope; a free
  variable when a var-swap quote binds); roughness regularization; convex
  wing OFF by default and confined to the unquoted tail when on.
- Tangent and transpose/adjoint actions for sensitivities; compiled batched
  tridiagonal marching (~6×) with a tested banded fallback and a memory
  budget for basis tensors (dense per-step storage can OOM); warm starts;
  early stopping.
- Matrix-free Gauss–Newton for the smooth mid objective when its
  prerequisites hold (fast kernel active, mid target); robust trust-region
  fallback otherwise (band objectives, var-swap fits, banded march).
- Output density from converged PDE reprices — never a finite difference of a
  drawn IV curve; quality metrics reprice on a refined operator because
  in-operator RMS hides operator error (11 vs 46 bp measured).
- Report per expiry: in-range vertex count, vega-floor incidence, PDE steps,
  optimizer evaluations, active bounds, timing attribution.

### 8.9 Variance swaps (Note 08)

- A var-swap quote is volatility plus included/excluded state, editable with
  undo/redo.
- Its penalty weight is an explicit percentage of the node's total quote
  information (default 10%).
- Each model uses its native route: LQD closed form/quadrature; arithmetic
  integration for SVI/MCS; static log-contract replication or the source-PDE
  route for local variance (the source-PDE value is local and robust to wing
  truncation).
- Never an expensive replication loop inside a Jacobian column (this
  happened; it is a certification case).
- Report model fair var-swap vol next to the quote.

### 8.10 Wings and calendar (Notes 09, 10)

- Distinguish one-curve constraints (butterfly, Lee) from two-curve
  comparisons (calendar); confine two-curve enforcement to common
  data-identified support unless the explicit tail contract is armed.
- Measure call-price/convex order or total-variance order on a shared grid;
  ATM monotonicity alone never certifies a calendar.
- Default symmetric treatment: fit independently, screen adjacent interfaces
  for identified violations, jointly Gauss–Newton-repair only
  violation-connected runs; clean ladders are exactly their independent fits;
  sequential mode is comparison/fallback.
- Report pre/post minimum gap and repair magnitude; publish-time wing
  projection onto the discrete arb-free set with the traded core pinned, and
  an audit that the projection introduced no calendar crossings (stored in
  the manifest).

### 8.11 Event and intraday clocks (Note 11)

- Scheduled events add explicit variance-day weights; optional one-year
  normalization; switching clocks preserves price and total variance; event
  time applies to fitting/annualization, never to American exercise or carry.
- Event auto-calibration: infer event weights from the observed term
  structure (the calendar as an inverse problem).
- Exact session clock for sub-day expiries: exchange sessions, holidays,
  half-days, settlement-instant valuation, configurable session/non-trading
  variance shares (defaults 6.5/24 and 1.0). Keep the 0DTE path off by
  default until its replay gates pass in the new environment.

### 8.12 Prior persistence (Note 13)

- Transport the saved prior to the current forward before comparing with
  data; prefer level-invariant shape operators over absolute strike anchors;
  persist **shape, not market level** — a true overnight ATM jump must pass
  through undamped (golden test).
- Seven modes: off, overlay, strike-gap, quote-operator, smile-factor,
  hybrid (default), graph-only; the mode is the single source of truth
  (legacy toggles migrate on load).
- Precision-ratio activation gate: a well-observed feature turns its prior
  row off **exactly**; gap exponent and per-operator required precision as in
  `SETTINGS_REFERENCE.md`; the strike-gap coverage-deficit gate is a separate
  concept.
- Operator vocabularies ATM/RR25/BF25/RR10/BF10/VarSwap and factor
  vocabularies level/skew/curvature/wings/VarSwap; collar sign convention is
  a desk choice.
- Expose per-operator prior value, observed precision, required precision,
  activation gap, active weight; optional data-only prepass to avoid
  contaminated activation measurements.
- The prior freshness ladder (saved → recent pre-close → bootstrap → flat)
  with explicit provenance; saving priors is part of the publish workflow and
  is certification-locked.

### 8.13 Observation filter (Note 15)

- State: ATM level/skew/curvature handles with covariance; measurement
  covariance from the calibrated fit Jacobian and stated quote noise
  (factor-based fallback retained as A/B).
- Predict by transporting the prior state and adding elapsed/process noise
  (30 bp/√day level, 0.02 skew, 0.05 curvature, plus transport noise 0.10 per
  unit |Δlog F|); distinguish absent data from contradictory data (residual
  inflation ρ = clip(χ²/(m−d), 1, cap)); innovation-gated adaptive process
  noise at 3σ (active mode gates the level row on a fit-free ATM probe).
- Per-handle updates by default; explicit reset after 96 h gaps or
  incompatible config changes, with a stated reason.
- Modes off/overlay/active; overlay touches display/state only; active adds
  the prediction as a single prior block in the calibration MAP — never a
  second pass on the same quotes.
- Report prediction, observation, innovation, gain, posterior, uncertainty,
  transport distance, contamination, reset reason. The ζ audit (standardized
  innovations) is the calibration instrument.
- Session clock available (share 0.60, non-trading 0.0): no calendar-clock
  process noise can calibrate a 30-minute step, an overnight, and a weekend
  simultaneously.

### 8.14 Spot and forward transport (Note 12)

- A spot/forward move refreshes displayed smiles, term structures, and
  local-vol coordinates analytically, without recalibration.
- Regimes: sticky moneyness, sticky strike (default), sticky local vol,
  sticky local-vol grid, custom SSR (default value 2.0); sign conventions
  fixed and tested; pre-transport and transported curves drawn together;
  explicit calibration re-anchors and clears transport state.
- SSR is an *input dial* for transport and an *output diagnostic* of the
  frozen-LV surface; a snapshot does not identify dynamics — that is the
  point of the note.

---

## 9. Graph extrapolation

The graph is the differentiating feature — extrapolating sparse observations
to the full universe of smiles across expiries and assets — and needs its own
product contract. Note 14 (three priors) is the primary spec; the message
supplement is the deep operator contract.

### 9.1 Common spine (all modes)

For each selected node $i = (\text{ticker}, T)$:

1. Resolve a transported prior baseline via the ladder: exact active prior →
   nearest-expiry prior → same-day bootstrap → flat-ATM last resort, with
   decreasing confidence and explicit provenance.
2. Calibrate only lit nodes.
3. Form the lit innovation $d_i = h_i^{\text{calibrated}} -
   h_i^{\text{transported prior}}$.
4. Solve three model-agnostic fields: ATM vol, ATM skew, ATM curvature.
5. Reconstruct absolute handles $h_i^+ = h_i^0 + \hat z_i$.
6. Retarget an arbitrage-safe slice backbone (LQD) to those handles.
7. Push handle covariance through the reconstructed smile for a functional
   band, including wing, tail-mass, and var-swap uncertainty where available,
   with the idiosyncratic ATM floor (~0.55× the node's trailing innovation
   RMS — strictly causal, mean-invariant, cold-start silent).
8. Compare with withheld/dark quotes only after the solve.

A component with no observation-supported route has zero innovation, broad
uncertainty, and an explicit unsupported/no-lit-path status.

### 9.2 Relationship semantics

Amplitude and confidence are separate dials, in canonical desk language
(**source/informer → target/receiver**):

- **beta** — how much of the informer's move reaches the receiver;
- **precision** — how reliable that relation is;
- optional **temporal persistence** — how long a target-specific residual
  survives (layered mode only).

Relation classes: calendar (same ticker across T, beta from maturity distance
with exponent α_T = 1), broad index, sector ETF, sector peer, custom. Support
per-handle beta, explicit or maturity-derived precision, class-level
amplitude presets (desk 1.0 default; learned presets selectable but never
silently), calendar policy overrides, and bulk block-rules that expand into
per-edge overrides.

### 9.3 Precision-message default

One Gaussian relation factor per configured relationship,
$p_{ij}\,(z_i - \beta_{ij} z_j)^2$, assembled into one global
information-form solve. The acceptance semantics (golden-locked three ways in
the reference implementation — against a brute-force Gaussian reference,
through production assembly, and through the API):

- one known informer maps to mean $\beta z$ regardless of confidence;
- two equally trusted messages average rather than add;
- independent precisions add;
- lower trust widens uncertainty without mechanically shrinking the mean;
- path betas multiply and relation variances accumulate along paths;
- one source is not double-counted through parallel graph paths;
- a dead/dark informer contributes nothing (zero dilution);
- baseline uncertainty enters exactly once;
- inconsistent beta cycles are diagnosable.

Daily-horizon bands can run narrow — always show held-out coverage next to
the band and keep the smooth-field comparison arm.

### 9.4 Smooth-field comparison mode

A directed/reversibilized smooth-increment prior with local zero-innovation
anchoring (κ), reach (η), and optional OT regularization (λ, source allowance
ν). Keep it as: a simpler prior, the rollback, the controlled comparison in
validation, and the wire default on the solve request (so replay and
byte-identity locks are stable). Its edge weights are NOT message precisions;
the modes encode different priors. Topology lesson: one-way informer→name
edges make names transient and silently strand dark nodes — reverse edges
with inverse beta restore recurrence.

### 9.5 Layered dynamic-harmonic mode (opt-in, experimental)

Implement only after the static modes are certified:

- reciprocal harmonic relations for calendar/peer interpolation; genuinely
  directed DAG arcs for index/ETF→name dependencies;
- exact zero reverse influence at a cut source; exact Dirichlet clamping of
  fresh certified observations; soft stale anchors; directed predictions
  entering the harmonic layer as unary information;
- persistent target-idiosyncratic residual updated only by actual target
  calibrations, with explicit half-life/process variance and a caller-owned
  stable residual-config identity (incidental config-hash identity silently
  purged state once — see pitfalls);
- mark decomposition into baseline + systematic + residual + harmonic with a
  consistency statistic χ;
- no look-ahead; no state writes during what-if/holdout; fractional now-day
  clock and observation ages on the scenario clock;
- residual store persisted and restored across restarts, corrupt-tolerant.

The measured lesson to preserve: intraday residual half-life ≈ 0.1 day shows
genuine persistence skill, but the layered carrier has not beaten static
messages; infinite persistence ("desk mode" memory) was the worst arm.

### 9.6 Graph product workflow

```text
Configure -> Preview -> Preflight -> Run -> Explain -> Validate
```

Required capabilities:

- selected lit/dark universe (ticker and node granularity);
- auto relationships plus sparse explicit overrides; ticker-by-ticker and
  expiry-ladder views;
- draft/active config lifecycle with metadata, activation (event-logged),
  revert, and diff; layered policy dials staged on the draft;
- non-persisting canonical what-if pulses;
- preflight blockers/warnings: empty universe, missing priors, unsupported
  components, extreme beta, precision outliers, directed cycles,
  conditioning, residual-config mismatch, stale residuals — a dry run over
  exactly the request Run would use;
- per-node prior/post handles, uncertainty, innovation, incoming confidence,
  provenance, decomposition, and exact attribution (attribution sums to the
  posterior move);
- current-day LOO comparison of transported prior vs smooth field vs
  messages; offline benchmark artifact linkage;
- ranked next-observation plan by closed-form exposure-weighted posterior
  variance reduction, with per-beneficiary breakdown;
- projection of reconstructed smiles onto a ticker local-vol surface;
- smooth-field reach autotune via production LOO.

---

## 10. Data, persistence, workflow, and governance

### 10.1 Provider abstraction

Start with a deterministic synthetic provider that exercises: European and
American options; multiple expiries including short-dated and sub-day;
dividends and nonzero carry; wide/tight, one-sided, crossed, stale, and
contradictory quotes; event smiles and W-shaped smiles; delayed and missing
nodes; zero-carry synthesized chains.

Then add adapters appropriate to the work environment. A provider exposes
**capabilities and health** (live/delayed/EOD, streaming, history depth,
symbol coverage, option-level NBBO availability) rather than pretending
everything supports everything. Lessons from the reference environment:

- Entitlements gate more than code does; probe and surface health, and make
  source switching a first-class top-bar action with automatic best-reachable
  selection at startup.
- Delayed tiers synthesize quotes (the zero-carry pin exists for this) and
  intermittently drop far-dated nodes.
- A full options NBBO firehose is ~100+ GB/day — historical capture campaigns
  should use snapshot/REST sampling with resumable chunked jobs, not raw
  firehose recording; long campaigns run detached from tool sessions.
- Bloomberg-style desktop APIs may be blocked account-side
  (workflow-review gates): build the adapter so its absence degrades to the
  other sources cleanly. BYO-entitlement is the settled product stance.

The active source and as-of selection are global, visible, and included in
every manifest. Support live, previous close, historical EOD, and captured
intraday replay when the provider can supply them.

### 10.2 Persistence

SQLite behind repository interfaces, with migrations, is sufficient
initially. Persist: raw/captured snapshots (or references to immutable
columnar files); named universes and expiry selections; market/carry settings
and dividend schedules; global fit/engine/view defaults (save/reset); quote
and var-swap edit sessions with undo/redo; prior snapshots and filter state;
graph draft/active configs and the layered residual store; fit artifacts,
diagnostics, hashes, history; publication manifests and append-only audit
events. Bulk historical quotes live in columnar files queried analytically.

Persisted-blob discipline: missing new fields coerce to defaults; legacy
fields migrate on load; out-of-range values clamp; corrupt blobs are
tolerated with a logged reset, never a crash. Note the operational corollary:
a persisted store pins explicit old defaults until re-saved — surface this in
the UI rather than silently overriding.

### 10.3 State and invalidation

An explicit serializable workspace/session object — not process globals
spread through routers. Each fit records: exact input snapshot identity;
carry/prior/event/graph versions; fit and engine settings versions; model
implementation version; output and certificate hashes. Deterministic replay
(≤1e-9, bitwise where promised) from these records is a governance
requirement, not a nicety.

Invalidation is scoped: one dividend schedule invalidates one ticker; chart
colors invalidate nothing; a graph config invalidates graph state but not
calibrated slices; LV-only settings never invalidate parametric fits; a
temporary spot transport marks display state, not the anchor fit.

### 10.4 Workflow semantics

Trigger-gated calibration in production:

- fetching spots transports surfaces (cheap, analytic);
- fetching options refreshes inputs and marks affected nodes stale;
- **Calibrate** does the expensive work; auto-calibrate is an explicit opt-in
  (the gated live server boots with it off; dev/test may default on);
- streaming sources may drive a faster book-fed refit loop (5 s cadence)
  independent of the REST refetch cadence;
- the previous successful artifact remains visible while stale;
- status distinguishes: no fit, stale fit, failed new fit, degraded market,
  current fit.

### 10.5 Quality and publishing

Quality reads committed artifacts; it must never trigger a hidden fit.

Per node/ticker report: data age and source health; fit RMS/max and quote
counts; convergence and certificate status; butterfly and calendar
diagnostics; prior/filter/graph provenance; local-vol health; stale/degraded
status; publish-ready boolean plus typed reasons.

Lifecycle:

```text
Captured -> Prepared -> Calibrated -> Reviewed -> Published
                                      \-> Rejected
Published -> Superseded or Recalled
```

Publishing creates a content-addressed manifest with parent lineage, embedded
inputs, the wing-projection calendar audit, and an append-only event. Export
CSV/JSON surfaces and a self-contained human-readable HTML report. Hard
publish blocks (HTTP 409 with typed reasons, checked before any manifest
persists): uncertified displayed slice; red-stale data; unresolved intrinsic
or calendar inconsistency; unsupported required dark component; named hard
failures. A block is never downgraded to a warning.

---

## 11. Service/API contract

`API_AND_UI_INVENTORY.md` lists the reference surface (107 routes) as a
completeness checklist; URL names are free. Rules:

- one naming convention throughout; requests validate ranges and units;
- errors carry stable machine codes plus desk-readable messages;
- long jobs return job identity and stream progress via SSE or WebSocket;
- read endpoints never mutate or fit; what-if/preflight/holdout never
  persist; write requests return the committed revision; concurrent commits
  use optimistic version checks;
- bulk graph payloads return summaries; full curves fetched on drill-in;
- generated OpenAPI docs stay on.

The UI may fall back to mock/synthetic data when the backend is unreachable,
behind an unmistakable MOCK badge.

---

## 12. User interface contract

A professional analytics workstation: dense but calm, fast,
keyboard-friendly, explicit about freshness and failure. The reference
layout (see `API_AND_UI_INVENTORY.md` §11 for the full inventory): a
persistent top bar (source + health, as-of, data-age pill, fetch actions,
calibrate/cancel + progress, stale count, prior actions, navigation) over
eight workspaces — **Parametric, Local Vol, Forwards, Options, Graph,
Quality, Universe, View** — each wrapped in its own error boundary so one
chart crash never takes the shell down, each keeping its session state across
tab switches.

Highlights the rebuild must preserve:

- Parametric sub-views: smile, stacked densities, log-quantile density, term
  structure, 3D surface, stacked total variance, table; five strike
  coordinate systems; zoom/pan/reset; quote-edit and var-swap-edit sessions
  with undo/redo; overlay set (prior, fit, pre-transport anchor, filtered,
  graph reconstruction).
- Options renders the whole `SETTINGS_REFERENCE.md` control surface with
  label, purpose, unit, range, default, activation condition, and
  invalidation note per knob; Apply / Save as default / Reset; no duplicate
  controls scattered in viewers.
- Graph three-pane shell (relationships/policy | canvas | inspector) with a
  bottom drawer (Preview, Diagnostics, Validation, Observation Plan); desk
  language first, raw precision behind an advanced toggle.
- Quality never fits on view load.
- Both light and dark themes with adequate contrast on overlay badges (a
  light-theme contrast pass was needed once; test both).

---

## 13. Performance contract

Measure on a quiet reference machine, report medians after warm-up; CI rails
are looser ceilings to catch algorithmic regressions, not scheduler noise.

| Operation | Design target | Portable CI rail |
|---|---:|---:|
| Warm LQD-6 slice fit, ~40 quotes | < 50 ms | < 350 ms |
| Warm 0DTE slice fit, ~19 quotes | < 50 ms (~20 ms measured) | < 150 ms |
| Graph build + posterior, 1,000 nodes / 25 observations | < 1 s | < 2.5 s |
| Local-vol forward solve, small 2-expiry grid | < 50 ms | < 250 ms |
| American chain conversion, ~80–200 quotes, compiled | single-digit ms | < 1.8 s incl. fallback allowance |
| Default affine LV fit, ~143 vertices / ~110 quotes | ~1 s | < 3 s |
| Heavy affine LV fit, ~255 vertices | ~2 s | < 6 s |
| Heavy matrix-free GN route | ~1.2 s | < 4 s |
| Belly certificate, 801 points | ~0.05 ms | n/a (inline) |

If the work environment is materially slower, establish a baseline and keep
the same regression *ratios*.

Engineering requirements: no network/database work inside residual
evaluation; vectorize quote-wide operations; cache quadrature nodes, basis
matrices, grids, prepared chains; analytic or matrix-free derivatives on hot
fits; reuse factorizations; avoid dense posteriors when only
columns/diagonals are needed; compile CRR and LV marching loops behind
tested fallbacks; warm-start recalibration; parallelize independent
nodes/tickers with the bounded pool; downsample display curves separately
from calculation grids; record prep/fit/PDE-value/PDE-sensitivity/assembly/
optimizer time attribution.

Never improve speed by removing diagnostics, weakening a grid without a
quality comparison, or returning before an independent certificate.

---

## 14. Testing and validation contract

The test suite is part of the product. For scale calibration: the reference
implementation holds ~1,470 backend tests (including 7 performance rails and
feature-off byte-identity locks), a component test suite, a browser smoke
run, 22 named certification cases, and a chunked/resumable historical
benchmark pack. The rebuild should converge on the same order.

### 14.1 Test layers

1. **Primitive unit tests** — pricing, inversion, clocks, interpolation,
   linear algebra.
2. **Equation goldens** — small deterministic cases derived independently
   from each note.
3. **Derivative tests** — analytic/tangent/adjoint vs central differences
   over randomized admissible inputs.
4. **Model property tests** — positivity, martingale mass, monotonicity,
   convexity, Lee limits, calendar order.
5. **Feature-off identity tests** — baseline unchanged when a feature is
   disabled (byte-identical where promised).
6. **Pipeline integration tests** — raw quotes → prepared → fits → views.
7. **State/cache tests** — scoped invalidation, restart round trips,
   migrations, stale behavior, no hidden mutation.
8. **API contract tests** — validation, schemas, errors, async jobs,
   what-if non-persistence.
9. **UI component and browser smoke tests** — all eight workspaces, workflow
   actions, error boundaries, both themes.
10. **Certification cases** — the frozen named failures
    (`PITFALLS_AND_ADJUDICATIONS.md` §1), each bound to explicit test locks,
    runnable by one command emitting JSON + client-readable HTML.
11. **Historical replay/backtest** — precision, skill, uncertainty
    calibration, speed.
12. **Performance rails** — the Section 13 table.

### 14.2 Mandatory golden cases

At minimum: normalized Black/IV round trips over tails and short maturities;
LQD benchmark smile recovery, martingale mass, non-negative density,
Jacobian audit; SVI raw/JW round trips inside the valid domain with explicit
boundary failure; the strict Lee fence, the classical negative-belly example,
one-shot repair, and publish block; the SVI adversarial battery on both
charts including deterministic <3-quote refusal; MCS event/W smile plus the
put-wing arb case; LV synthetic recovery, M-matrix/maximum-principle
behavior, short-expiry grid rescue, tangent/adjoint identity,
converged-reprice quality; American inversion, bid/ask preservation, cache
identity, confined wing repair, duplicate-strike survival; robust parity
forward under noisy discounts and the zero-carry pin; band residual zero
inside the band; var-swap equality through every native route on one
synthetic case; the phantom-calendar case and confined symmetric repair;
event-clock price preservation and exact intraday settlement; spot-transport
sign/regime cases; prior activation row exactly zero when data identifies
the feature, and the undamped true-jump case; filter gap-vs-contradiction
and active-MAP no-double-count; the full precision-message golden set
(single source, competing sources, unequal precision, multi-hop variance,
finite source uncertainty, disconnected component, dead informer, reciprocal
beta, cycle diagnostics, baseline-uncertainty-once); layered async A/B, zero
reverse influence, residual decay, hard/soft boundaries, no-look-ahead;
publish gates and manifest lineage.

### 14.3 Certification pack

One command runs the named-case matrix (each case = story + pytest locks)
and emits JSON plus a client-readable HTML report; a second command produces
the report from stored results. Seed the registry from
`PITFALLS_AND_ADJUDICATIONS.md` §1 and grow it: every future production bug
becomes a named case, not an anecdote.

### 14.4 Historical benchmark

When data entitlement permits, recapture rather than transfer fixtures. Use
a time-split design with: a volatility-spike regime, a sustained high-vol
regime, a low/stable regime; broad indexes, ETFs, liquid single names, and
an American-exercise-heavy set; one near-close snapshot per day plus a
smaller intraday asynchronous set. Record per fit: in-sample and held-out
RMS; max error and convergence status (and **split every aggregate by
convergence status** — the survivorship lesson); prep vs fit time; arbitrage
diagnostics; optimizer work; LV per-expiry quality/timing; graph skill vs
transported prior; standardized-residual mean/std and 50/80/95% coverage;
graph distance and relation class; wing RMS; full config provenance.
**Pre-register adoption gates before comparing new defaults**, assert that
ablation arms actually differ, and make long sweeps chunked/resumable.

---

## 15. Rebuild sequence

Ten phases, each ending in a working, tested vertical slice. Reading lists
name the pack's Markdown notes.

### Phase 0 — Contract and skeleton

Repository + dependencies; typed settings and domain objects; a
units/conventions document; decision log + requirements matrix; synthetic
provider schema; test/benchmark harness skeleton; health endpoint and UI
shell. *Exit:* snapshot and settings round-trip deterministically; every
requirement has a target module/test owner.

### Phase 1 — Pricing and one complete slice

Read `01_lqd_model_coordinates.md` and `07_calibration_objective_measure.md`.
Deliver the Black/IV core; prepared synthetic European quotes; the LQD fit
with analytic Jacobian; mid/band/haircut and equal/tv-density objectives;
smile/density/table API and a minimal Parametric viewer. *Exit:* equation
goldens, density/martingale checks, fit quality, LQD performance rail.

### Phase 2 — Market preparation

Read `05_deamericanization_stopping.md` and
`06_forwards_dividends_inference.md`. Deliver exact expiry/settlement
semantics; forward/discount/dividend policies + the zero-carry pin; the
American pricer and de-Americanization; quarantine/provenance;
prepared-chain caching; the Forwards workspace. *Exit:* European inputs
unchanged; American round trips pass; every dropped quote has a reason;
compiled and fallback paths agree.

### Phase 3 — Model breadth and certification

Read `02_svi_jw_rewrite.md`, `02_svi_jw_moments.md`,
`03_multicore_mcs_corrections.md`, `09_wings_last_quote.md`. Deliver the
SVI structural fit; MCS to two cores; wing diagnostics; the independent
belly certificate and publish block; model switching in the viewer. *Exit:*
the adversarial battery passes; no uncertified slice can publish.

### Phase 4 — Surface couplings

Read `08_varswap_representations.md`, `10_calendar_unnamed_martingale.md`,
`11_event_market_clock.md`, `12_spotvol_missing_derivative.md`. Deliver
variance swaps; symmetric calendar detection/repair; event and intraday
clocks; analytic spot transport; term/stacked-variance/surface views.
*Exit:* feature-off identity, price preservation, phantom-calendar test,
spot sign/regime goldens.

### Phase 5 — Local variance

Read `04_local_volatility_forward.md`. Deliver the affine representation;
forward PDE, sensitivities, calibration solvers; fast/fallback kernels; the
Local Vol workspace and diagnostics. *Exit:* synthetic recovery,
short-expiry rescue, adjoint identity, converged-reprice checks, all LV
rails.

### Phase 6 — Workflow, state, and quality

Deliver persistent workspace/repositories; edit sessions with undo/redo; the
background job manager and SSE progress; scoped invalidation and stale
states; Quality/Universe/Options/View workspaces; manifests, export,
publish/recall, audit log. *Exit:* restart/replay and migration tests; no
read endpoint fits; a failed new calibration preserves the prior good
artifact; UI smoke passes.

### Phase 7 — Priors and observation filtering

Read `13_prior_flat_directions.md` and `15_kalman_computed_trust.md`.
Deliver prior snapshots and the transport ladder; hybrid activation and
diagnostics; filter off/overlay/active; uncertainty overlays and state
lifecycle. *Exit:* a true level jump is not damped; gap and contradiction
differ; no evidence counted twice; off recovers the pre-feature result.

### Phase 8 — Static graph product

Read `14_graph_three_priors.md` and `14_graph_messages.md`. Deliver the
lit/dark graph universe; precision-message and smooth-field modes;
transported-prior innovations; functional bands + idio floor; config
lifecycle, preview, preflight, run, attribution, LOO, observation plan; the
Graph workspace. *Exit:* all graph goldens; unsupported-component behavior;
preflight non-mutation; current-day LOO; the 1,000-node rail; no dark-quote
leakage.

### Phase 9 — Dynamic graph and 0DTE research modes

Deliver the layered dynamic-harmonic mode with its causal residual store and
persistence; exact directed cuts and harmonic completion; intraday
asynchronous replay; research-grade 0DTE capture/replay and degraded mode.
*Exit:* async goldens and no-look-ahead; the mode stays opt-in unless a new
pre-registered benchmark in the new environment earns a change.

### Phase 10 — Certification and release

Deliver the complete named certification pack; historical benchmark/capture
commands; a performance dashboard; install/deploy documentation;
backup/recovery and retention policy; a client-readable model/limitations
report. *Exit:* one clean-machine command starts the product; one runs unit
tests; one runs certification; one produces the benchmark report.

---

## 16. Coding-model working protocol

Maintain per phase: `REQUIREMENTS.md` (requirement → implementation → test),
`DECISIONS.md` (non-obvious choices with alternatives and evidence),
`LIMITATIONS.md`, `PERFORMANCE.md` (hardware, data size, median, rail), a
small architecture diagram, and a runbook.

Start of phase: summarize the relevant note's invariants, equations, edge
cases, and acceptance examples; propose the smallest vertical slice; write
independent goldens; implement the pure numerical layer; add service/API/UI
only after the numerical layer is green. End of phase: focused tests, full
suite, the relevant rail, one real vertical workflow, updated traceability
and limitations, and a handoff with measured results.

Style: small single-purpose files; validated models/dataclasses; pure
functions and immutable inputs; dependency injection for providers/storage;
comments explain economic or numerical *reasons*, not syntax. Working with
Copilot-class context windows: feed one primary note (or one of its
sections) plus the relevant spec section at a time; the notes' section
structure was designed to be excerpted.

---

## 17. Decision rules for ambiguity

1. Preserve the economic invariant and the observable failure semantics.
2. Prefer structural guarantees over penalty tuning.
3. Prefer an independent certificate over trusting optimizer status.
4. Prefer model-native calculations over a forced uniform route.
5. Prefer a deterministic synthetic golden before a live-data example.
6. Prefer a feature flag with exact off behavior over irreversible coupling.
7. Prefer explicit provenance over a best guess.
8. Prefer a measured simple model over an unvalidated sophisticated one.
9. Never choose a default from in-sample RMS alone; include held-out error,
   convergence (split aggregates by it), arbitrage, uncertainty calibration,
   wings, and speed.
10. If an ambiguity can materially alter desk behavior, record it in the
    decision log and surface it as configuration.

---

## 18. Final completion checklist

### Numerical

- [ ] All three parametric models and local variance usable.
- [ ] Displayed slices carry independent static-arbitrage certificates.
- [ ] Calendar and wing authority correctly confined.
- [ ] American chains, carry, event time, var swaps, priors, and spot
      transport compose additively.
- [ ] Every derivative hot path has a numerical check.
- [ ] Performance rails pass on stated hardware.

### Graph

- [ ] Only lit calibrations influence the solve.
- [ ] Unsupported components stay at prior with explicit status.
- [ ] Precision-message semantics pass all goldens.
- [ ] Smooth-field comparison retained; modes not conflated.
- [ ] Bands are functional; held-out coverage reported; idio floor active.
- [ ] Preflight/what-if/LOO never write production state.
- [ ] Attribution sums to the posterior move.
- [ ] Dynamic mode, if present, is causal, persistent-store-backed, opt-in.

### Product

- [ ] Eight workspaces functional, not placeholders.
- [ ] Progress, cancellation, stale state, failure recovery work.
- [ ] Settings explicit, validated, documented, persistable, migratable.
- [ ] Quality never triggers calibration.
- [ ] Publish hard-blocks uncertified/stale/unsupported surfaces (409).
- [ ] Manifests, lineage, audit events, export, recall work.
- [ ] Offline synthetic mode works without credentials, behind a MOCK badge.

### Validation

- [ ] Equation goldens and adversarial cases pass.
- [ ] Feature-off identity tests pass (byte-identical where promised).
- [ ] Restart, migration, scoped-invalidation tests pass.
- [ ] API and browser smoke tests pass, both themes.
- [ ] Certification emits JSON and HTML from one command.
- [ ] Historical replay reports precision, uncertainty calibration, breaks,
      and speed with full provenance.

---

## 19. Suggested first prompt in the new environment

> Read `VOL_FITTER_CLEAN_ROOM_REBUILD.md` completely, then
> `SETTINGS_REFERENCE.md` and `PITFALLS_AND_ADJUDICATIONS.md`. We are
> performing a clean-room rebuild: do not ask for or assume access to another
> codebase. Create the Phase 0 deliverables only. Then read
> `notes/01_lqd_model_coordinates.md` and
> `notes/07_calibration_objective_measure.md` completely, extract their
> mathematical invariants and golden cases into the requirements matrix, and
> propose the smallest Phase 1 vertical slice. Do not implement later phases
> yet. Every completion claim must include tests and measured performance.

Continue phase by phase. Never ask a model to "build the whole Vol-Fitter"
in one conversation; the pack is structured so each phase fits a focused
context.


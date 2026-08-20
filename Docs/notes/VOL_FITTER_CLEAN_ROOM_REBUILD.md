# Vol-Fitter: clean-room rebuild specification

**Purpose:** rebuild a professional volatility-surface fitting application from
first principles, using the accompanying technical notes as the mathematical
specification.

**Target:** capability-equivalent to the reference application, but not a
source-compatible or visually identical clone.

**Version:** 2026-07-27.

**Audience:** a strong coding model and its human reviewer.

---

## 1. Instructions to the implementing model

You are building a new Vol-Fitter in a new repository. You do not have, and
must not request, the previous source tree. The accompanying notes and this
document are the complete design input.

The objective is not to guess how the old application was written. It is to
produce an independently designed application with comparable quant
capabilities, numerical quality, latency, auditability, and desk usability.
Choose clean interfaces and current, well-supported libraries. It is acceptable
to improve the architecture, API, storage model, or UI when the externally
visible capability and the mathematical contracts are preserved.

Work incrementally:

1. Read this document completely.
2. Read the relevant note completely before implementing its subject.
3. Convert every mathematical claim into an independent test before relying on
   it in a higher layer.
4. Keep a requirements-to-tests matrix and a short decision log in the new
   repository.
5. Deliver a working, tested vertical slice at the end of every phase below.
6. Never call a feature complete because its UI exists. Completion requires the
   numerical tests, failure semantics, diagnostics, and performance rail.
7. Never silently weaken a guarantee. Label it **structural**, **certified**,
   **measured**, or **experimental**.

This is a clean-room capability specification, not a request to reproduce
source text. Reference implementations inside the notes are mathematical
oracles and test aids; write new production code around independently chosen
interfaces.

---

## 2. The document pack

The preferred transfer pack is exactly this Markdown file plus the following
15 topic PDFs:

| Note | Preferred attachment | Subject |
|---:|---|---|
| 01 | `01_lqd_model.pdf` | LQD log-quantile-density smile |
| 02 | `02_svi_jw_rewrite.pdf` | SVI, SVI-JW, structural chart, certification |
| 03 | `03_multicore_siv.pdf` | Multi-Core Sigmoid / SIV |
| 04 | `04_local_volatility.pdf` | Piecewise-affine local variance and Dupire |
| 05 | `05_deamericanization.pdf` | American-to-European quote conversion |
| 06 | `06_forwards_dividends.pdf` | Forwards, discounts, dividends, carry |
| 07 | `07_calibration_objective.pdf` | Residuals, weights, bid/ask objectives |
| 08 | `08_variance_swaps.pdf` | Variance-swap targets and native routes |
| 09 | `09_wings_lee_bounds.pdf` | Wing behavior, Lee bounds, confinement |
| 10 | `10_calendar_arbitrage.pdf` | Calendar control and convex order |
| 11 | `11_event_variance_clock.pdf` | Event and intraday variance clocks |
| 12 | `12_spot_vol_dynamics.pdf` | Spot-move transport and SSR |
| 13 | `13_bayesian_prior_persistence.pdf` | Prior persistence and activation gates |
| 14 | `14_graph_three_priors.pdf` | Smooth, message, and layered graph priors |
| 15 | `15_kalman_filtering.pdf` | Temporal observation filtering |

If one extra attachment is acceptable, add `00_system_overview.pdf` as a
reader-friendly overview. It is helpful, but this file is intended to replace
it as the authoritative rebuild contract.

Do not substitute the older `02_svi_jw.pdf` for the rewrite. Do not send all
the lecture variants, intermediate roadmaps, or historical implementation
plans: they add context but also conflicting historical defaults.

### 2.1 Precedence when documents disagree

Use this order:

1. This rebuild specification for scope, product defaults, sequencing, and
   acceptance.
2. The preferred numbered note above for mathematics and numerical contracts.
3. A note's measured result over its earlier design intention.
4. A simpler, better-tested implementation over a speculative extension.

The most important current-default overrides are:

- LQD is the default parametric smile family.
- SVI uses its structural optimization chart by default, a strict Lee slope
  cap of 1.95, and a one-shot belly repair followed by certification.
- Multi-Core SIV is capped at two hat cores in normal product configuration.
- The normal graph UI defaults to **precision messages** at desk amplitude
  1.0. Smooth-field remains an explicit rollback/comparison mode.
- Layered dynamic-harmonic propagation remains opt-in and experimental. Its
  residual-memory mechanism is credible intraday, but the full layered carrier
  has not beaten static precision messages on the measured universe.
- The optimal-transport graph term is available but off by default.
- Observation filtering is off by default; overlay mode is the safe first
  activation.

---

## 3. Definition of success

The rebuild succeeds when a desk user can:

1. Select an asset/expiry universe and a market-data source.
2. Fetch or replay option chains, spots, carry inputs, and dividends.
3. Infer or override forwards and discounts with explicit provenance.
4. Prepare European and American chains robustly, retaining a reason for every
   quarantined quote.
5. Fit each smile with LQD, SVI, or Multi-Core SIV under mid, bid/ask-band, or
   haircut-band objectives.
6. Jointly fit a piecewise-affine local-variance surface through a forward
   Dupire PDE.
7. Apply variance-swap targets, calendar controls, event time, prior
   persistence, and optional observation filtering without hidden behavior.
8. Transport a calibrated surface after a spot move without recalibration.
9. Mark dark smiles from lit innovations through a configurable graph, with
   credible bands, provenance, attribution, preflight, what-if, and
   leave-one-out validation.
10. Inspect smiles, densities, term structures, local volatility, forwards,
    settings, graph relationships, universe membership, and publish quality in
    a professional UI.
11. Run calibration in the background with progress, cancellation, stale-state
    handling, scoped invalidation, and deterministic replay.
12. Export only surfaces that pass explicit data, fit, and arbitrage gates.
13. Re-run a certification suite and a historical benchmark pack that report
    precision, uncertainty calibration, breaks, and speed.

“Comparable” does not mean identical floating-point values, HTTP routes, or
pixels. It means the same economic questions can be answered, the central
mathematical invariants hold, failures are visible, and the latency is of the
same order.

---

## 4. Scope and priorities

### 4.1 Required for the first full release

- Forward-normalized option-pricing primitives and robust implied-volatility
  inversion.
- Synthetic offline provider plus at least one real provider adapter.
- Typed market snapshots, exact timestamps, settlement semantics, and as-of
  replay.
- Parity forwards/discounts, dividends, manual overrides, and provenance.
- American-option de-Americanization with a vectorized/compiled fast path and
  a deterministic fallback.
- The three parametric slice models: LQD, SVI, and Multi-Core SIV.
- The piecewise-affine local-variance surface.
- Mid, bid/ask, and haircut objectives; equal and time-value-density weights.
- Static-arbitrage diagnostics and publish certification.
- Calendar control, event variance time, variance-swap targets, and spot
  transport.
- Saved/transported priors and hybrid prior persistence.
- Static precision-message graph propagation, smooth-field comparison mode,
  functional uncertainty bands, graph attribution, and observation planning.
- Eight workspaces described in Section 12.
- Persistent settings, named universes, prior snapshots, fit history, edit
  sessions, publish manifests, and an audit/event log.
- Background calibration, progress, cancellation, stale-state semantics, and
  cached read-only views.
- Unit, golden, integration, UI, certification, and performance tests.

### 4.2 Required as an explicit advanced mode

- Local-vol variance-swap source-PDE route.
- Symmetric calendar repair of only violation-connected expiry blocks.
- Prior operator/factor diagnostics and optional two-pass activation.
- Observation-filter overlay and active one-stage MAP modes.
- Graph relationship configuration lifecycle: draft, preview, activate, diff,
  revert.
- Graph preflight, non-persisting what-if pulses, leave-one-out comparison, and
  “which node should be quoted next?” ranking.
- Research/replay-grade 0DTE clock and degraded-market behavior.
- A client-readable HTML certification report.

### 4.3 Experimental or opt-in

- Layered dynamic-harmonic graph mode with directed state, residual half-life,
  exact zero reverse influence, and harmonic completion.
- Smooth-field/message hybrid and optimal-transport regularization.
- Joint borrow/de-Americanization fixed point.
- Tapered extrapolated-region no-arbitrage enforcement.
- Full cross-handle covariance in prior and observation filters.
- Learned graph betas.

Experimental features must never be the only path to a publishable surface.
They must be removable without changing the baseline result except for
documented setting/version metadata.

### 4.4 Non-goals

- Exotic pricing or risk management.
- Order routing or trade execution.
- Forecasting dividends, borrow, volatility, or returns.
- Redistributing market data.
- A hyperscale multi-tenant platform in the first release.
- Bit-for-bit reproduction of an unavailable implementation.
- A neural model whose behavior cannot be explained or benchmarked against the
  mathematical models.

### 4.5 Reference starting profile

Use this as the first coherent configuration. The notes' parameter atlases
explain the controls and give wider ranges. A later benchmark may change a
default, but only through an explicit, recorded decision.

| Area | Starting choice |
|---|---|
| Parametric family | LQD |
| LQD | order 6; logistic endpoint chart; ridge \(10^{-6}\), power 1 |
| SVI | structural chart; penalty \(10^3\); Lee cap 1.95; belly repair on |
| Multi-Core SIV | 2 cores; amplitude ridge \(10^{-2}\); put-wing penalty on |
| Objective | mid; equal weights; haircut amount 0.005; band mid-anchor 0.05 |
| Variance swap | enabled; 10% information budget; static route initially |
| Calendar | enabled; symmetric violation-block repair; penalty \(10^6\) |
| Extrapolated-region enforcement | off; advisory diagnostics remain on |
| Event clock | enabled; one-year normalization off; intraday clock off |
| Prior persistence | hybrid; ATM/RR25/BF25/VarSwap operator set |
| Observation filter | off; Jacobian covariance when enabled; overlay first |
| Local-variance grid | delta strike grid; 12-node floor; at least 8 in-range vertices per expiry; 10 positive-time-node floor |
| Local-variance solver | positive variance; implicit time step; compiled fast kernel; early stop; matrix-free GN where eligible |
| Local-variance extras | front tie on; convex-wing penalty off; adaptive vol cap |
| Spot dynamics | sticky strike; custom SSR value 2.0 |
| Graph | precision messages; desk amplitude 1.0; \(\alpha_T=1\); functional band and idiosyncratic ATM floor on |
| Graph alternatives | smooth field available; OT weight 0; layered mode opt-in |
| Workflow | manual/trigger-gated calibration; local variance enabled; spots static/on-demand; option fetch on-demand |

---

## 5. System-wide invariants

These rules outrank convenience.

### 5.1 Normalization and units

- Use the expiry forward \(F_T\) and log-moneyness
  \(k=\log(K/F_T)\).
- Work in forward-normalized, undiscounted option prices inside the quant core.
- Treat total variance \(w\) as the clock-independent quantity implied by
  price.
- Keep calendar time \(t\), event/working variance time \(\tau\), market IV
  \(\sqrt{w/t}\), and working IV \(\sqrt{w/\tau}\) distinct.
- Store volatility as a decimal. One vol point is 0.01; one vol basis point is
  \(10^{-4}\).
- Use timezone-aware valuation, quote, last-trading, exercise, and settlement
  timestamps. Do not represent a sub-day expiry with an integer day count.
- Label every precision and variance with the units of the handle it governs.

### 5.2 Guarantees are graded

- **Structural:** guaranteed by the parameterization or numerical operator.
- **Certified:** checked independently on the finished artifact and used as a
  publish gate.
- **Measured:** reported but not guaranteed.
- **Experimental:** available only with an explicit label and comparison path.

Examples:

- LQD slice butterfly freedom: structural.
- Positive-local-variance Dupire surface: structural, subject to a verified
  monotone numerical scheme.
- SVI/MCS penalty satisfaction: measured; final dense-grid belly certificate:
  certified.
- Calendar order outside common identified support: measured unless a
  documented tail contract is active.
- Graph uncertainty calibration: measured by held-out standardized residuals
  and coverage.

### 5.3 Features are additive

Turning off a feature must recover the feature-absent calculation to floating
point tolerance, and where practical byte-identically. Lock this for:

- bid/ask bands and haircut;
- variance-swap targets;
- calendar coupling;
- event time;
- priors;
- observation filtering;
- graph betas/extra regularizers;
- local-vol fast kernels;
- extrapolated-region penalties.

Do not let a disabled feature alter initialization, cache keys, random seeds,
or iteration limits unless its absence itself is part of the key.

### 5.4 No hidden evidence

- Dark-node quotes do not influence the graph solve; they may score it only
  afterwards.
- A graph prediction is never recycled as a later market observation.
- A filtered posterior is never counted again as an independent quote.
- An active Kalman fit is one MAP problem, not “fit, filter, then fit again on
  the same evidence.”
- A saved prior carries an as-of timestamp and provenance.
- No unsupported graph component invents an innovation.

### 5.5 Fail visibly

Every failed or omitted datum needs a typed reason. At minimum distinguish:

- source unavailable or delayed;
- stale snapshot;
- crossed/one-sided market;
- below price/intrinsic tolerance;
- no parity forward;
- American inversion failure;
- implied-vol inversion failure;
- quarantined wing;
- no fittable market;
- optimizer non-convergence;
- uncertified butterfly;
- calendar failure;
- unsupported graph component;
- missing or stale prior.

Fallbacks may keep the application usable, but must never masquerade as fresh
market calibration.

---

## 6. Recommended architecture

The exact directory names are free. Preserve the dependency direction.

```text
pure numerical core
    -> market preparation and calibration
        -> stateful application services
            -> HTTP/streaming API
                -> web UI

persistence and audit sit beside services
backtest/certification call the same production core
```

A sensible new layout is:

```text
backend/
  volfit/
    core/            Black pricing, IV inversion, grids, linear algebra
    data/            providers, snapshots, symbols, expiry metadata
    market/          carry, forwards, dividends, de-Americanization
    models/          lqd, svi, mcs, local_variance
    calibration/     objectives, weights, calendars, priors, filters
    dynamics/        spot/forward transport
    graph/           smooth, messages, dynamic-harmonic, uncertainty
    services/        workflows, sessions, cache, quality, publishing
    api/             typed schemas and routers
    persistence/     SQLite repositories, migrations, manifests, event log
  tests/
  backtest/
frontend/
  src/
    workspaces/
    components/
    state/
    charts/
    api/
```

Keep the numerical packages independent of HTTP, UI, databases, and live data.
They should accept immutable arrays/domain objects and return typed results plus
diagnostics.

### 6.1 Suggested technology

- Python 3.11 or newer.
- NumPy and SciPy for numerical work.
- Numba or an equivalent compiled-array route for the CRR and local-vol hot
  loops, behind a tested fallback.
- FastAPI or another typed async HTTP framework.
- SQLite for a single-desk/single-tenant first release; use repository
  interfaces so another database can replace it.
- React + TypeScript or an equivalently mature typed web stack.
- SVG/canvas/WebGL charts chosen by data size; do not make charting libraries
  part of the quant core.
- Pytest and a browser-level test runner.

Avoid a distributed system until measurement requires it. A single service
with a bounded process pool is enough for desk scale.

### 6.2 Domain objects

Define typed, serializable objects early:

- `NodeKey`: ticker plus exact expiry/settlement identity.
- `MarketSnapshot`: source, as-of time, spot, raw quotes, data-age/provenance.
- `OptionQuote`: option type, strike, expiry metadata, bid, ask, sizes, quote
  time, exercise style.
- `CarryCurve`: discounts, forwards, dividends, borrow, source and confidence
  per component.
- `PreparedQuote`: normalized price/IV/total variance, \(k\), band, weight,
  original quote identity, and quarantine status.
- `FitSettings` and `EngineSettings`: versioned, validated, explicit units.
- `FittedSlice`: model family, parameters, curve, handles, diagnostics,
  uncertainty, input/settings hashes, timestamps, stale state.
- `FittedSurface`: ordered slices plus calendar/LV diagnostics.
- `PriorSnapshot`: fitted state, original forward, as-of, provenance.
- `HandleState`: ATM level/skew/curvature and covariance.
- `GraphRelation`: informer, receiver, relation class, per-handle beta,
  precision, semantics, version.
- `SurfaceManifest`: parent hashes, inputs, settings, model version, quality,
  lifecycle status.

Use stable content hashes for expensive derived artifacts. Never use mutable
object identity as a cache key.

---

## 7. End-to-end compute pipeline

Implement and test these stages independently:

```text
provider snapshot
  -> exact expiry/settlement clock
  -> forward, discount, dividends, optional borrow
  -> OTM selection and quote preparation
  -> American-to-European conversion where needed
  -> price/IV inversion, screening, quarantine, weights
  -> parametric slice fits and joint local-variance fit
  -> independent certificates and quality gates
  -> saved fit + manifest
  -> views and exports
  -> transported prior + lit innovations
  -> graph posterior for dark nodes
  -> reconstructed smile + uncertainty + validation
```

The data pull, carry inference, quote preparation, and fits need separate cache
keys. Changing a model penalty must not fetch data or rerun
de-Americanization. Changing one ticker's dividends must not invalidate other
tickers. A spot-only move should use analytic transport, not recalibration.

Background “Calibrate” should:

- snapshot the requested inputs and settings;
- fit lit slices in parallel;
- fit each enabled ticker's local-vol surface as a separate task;
- publish progress events;
- allow cancellation between bounded work units;
- atomically commit successful artifacts;
- leave the previous good fit available when a new fit fails;
- mark affected artifacts stale until replaced.

---

## 8. Quantitative requirements

The notes contain the derivations. This section defines their product role and
integration contract.

### 8.1 Shared pricing core

Implement vectorized normalized Black calls/puts, derivatives, total-variance
conversion, and robust IV inversion.

Tests must include:

- put-call parity in normalized units;
- zero-variance intrinsic limits;
- deep ITM/OTM and very short maturity;
- monotonicity in variance;
- finite-difference checks of analytic derivatives;
- price-to-IV-to-price round trips over a wide deterministic grid.

Prefer array-wide bracketing/Newton methods with safe fallbacks over one
high-level scalar root solver per quote.

### 8.2 Forwards, discounts, dividends, and carry

Follow Note 06:

- infer \(F_T\) and discount from put-call parity using robust, near-ATM-aware
  regression;
- make the forward level robust to noisy slope identification;
- clamp or reject implausible discount estimates explicitly;
- support proportional, discrete, mixed, and manual dividend policies;
- support a theoretical/manual forward override with provenance;
- recognize provider chains synthesized at zero carry and pin them rather than
  regressing invented carry;
- offer joint borrow/de-Americanization only behind a gated advanced setting.

Every downstream object must report which forward/discount it used.

### 8.3 De-Americanization and quote preparation

Follow Notes 05 and 07:

- apply de-Americanization only to American-style contracts;
- invert a CRR or equivalently validated American pricer to recover the
  European-equivalent price/IV;
- preserve the bid/ask structure rather than converting only a mid;
- use deterministic bracketing, explicit static bounds, and typed failure
  reasons;
- batch the chain and compile the hot loop where possible;
- cache by the complete content digest, carry inputs, tree controls, and clock;
- repair only the wing convexity defect that the method is authorized to
  repair; do not let a global repair move the ATM core;
- select the appropriate OTM side, apply price/intrinsic/vega screens, and
  retain every dropped row with its reason;
- use price/band-space authority near zero vega, especially for 0DTE.

### 8.4 Calibration objectives

All models must expose the same user choices:

- mid fit;
- bid/ask-band fit, zero residual inside the band;
- haircut band, shrinking each side toward the mid by a stated amount;
- optional small mid anchor in band modes;
- equal or time-value-density observation weights;
- weighted RMS and max error in stable, desk-readable units.

LQD and local variance should normally use vega-normalized price residuals.
SVI and MCS may use IV residuals. A shared product choice does not require a
single inappropriate internal residual for every model.

### 8.5 LQD

Follow Note 01. The implementation must provide:

- a valid risk-neutral density and martingale normalization by construction;
- stable logit/quantile coordinates and endpoint tail scales;
- Legendre body modes with regularization;
- prices, IVs, density, log-quantile density, quantiles, tail moments, and Lee
  slopes;
- exact ATM level, skew, and curvature;
- a well-conditioned optimization chart;
- analytic residual Jacobians;
- a native variance-swap route;
- optional calendar constraints in the appropriate LQD object.

LQD is the default parametric model and the preferred reconstruction backbone
for graph handle retargeting.

### 8.6 SVI and SVI-JW

Follow the Note 02 rewrite:

- implement raw SVI and exact JW handle maps with guarded domains;
- keep symmetric/degenerate chart singularities explicit;
- fit through the structural chart by default so all finite iterates respect
  positivity and the strict Lee fence;
- use a Lee slope cap of 1.95, not the mathematical boundary 2.0;
- implement analytic Jacobians for the chosen chart;
- evaluate the exact Durrleman butterfly functional from model derivatives;
- certify the finished displayed slice on a dense in-range grid (801 points is
  a suitable reference) with tolerance \(g\ge-10^{-4}\);
- if the first fit fails in the belly, allow one targeted repair fit and keep it
  only if the independent certificate passes;
- prevent an uncertified SVI slice from becoming a published mark.

### 8.7 Multi-Core SIV

Follow Notes 03 and 09:

- implement the six-parameter sigmoid base and zero-wing hat cores;
- treat the curve as the contract; hat decomposition need not be unique;
- expose zero, one, or two cores in normal configuration;
- seed deterministically and regularize hat amplitudes;
- measure Durrleman \(g\) beyond the observed wing;
- include the put-wing penalty/repair that targets the observed failure mode;
- keep input de-Americanization repair and output-model wing penalty as
  separate, composable protections.

### 8.8 Piecewise-affine local variance

Follow Note 04:

- unknowns are positive nodal local variances on a maturity-by-strike grid;
- interpolate piecewise-affinely;
- price with the forward Dupire PDE;
- make the production time step monotone and stable; fully implicit is the
  safe default;
- use a delta-aware strike grid, a \(\sqrt T\)-aware time grid, every lit expiry,
  and a minimum in-range strike-vertex count per expiry;
- include a pre-front time row and a mild front tie;
- use adaptive local-vol bounds, controlled left-wing extrapolation, and
  roughness regularization;
- provide tangent and transpose/adjoint actions for sensitivities;
- use compiled batched tridiagonal marching with a tested banded fallback;
- use warm starts and early stopping;
- use matrix-free Gauss-Newton for the smooth mid objective when its numerical
  prerequisites hold, and a robust trust-region fallback for non-smooth band
  objectives or unsupported routes;
- compute output density from converged PDE reprices, not a fragile finite
  difference of a drawn IV curve;
- report per-expiry vertex coverage, vega-floor incidence, PDE steps,
  optimizer evaluations, active bounds, and timing attribution.

Positive local variance and the verified forward scheme provide the structural
arbitrage story. Still independently test normalized call monotonicity and
convexity on converged reprices.

### 8.9 Variance swaps

Follow Note 08:

- store a variance-swap quote as volatility plus included/excluded state;
- weight its penalty as an explicit fraction/percentage of the node's total
  quote information;
- use each model's native route: LQD closed form/quadrature, arithmetic
  integration for SVI/MCS, static log-contract or source PDE for local
  variance;
- do not put an expensive replication loop inside every Jacobian column;
- report model fair variance-swap vol next to the quote.

### 8.10 Calendar arbitrage and wings

Follow Notes 09 and 10:

- distinguish one-curve constraints from two-curve comparisons;
- confine two-curve enforcement to common, data-identified support unless an
  explicit tail contract is enabled;
- measure call-price/convex-order or total-variance order on a shared grid;
- default to symmetric treatment of expiries: fit independently, detect
  identified adjacent violations, then jointly repair only connected violating
  runs;
- retain a sequential mode only as a comparison/fallback;
- report the pre/post minimum gap and repair magnitude;
- never claim that ATM monotonicity alone certifies a calendar.

### 8.11 Event and intraday variance clocks

Follow Note 11:

- scheduled events add explicit variance-day weights;
- optionally normalize the one-year weight budget;
- preserve option price/total variance when switching clocks;
- apply event time to fitting/annualization, not to American exercise or carry;
- support an exact session clock for sub-day expiries with exchange sessions,
  holidays, half-days, and configurable session/non-trading variance shares;
- keep the 0DTE path off by default until its replay gates pass in the new
  environment.

### 8.12 Prior persistence

Follow Note 13:

- transport the saved prior to the current forward before comparing it with
  data;
- prefer level-invariant shape operators/factors over absolute strike anchors;
- support off, overlay, strike-gap, quote-operator, smile-factor, hybrid, and
  graph-only modes;
- make hybrid the normal starting mode;
- implement a precision-ratio activation gate: a well-observed feature turns
  its prior row off exactly;
- keep the strike-gap coverage-deficit gate conceptually separate;
- support ATM, RR25, BF25, optional RR10/BF10, variance swap, and
  level/skew/curvature factor vocabularies;
- expose per-operator prior value, observed precision, required precision,
  activation gap, and active weight;
- optionally use a data-only prepass to avoid contaminated activation
  measurements;
- persist shape, not market level, so a real overnight ATM jump is not damped.

### 8.13 Observation filter

Follow Note 15:

- state is the ATM level/skew/curvature handle vector with stated covariance;
- measurement covariance should normally come from the calibrated fit
  Jacobian and the stated quote noise; retain a factor-based fallback;
- predict by transporting the prior state and adding elapsed/process noise;
- distinguish absent data from contradictory noisy data;
- update per handle by default unless a full covariance route proves stable;
- include residual inconsistency inflation and innovation-gated adaptive
  process noise;
- reset explicitly after stale gaps or incompatible configuration changes;
- provide off, overlay, and active modes;
- overlay updates display/state only;
- active adds the prediction as a single prior block in the calibration MAP;
- report prediction, observation, innovation, gain, posterior, uncertainty,
  transport distance, contamination, and reset reason.

Default to off. Enable overlay first in a new environment.

### 8.14 Spot and forward transport

Follow Note 12:

- a spot/forward move refreshes displayed parametric smiles, term structures,
  and local-vol coordinates analytically without recalibration;
- support sticky moneyness, sticky strike, sticky local vol, sticky local-vol
  grid, and a custom SSR;
- keep sign conventions fixed and tested;
- draw the pre-transport and transported curves together;
- a later explicit calibration re-anchors the surface and clears the temporary
  transport state.

---

## 9. Graph extrapolation

The graph is the differentiating feature and needs its own product contract.

### 9.1 Common spine

For each selected node \(i=(\text{ticker},T)\):

1. Resolve a transported prior baseline from exact active prior, nearest-expiry
   prior, same-day bootstrap, or flat-ATM last resort, with decreasing
   confidence and explicit provenance.
2. Calibrate only lit nodes.
3. Form the lit innovation
   \(d_i=h_i^{\text{calibrated}}-h_i^{\text{transported prior}}\).
4. Solve three model-agnostic fields: ATM vol, ATM skew, ATM curvature.
5. Reconstruct absolute handles \(h_i^+=h_i^0+\hat z_i\).
6. Retarget an arbitrage-safe slice backbone to those handles.
7. Push handle covariance through the reconstructed smile for a functional
   band, including wing, tail-mass, and variance-swap uncertainty where
   available.
8. Compare with any withheld/dark quotes only after the solve.

A component with no observation-supported route has zero innovation, broad
uncertainty, and an explicit `noLitPath`/unsupported status.

### 9.2 Relationship semantics

Keep amplitude and confidence separate:

- beta: how much of the informer's move reaches the receiver;
- precision: how reliable that relation is;
- optional temporal persistence: how long an observed target-specific residual
  survives.

Use canonical language everywhere: **source/informer → target/receiver**.

### 9.3 Precision-message default

The default static operator uses one Gaussian relation factor per configured
relationship:

\[
p_{ij}(z_i-\beta_{ij}z_j)^2.
\]

Assemble all factors into one global information-form solve. This guarantees:

- one known informer maps to mean \(\beta z\) regardless of confidence;
- two equally trusted messages average rather than add;
- independent precisions add;
- lower trust widens uncertainty without mechanically shrinking the mean;
- path betas multiply and relation variances accumulate;
- one source is not counted as independent once per graph path;
- inconsistent beta cycles are diagnosable.

Provide relation classes for calendar, broad index, sector ETF, sector peer,
and custom. Support per-handle beta, explicit precision or
maturity-distance-derived precision, class-level amplitude presets, and
calendar policy overrides.

Current starting controls:

- calendar beta exponent \(\alpha_T=1\);
- desk amplitude 1.0;
- learned amplitude presets may be exposed but not silently selected;
- precision messages are the normal UI default;
- daily-horizon bands may be too narrow, so always show held-out coverage and
  retain smooth-field comparison.

### 9.4 Smooth-field comparison mode

Retain a directed/reversibilized smooth increment prior with local
zero-innovation anchoring and optional OT regularization. It is valuable as:

- a simpler prior;
- a rollback;
- a controlled comparison in validation;
- a smoother for some neighbor-supported calendar problems.

Do not reinterpret its edge weights as the direct message precisions above.
The modes encode different priors.

### 9.5 Layered dynamic-harmonic mode

Implement only after the static modes are certified:

- reciprocal harmonic relations for calendar/peer interpolation;
- genuinely directed DAG influence arcs for index/ETF-to-name dependencies;
- exact zero reverse influence at a cut source;
- persistent target idiosyncratic residual updated only by actual target
  calibrations;
- explicit residual half-life/process variance;
- exact Dirichlet clamping of fresh certified observations;
- soft stale anchors;
- directed predictions entering the harmonic layer as unary information;
- mark decomposition into baseline + systematic + residual + harmonic;
- no look-ahead and no state writes during what-if/holdout solves.

Keep this mode opt-in. The measured lesson to preserve is nuanced: a finite
intraday residual half-life around 0.1 day showed genuine persistence skill,
but static precision messages still beat the full layered carrier on the
tested ETF universe. Never use infinite residual persistence as a default.

### 9.6 Graph product workflow

The graph workspace should follow:

```text
Configure -> Preview -> Preflight -> Run -> Explain -> Validate
```

Required capabilities:

- selected lit/dark universe;
- auto relationships plus sparse explicit overrides;
- ticker-by-ticker and expiry-ladder views;
- draft/active config with metadata, activation, revert, and diff;
- non-persisting canonical what-if pulses;
- preflight blockers/warnings for empty universe, missing priors,
  unsupported components, extreme beta, precision outliers, bad cycles, and
  conditioning;
- per-node prior/post handles, uncertainty, innovation, incoming confidence,
  provenance, and exact attribution;
- current-day LOO comparison of transported prior, smooth field, and messages;
- offline benchmark artifact link;
- ranked next-observation plan using closed-form posterior variance reduction;
- projection of reconstructed smiles to a ticker local-vol surface.

---

## 10. Data, persistence, workflow, and governance

### 10.1 Provider abstraction

Start with a deterministic synthetic provider that exercises:

- European and American options;
- multiple expiries including short-dated;
- dividends and nonzero carry;
- wide/tight, one-sided, crossed, stale, and contradictory quotes;
- event smiles and W-shaped smiles;
- delayed and missing nodes.

Then add adapters appropriate to the work environment. A provider must expose
capabilities and health rather than pretending every source supports live
streaming, full history, non-US symbols, or option-level NBBO.

The active source and as-of selection are global, visible, and included in
every manifest. Support live, previous close, historical EOD, and captured
intraday replay when the provider can supply them.

### 10.2 Persistence

SQLite is sufficient initially. Use migrations and repository interfaces.
Persist:

- raw/captured snapshots or references to immutable columnar files;
- named universes and expiry selections;
- market/carry settings and dividend schedules;
- global fit/engine/view defaults;
- quote and variance-swap edit sessions with undo/redo;
- prior snapshots and filter state;
- graph draft/active relationship configurations;
- fit artifacts, diagnostics, input/settings hashes, and history;
- publication manifests and audit events.

Large historical quote tables should live in Parquet or another columnar form,
queried analytically without loading the entire history into application
memory.

### 10.3 State and invalidation

Use an explicit serializable workspace/session object rather than process
globals spread through routers.

Each fit records:

- exact input snapshot identity;
- carry/prior/event/graph versions;
- relevant fit and engine settings versions;
- model implementation version;
- output and certificate hashes.

Invalidation is scoped. Editing one dividend schedule invalidates that ticker,
not the whole universe. Changing chart colors invalidates nothing. Changing a
graph config invalidates graph state but not calibrated slices. A temporary
spot transport marks a display state but not the underlying anchor fit.

### 10.4 Workflow semantics

Production should default to trigger-gated calibration:

- fetching spots transports surfaces;
- fetching options refreshes inputs and marks affected nodes stale;
- “Calibrate” performs the expensive work;
- an explicit auto-calibrate mode may refit after changes;
- the previous successful artifact remains visible while stale;
- status distinguishes no fit, stale fit, failed new fit, degraded market, and
  current fit.

Use a bounded process pool for independent slice/ticker fits. A reasonable
default is `min(cpu_count - 1, 8)`, with serial mode available for tests and
deterministic diagnosis.

### 10.5 Quality and publishing

Quality reads committed artifacts; it must never trigger a hidden fit.

Per node/ticker report:

- data age and source health;
- fit RMS/max error and quote count;
- convergence and certificate status;
- butterfly and calendar diagnostics;
- prior/filter/graph provenance;
- local-vol surface health;
- stale/degraded status;
- publish-ready boolean plus reasons.

Use a lifecycle such as:

```text
Captured -> Prepared -> Calibrated -> Reviewed -> Published
                                      \-> Rejected
Published -> Superseded or Recalled
```

Publishing creates a content-addressed manifest with parent lineage and an
append-only event. Export CSV/JSON surfaces and a human-readable HTML report.
An uncertified displayed slice, red-stale data, an unsupported required node,
or a named hard failure blocks publish rather than becoming a warning.

---

## 11. Service/API contract

The exact URL names are free. Provide typed, versioned resource groups for:

- data sources and health;
- as-of selection;
- universe, symbols, expiries, and lit/dark state;
- market settings, carry, forwards, dividends;
- fit and engine settings/defaults;
- smile data, density, table, and quote/variance-swap edits;
- surface and local-vol calibration/views;
- term structure and events;
- spot state and scenario transport;
- priors and filter diagnostics;
- calibration jobs, progress stream, and cancellation;
- graph relations/config lifecycle, preflight, solve, node drill-in,
  validation, and observation plan;
- quality, export, publish history, and recall.

API rules:

- schemas use one naming convention consistently;
- requests validate ranges and units;
- errors have stable machine codes plus desk-readable messages;
- long jobs return job IDs and stream progress via SSE or WebSocket;
- read endpoints do not mutate or fit;
- what-if, preflight, and holdout requests never persist state;
- write requests return the committed revision/version;
- concurrent commits use optimistic version checks or an equivalent guard;
- bulk graph payloads return summaries; fetch full curves on drill-in.

The UI may use mock/synthetic data when the backend is unavailable, but it must
display an unmistakable mock/offline badge.

---

## 12. User interface contract

The visual design may be new. It should feel like a professional analytics
workstation: dense but calm, fast, keyboard-friendly, and explicit about
freshness and failure.

Use a persistent top bar for:

- data source and health;
- as-of time;
- fetch spots/options;
- calibrate/cancel and progress;
- stale count;
- prior actions;
- global navigation.

Use these eight workspaces.

### 12.1 Parametric

- Ticker and expiry selectors.
- Model and current settings summary.
- Quote bands with include/exclude/amend/reset and undo/redo.
- Prior, current fit, pre-transport anchor, filtered overlay, and graph
  reconstruction where relevant.
- Variance-swap quote editor.
- Spot-move controls and regime.
- Stale/no-fit/degraded/certificate state.
- Subviews: Smile, stacked densities, log-quantile density, term structure,
  3D surface, stacked total variance, and table.
- Strike coordinates: log-moneyness, strike, percent ATM, delta, normalized.
- Charts support wheel zoom, drag pan, and reset.

### 12.2 Local Vol

- Joint surface calibration status and per-expiry diagnostics.
- Smile/reprice view, density, term, local-vol heatmap, 3D IV surface, table.
- Grid/solver settings live in the global Options workspace, not duplicated.
- Clear disable state when local-vol calibration is off.

### 12.3 Forwards

- Active, parity, theoretical, and manual forwards by maturity.
- Discount/carry provenance and confidence.
- Dividend ex-date markers and schedule editor.
- Forward curve and table.
- Clear warning when carry is unidentified or an American correction is
  material.

### 12.4 Options

Expose every meaningful coefficient with:

- label and plain-language purpose;
- unit;
- valid range;
- default;
- activation condition;
- whether it invalidates/calibrates anything.

Group model controls, objectives, arbitrage/calendar, variance swaps/events,
prior/filter, local variance, graph, dynamics, and workflow. Support Apply,
Save as default, and Reset. Do not scatter duplicate controls through viewers.

### 12.5 Graph

Use a three-pane shell or equivalent:

- left: relationships and policy;
- center: node/edge canvas;
- right: selected-node/edge inspector;
- bottom drawer: Preview, Diagnostics, Validation, Observation Plan.

Prefer desk language (“relationship uncertainty”, “A informs B”) over solver
jargon. Keep raw precision available behind an advanced toggle.

### 12.6 Quality

- Headline ready/stale/arbitrage/RMS tiles.
- Per-ticker rollup including local-vol health.
- Filterable per-node exception table.
- Publish/export controls and manifest/report history.
- Never fit on view load.

### 12.7 Universe

- Provider symbol search.
- Per-ticker expiry selection with expiry-type labels.
- Lit/dark matrix.
- Named universe save/load/delete.
- Clear selected-node count and expected calibration load.

### 12.8 View

- Dark/light/high-contrast/warm schemes.
- Contrast/brightness.
- Expiry-label and time-axis preferences.
- Client-side preview, explicit save/reset.

Every workspace gets a local error boundary so one chart cannot white-screen
the entire application.

---

## 13. Performance contract

Measure on a quiet reference machine, report medians after warm-up, and use
looser CI ceilings to catch algorithmic regressions rather than scheduler
noise.

| Operation | Design target | Portable CI rail |
|---|---:|---:|
| Warm LQD-6 slice, ~40 quotes | < 50 ms | < 350 ms |
| Warm 0DTE slice, ~19 quotes | < 50 ms | < 150 ms |
| Graph build + posterior, 1,000 nodes / 25 observations | < 1 s | < 2.5 s |
| Local-vol forward solve, small 2-expiry grid | < 50 ms | < 250 ms |
| American chain conversion, ~80–200 quotes, compiled | single-digit ms preferred | < 1.8 s including fallback allowance |
| Default affine local-vol fit, ~143 vertices / ~110 quotes | about 1 s | < 3 s |
| Heavy affine local-vol fit, ~255 vertices | about 2 s | < 6 s |
| Heavy matrix-free GN route | about 1.2 s | < 4 s |

These are order-of-magnitude requirements, not promises about unknown work
hardware. If the environment is materially slower, establish a baseline and
retain the same regression ratios.

Engineering requirements:

- no network or database work inside numerical residual evaluation;
- vectorize quote-wide operations;
- cache quadrature nodes, basis matrices, grids, and prepared chains;
- provide analytic or matrix-free derivatives on hot fits;
- reuse factorization where the operator is unchanged;
- avoid full dense posterior matrices when only selected columns/diagonals are
  needed;
- compile CRR and local-vol marching hot loops with a tested fallback;
- warm-start recalibration;
- parallelize independent nodes/tickers with bounded processes;
- downsample display curves separately from calculation grids;
- record prep, fit, PDE value, PDE sensitivity, assembly, and optimizer time.

Never improve speed by removing diagnostics, weakening a grid without a quality
comparison, or returning before an independent certificate.

---

## 14. Testing and validation contract

The test suite is part of the product.

### 14.1 Test layers

1. **Primitive unit tests:** Black pricing, IV inversion, clocks, interpolation,
   linear algebra.
2. **Equation goldens:** small deterministic cases derived independently from
   each note.
3. **Derivative tests:** analytic/tangent/adjoint against central differences
   over randomized admissible inputs.
4. **Model property tests:** positivity, martingale mass, monotonicity,
   convexity, Lee limits, calendar order.
5. **Feature-off identity tests:** baseline result unchanged when a feature is
   disabled.
6. **Pipeline integration tests:** raw quotes to prepared quotes to fits to
   views.
7. **State/cache tests:** scoped invalidation, restart round trips, migration,
   stale behavior, no hidden mutations.
8. **API contract tests:** validation, response schema, errors, async jobs.
9. **UI component and browser smoke tests:** all eight workspaces, workflow
   actions, and chart/error boundaries.
10. **Certification cases:** frozen named production-like failures.
11. **Historical replay/backtest:** precision, skill, uncertainty calibration,
    and speed.
12. **Performance rails:** the table in Section 13.

### 14.2 Mandatory golden cases

At minimum:

- normalized Black/IV round trip over tails and short maturities;
- LQD benchmark smile recovery, martingale mass, non-negative density, and
  Jacobian;
- SVI raw/JW round trips inside the valid domain and explicit boundary failure;
- SVI strict Lee fence, classical negative-belly example, one-shot repair, and
  publish block;
- MCS event/W-shaped smile plus put-wing arb case;
- local-vol synthetic surface recovery, M-matrix/maximum-principle behavior,
  short-expiry grid rescue, tangent/adjoint identity, and converged reprice
  quality;
- American price inversion, bid/ask preservation, cache identity, and confined
  wing repair;
- robust parity forward under noisy discounts and zero-carry synthetic feed;
- bid/ask residual zero inside band and weight normalization;
- variance-swap equality through every native route on a common synthetic case;
- phantom-calendar case and confined repair;
- event-clock price preservation and exact intraday settlement;
- spot-transport sign/regime cases;
- prior activation row exactly zero when the data identifies the feature;
- observation-filter gap versus contradiction and active-MAP no-double-count;
- precision-message single source, competing sources, unequal precision,
  multi-hop variance, finite source uncertainty, disconnected component,
  dead informer, reciprocal beta, cycle diagnostics, and baseline uncertainty
  entering once;
- layered asynchronous A/B sequence, zero reverse influence, residual decay,
  hard/soft boundary behavior, and no-look-ahead;
- publish gate and manifest lineage.

### 14.3 Certification pack

Turn the important failures into named cases, not anecdotes:

- Lee cap exactly on the broken boundary;
- negative SVI belly despite clean wings;
- six-day local-vol grid undercoverage;
- local-vol convex wing applied outside its authority;
- global de-Americanization repair moving ATM;
- noisy discount regression shifting the smile;
- variance-swap computation accidentally placed inside the Jacobian;
- invented MCS put wing;
- phantom calendar flattening a far expiry;
- prior anchor damping a true level jump;
- graph topology producing exactly zero skill through disconnection;
- graph ablation arms accidentally identical through state invalidation;
- filter cross-handle blow-up;
- stale data incorrectly marked publish-ready;
- unsupported dark component;
- 0DTE no-parity/no-fittable-market degraded mode;
- a browser render failure isolated by a workspace error boundary.

One command should execute the certification matrix and emit JSON plus a
client-readable HTML report.

### 14.4 Historical benchmark

When data entitlement permits, recapture rather than transfer old fixtures.
Use a time-split design with:

- a volatility spike regime;
- a sustained high-vol regime;
- a low/stable regime;
- broad indexes, ETFs, liquid single names, and at least one
  American-exercise-heavy set;
- one near-close snapshot per day plus a smaller intraday asynchronous set.

Record per fit:

- in-sample and held-out RMS;
- max error and convergence;
- quote preparation versus fit time;
- arbitrage diagnostics;
- optimizer work;
- local-vol per-expiry quality and timing;
- graph skill versus transported prior;
- standardized residual mean/std and 50/80/95% coverage;
- graph distance and asset/relation class;
- wing RMS;
- all active model/config provenance.

Pre-register adoption gates before comparing new defaults.

---

## 15. Rebuild sequence

Do not attempt the entire application in one pass.

### Phase 0 — Contract and skeleton

Deliver:

- repository and dependency setup;
- typed settings and domain objects;
- units/conventions document;
- decision log and requirements matrix;
- synthetic provider schema;
- test and benchmark harness skeleton;
- minimal service health endpoint and UI shell.

Exit gate: a snapshot and settings object round-trip deterministically, and
every future requirement has a target module/test owner.

### Phase 1 — Pricing and one complete slice

Read Notes 01 and 07.

Deliver:

- Black/IV core;
- prepared synthetic European quotes;
- LQD fit with analytic Jacobian;
- mid/band/haircut and equal/tv-density objectives;
- smile/density/table API and minimal Parametric viewer.

Exit gate: equation goldens, non-negative density/martingale checks, fit
quality, and LQD performance rail.

### Phase 2 — Market preparation

Read Notes 05 and 06.

Deliver:

- exact expiry/settlement semantics;
- forward/discount/dividend policies;
- American pricer and de-Americanization;
- quarantine/provenance;
- prepared-chain caching;
- Forwards workspace.

Exit gate: European inputs are unchanged, American round trips pass, every
dropped quote has a reason, and the compiled/fallback paths agree.

### Phase 3 — Model breadth and certification

Read Notes 02, 03, and 09.

Deliver:

- SVI/JW structural fit;
- MCS up to two cores;
- wing diagnostics;
- independent belly certificate and publish block;
- model switching in the Parametric viewer.

Exit gate: all adversarial cases pass; no uncertified slice can be published.

### Phase 4 — Surface couplings

Read Notes 08, 10, 11, and 12.

Deliver:

- variance swaps;
- symmetric calendar detection/repair;
- event and intraday clocks;
- analytic spot transport;
- term/stacked variance/surface views.

Exit gate: feature-off identity, price preservation, phantom-calendar test,
and spot sign/regime goldens.

### Phase 5 — Local variance

Read Note 04.

Deliver:

- affine local-variance representation;
- forward PDE, sensitivities, calibration solvers;
- fast/fallback kernels;
- local-vol workspace and quality diagnostics.

Exit gate: synthetic recovery, short-expiry rescue, adjoint identity,
arbitrage/reprice checks, and all local-vol performance rails.

### Phase 6 — Workflow, state, and quality

Deliver:

- persistent workspace/repositories;
- edit sessions and undo/redo;
- background job manager and progress stream;
- scoped invalidation and stale states;
- Quality/Universe/Options/View workspaces;
- manifests, export, publish/recall, audit log.

Exit gate: restart/replay and migration tests, no read endpoint fits, failed new
calibration preserves the prior good artifact, and UI smoke passes.

### Phase 7 — Priors and observation filtering

Read Notes 13 and 15.

Deliver:

- prior snapshots and transport hierarchy;
- hybrid activation and diagnostics;
- filter off/overlay/active modes;
- uncertainty overlays and state lifecycle.

Exit gate: true level jump is not damped by shape persistence, gap and
contradiction behave differently, no evidence is counted twice, and off mode
recovers the pre-feature result.

### Phase 8 — Static graph product

Read Note 14.

Deliver:

- selected lit/dark graph universe;
- precision-message and smooth-field modes;
- transported-prior innovations;
- functional bands and idiosyncratic ATM floor;
- graph config lifecycle, preview, preflight, run, attribution, LOO, and
  observation plan;
- graph workspace.

Exit gate: all graph goldens, unsupported-component behavior, preflight
non-mutation, current-day LOO, 1,000-node performance, and no dark-quote
leakage.

### Phase 9 — Dynamic graph and 0DTE research modes

Deliver:

- layered dynamic-harmonic mode;
- causal residual store and half-life;
- exact directed cuts and harmonic completion;
- intraday asynchronous replay;
- research-grade 0DTE capture/replay and degraded mode.

Exit gate: asynchronous goldens and no-look-ahead; retain opt-in status unless
the new environment's pre-registered benchmark earns a change.

### Phase 10 — Certification and release

Deliver:

- complete named certification pack;
- historical benchmark/capture commands;
- performance dashboard;
- install/deploy documentation;
- backup/recovery and data-retention policy;
- client-readable model/limitations report.

Exit gate: one clean-machine command starts the product; one command runs unit
tests; one runs certification; one produces the benchmark report.

---

## 16. Coding-model working protocol

For each phase, the coding model should create and maintain:

- `REQUIREMENTS.md`: each requirement mapped to implementation and test.
- `DECISIONS.md`: only non-obvious choices, with alternatives and evidence.
- `LIMITATIONS.md`: known gaps and experimental features.
- `PERFORMANCE.md`: representative hardware, data size, median, and rail.
- a small architecture diagram and runbook.

At the start of a phase:

1. Summarize the relevant note's invariants, equations, edge cases, and
   acceptance examples.
2. Propose the smallest vertical slice.
3. Write independent golden tests.
4. Implement the pure numerical layer.
5. Add service/API/UI only after the numerical layer is green.

At the end of a phase:

1. Run focused tests, then the full suite.
2. Run the relevant performance rail.
3. Exercise one real vertical workflow.
4. Update traceability and limitations.
5. Produce a concise handoff with measured results, not “should work.”

Avoid files that mix unrelated responsibilities. Prefer explicit dataclasses or
validated models, pure functions, immutable inputs, dependency injection for
providers/storage, and small routers/components. Comments should explain
economic or numerical reasons, not restate syntax.

---

## 17. Decision rules for ambiguity

When the documents do not specify an implementation detail:

1. Preserve the economic invariant and observable failure semantics.
2. Prefer structural guarantees over penalty tuning.
3. Prefer an independent certificate over trusting optimizer status.
4. Prefer model-native calculations over a forced uniform route.
5. Prefer a deterministic synthetic golden before a live-data example.
6. Prefer a feature flag with exact off behavior over an irreversible coupling.
7. Prefer explicit provenance over a “best guess.”
8. Prefer a measured simple model over an unvalidated sophisticated one.
9. Do not choose a default from in-sample RMS alone; include held-out error,
   convergence, arbitrage, uncertainty calibration, wings, and speed.
10. If an ambiguity can materially alter desk behavior, record it in the
    decision log and surface it as configuration rather than hiding it.

---

## 18. Final completion checklist

The rebuild is not finished until all answers are “yes.”

### Numerical

- [ ] All three parametric models and local variance are usable.
- [ ] Finished displayed slices have independent static-arbitrage diagnostics.
- [ ] Calendar and wing authority are confined correctly.
- [ ] American chains, carry, event time, variance swaps, priors, and spot
      transport compose.
- [ ] Every derivative hot path has a numerical check.
- [ ] Performance rails pass on stated hardware.

### Graph

- [ ] Only lit calibrations influence the solve.
- [ ] Unsupported components remain at prior with explicit status.
- [ ] Precision-message semantics pass all goldens.
- [ ] Smooth-field comparison is retained.
- [ ] Bands are functional and held-out coverage is reported.
- [ ] Preflight/what-if/LOO never write production state.
- [ ] Attribution sums to the posterior move.
- [ ] Dynamic mode, if present, is causal and opt-in.

### Product

- [ ] Eight workspaces are functional, not placeholders.
- [ ] Workflow progress, cancellation, stale state, and failure recovery work.
- [ ] Settings are explicit, validated, documented, and persistable.
- [ ] Quality never triggers calibration.
- [ ] Publish hard-blocks uncertified/stale/unsupported required surfaces.
- [ ] Manifests, lineage, audit events, export, and recall work.
- [ ] Offline synthetic mode works without credentials.

### Validation

- [ ] Equation goldens and adversarial cases pass.
- [ ] Feature-off identity tests pass.
- [ ] Restart, migration, and scoped invalidation tests pass.
- [ ] API and browser smoke tests pass.
- [ ] Certification emits JSON and HTML.
- [ ] Historical replay reports precision, uncertainty calibration, breaks,
      and speed with full provenance.

---

## 19. Suggested first prompt in the new environment

> Read `VOL_FITTER_CLEAN_ROOM_REBUILD.md` completely. We are performing a
> clean-room rebuild: do not ask for or assume access to another codebase.
> Create the Phase 0 deliverables only. Then read Notes 01 and 07 completely,
> extract their mathematical invariants and golden cases into the requirements
> matrix, and propose the smallest Phase 1 vertical slice. Do not implement
> later phases yet. Every completion claim must include tests and measured
> performance.

That prompt deliberately starts with a narrow, testable slice. Continue phase
by phase rather than repeatedly asking a model to “build the whole Vol-Fitter.”

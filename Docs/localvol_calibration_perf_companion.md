# Local-Vol Calibration Compute-Time Strategy - Companion Note

Technical companion note - 2026-06-19.

This note complements `Docs/localvol_calibration_perf_note.md`. The original note explains
the current piecewise-affine local-volatility calibration implementation and lists possible
compute-time optimisations. This companion note sharpens the diagnosis, identifies the main
engineering risks, and turns the ideas into implementable work packages with acceptance gates.

Nothing in this note changes code. The goal is to make the next implementation pass faster,
safer, and measurable.

---

## 1. Executive summary

The current local-volatility workspace calibrates a continuous piecewise-affine local variance
surface to option and optional variance-swap quotes. The implementation is mathematically
sound and well tested, but its compute-time profile has two different bottlenecks:

| Regime | Likely bottleneck | Main lever |
|---|---|---|
| Default grid, roughly 100-200 vertices | Repeated forward Dupire solves with full sensitivities | Fewer evaluations, cheaper PDE grids, compiled kernel |
| Heavy grid, roughly 500+ vertices | Dense least-squares linear algebra inside bounded TRF | Matrix-free or sparse Gauss-Newton, better warm starts |

The important conclusion is that "parallelise it" is not the first-order solution. The current
Python/SciPy path holds too much work inside per-evaluation dense/sensitivity machinery, and
Windows process spawning makes brute-force process parallelism unattractive. The most robust
path is:

1. Measure calibration time in a way that separates PDE cost, optimizer cost, and iteration
count.
2. Reduce optimizer evaluations through scaling and warm starts.
3. Decouple the calibration PDE grid from the final publication grid.
4. Remove variance-swap accuracy dependence on a wide, fine strike grid.
5. For high vertex counts, replace dense TRF with a matrix-free Gauss-Newton/LSMR path.
6. Only then decide whether Numba or a native kernel is needed.

The original note is directionally right. The main correction is that the data Jacobian should
not be assumed to be cleanly sparse. A better mental model is:

```text
J = dense-ish PDE data block + sparse regularisation/constraint block
```

That distinction matters because simply asking SciPy to use sparse least-squares machinery is
unlikely to be enough. A custom matrix-free formulation is more likely to pay off.

---

## 2. Current code paths to keep in view

The implementation is concentrated in the following files:

| Concern | File |
|---|---|
| P1 surface, basis, Dupire solver, forward sensitivities | `backend/volfit/models/localvol/affine.py` |
| Calibration residuals, Jacobian, roughness, varswap replication | `backend/volfit/models/localvol/affine_calib.py` |
| API/workflow orchestration, grid construction, fit cache | `backend/volfit/api/affine_fit.py` |
| Derived local-vol views | `backend/volfit/api/affine_views.py` |
| Background calibration dispatch | `backend/volfit/api/workflow.py` |
| Performance test harness | `backend/tests/test_perf.py` |
| Local-vol affine golden tests | `backend/tests/test_localvol_affine.py` |
| Grid/design contract tests | `backend/tests/test_affine_grid_design.py` |
| API contract tests | `backend/tests/test_api_affine.py` |

Useful implementation facts:

- The fitted parameters are nodal local variances on a tensor `t_nodes x x_nodes` vertex set.
- The Dupire pricer uses a uniform strike grid by default, with `dx = 0.01` and
  `x_max >= 2.5`.
- Time is refined so that quoted expiries are hit exactly and each step is at most about
  `dt = 0.01`.
- Each objective evaluation can propagate the full sensitivity matrix `dU/dtheta`.
- `scipy.optimize.least_squares(method="trf")` receives an explicit dense Jacobian.
- The roughness and shape penalty rows are structurally sparse, but the PDE data rows are not
  obviously sparse after propagation through time.

The last point is the key architectural issue for large grids.

---

## 3. Performance model

Let:

- `m` = number of fitted theta parameters, plus optional left-wing parameter.
- `N_x` = number of PDE strike grid nodes.
- `N_t` = number of PDE time steps.
- `N_q` = number of option quotes.
- `N_z` = number of variance-swap quotes.
- `N_r` = number of regularisation and shape residual rows.
- `N_eval` = number of objective evaluations.

The rough cost per objective evaluation is:

```text
PDE value solve:              O(N_t * N_x)
Forward sensitivity solve:    O(N_t * N_x * active_m)
Residual/Jacobian assembly:   O((N_q + N_z + N_r) * m)
Dense TRF linear algebra:     approximately O(M * m^2) or worse per optimizer iteration
```

where `M = N_q + N_z + N_r`.

For small grids, sensitivity propagation tends to dominate. For large grids, the dense
least-squares step becomes the wall. This is consistent with the measured heavy case in the
original note: about 533 vertices, about 86 seconds, and the optimizer hitting the 200-eval cap.

The performance work should therefore target three separate multipliers:

| Multiplier | Examples |
|---|---|
| Reduce `N_eval` | warm starts, scaling, tolerances, better trust-region steps |
| Reduce per-evaluation PDE cost | nonuniform calibration grid, source-PDE varswap, compiled kernel |
| Reduce per-iteration optimizer algebra | matrix-free Gauss-Newton, LSMR/CG, preconditioning |

Any proposal that improves only one multiplier can still lose if another multiplier dominates.
This is why instrumentation is the first deliverable.

---

## 4. Instrumentation first

Before changing numerics, add a small timing and diagnostics layer to affine calibration. The
goal is to make every local-vol fit produce enough information to explain why it was slow.

### 4.1 What to measure

Add per-fit diagnostics:

```text
fit_id
ticker
grid_t_count
grid_x_count
vertex_count
pde_x_count
pde_t_count
quote_count
varswap_count
residual_count
regularisation_row_count
fit_left_a
max_nfev
nfev
njev
status
cost
optimality
active_bound_count
wall_ms_total
wall_ms_pde_value
wall_ms_pde_sensitivity
wall_ms_residual_assembly
wall_ms_jacobian_assembly
wall_ms_optimizer_outer
```

Not every field must be exact on day one. Even approximate timers around the PDE solve and the
`least_squares` call will clarify priorities.

### 4.2 Where to instrument

Suggested locations:

- `backend/volfit/models/localvol/affine.py`
  - instrument `solve_affine_dupire`
  - if possible, split value-solve and sensitivity-solve timers
- `backend/volfit/models/localvol/affine_calib.py`
  - count residual rows by block
  - expose `nfev`, `njev`, `cost`, `optimality`, active bound count
- `backend/volfit/api/affine_fit.py`
  - attach the fit diagnostics to the cached surface object or response metadata

Keep the diagnostics lightweight and optional. A simple dataclass returned in the fit result is
enough. Avoid logging-only diagnostics; tests should be able to assert against the counters.

### 4.3 Perf gates

Add affine-specific performance tests to `backend/tests/test_perf.py`.

Suggested initial tests:

| Test | Purpose |
|---|---|
| `test_affine_localvol_default_budget` | Protect default-grid latency |
| `test_affine_localvol_heavy_budget` | Protect large-grid behavior, skipped unless perf flag enabled |
| `test_affine_localvol_warm_start_eval_count` | Ensure warm start reduces or does not increase `nfev` |
| `test_affine_localvol_grid_refinement_stability` | Ensure calibration-grid changes do not move final IVs/surface beyond tolerance |

Use relaxed budgets at first. The first objective is regression visibility, not a strict SLA.

---

## 5. Optimizer scaling and tolerances

This is the lowest-risk code change.

### 5.1 Current issue

The affine calibration problem is badly scaled:

- ATM/front nodes are strongly identified by option prices.
- Far-wing and late-time nodes may be weakly identified.
- Roughness rows identify smooth combinations, not individual nodes.
- Bounds can be active in wings.

A single trust-region radius in raw variance units is therefore inefficient. Some columns want
large steps; others need small steps.

### 5.2 Proposed implementation

In `backend/volfit/models/localvol/affine_calib.py`, add solver options to
`calibrate_affine`:

```text
x_scale: "jac" by default, or explicit vector
ftol: default around 1e-8 or 1e-10
xtol: default around 1e-8 or 1e-10
gtol: default around 1e-8 or 1e-10
max_nfev: keep configurable
```

The current note mentions tolerances around `1e-12`. That is much stricter than the data
accuracy and stricter than SciPy's defaults. The calibration objective is ultimately governed
by quote noise, vega scaling, bid/ask bands, and regularisation. A `1e-12` numerical target is
not economically meaningful.

### 5.3 Acceptance gate

Required:

- Golden local-vol tests remain within tolerance.
- Calibrated option IV errors remain effectively unchanged.
- `nfev` decreases or stays flat on default and heavy cases.
- Surface diagnostics still show no density/calendar-arbitrage regression.

If `x_scale="jac"` changes results because convergence stops earlier, tighten only the final
termination tolerance, not the entire algorithmic direction.

---

## 6. Warm starts

Warm starts are likely the highest value near-term improvement because they reduce `N_eval`
without changing the pricing model.

### 6.1 Warm-start hierarchy

Use this order:

1. Previous affine local-vol surface for the same ticker and materially same settings.
2. Previous affine surface interpolated to the new grid.
3. Parametric/LQD implied surface converted to Dupire local variance at the affine vertices.
4. Existing flat median-variance initial guess.

The previous affine surface is the best seed after the first successful calibration. The
parametric Dupire seed is the best first-fit seed when the parametric surface has already been
calibrated.

### 6.2 Previous affine surface seed

Store the fitted theta, `t_nodes`, `x_nodes`, bounds, and relevant calibration settings in the
affine cache.

On a new calibration:

1. Check whether the old surface key is compatible.
2. If `t_nodes` and `x_nodes` match exactly, reuse theta directly.
3. If the grid changed, interpolate old theta onto the new tensor grid.
4. Clip to new `[var_lo, var_hi]`.
5. Use the clipped/interpolated theta as `theta0`.
6. Use it also as `theta_ref` if the roughness prior is intended to penalize movement from the
   previous surface.

Interpolation should be monotone-safe and boring: linear interpolation in time and strike is
adequate for a seed. Do not use a high-order interpolant that can create negative variances or
overshoots.

### 6.3 Parametric Dupire seed

When no previous affine surface exists, seed from the current parametric implied volatility
surface:

1. Evaluate total implied variance `w(T, k)` from the fitted parametric model.
2. Compute local variance through the existing Dupire extraction machinery where possible.
3. Evaluate local variance at each affine vertex `(t_i, x_j)`, with `k = log(x_j)`.
4. Fill nonfinite values by nearest-neighbor or median fallback.
5. Clip to affine bounds.
6. Blend with the flat median in weakly identified far wings if the raw Dupire seed is unstable.

Pseudo-policy:

```text
if previous_affine_seed_available:
    theta0 = interpolate_previous_affine()
elif parametric_surface_available:
    theta0 = clipped_smoothed_dupire_seed()
else:
    theta0 = flat_median_variance()
```

### 6.4 Risks

Dupire local variance from an implied surface can be noisy, especially:

- short maturities,
- far wings,
- regions with sparse quotes,
- around event-adjusted time transformations.

Therefore the parametric seed should be a seed only, not a hard prior, unless the user has
explicitly selected a strong prior mode.

### 6.5 Acceptance gate

Required:

- Same final calibration quality as flat start.
- `nfev` reduction on normal recalibration.
- Stable behavior if the parametric surface is missing or fails.
- No worse behavior on a deliberately bad initial seed test.

---

## 7. Calibration grid versus publication grid

The original note correctly identifies grid separation as a major opportunity. The important
detail is to avoid moving the product output accidentally.

### 7.1 Current risk

Naively coarsening the uniform PDE grid changed nodal variance far beyond golden tolerance.
That is not just a test inconvenience. The local-vol surface itself is part of the product
output, so a faster calibration that preserves option prices but materially changes theta may
still be unacceptable.

### 7.2 Safer design

Separate three grids:

| Grid | Purpose |
|---|---|
| Vertex grid | Parameters users inspect and regularisation acts on |
| Calibration PDE grid | Fast grid used inside optimizer |
| Publication PDE grid | Fine grid used after convergence for final smiles, density, diagnostics |

The first implementation should keep the vertex grid unchanged and make only the PDE solve grid
nonuniform.

### 7.3 Nonuniform calibration PDE grid

Build an `x_grid_calib` that includes:

- `0`
- `1`
- all normalized quote strikes `K/F`
- key variance-swap quadrature/source points until source-PDE varswap exists
- a dense band around ATM, for example `[0.8, 1.2]`
- moderate density around quoted strikes
- sparse geometric tails out to `x_max`

Then sort and deduplicate with a minimum spacing.

Example construction sketch:

```text
x_points = {0, 1, x_max}
x_points += quote_x_values
x_points += atm_band_grid(0.75, 1.25, dx=0.01 or 0.015)
x_points += local_grids_around_each_quote(width=0.03 to 0.06)
x_points += geometric_tail_grid(low_tail, high_tail)
x_grid_calib = sorted_unique_with_min_spacing(x_points)
```

For time:

- include every quoted expiry exactly,
- include every vertex time exactly,
- use coarser steps where no expiry or event boundary is nearby,
- keep a maximum step that passes golden convergence.

### 7.4 Publication pass

After optimizer convergence:

1. Take final theta.
2. Run one fine solve on the current publication grid.
3. Reconstruct smiles, density, and diagnostics from that fine solve.
4. Store both calibration diagnostics and publication diagnostics.

The API should continue serving the publication-quality result. Calibration-grid artifacts
should not leak into user-facing surfaces unless explicitly requested for debugging.

### 7.5 Acceptance gate

Required:

- Golden nodal theta within existing tolerance, or an explicitly reviewed tolerance update.
- Golden option IV and varswap rows within tolerance.
- Dense output density remains nonnegative within current numerical tolerance.
- Heavy-grid runtime improves.

---

## 8. Variance-swap pricing path

Variance swaps currently make grid reduction harder because log-contract replication is
integrated over the PDE strike grid. The `1/k^2` weighting gives wings disproportionate
importance.

### 8.1 Why this matters

If the PDE grid is coarsened or shortened, option prices near quoted strikes may remain good
while the variance-swap residual changes materially. This creates a false tradeoff between
speed and variance-swap accuracy.

### 8.2 Source-PDE or density expectation

Implement an alternative variance-swap pricing method that does not depend on a wide/fine
static strike integral.

Two viable paths:

| Path | Description | Fit with current code |
|---|---|---|
| Backward source PDE | Solve a PDE for expected accumulated variance/log payoff | Natural complement to call PDE |
| Forward density expectation | March density and compute `-2 E[log X_T]` or accumulated local variance | More structural rewrite |

The source-PDE path is probably the better incremental step because the rest of the calibration
can remain call-PDE based.

### 8.3 Implementation sketch

Add a varswap pricer interface:

```text
price_varswap(surface, expiry, method="static" | "source_pde")
```

Initially:

- keep `static` as default,
- implement `source_pde` behind an option or internal flag,
- test both methods against each other on the golden setup,
- switch calibration to `source_pde` only after stability is proven.

Sensitivity support:

- Either derive and implement the source-PDE sensitivity recurrence, or
- Use matrix-free directional products once the optimizer is refactored.

For the first version, exact analytic sensitivity is preferred so current `least_squares`
contracts remain intact.

### 8.4 Acceptance gate

Required:

- Golden varswap prices match current static-replication values.
- Varying `x_max` on the calibration PDE grid has much smaller impact on varswap residuals.
- Calibration with option plus varswap quotes remains stable.

---

## 9. Rethinking the optimizer for heavy grids

This is the largest structural improvement. It should be done after instrumentation and warm
starts, because those may already make many practical cases fast enough.

### 9.1 Why dense TRF is the wrong asymptotic path

SciPy's bounded `trf` method is robust and appropriate for moderate dense problems. But when
the Jacobian is passed as a dense array, the solver uses dense linear algebra. As `m` grows, the
cost rises quickly.

For a 500+ vertex local-vol surface, this is the wrong shape of computation. Most of the model
structure is being discarded:

- Regularisation is a sparse finite-difference operator.
- Convex/front-tie penalties are sparse.
- PDE products can be computed by tangent and adjoint sweeps.
- The data block has far fewer rows than a generic dense inverse problem of the same `m`.

### 9.2 Better formulation

Move from explicit dense Jacobian to matrix products:

```text
Given v, compute J v       via tangent-linear PDE propagation.
Given w, compute J^T w     via discrete adjoint PDE propagation.
```

Then solve Gauss-Newton or Levenberg-Marquardt steps with LSMR/CG:

```text
(J^T J + lambda * R^T R + damping * D) delta = -J^T r
```

where:

- `R` is the roughness operator,
- `D` is a scaling/preconditioning diagonal,
- bounds are handled by active-set projection or a smooth reparameterisation.

This avoids materialising the full dense Jacobian and aligns the computation with the PDE.

### 9.3 Bound handling options

| Option | Pros | Cons |
|---|---|---|
| Keep projected active-set bounds | Preserves current parameter meaning | More optimizer code |
| Sigmoid reparameterise theta | Converts to unconstrained problem | Can worsen conditioning near bounds |
| Softplus/log variance with upper cap penalty | Smooth positivity | Changes exact bound semantics |

Recommended first implementation: active-set projected Gauss-Newton if feasible. If that is
too much code, use sigmoid reparameterisation only behind a solver option and test bound-heavy
cases carefully.

### 9.4 Preconditioning

A naive LSMR path can behave poorly. The preconditioner matters.

A reasonable first preconditioner:

```text
P = diagonal(data_sensitivity_magnitude) + lambda_t * L_t^T L_t + lambda_x * L_x^T L_x + eps * I
```

If an exact sparse factorisation of the roughness block is easy, use it. Otherwise start with a
diagonal or block-diagonal approximation.

### 9.5 Acceptance gate

Required:

- Golden fit reaches same objective and same theta within tolerance.
- Heavy-grid case matches current dense TRF result within IV/surface tolerance.
- Heavy-grid runtime improves materially.
- Failure mode falls back to dense TRF, at least initially.

---

## 10. Tangent and adjoint products

The current code propagates all forward sensitivities `dU/dtheta`. This is simple and valuable
for moderate `m`, but expensive for large `m`.

### 10.1 Products needed

For matrix-free optimization:

| Product | Use |
|---|---|
| `J v` | LSMR/CG, directional derivative tests |
| `J^T w` | Gradient, normal-equation RHS, adjoint validation |
| `J^T J v` | Gauss-Newton normal products |

`Jv` can be computed with one tangent-linear PDE sweep for a chosen parameter direction `v`.
`J^T w` can be computed with one discrete adjoint sweep seeded by residual weights at observed
quotes and varswap functionals.

### 10.2 Test strategy

Add three numerical identity tests:

1. Directional finite-difference test:

```text
(F(theta + eps v) - F(theta)) / eps ~= Jv
```

2. Adjoint identity test:

```text
dot(Jv, w) ~= dot(v, J^T w)
```

3. Gradient alpha test:

```text
Phi(theta + alpha v) - Phi(theta)
  ~= alpha * dot(grad Phi(theta), v)
```

These tests are standard for PDE-constrained optimization and should be added before trusting
the new optimizer.

### 10.3 Implementation sequencing

Do not start by deleting the dense sensitivity code. Add products alongside it:

1. Implement `apply_jacobian(theta, v)`.
2. Compare with dense `jac @ v`.
3. Implement `apply_jacobian_transpose(theta, w)`.
4. Compare with `jac.T @ w`.
5. Only then introduce a matrix-free solver.

This staged path keeps the existing implementation as an oracle.

---

## 11. Compiled PDE kernel

A compiled kernel is attractive, but it should target a measured bottleneck.

### 11.1 What to compile

The best Numba candidate is the inner Dupire march:

- tridiagonal coefficient assembly,
- Thomas solve for value,
- Thomas solve for multiple right-hand sides or tangent directions,
- boundary term handling,
- interpolation from grid prices to quote prices if simple enough.

Keep Delaunay/basis precomputation in Python/SciPy. Pass plain numeric arrays into Numba.

### 11.2 Why Numba before C++

Numba can compile nopython loops, release the GIL with `nogil=True`, and parallelise selected
loops when appropriate. This is much lower operational risk than adding a Windows C++ build
pipeline.

Recommended approach:

```text
@njit(cache=True, nogil=True)
def march_dupire_numba(...):
    ...
```

Use `cache=True` to reduce repeated compile overhead. Trigger a warm-up call in tests or during
startup if first-use latency matters.

### 11.3 Caution

If dense TRF linear algebra dominates the heavy-grid case, a compiled PDE kernel alone will not
solve the 86-second profile. Numba is most valuable after `N_eval` is under control and after
profiling shows the PDE kernel is still a major share of wall time.

### 11.4 Acceptance gate

Required:

- Value solve matches current SciPy/banded result within tight numerical tolerance.
- Sensitivity or tangent products match current dense sensitivities.
- First-call compile latency is not counted as calibration latency, or is explicitly reported.
- Perf test shows a real speedup outside the JIT warm-up path.

---

## 12. Higher-order time stepping

Backward Euler is robust and monotone, but first-order in time. Reducing `N_t` could be a
meaningful speedup.

### 12.1 Candidate

Use Rannacher smoothing:

1. A few backward-Euler half-steps near the payoff kink.
2. Then Crank-Nicolson or theta-method steps for the rest of the grid.

This is a standard option-PDE trick for improving convergence while controlling oscillations
near nonsmooth payoffs.

### 12.2 Risks

- Crank-Nicolson can introduce oscillations if applied directly to a kinked payoff.
- Sensitivity recurrences must be updated.
- Existing density and arbitrage diagnostics must remain valid.
- Time-dependent local variance at step boundaries needs careful convention.

### 12.3 Acceptance gate

Required:

- Golden example remains within tolerance.
- Time-step convergence improves versus backward Euler.
- No density negativity or calendar violations are introduced.
- Sensitivities pass finite-difference checks.

This is worthwhile, but it should not precede easier wins like warm starts and grid separation.

---

## 13. Adaptive vertex grids

The current tensor grid is simple and stable, but it spends parameters in regions with little
data. Adaptive grids can reduce `m`, which helps both PDE sensitivity cost and optimizer linear
algebra.

### 13.1 Two-pass design

Pass 1:

- Fit on a conservative coarse tensor grid.
- Collect residuals, curvature, and active-bound diagnostics.

Pass 2:

- Add time or strike vertices where residuals/curvature are large.
- Avoid adding vertices in dead wings unless varswap residuals demand it.
- Interpolate pass-1 theta to the refined grid.
- Refit.

### 13.2 Refinement indicators

Possible indicators:

- large option residual at a quote,
- high local roughness penalty contribution,
- high curvature in theta,
- active bounds in a region with quote residuals,
- varswap residual sensitive to wing movement.

### 13.3 Risks

Adaptive grids can create hard-to-debug output differences. They also complicate cache keys and
warm-start interpolation.

Therefore adaptive vertex grids should come after:

- instrumentation,
- warm starts,
- publication/calibration grid split,
- and maybe matrix-free products.

---

## 14. Suggested implementation roadmap

### Stage 0 - measurement and safety rails

Deliverables:

- Add affine timing/counter diagnostics.
- Add default and heavy affine perf tests.
- Expose `nfev`, `njev`, `cost`, `optimality`, and active bounds in fit diagnostics.

Acceptance:

- No calibration result changes.
- Perf diagnostics available in tests.

### Stage 1 - cheap optimizer improvements

Deliverables:

- Add affine solver options: `x_scale`, tolerances, configurable `max_nfev`.
- Default to `x_scale="jac"` unless tests show instability.
- Relax affine tolerances to economically meaningful values.

Acceptance:

- Golden tests unchanged.
- Evaluation count decreases or remains flat.

### Stage 2 - warm starts

Deliverables:

- Previous affine theta warm start.
- Grid interpolation for previous theta.
- Parametric Dupire seed fallback.
- Seed diagnostics: source, clipping count, nonfinite fill count.

Acceptance:

- Same final fit quality.
- Lower `nfev` on repeated calibration.
- Safe fallback when parametric fit is unavailable.

### Stage 3 - calibration PDE grid split

Deliverables:

- Nonuniform calibration PDE grid builder.
- Final publication solve on existing fine grid.
- Grid diagnostics in fit result.

Acceptance:

- Golden theta/IV/varswap tolerance preserved.
- Runtime improves on default and heavy cases.

### Stage 4 - variance-swap source pricer

Deliverables:

- Source-PDE or equivalent variance-swap pricer.
- Analytic sensitivity or matrix-free product support.
- Side-by-side static/source validation mode.

Acceptance:

- Vswap golden rows match.
- Vswap sensitivity to `x_max` decreases.

### Stage 5 - matrix-free optimizer

Deliverables:

- `Jv` product.
- `J^T w` product.
- Product identity tests.
- LSMR/CG Gauss-Newton prototype with fallback to dense TRF.

Acceptance:

- Dense and matrix-free solutions agree.
- Heavy-grid runtime materially improves.

### Stage 6 - compiled PDE kernel

Deliverables:

- Numba value/tangent/sensitivity march.
- Warm-up handling.
- Optional thread-pool parallelism only after `nogil` correctness is verified.

Acceptance:

- Numerical equivalence.
- Speedup outside compile time.

---

## 15. Specific challenges to expect

### 15.1 The local-vol surface is an output, not just a hidden calibrator

Many calibration systems care only about repriced option errors. Here the calibrated nodal
surface, reconstructed smiles, density, and diagnostics are user-facing. Speedups that preserve
prices but materially alter theta may still be unacceptable.

Implication: always test both price/IV fit quality and nodal/local-vol stability.

### 15.2 Variance swaps amplify wing choices

Static replication makes the fit sensitive to strike-grid truncation and wing resolution.

Implication: do not judge a calibration-grid change only on option quote repricing. Include
varswap rows and wing stress cases.

### 15.3 Dense data rows complicate sparse narratives

Regularisation is sparse, but PDE data sensitivities are not guaranteed to be sparse after
time propagation.

Implication: prefer matrix-free products and preconditioned iterative solves over assuming a
simple sparse Jacobian mask will solve the problem.

### 15.4 Bounds are not incidental

Adaptive variance caps and positivity bounds are part of the model's stability. Solver changes
must preserve their semantics.

Implication: if using sigmoid reparameterisation, test bound-heavy cases and monitor
conditioning near active caps.

### 15.5 Windows matters

The app runs in a Windows environment. Process spawning, native build toolchains, and compiled
dependencies carry practical risk.

Implication: prefer pure SciPy/NumPy/Numba changes before C++.

---

## 16. Recommended first pull request

The first implementation PR should be deliberately modest:

1. Add affine calibration diagnostics.
2. Add affine perf tests with loose budgets.
3. Add affine solver options and default `x_scale="jac"`.
4. Relax affine tolerances from ultra-tight values to around `1e-8` or `1e-10`.
5. Report `nfev`, final cost, active bound count, and timing breakdown.

This PR should not change grids, variance-swap pricing, or optimizer architecture. Its purpose
is to make every subsequent PR measurable.

Suggested acceptance checklist:

```text
[ ] Existing local-vol affine golden tests pass.
[ ] API contract tests pass.
[ ] New perf diagnostics are populated.
[ ] Default affine perf budget test exists.
[ ] Heavy affine perf test exists, possibly opt-in/slow.
[ ] Calibration result changes are zero or explicitly explained.
```

---

## 17. External references

These references informed the recommendations:

- SciPy `least_squares` documentation:
  `https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html`
- Numba JIT documentation:
  `https://numba.pydata.org/numba-doc/dev/user/jit.html`
- Andreasen and Huge, volatility interpolation / local variance finite-difference approach:
  `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1694972`
- Local volatility calibration and adjoint/gradient verification:
  `https://www.math.fsu.edu/~kim/ATE_N.pdf`
- PDE-constrained local-volatility calibration:
  `https://www.diva-portal.org/smash/get/diva2%3A764597/FULLTEXT01.pdf`
- Rannacher time stepping for option finite differences:
  `https://people.maths.ox.ac.uk/gilesm/files/giles_carter.pdf`
- Arbitrage-free interpolation context:
  `https://arxiv.org/pdf/2004.08650`

---

## 18. Bottom line

The best near-term speedup path is not one heroic rewrite. It is a sequence:

```text
measure -> scale/warm-start -> decouple grids -> fix varswap path -> matrix-free solver -> compile kernel
```

That sequence keeps the current mathematical contract intact while progressively removing the
three true bottlenecks: too many optimizer evaluations, too much PDE work per evaluation, and
dense optimizer algebra at high vertex counts.


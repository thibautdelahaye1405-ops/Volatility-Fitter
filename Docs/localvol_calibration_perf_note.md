# Local-Volatility (Piecewise-Affine) Calibration — Implementation & Compute-Time Optimisation

*Technical note — 2026-06-19. Describes the current Local-Vol calibration as built, then
proposes compute-time optimisations from one-line patches to structural rewrites. No code
is changed by this note.*

---

## 1. Scope and context

The "Local-Vol" workspace fits a **continuous piecewise-affine local-variance surface**
ν(t,x) directly to a ticker's option (and optional variance-swap) quotes, by pricing every
quote through the **forward Dupire PDE** and minimising a weighted least-squares misfit. It
is the implementation of `Docs/piecewise_affine_local_variance_calibration.tex` (the
Andreasen–Huge philosophy with a P1 finite-element parameterisation). It is *distinct* from
`GET /localvol/{ticker}`, which merely *extracts* a Dupire grid from already-fitted LQD
smiles.

Code map:

| Concern | File |
|---|---|
| P1 surface, basis, implicit-Euler Dupire pricer, forward sensitivities | `backend/volfit/models/localvol/affine.py` |
| LSQ objective, roughness/convex/front-tie operators, var-swap replication | `backend/volfit/models/localvol/affine_calib.py` |
| Orchestration: grid build, quote prep, bounds, caching, reconstruction | `backend/volfit/api/affine_fit.py` |
| Derived views (density/term/table) | `backend/volfit/api/affine_views.py` |
| Background dispatch (one work-item per ticker) | `backend/volfit/api/workflow.py:112` |

The fit runs **only on an explicit Calibrate** (or fetch-driven auto-calibrate); the read
path serves a frozen cached surface and transports it under spot moves. One ticker's whole
surface is one sequential work-item (`_affine_thunk`). The relevant measured datapoint: a
**~533-vertex grid takes ~86 s and hits the 200-eval cap**; a default ~143-vertex grid is a
few seconds. Thread/process parallelism was tried and rejected (GIL-negative; Windows-spawn
risk) — see `memory/calibration-perf.md`.

---

## 2. Current implementation

### 2.1 Parameterisation and assumptions

- **Forward normalisation** (note §2): deterministic rates r(t) and dividends q(t); work in
  X = S/F(0,t), a driftless martingale dX = X·√ν(t,X) dW, X₀=1. Prices are normalized
  undiscounted forward calls c(T,x)=E[(X_T−x)⁺], x=K/F. Puts are parity-converted.
- **Surface**: ν_θ(t,x)=Σ θ_ℓ φ_ℓ(t,x) on a **tensor-product vertex set**
  `(t_nodes × x_nodes)` with nodal *variances* θ (note eq. p1_lv). Triangulation is a cached
  qhull **Delaunay** of the tensor vertices (`affine.py:100`); barycentric positivity ⇒ nodal
  bounds imply surface bounds (note App. B). Despite the Delaunay machinery the grid is
  **rectangular/tensor**, not a true per-maturity "bowtie" point cloud (that is the deferred
  Stage 5).
- **Diffusion clock** is the event-weighted variance time τ (`prepared.tau`), not calendar t
  — events lower reconstructed IVs consistently with the Parametric fit (`affine_fit.py:316`).

### 2.2 Pricing map — forward Dupire, fully implicit Euler

`solve_affine_dupire` (`affine.py:309`) marches
∂_T c = ½ ν(T,x) x² ∂_xx c, c(0,x)=(1−x)⁺, with Dirichlet BCs c(·,0)=1, c(·,x_max)=0.

- **Spatial grid** (`_pde_grids`, `affine_fit.py:257`): **uniform** x = {0, 0.01, 0.02, …},
  x_max = max(e^{k_hi}·1.4, 2.5). So x=1 (the var-swap anchor) is always a node; a typical
  x_max=2.5 ⇒ **~251 spatial nodes**. Non-uniform central second difference
  (note eq. nonuniform_second_derivative).
- **Time grid**: every quoted expiry forced onto the grid, refined to dt ≤ 0.01 ⇒
  **~100–250 steps** for a 1–2.5y surface.
- **Step**: banded `(I − Δt·A^{n+1}) U_I^{n+1} = U_I^n + boundary` via `scipy.linalg.solve_banded`
  — tridiagonal, O(N_x) per step. Backward Euler ⇒ unconditionally stable M-matrix, **first
  order in time** with no Rannacher smoothing of the kinked payoff.

### 2.3 Sensitivities

`sensitivities=True` propagates the full dU/dθ by the discrete sensitivity recursion
(note eq. discrete_sensitivity): same tridiagonal factor per step, **multi-RHS** solve.
Two precomputation tricks already shipped (`memory/calibration-perf.md`):

- `precompute_dupire_steps` hoists the **θ-independent hat basis** φ[n] out of the per-eval
  loop (`affine.py:267`).
- `active_k[n]` restricts the sensitivity solve to the **live column prefix** — a vertex's
  column is exactly zero until the march reaches its hat support; bit-identical, cheaper.

Cost per evaluation ≈ Σ_n N_x · active_k[n] ≈ **O(N_t · N_x · m)** where m = #vertices. The
left-wing slope `a` is an optional extra fitted column (`fit_left_a`).

### 2.4 Objective and solver

`calibrate_affine` (`affine_calib.py:280`) builds residuals (note eq. calibration_objective):

1. **Option block**: mid `(P−y)/η`, or in bid-ask/haircut mode a band-violation hinge + soft
   mid anchor (`calib/band.py`). η = vega·VOL_TOL/√weight ⇒ residuals ≈ vol-error, with the
   quote-weighting scheme folded in.
2. **Var-swap block**: `(Z−z)/ζ`, Z by **static log-contract replication** — trapezoid of
   2·P/k² + 2·C/k² on the PDE grid (`varswap_weights`), θ-linear so it reuses dC/dθ.
3. **Roughness**: √λ·L(θ−θ_ref). L is the **spacing-aware** second-difference operator on the
   real vertex positions (`second_difference_rows_spacing`), reducing to (1,−2,1) on a uniform
   grid.
4. Optional **convex-wing** hinge (concavity of σ below ~5Δ) and **front-tie** (pin t=0 row to
   first data row).

Solved by **`scipy.optimize.least_squares(method="trf")`** with an **explicit dense Jacobian**,
box bounds [var_lo, var_hi] (adaptive cap, `_lv_bounds`), `max_nfev=200`. fun/jac share one
memoised PDE solve. The Jacobian is **dense** of shape (M_resid × m) with M_resid ≈ #quotes +
#varswaps + ~2m roughness rows; trf's bounded `tr_solver='exact'` does a **dense SVD of J each
iteration**.

### 2.5 Grid construction and reconstruction

- Delta-spaced strike axis x = e^{±σ*√T* Φ⁻¹(δ)} clipped to traded range, ATM forced in
  (`_delta_strike_nodes`); `gridXNodes` a floor. Time axis 0 + √T-spread of expiries
  (`_time_nodes`); `gridTNodes` a floor. Adaptive var cap = max(req, mult×max-IV) ≤ (400%)².
- After the fit each expiry's smile is reconstructed by inverting the PDE call prices through
  Black (`_reconstruct_smile`), and the density taken straight from d²C/dx² (Breeden–
  Litzenberger, smooth ≥0).

### 2.6 Worked example (the note's golden case)

15 options (5 strikes × 3 expiries) + 3 var-swaps, a 21-vertex (3×7) grid, PDE on 221 x-nodes
× 201 t-steps. Reproduces the published table: RMS price error 7.6e-6, RMS IV error 1.26 vol-bp,
var-swaps within 0.3 var-bp. This is the byte-identical regression anchor — **any optimisation
must keep it within golden tolerance.**

---

## 3. Where the time goes — two regimes

| Regime | Dominant cost | Scaling |
|---|---|---|
| **Small grid** (~143 vtx, default) | the **sensitivity PDE solve** (multi-RHS banded), repeated per eval | O(N_eval · N_t · N_x · m) |
| **Large grid** (~500+ vtx) | trf's **dense SVD of J** each iteration | O(N_eval · M_resid · m²) ≈ O(N_eval · m³) |

Both are multiplied by **N_eval** (≤200), which is large because trf takes many small
trust-region steps on a stiff, poorly-scaled problem (wing columns barely move the data
residuals). So three independent levers exist: **cost per PDE solve**, **cost of the linear
algebra per iteration**, and **number of iterations**.

---

## 4. Optimisation proposals

Ordered by risk/effort. Each notes the regime it helps and the test gate.

### Tier A — low-risk patches (days, byte-tolerant)

**A1. Separate calibration and pricing grids.** The PDE x-grid is uniform dx=0.01 to x_max≥2.5
(~251 nodes) and dt≤0.01 (~200 steps) — far finer than the ~10–25 strike vertices the data
identify. The accuracy that matters is *at the quote strikes and the var-swap integral*, not
everywhere. Use a **coarser solve grid** (e.g. dx=0.02, geometric in the wings; dt tied to
expiry spacing) during optimisation, then **one final fine solve** for the published surface /
reconstruction. *Caveat from `calibration-perf.md`: naive uniform coarsening shifted nodal
variances ~30× over golden tol — so this must be done as a **non-uniform, accuracy-targeted**
grid (dense near x=1 and near quote strikes, coarse in the dead wings) with the final-pass
refine, not a blanket coarsening.* Helps both regimes (smaller N_x, N_t). **Gate**: golden
example + a convergence test (coarse vs fine surface within IV tol).

**A2. Var-swap via the source PDE instead of grid quadrature.** Z is currently a trapezoid over
the whole x-grid of 2C/k²+2P/k² (k⁻² weight ⇒ wing-sensitive, ties var-swap accuracy to a wide
fine grid). The note's §6.3 backward **source PDE** gives I(T)=g(0,1) with a sensitivity PDE
(eq. var_sensitivity_pde) — one extra cheap sweep, **decoupled from the option x_max** and from
wing truncation. Lets A1's grid shrink without hurting var-swap fits. **Gate**: var-swap rows of
the golden example.

**A3. Solver scaling and tolerances.** trf is poorly scaled (variance columns of wildly
different identifiability). Pass **`x_scale='jac'`** (or an explicit per-column scale from the
data-sensitivity magnitude) so the trust region is isotropic in identified directions — fewer,
larger steps. Loosen `xtol/ftol/gtol` from 1e-12 to ~1e-8 (the data is good to ~vol-bp; 1e-12
buys nothing but iterations) and consider lowering `max_nfev` once warm-started (A5/C3). Pure
N_eval reduction, both regimes. **Gate**: golden RMS unchanged to tol; assert N_eval drops.

**A4. Cache invariants across the surface fit.** `varswap_weights/_const`, the roughness L
rows, the convex/front-tie stencils, and the band edges are rebuilt per call but depend only on
the grid/quotes. Confirm they are hoisted out of `evaluate` (most are) and memoised across the
ticker's repeated fits where the grid is unchanged. Small constant-factor win.

**A5. Warm-start θ from the prevailing parametric surface.** The flat-median initial guess
(`affine_fit.py:602`) is far from the skewed/term-structured optimum, costing early iterations.
Seed θ from the Dupire local-variance of the already-fitted LQD/SVI surface (a closed-form
Dupire-from-implied evaluation at the vertices). Typically the largest single N_eval reduction.
**Gate**: same optimum (LSQ is re-run to convergence), fewer evals.

### Tier B — structural numerics (1–2 weeks, same model, new linear algebra)

**B1. Sparse Gauss–Newton replacing the dense SVD (the headline large-grid fix).** The
Jacobian is **structurally sparse**: option/var-swap rows are dense in only the few vertices
their expiry/strike touches; the roughness and convex blocks are **banded** (3-point stencils).
trf's dense SVD ignores all of this (O(m³)/iter). Replace with a **Gauss–Newton / Levenberg–
Marquardt step solving the normal equations (JᵀJ + λD)Δ = −Jᵀr** where JᵀJ is assembled as a
**sparse** matrix (the roughness block is a fixed sparse LᵀL; the data block is low-rank
updates), factorised by `scipy.sparse.linalg` (sparse Cholesky / `splu`) or solved matrix-free
by **LSMR/CG with the roughness block as preconditioner**. The note explicitly recommends this
("graph-gradient or second-difference penalties", sparse L). Box bounds are handled by a
**projected / bound-constrained GN** (active-set or a smooth sigmoid reparameterisation
θ_ℓ = v_lo+(v_hi−v_lo)·σ(α_ℓ), note Step 8 — turns it into an *unconstrained* problem amenable
to plain GN). Expected: O(m³)→ ~O(m^1.5–2) per iteration on the structured sparsity; the ~86 s /
533-vtx case is where this pays off. *Note `tr_solver='lsmr'` was tried inside trf and diverged
— that failure was LSMR **without** a roughness preconditioner inside trf's machinery; a
purpose-built preconditioned GN is a different animal.* **Gate**: golden example + the large-grid
surface within IV tol of the current trf result; new perf budget entry.

**B2. Discrete adjoint gradient (the large-m PDE fix).** The forward sensitivity propagates all
m columns (O(N_t·N_x·m)); the note's **adjoint** (eq. adjoint_grad) computes the full gradient
in **one forward + one backward sweep, independent of m** (O(N_t·N_x)). For a pure-gradient
optimiser (L-BFGS-B on the sigmoid-reparameterised objective, or a Gauss–Newton that only needs
Jᵀr and JᵀJ·v matrix-vector products) this removes the m-factor from the PDE cost. Pairs
naturally with B1's matrix-free GN (adjoint gives Jᵀr; a tangent sweep gives J·v). **Gate**:
adjoint gradient vs finite-difference and vs the existing forward sensitivities (already a test
pattern for `fit_left_a`).

**B3. Rannacher start-up / higher-order time stepping.** Backward Euler is first-order and
smears the payoff kink at x=1; achieving target accuracy currently needs dt≤0.01 (~200 steps).
Two implicit Euler half-steps then Crank–Nicolson (**Rannacher**) is 2nd-order and lets dt grow
several-fold at equal accuracy — directly shrinks N_t in every PDE solve. **Gate**: golden +
convergence-order test.

**B4. Two-pass adaptive grid.** Pass 1: fit on a coarse vertex set (fewer m ⇒ cheap, well-posed
wings). Pass 2: refine vertices only where the **pass-1 residual / surface curvature** is large
(near the skew, short end), warm-started from pass 1 interpolated. Concentrates degrees of
freedom where data lives; keeps m small for a given fit quality, compounding with A1/B1. **Gate**:
final RMS ≤ single-pass; document the refinement criterion.

### Tier C — ambitious / structural (research-grade)

**C1. Fokker–Planck (forward Kolmogorov) solve in ln(S).** Instead of marching the call surface
c(T,x) for *all* strikes, march the **density p(T,y)** (note eq. density_pde,
∂_T p = ½∂_yy(ν y² p)) **once** per parameter set on a log grid y=ln x; every option price and
the var-swap are then linear functionals (quadratures) of the single evolving density, and
−2E[ln X_T] gives the var-swap directly. In log-space the operator has near-constant
coefficients (better conditioning, uniform grid resolves the wings in fewer nodes). This can be
cheaper than solving the call PDE when many strikes per expiry are quoted, and gives all
maturities in one sweep. Significant rewrite (new pricer, new sensitivity/adjoint, careful δ₁
initial condition and mass conservation). **Gate**: reprice the golden option+var-swap table.

**C2. Native compute kernel (C++ / Julia / Numba).** The per-step Python loop in
`solve_affine_dupire` (the band assembly + `solve_banded`) holds the GIL and dominates the
small-grid regime; numpy granularity is the bottleneck, not algorithm. A **Numba `@njit`** inner
march (Thomas solver + sensitivity recursion, no scipy call overhead) is the lowest-friction
big constant-factor win and keeps everything in-process/in-repo; a C++/`pybind11` or Julia
kernel is the ceiling but adds a build/toolchain dependency on a Windows box where PyPI is
already flaky. Recommended order: **Numba first**, native only if Numba is insufficient.
Crucially, this *also* unlocks the rejected **parallelism**: a nogil Numba/C++ march lets the
per-ticker (or per-trial) PDE solves run on a thread pool without the GIL penalty that killed
the earlier attempt. **Gate**: bit-comparable march output; perf budget.

**C3. Analytic / amortised warm-start across the day.** Beyond A5, persist each node's
calibrated θ and **start the next intraday recalibration from yesterday's / last-tick's surface**
(the note's "θ_ref = previous day's surface", already half-present as the roughness prior). With
a good warm start the optimiser needs a handful of GN steps. Combine with an event-/spot-only
**incremental** update (only refit columns whose quotes moved). **Gate**: stability test (small
data perturbation ⇒ small surface change).

---

## 5. Recommended sequencing

1. **A3 + A5** (solver scaling + parametric warm-start) — cheapest, cuts N_eval, no model
   change, helps every grid size immediately.
2. **A1 + A2** (calibration/pricing grid split + source-PDE var-swap) — shrinks the per-solve
   cost without the wing-accuracy regression that blocked naive coarsening.
3. **B1** (sparse Gauss–Newton) — the structural fix for the large-grid O(m³) wall; the single
   highest-value item for the ~533-vtx / 86 s regime.
4. **B2 + C2** (adjoint + Numba march) — remove the m-factor and the Python-loop constant; these
   make Stage 5 (the ~1000-vertex bowtie) tractable and re-open safe parallelism.
5. **B3, B4, C1, C3** — opportunistic, each independently shippable behind the existing Options
   gating.

The first three are expected to take the default fit from seconds to sub-second and the heavy
grid from ~86 s into the few-second range, with no model change visible to the user.

---

## 6. Risks and invariants

- **Golden example is sacred**: every change keeps `Docs/piecewise_affine_local_variance_calibration.tex`'s
  table within tolerance (`test_localvol_affine.py`, `test_affine_grid_design.py`). The local-vol
  surface *is* the product output — coarse-grid shortcuts that move nodal variances are out
  (proven by the earlier 30× regression).
- **Arbitrage-freedom**: implicit Euler's M-matrix gives monotone, convex prices; any new pricer
  (C1) or time-stepper (B3) must preserve `_diagnostics` (min density ≥0, no calendar
  violations).
- **Bounds & positivity**: nodal positivity ⇒ surface positivity is the safety net; a sigmoid
  reparameterisation (B1) must keep the same effective [var_lo, var_hi] box.
- **Determinism**: fits feed cached pointers and priors; keep results reproducible (no
  randomised solvers without a fixed seed) so `affine_key` caching stays valid.
- **Gate every perf claim** with a `test_perf.py` budget entry (the suite's purpose is catching
  algorithmic regressions, not absolute speed).

---

*Prepared for review. Nothing in this note is implemented; the proposals are sequenced so each
can ship independently behind the existing Options toggles and cache keys.*

# Local-Vol Calibration — Compute-Time Implementation Roadmap

*Roadmap — 2026-06-20. Builds on `localvol_calibration_perf_note.md` (current
implementation + idea list) and `localvol_calibration_perf_companion.md`
(sharpened diagnosis + work packages). This file is the agreed build order:
stages, refinements, and per-stage acceptance gates. Status is tracked inline.*

> **The consolidated reference is now `localvol_calibration_methodology.md`** — a
> standalone note covering the model, the pricing map, the objective, both solvers,
> every shipped optimisation, and everything shelved (with reasons). Read it first;
> this file is the chronological build order + per-stage acceptance gates.

---

## Agreed framing

Three independent cost multipliers, each with its own lever:

| Multiplier | Lever | Dominant regime |
|---|---|---|
| `N_eval` (optimizer iterations) | scaling, warm starts, tolerances | both |
| per-eval PDE cost (`N_t·N_x·m` sensitivity march) | non-uniform calib grid, source-PDE var-swap, compiled kernel | default grid (~100–200 vtx) |
| per-iteration dense linear algebra (`~m³` SVD) | matrix-free Gauss–Newton, preconditioned LSMR/CG | heavy grid (~500+ vtx) |

**Key correction adopted from the companion:** the Jacobian is *not* cleanly
sparse. `J = dense-ish PDE data block + sparse regularisation/constraint block`.
So the heavy-grid fix is **matrix-free products + preconditioned iterative
solves**, not "hand SciPy a sparse Jacobian mask".

## Seven refinements folded into the plan

1. **Data block is dense in strike but causal in time.** A quote at expiry `T_j`
   has exactly zero sensitivity to vertex rows with `t_node > T_j` — already
   encoded by `DupireSteps.active_k`. Stage 5's adjoint/tangent sweeps march only
   to each quote's expiry; `JᵀJ` is time-blocked even with dense strike blocks.
2. **Warm-start `theta0` ≠ temporal prior `theta_ref`.** Stage 2 sets the seed
   only; `theta_ref` stays at its current default. This keeps the golden example
   byte-identical (no previous surface ⇒ flat seed) and keeps the speed win
   surface-neutral. "Stick to yesterday's surface" remains the separate,
   existing `autoLoadPrior`/θ_ref lever. Gates must assert **theta stability**
   because the problem is non-convex (a different seed *can* change the basin).
3. **Stage 2 is mostly plumbing.** `dupire.extract_grid` already does
   parametric→local-variance; warm-start θ is already persisted in
   `AffineFitResponse.localVol` (=√θ) + `_affine_cache` and in
   `PriorSurfaceSnapshot` (`schemas_prior.py`). No new storage, only retrieval +
   grid interpolation.
4. **Stages 3 & 4 are coupled — build 4 first.** The `k⁻²` var-swap replication
   is exactly what breaks when the wing is shrunk/coarsened. So the source-PDE
   var-swap (Stage 4′) is the *enabler* for the grid shrink (Stage 3): build and
   validate 4′ against static replication on the current fine grid first, then
   coarsen. Stage 4′ is net-negative on the current grid (it adds a second sweep)
   and only nets positive paired with Stage 3 — judge them jointly.
5. **Split `x_scale` and tolerance relaxation into two toggles (Stage 1)** so a
   surface shift can be bisected to its cause.
6. **Parallelism pays across tickers, post-Numba.** The job runs one work-item
   per ticker sequentially (`workflow.py`). Intra-fit thread-parallel is
   GIL-negative; process pools are Windows-hostile. The viable win is
   across-ticker threads once Stage 6's `nogil` march releases the GIL.
7. **Stages 5 and 6 target different regimes.** Default grid → sensitivity march
   bound → Numba (Stage 6), keep dense TRF. Heavy grid → dense SVD bound →
   matrix-free GN (Stage 5), where the adjoint is required. Both must exist;
   neither alone clears both regimes.

---

## Stages

Every stage is independently shippable behind the existing Options/cache
machinery. The golden example (`test_localvol_affine.py`,
`test_affine_grid_design.py`) is the byte-identical anchor throughout.

### Stage 0 — Instrumentation & perf rails  ✅ DONE (2026-06-20)
Zero behaviour change. Shipped:
- `AffineFitDiagnostics` dataclass (`affine_calib.py`): problem-size counts,
  optimizer counters (`nfev/njev/status/cost/optimality/active_bound_count`), and
  a coarse wall-time split (`pde_value` / `pde_sensitivity` / `residual_assembly`
  / `optimizer_outer`). Returned on `AffineCalibration.diagnostics`; pure side
  metadata, never fed back, not on `AffineFitResponse` (golden serialization
  unchanged), not in `affine_key`.
- `solve_affine_dupire(..., timing=None)`: optional dict accumulating the
  per-step value vs multi-RHS sensitivity solve seconds. None = zero-overhead
  hot path (every standalone caller).
- Perf rails in `test_perf.py`: `affine_localvol_default` (143 vtx, ~1.0 s) and
  `affine_localvol_heavy` (255 vtx, `max_nfev` capped, ~2.1 s), plus a
  diagnostics-counter unit test in the normal suite.

Measured split confirms the regime model: at the default grid the **sensitivity
march dominates** (~60% of wall), with the optimizer/dense-algebra share rising
at the heavy grid.

**Gate (met):** full suite byte-identical; ruff + counters green.

### Stage 1 — Solver scaling & tolerances
- Surface `x_scale`, `ftol/xtol/gtol`, `max_nfev` on `calibrate_affine`
  (currently hard-wired `1e-12`). Default `x_scale="jac"`, relax tols to ~`1e-8`.
  Ship as **two independent flags** (refinement 5).
- **Gate:** golden RMS/IV within tol; **theta stable** within an explicit tol;
  `nfev` ↓ or flat on default + heavy (assert via Stage-0 counters); no
  density/calendar-arb regression.

### Stage 2a — Warm starts (previous surface)  ✅ DONE (2026-06-20)
- `affine_fit._seed_theta`: seed `theta0` from the previous calibrated surface
  (direct reuse on a matching vertex grid, linear-interp + clip onto a changed
  grid), flat-median fallback. **`theta0` only; `theta_ref` pinned to the flat
  `var0`** (refinement 2) so the roughness penalty `L·(θ−flat)=L·θ` is unchanged
  and a flat seed is byte-identical to the legacy start. `seed_source` recorded in
  `AffineFitDiagnostics`; diagnostics stashed on an AppState side-dict
  (`last_affine_diagnostics`) — off the wire response (wall times are
  non-deterministic), available to perf rails / a future UI cue.
- **Gate (met):** cold-start byte-identical (golden + API green); a recalibration
  flips `seed_source` flat→prev-affine, **nfev 19→1 / wall 2089→54 ms** on the
  ALPHA synthetic, surface bit-identical. New `test_affine_warm_start.py`
  (6 tests). ruff green.

### Stage 2b — Parametric Dupire cold-start seed  ✅ DONE (2026-06-20)
- `affine_fit._parametric_seed`: a COLD fit (no previous surface) now seeds θ from the
  **parametric surface's Dupire local variance** at the vertices, reusing the GET
  /localvol extraction (`localvol._w_surface` over the displayed slices →
  `dupire.extract_grid` at k = log x, t = the τ vertices, nan-fill + clip). **Cached
  lookup only** — uses the parametric slices the Calibrate job already fit (the app
  calibrates parametric before LV), never triggers a parametric fit; returns None →
  flat when fewer than two are calibrated or on any extraction error (best-effort).
  ``theta_ref`` stays flat, so it changes only the start, not the converged optimum.
- **Measured (SPY/NVDA, GN default):** nfev 84→66 / 64→36 / 159→80 and the optimizer
  (lsmr) work ~1.7× lower (a better-conditioned start) ⇒ **~1.3–1.8× on the cold fit**.
  Data-dependent: large on real skewed surfaces (flat start is far off), neutral on a
  smooth synthetic (flat is already near-optimal), so the unit test pins the mechanism
  + quality, not the eval cut. Golden byte-identical (no parametric surface at the
  model layer). `test_affine_warm_start.py` +1.

### Stage 4′ — Source-PDE variance-swap  ✅ DONE (2026-06-20)  *(built before Stage 3)*
- `volfit/models/localvol/varswap_pde.py`: backward source PDE
  `∂_t g + ½ν x²∂_xx g + ν = 0, g(T,·)=0, I(T)=g(0,1)` (note eq.
  variance_swap_source_pde), same implicit-Euler tridiagonal operator as the
  forward march, marched backward with a +ν source and degenerate-boundary
  accumulation. **Analytic dI/dθ** (note eq. var_sensitivity_pde, multi-RHS) +
  **dI/da** (left-wing slope) — both validated vs FD to ~1e-10. `precompute_
  varswap_steps` hoists the θ/a-independent basis; sliced per var-swap expiry.
  Wired through `calibrate_affine(varswap_method=)`, `affine_fit` (fit + displayed
  level + `affine_key`), `OptionsSettings.varSwapMethod` ("static"|"source_pde",
  default static), and an Options "Var-swap pricing" selector.
- **Note:** first tried the cheap **log-contract-via-density** form
  (`I=−2∫log(x)∂_xx c dx`, reusing the forward solve) — it matched static on the
  golden grid but was *more* sensitive to x_max truncation, not less, so it was
  dropped. The source PDE's `g(0,1)` is a genuinely local quantity (robust to a
  coarse/truncated wing — the Stage-3 payoff).
- **Gate (met):** source value matches static to ≤1 var-bp on the golden grid;
  dI/dθ + dI/da match FD; an end-to-end fit with `source_pde` hits the var-swap
  quotes to <1 var-bp; `static` (default) byte-identical. `test_varswap_source.py`
  (4 tests). Cost: one extra backward march per var-swap quote per eval
  (net-negative until Stage 3, as planned).

### Stage 3 — Calibration grid ≠ publication grid  ❌ ATTEMPTED, NOT VIABLE (2026-06-20)
- Built it: a coarse non-uniform calibration grid (fine 0.01 band across the
  quotes, coarse dead tails) + a fine **publication** solve for display + forced
  source-PDE var-swap, gated behind `coarseCalibGrid` (byte-identical off). Tried
  abrupt-4× and geometric tails, 0.1–0.3 band pads.
- **Failed the gate decisively** on the Bloomberg benchmark: the coarse
  calibration **biases θ by 0.08–0.47 in variance (up to ~26 vol points at a
  node)** — orders of magnitude over the ~2.5e-3 golden tolerance — SPY even
  produced a **nan/pathological surface**, and the speedup was modest/inconsistent
  (often negative on SPY, ~2× on NVDA). The publication re-solve does NOT fix it
  because the *θ itself* is biased: the optimizer absorbs the coarse-grid
  discretization error into the nodal variances. This re-confirms the documented
  prior rejection ([[calibration-perf]]: "coarse-grid breaks the affine surface")
  and the companion's §7.1 warning. **Reverted.**
- **Conclusion:** grid coarsening is the *only* Stage-3 lever for per-eval cost,
  and it is fundamentally unsafe for this model (the local-vol surface is the
  product output, and it's sensitive to the pricing grid). The real per-eval wins
  must come from **faster linear algebra (Stage 5)** and a **compiled march
  (Stage 6)**, not fewer grid points. Stage 4′ (grid-robust var-swap) still stands
  on its own as a correctness improvement.

### Stage 5 — Matrix-free Gauss–Newton  ✅ REVISITED & SHIPPED as the DEFAULT (2026-06-20) after Stage 6′
*(Default `lvSolver="gn"`, gated to the smooth MID fit target + Numba march; band/
haircut/var-swap fits keep trf. The user accepted the ~0.25 bp surface difference for
the ~1.3–1.65× speed. The write-up below says "opt-in" — that was the initial ship; it
was promoted to default the same day.)*
**First verdict (non-viable) was REVERSED once the march got cheap.** Originally GN
lost to TRF because it needs ~1.7× more evals AND its tight lsmr made each eval
costlier — when the march dominated. But Stage 6′ showed the per-eval split is
**optimizer/SVD 52%**, march 32%, assembly 14%: GN's whole point is to AVOID that 52%
dense SVD, and with the Numba march making each eval cheap, GN's no-SVD evals finally
win. Re-benchmarked (SPY/NVDA, numba + early-stop): **GN is ~1.3–1.65× faster than TRF**
(and on SPY gridX=20 it lands a *better* surface). Shipped **opt-in** (`OptionsSettings
.lvSolver="gn"`, default "trf") because GN converges to a slightly different local
optimum on stiff real data — surface within ~0.25 vol-bp of TRF (sometimes better),
but not identical, so the default surface is left unchanged.
- **Hardening (the key work):** GN's option-block-misfit trajectory is noisier than
  TRF's monotone trust region, so its early-stop (1) tracks the best among ACCEPTED
  iterates only (never a fluky rejected lsmr trial), (2) counts rejects as no-progress,
  and (3) uses a more conservative window/rtol (18 / 3e-3 vs TRF's 12 / 5e-3) and a
  looser inner lsmr (1e-6; 1e-10 over-solves, 1e-4 misfires). Benchmark-tuned. The
  +0.25 bp NVDA gap is INHERENT (a different local optimum), not closable by more
  conservative stopping. `gn_lsmr_tol` threaded through `calibrate_affine`;
  `affine_fit` picks GN-specific stall + lsmr; `lvSolver` in `affine_key` + Options
  selector. `test_affine_gn.py` gains the GN early-stop test (status 4, cuts evals,
  no fallback, quote-fit preserved).
- Below: the original (pre-revisit) write-up, kept for the reasoning trail.

- **What was built (correct, retained):** `volfit/models/localvol/affine_gn.py` —
  `LinearizedJacobian` (matrix-free `apply_jacobian` / `apply_jacobian_transpose` +
  `column_scale` Jacobi preconditioner) and `gauss_newton`, a projected
  Levenberg–Marquardt loop whose step is the column-preconditioned LM-damped least
  squares solved **matrix-free by `scipy.sparse.linalg.lsmr`** (no JᵀJ, no SVD; the
  column scaling is the ingredient the earlier unpreconditioned `tr_solver='lsmr'`
  lacked). Bounds via active-set projection. The three identity tests + golden/heavy
  agreement + bound-binding + TRF-fallback tests pass (`test_affine_gn.py`, 8).
- **Why it's non-viable (measured on the SPY/NVDA Bloomberg benchmark, cold-start,
  gridXNodes 12→40 = 143→440 vtx):** GN is **~1.4× SLOWER than TRF everywhere** and
  every fit shows the **TRF-fallback message** — i.e. GN does NOT converge within the
  200-eval cap and falls back. Capturing GN's own result pre-fallback (SPY, 220 vtx):
  it converges only by *ftol* at **nfev ≈ 339** (vs TRF's 200 cap) to the **same
  surface** (cost 0.32905 vs 0.32927, RMS 2.71 bp both; only 11/220 nodes at a
  bound). So GN needs ~1.7× TRF's evaluations, and its tight inner-lsmr makes each
  eval costlier. Decisively: **removing the SVD made fits SLOWER, not faster** ⇒ at
  ≤440 vertices the per-eval bottleneck is the **PDE sensitivity march**
  (O(N_t·N_x·m), shared by both solvers), *not* the SVD. The SVD-O(m³) wall is a
  ≳1000-vertex (bowtie) phenomenon that the current tensor grid never reaches; and
  TRF's exact bounded trust-region simply out-converges the projected-LM on the
  stiff, large-residual real problem. The clean perf rail (synthetic, zero-residual,
  in-bounds ⇒ GN converges in 8 evals) hid all of this.
- **Disposition:** the `lvSolver` Options field + UI selector + `affine_fit` wiring
  were removed; the app always uses TRF. `affine_gn.py`, `calibrate_affine(gn=)`,
  its tests, and the synthetic perf rail remain as the bowtie-regime seed.
- **Lesson:** the real per-eval win is the **PDE march itself → Stage 6 (Numba)**,
  not the outer linear algebra. Revisit matrix-free GN only alongside the non-tensor
  bowtie grid (Stage 5's original "true delta point-cloud" half), where m is large
  enough that the SVD actually dominates AND an adjoint removes the m-factor PDE cost.

### Stage 6 — Numba march, first attempt  ❌ ~1.2× (column-outer scalar Thomas)
- A first `@njit` Thomas march (numerically exact) gave only **1.1–1.26×** on the
  march. **Cause (mis-diagnosed at the time as "LAPACK is optimal"): the kernel
  looped column-OUTER, scalar** — a per-column Thomas that couldn't beat LAPACK's
  vectorised multi-RHS solve, and its dense `nu = phi·theta` loop LOST to BLAS. The
  real opportunity (Stage 6′) was the loop ORDER. Reverted at the time.

### #3 — Sparse reg block in the GN Jacobian operator  ✅ DONE (2026-06-20)
- After the SVD is gone (GN) and the march is cheap (Numba), the per-eval cost is the
  Jacobian assembly + the lsmr matvec. The roughness / convex / front-tie rows are
  3-nnz/row but were assembled dense and `vstack`'d. `LinearizedJacobian` now carries a
  **dense data block over a SPARSE (CSR) reg block**: `apply_jacobian` /
  `apply_jacobian_transpose` / `column_scale` combine the two, so the reg matvec is
  O(nnz) not O(M_reg·m) and no dense reg is materialised. `gauss_newton` was refactored
  onto the operator abstraction; `calibrate_affine` builds the sparse operator for the
  GN-eligible case (mid, no var-swap, no left slope), constant roughness/front rows as
  CSR once, the convex block sparse per-eval. **Numerically identical** to the dense
  path (output to the bit); a GN→TRF fallback densifies via `to_dense`. Behind the
  `_GN_SPARSE_REG` rollback flag.
- **Measured (A/B, GN default):** negligible at ~220 vtx (~1.03×) but **~1.29× at
  ~440 vtx** (the dense reg matvec is O(m²), so it pays as the grid grows). drms 0.000.
  `test_affine_gn.py` +2 (operator identity vs dense, sparse==dense calibrated surface).

### Stage 6′ — Numba vectorized-Thomas march  ✅ SHIPPED (2026-06-20) — 6.5× the banded march
- `volfit/models/localvol/affine_march.py`: a `@njit(cache=True, nogil=True,
  fastmath=True)` value+sensitivity march that **beats scipy/LAPACK ~6× on the
  march** by exploiting what `dgbsv` cannot:
  * **no-pivot Thomas** (factor-once, shared by the value + every sensitivity
    column) — our M-matrix needs no pivoting/fill, so ~⅓ of `dgbsv`'s flops;
  * the **k RHS columns are the CONTIGUOUS INNER loop** of the forward/back sweeps
    ⇒ SIMD across columns (the sweeps are sequential only in strike);
  * the sensitivity **source fused into the forward sweep** (no dense `rhs_s`,
    no per-step `scipy` call / allocation).
  Numerically exact vs banded (prices/sens ≈1e-15). Measured march: **6.1–6.9× at
  220–440 vtx** (banded 94/139/184 ms → 14/23/29 ms). The earlier 1.2× was purely
  the wrong loop order (column-outer scalar).
- Wired via `solve_affine_dupire(engine="banded"|"numba")` (self-restricts to the
  implicit / no-left-slope / sensitivity path, else falls back to banded),
  `precompute_dupire_steps` storing the basis as one contiguous `(n_steps, n_int, m)`
  array (banded indexes views ⇒ byte-identical golden), `calibrate_affine(engine=)`,
  `OptionsSettings.lvFastKernel` (default ON, in `affine_key`) + Options toggle, and
  `numba` added to `pyproject` deps with a **graceful import-guard fallback** to
  banded. `test_affine_march.py` (5).
- **Whole-fit leverage is Amdahl-bounded** — the march is only **~32%** of each eval
  (measured SPY gridX=20: pde_sensitivity 32%, residual_assembly 14%, **optimizer_
  outer 52%**, pde_value 2%). So the 6.5× march → **~1.3× whole-fit on its own**, and
  combined with the Stage-8 early-stop (shipped) → **1.7× (SPY) to 3.8× (NVDA)** on
  the cold fit. **The new dominant cost is the optimizer (scipy trf's dense SVD /
  trust-region, 52%)** — the next lever if more is wanted (early-stop already attacks
  it by cutting the eval count).

### Stage 7 — Rannacher 2nd-order time stepping  ⚠️ BUILT but only ~1.1× + arb risk — default OFF
- **Built + validated:** Crank–Nicolson after 2 implicit-Euler kink-damping start-up
  steps, in `solve_affine_dupire(time_scheme="rannacher")` with the full analytic CN
  sensitivity recurrence (the dual-level ½Δt·dA sources + the explicit-half operator
  on the previous sensitivities). Confirmed 2nd-order: at dt=0.02 Rannacher's price
  error vs a time-converged reference is **21× smaller** than implicit Euler's
  (1.3e-5 vs 2.6e-4); analytic sensitivities match FD to ~3e-11; golden byte-identical
  on the implicit default. Gated `timeScheme`, folded into `affine_key`.
  `test_affine_time_scheme.py` (5).
- **Why only ~1.1× (the surprise):** on the SPY/NVDA benchmark Rannacher cut the time
  steps **2.7–2.8×** (N_t 102→37, 52→19) at equal RMS (±0.1 bp) — but **total speed-up
  was only ~1.12×**. The **CN sensitivity step is ~2× costlier per step** than implicit
  (an explicit-operator matvec on the previous sensitivities + two dual-level source
  terms + the solve = 4 dense O(N_x·m) ops, vs implicit's 2), so ~2.7× fewer steps ×
  ~2× per step ≈ break-even; the non-march cost (assembly + optimizer SVD, N_t-
  independent) dilutes the rest. **And CN is not monotone** (no M-matrix), so on the
  coarse-x NVDA gridX=12 grid it produced a small arbitrage violation. So Rannacher is
  **default OFF**, kept as a tested opt-in (`timeScheme`).
- **The deeper lesson (4th underdelivering approach — Stages 3,5,6,7):** the cold-fit
  cost is *distributed* roughly evenly across the march, the residual/Jacobian
  assembly, and the optimizer linear algebra. No single per-eval/per-step lever moves
  the total much because the others dilute it. **The only lever that scales the whole
  fit is fewer evals** — see Opportunistic below.

### Stage 8 — Stall-based early-stop  ✅ DONE (2026-06-20) — THE win that scales the whole fit
- `calibrate_affine(stall_window=, stall_rtol=)`: track the best OPTION-BLOCK misfit
  (the quote-fit quality, excluding the always-changing roughness penalty) across trf
  objective evals; raise `_StallStop` once it has not improved by `stall_rtol`
  (relative) over `stall_window` evals, and return the **best-cost iterate** (never
  worse than the stall point). `stall_window=0` (default) ⇒ byte-identical. Wired via
  `OptionsSettings.lvEarlyStop` (default ON, folded into `affine_key`) +
  `affine_fit._STALL_WINDOW=12` / `_STALL_RTOL=5e-3` + an Options toggle.
- **Why this is the lever that works** (where 3/5/6/7 failed): fewer evals multiply
  march + assembly + optimizer *together*, so it scales the whole fit. **Measured
  (SPY/NVDA gridX=20, vs the full 200-eval fit):** fast-converging NVDA (a clear
  convergence knee) → **3.3×** (16.8→5.1 s, nfev 200→41) at +0.25 bp; slow-converging
  SPY (no knee, keeps improving) → **1.45×** (31.2→21.5 s, nfev 200→109) at +0.10 bp.
  Adaptive by design — it stops when a fit has converged and keeps going while it is
  still improving. Warm-started recalibrations
  converge before the window, so they are unaffected (Stage 2a already made them ~1
  eval). `test_affine_early_stop.py` (3): disabled byte-identical, cuts evals + keeps
  surface, reports the stall status.
- Stacks with everything else (it is orthogonal to the march/optimizer). Rannacher
  (Stage 7, opt-in) would compound on top if enabled.

### Opportunistic (independent)
- **Across-ticker parallelism** in the calibration job (was Stage 6's second half;
  pure-Python intra-fit threads are GIL-negative, but the per-ticker work-items
  could run on a process pool — Windows-spawn caveats apply).
- **Adaptive vertex grids** (two-pass) — last; complicates cache keys and
  warm-start interpolation.

---

## Sequencing summary

Realised: `Stage 0 ✅ → 1 ✅ → 2a ✅ → 4′ ✅ → 3 ❌ → 6 ❌ → 6′ ✅ (6.5× march) → 8 ✅ (early-stop) → 5 ✅ (GN, now DEFAULT after the march got cheap) → 7 ⚠️ (opt-in) → 2b ✅ (#1 cold-start seed) → #3 ✅ (sparse reg)`.
The consolidated reference is `localvol_calibration_methodology.md`.
Stages 0–2a took the default grid faster and recalibration ~instant; 4′ made the
var-swap grid-robust. **Four approaches to cut the per-eval / per-step cost all
underdelivered for the same reason** — the cold-fit cost is *distributed* roughly
evenly across the PDE march, the residual/Jacobian assembly, and the optimizer linear
algebra, so killing any single one is diluted by the others: **3** (coarse grid)
biased θ; **5** (matrix-free GN) needs more evals than TRF; **6** (Numba march) is
exact but only ~1.2× (LAPACK already optimal); **7** (Rannacher) cuts N_t 2.7× but the
heavier CN sensitivity step ~cancels it (~1.1× net) and CN broke arb on a coarse grid.
**The one lever that scales the WHOLE fit is fewer evaluations** — Stage 8's
stall-based early-stop (✅ shipped) multiplies march+assembly+optimizer together:
3.3× on fast-converging names (NVDA), 1.45× on slow ones (SPY) — adaptive, +0.10–0.25
bp cost, and it stacks with everything. The mathematical contract and the golden example stay
intact throughout.

## Invariants (every stage)
- Golden example within tolerance — the local-vol surface *is* product output, so
  test both price/IV fit **and** nodal-θ stability.
- Arbitrage-freedom preserved (`_diagnostics`: min density ≥ 0, no calendar
  violations); any new pricer/time-stepper must keep it.
- Nodal positivity ⇒ surface positivity; a sigmoid reparmeterisation must keep
  the same effective `[var_lo, var_hi]` box.
- Determinism: no randomised solvers without a fixed seed; keep `affine_key`
  caching valid.
- Gate every perf claim with a `test_perf.py` budget entry.

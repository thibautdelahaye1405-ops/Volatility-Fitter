# Local-Vol Calibration — Compute-Time Implementation Roadmap

*Roadmap — 2026-06-20. Builds on `localvol_calibration_perf_note.md` (current
implementation + idea list) and `localvol_calibration_perf_companion.md`
(sharpened diagnosis + work packages). This file is the agreed build order:
stages, refinements, and per-stage acceptance gates. Status is tracked inline.*

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

### Stage 2b — Parametric Dupire cold-start seed  *(deferred)*
- Seed the *first* fit (no previous surface) from the parametric implied surface
  via `dupire.extract_grid` at the vertices (nan-fill + clip). Needs a 2D
  `w(k,T)` surface assembled from the per-expiry parametric fits (interp in T) and
  careful noise handling — the companion (§6.4) flags Dupire-from-implied as
  noisy, so it must be a *seed only*. Lower value than 2a (cold starts are rare)
  and higher risk, so split out for its own validation.
- **Gate:** same final IV quality vs flat cold-start; `nfev` ↓ on first fit; safe
  fallback when the parametric surface is missing/unstable (bad-seed test); golden
  byte-identical (no parametric surface in the model-layer golden case).

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

### Stage 5 — Matrix-free Gauss–Newton  ⚠️ BUILT but NON-VIABLE on real data (2026-06-20) — shelved, gated off
**The premise (dense SVD = the heavy-grid wall) does NOT hold at the current
tensor-grid sizes.** Built and tested, but the real-data benchmark shows it loses to
dense TRF, so it is kept gated off (`calibrate_affine(gn=...)` only, no app wiring) as
a seed for the future ≳1000-vertex non-tensor bowtie, where the SVD genuinely
dominates.

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

### Stage 6 — Numba `nogil` march  ❌ ATTEMPTED, NOT WORTH IT (~1.2×) — reverted
- Built a `@njit(nogil=True, cache=True)` Thomas-factor-once value+sensitivity
  march (numerically EXACT vs the banded path — prices/sens matched to ≈1e-15) and
  benchmarked it on the production PDE grid. **Speedup was only 1.1–1.26× at
  220–440 vertices** (2.3× only on the tiny 21-vtx golden), and a cache-friendly
  transposed `(m, n_x)` layout did not move it.
- **Why:** the per-eval cost is the **irreducible O(N_t·N_x·m) multi-RHS
  sensitivity solve**, which LAPACK (`solve_banded`) already executes at near-optimal
  efficiency; a hand-rolled compiled Thomas matches but cannot beat it by more than
  ~20%, and the dense `nu = phi·theta` / RHS-build (the parts compilation *could*
  speed up) are not the dominant term. A 40 MB+ `numba`/`llvmlite` dependency for
  ~1.2× is not worth it on this flaky-PyPI Windows box.
- **Reverted:** `affine_march.py` removed, `numba`/`llvmlite` uninstalled. (The
  validated kernel logic is recorded here should a future regime change the maths.)
- **Lesson (third of three on this axis, with Stages 3 & 5):** the per-eval PDE
  march cannot be shaved by better linear algebra or compilation — it is inherent
  and already efficient. **The remaining real levers change the problem:** fewer
  evals (the cold fit caps at 200 but the last ~80–120 evals buy <0.1 bp — measured),
  or fewer time steps at equal accuracy (Rannacher), or fewer vertices.

### Stage 7 — Rannacher 2nd-order time stepping  *(CHOSEN next — the real structural win)*
- Backward-Euler is 1st-order and forces dt ≤ 0.01 (~250 steps) to control the
  payoff-kink error at x=1. Replace with **Crank–Nicolson + Rannacher start-up**
  (2 implicit-Euler half/full steps to damp the kink, then CN): 2nd-order, so the
  same accuracy is reached at **~2–4× larger dt ⇒ ~2–4× fewer time steps in every
  eval** — quality-neutral by construction (better per-step accuracy, not coarsening
  the data grid as Stage 3 did). Cuts N_t in the O(N_t·N_x·m) march directly.
- The CN sensitivity recurrence carries two stencil terms (½Δt·dA at levels n and
  n+1) vs implicit Euler's one; the per-step tridiagonal factor (I − ½Δt A^{n+1})
  is the same banded solve. Gated `timeScheme="implicit"|"rannacher"`, default
  implicit ⇒ golden byte-identical.
- **Gate:** convergence-order test (Rannacher at coarse dt ≈ implicit at fine dt ≈
  the note's true prices); analytic sensitivities vs FD under CN; arb-free
  (`_diagnostics` min density ≥ 0, no calendar violations); golden unchanged on the
  implicit default; perf rail showing the N_t reduction.

### Opportunistic (independent)
- **Eval-cap / early-stop**: the cold fit's last ~80–120 evals buy <0.1 bp — a
  stall-based stop or lower `max_nfev` is a cheap ~1.5–2× cold-fit win (measured;
  small quality cost).
- **Across-ticker parallelism** in the calibration job (was Stage 6's second half;
  pure-Python intra-fit threads are GIL-negative, but the per-ticker work-items
  could run on a process pool — Windows-spawn caveats apply).
- **Adaptive vertex grids** (two-pass) — last; complicates cache keys and
  warm-start interpolation.

---

## Sequencing summary

Realised: `Stage 0 ✅ → 1 ✅ → 2a ✅ → 4′ ✅ → 3 ❌ → 5 ⚠️ (shelved) → 6 ❌ → 7 (Rannacher, chosen)`.
Stages 0–2a took the default grid faster and recalibration ~instant; 4′ made the
var-swap grid-robust. **Three approaches to cut the per-eval cost all failed for the
same reason** — the per-eval forward-sensitivity PDE march is inherent and already
LAPACK-efficient: **3** (coarse grid) biased θ; **5** (matrix-free GN) needs more
evals than TRF and the SVD isn't the bottleneck at tensor-grid sizes; **6** (Numba
march) is numerically exact but only ~1.2× (LAPACK already optimal). So the work
turned to levers that change the *problem*: **Stage 7 (Rannacher 2nd-order time
stepping)** cuts N_t at equal accuracy — the chosen structural win — with eval-cap
early-stop as a cheap complementary lever. The mathematical contract and the golden
example stay intact throughout.

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

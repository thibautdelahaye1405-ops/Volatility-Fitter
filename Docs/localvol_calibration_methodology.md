# Local-Volatility (Piecewise-Affine) Calibration — Methodology & Optimisation

*Standalone technical note — 2026-06-20. Describes the Local-Vol calibration as it
now stands: the model, the pricing map, the calibration objective, the grid, the two
solvers, every shipped optimisation, and everything that was tried and shelved (with
the reason). Self-contained: readable without the companion roadmap files. The
chronological build order and per-stage acceptance gates live in
`localvol_calibration_perf_roadmap.md`; the original idea list in
`localvol_calibration_perf_note.md`. This note is the consolidated reference.*

---

## 0. Scope

The **Local-Vol workspace** fits a *continuous piecewise-affine local-variance
surface* ν(t, x) directly to a ticker's option (and optional variance-swap) quotes by
pricing every quote through the **forward Dupire PDE** and minimising a weighted
least-squares misfit. It implements the Andreasen–Huge philosophy with a P1
finite-element parameterisation (`piecewise_affine_local_variance_calibration.tex`).

It is **distinct** from `GET /localvol/{ticker}`, which merely *extracts* a Dupire
grid from already-fitted parametric (LQD/SVI/sigmoid) smiles via Gatheral's formula.
The affine calibration is the inverse problem — find the local-variance surface whose
forward prices reproduce the market — and is the heavy compute path in the app.

Code map:

| Concern | File |
|---|---|
| P1 surface, basis, implicit/CN Dupire pricer + forward sensitivities | `backend/volfit/models/localvol/affine.py` |
| Numba vectorised-Thomas march (the compiled hot path) | `backend/volfit/models/localvol/affine_march.py` |
| LSQ objective, roughness/convex/front-tie operators, var-swap, the TRF+GN drivers, early-stop | `backend/volfit/models/localvol/affine_calib.py` |
| Matrix-free Gauss-Newton (operator, projected LM, lsmr step) | `backend/volfit/models/localvol/affine_gn.py` |
| Backward source-PDE variance swap | `backend/volfit/models/localvol/varswap_pde.py` |
| Orchestration: grid build, quote prep, bounds, seeds, caching, reconstruction | `backend/volfit/api/affine_fit.py` |
| Gatheral local-variance extraction (also feeds the cold-start seed) | `backend/volfit/models/localvol/dupire.py` |

---

## 1. The model — P1 piecewise-affine local variance

The surface is `ν_θ(t, x) = Σ_ℓ θ_ℓ φ_ℓ(t, x)` on a **tensor-product vertex set**
`(t_nodes × x_nodes)`, where:

- `x = K / F(0, t)` is **normalised strike** (driftless-martingale forward moneyness):
  prices are undiscounted forward calls `c(T, x) = E[(X_T − x)⁺]`, `X₀ = 1`. Rates and
  dividends enter only through the forward `F`; puts are parity-converted.
- `θ` is the flat vector of **nodal local variances** (t-major), the optimisation
  unknown. Nodal positivity ⇒ surface positivity by barycentric interpolation, so the
  box bounds on θ are also bounds on ν.
- `φ_ℓ` are P1 hat functions. Triangulation is a cached qhull **Delaunay** of the
  tensor vertices (the convention that reproduces the note's published table to every
  printed decimal). Off-hull: the **right wing is flat-clamped**; the **left wing
  continues LINEARLY** below `x_min` with slope `a × (first-cell slope)`
  (`left_extrap_a`), so the deep-put local variance keeps rising toward `x → 0`.
- The diffusion clock is the **event-weighted variance time τ** (`prepared.tau`), not
  calendar `t`: events lower the reconstructed IVs consistently with the Parametric fit.

---

## 2. The pricing map — forward Dupire PDE

`solve_affine_dupire` marches `∂_T c = ½ ν(T, x) x² ∂_xx c`, `c(0, x) = (1 − x)⁺`,
Dirichlet `c(·, 0) = 1`, `c(·, x_max) = 0`, on:

- **Spatial grid** (`_pde_grids`): uniform `x = {0, 0.01, 0.02, …}` to
  `x_max = max(e^{k_hi}·1.4, 2.5)` — so `x = 1` (the var-swap anchor) is always a node;
  ~251 nodes typically. Non-uniform central second difference.
- **Time grid**: every quoted expiry forced onto the grid, refined to `dt ≤ dt_max`
  (0.01 implicit / 0.03 Rannacher) ⇒ ~100–250 steps.
- **Step**: fully implicit (backward) Euler `(I − Δt·A^{n+1}) U_I^{n+1} = U_I^n +
  boundary`, a tridiagonal solve — unconditionally stable **M-matrix** (no pivoting
  needed), first order in time, no Rannacher kink smoothing by default.

### 2.1 Sensitivities

`sensitivities=True` propagates the full `dU/dθ` by the discrete sensitivity recursion
— the **same tridiagonal factor per step**, multi-RHS. The optimiser thus gets an
analytic Jacobian from one sensitivity-carrying solve per trial θ. Two precompute
tricks: the **θ-independent hat basis** `φ[n]` is hoisted out of the per-eval loop
(`precompute_dupire_steps`, stored as one contiguous `(n_steps, n_int, m)` array), and
`active_k[n]` restricts the sensitivity solve to the **live column prefix** (a vertex's
column is exactly zero until the march reaches its hat support — bit-identical, cheaper).

Cost per evaluation ≈ `O(N_t · N_x · m)`, dominated by the **multi-RHS sensitivity
solve**.

---

## 3. The calibration objective

`calibrate_affine` builds a bound-constrained weighted LSQ residual vector — a **data
block** over a **regularisation block**:

1. **Option block** — mid `(P − y)/η`, or in bid-ask/haircut mode a band-violation
   hinge + soft mid anchor (`calib/band.py`). `η = vega·VOL_TOL/√weight` ⇒ residuals
   ≈ vol-error, with the quote-weighting scheme (equal / TV-density) folded in.
2. **Var-swap block** — `(Z − z)/ζ` in total variance. `Z` by static log-contract
   replication (default) or the backward **source PDE** `g(0,1)` (grid-robust).
3. **Roughness** — `√λ · L(θ − θ_ref)`, the **spacing-aware** second-difference operator
   on the real vertex positions (reduces to the index-space `(1,−2,1)` on a uniform
   grid). `θ_ref` is a flat reference (decoupled from the warm-start seed — see §6.2).
4. **Convex-wing** hinge — `√W·relu(−D²σ)` penalising concavity of the vol row below
   ~5Δ, confined to the *extrapolation* tail (vertices below the deepest quote).
5. **Front-tie** — `√W·(θ[0,:] − θ[1,:])` pinning the unconstrained `t = 0` row to the
   first data-identified row.

Box bounds `[v_lo, v_hi]` are **adaptive**: `v_hi = max(60%², (lvVolCapMult·max-IV)²)`
capped at (400%)², so high-vol names' deep-put local variance is not clamped. The
left-wing slope `a` is a free parameter when a var-swap quote is present (analytic
`dPrice/da`), else fixed.

---

## 4. Grid construction

- **Strike vertices** (`_delta_strike_nodes`, default): the symmetric delta set
  `{1,2,5,10,25,40,50}Δ` mapped to standardised log-moneyness `k = ±σ*·√T*·Φ⁻¹(δ)`,
  clipped to the observed `[k_lo, k_hi]` with `x = 1` forced in. `gridXNodes` is a
  **floor**: the single widest gap is split one node at a time until reached (the same
  incremental scheme as the time axis — *not* the old doubling, which overshot the
  floor non-monotonically and gave similar names wildly different resolutions).
- **Short-expiry strike coverage floor** (`_augment_per_expiry_coverage`,
  `gridXMinPerExpiry`, default 8; **fix #1**): the delta axis above is sized to the
  *longest* expiry's `σ*·√T*` and clipped to the *global* `[k_lo, k_hi]`, so a narrow
  **short** smile lands only a handful of vertices on its sharpest curvature — a real,
  measured failure: a 6-DTE SPY weekly got 3/13 in-range vertices and **108 bp** LV
  RMS (vs the parametric ~47 bp), dropping to ~28 bp once it reaches ~8. After the
  axis is built, `_resolve_grid` splits the widest **in-range** gaps until *each*
  expiry has at least `gridXMinPerExpiry` vertices inside *its own* traded
  `[k_lo, k_hi]`. This densifies **only under-covered (short-front) expiries** — a
  well-covered normal expiry already meets the floor and is untouched (often
  byte-identical). Even gap-fill is used deliberately: clustering the expiry's *own*
  delta nodes instead left wing gaps and stalled at ~37 bp. `0` ⇒ the legacy axis.
- **Time vertices** (`_time_nodes`): `0` + a short-end node at `T₁/4` + every lit
  expiry, densified in √T to the `gridTNodes` floor (never dropping an expiry). NB:
  adding *more* time vertices ahead of a weekly does **not** help its fit — a single
  expiry constrains only the time-*integral* of local variance over `[0, τ₁]`, so
  extra front rows are unconstrained DOF (measured flat); the short-end lever is
  strike resolution, not time resolution.
- **PDE strike step** (`_pde_dx`, **fix #2**): the *fine* PDE lattice (§2) is a
  uniform `dx` shared by all expiries. The fixed `dx = 0.01` under-resolves a
  short-dated density, which concentrates near `x = 1` (a 6-DTE weekly lives in
  `x ∈ [0.93, 1.06]` — only ~13 nodes). `_pde_dx` refines `dx` to a fraction of the
  smallest ATM `σ√τ` across the lit expiries, **snapped to `1/N`** so the var-swap
  anchor `x = 1` stays node `N`. Originally `0.3 ×` clamped to `[1/400, 0.01]`;
  **since 2026-07-11 (daily-ladder pass): `0.15 ×`, capped at 800 nodes** — on 2-DTE
  dailies the quote spacing is finer than the lattice and the drawn smile wiggled at
  quote frequency until the step out-resolved it. A normal surface lands back on
  `0.01` ⇒ byte-identical.
- **2026-07-11 daily-ladder amendments** (the current short-end stack, Note 04 §3):
  - *Adaptive variance floor*: `ν_lo = min(request floor, (0.5·min ATM σ)²)`
    (`_LV_VOL_FLOOR_FRAC = 0.5`) — a low-vol short smile needs local vol below its
    minimum implied; the fixed 5% floor was measured riding the box on SPY 2-DTE
    upside quotes. ATM-keyed so noisy deep-wing quotes cannot drag the floor.
  - *PDE time refinement*: any short maturity interval that would receive fewer than
    8 implicit steps at the `dt = 0.01` ceiling is marched with 32 steps
    (`_PDE_NT_FIRST_GATE = 8`, `_PDE_NT_SHORT = 32`) — a 2-day interval otherwise
    gets one.
  - *Even-gap coverage* (expiries ≤ 10 days, `_COVERAGE_GAP_MAX_T`): the count floor
    is side-blind, so for short expiries the widest boundary-augmented gap is split
    until none exceeds `range/(gridXMinPerExpiry − 1)` — the daily front stopped
    drawing a V through its call quotes.
  - *Chained front tie* (fronts < 0.08y, `FRONT_TIE_SHORT_T`): the tie extends over
    every sub-front vertex row at effective weight ≥ 1 (`FRONT_TIE_CHAIN_WEIGHT`,
    up from the 1e-2 user default) — quotes pin only the variance integral to `T₁`,
    and the untied rows rang 5–30 vol points against each other.
- The grid build is one shared `_resolve_grid`, also surfaced read-only on
  `GET /fit/affine/{ticker}/grid-info` so the Options panel shows the exact grid.

---

## 5. The two solvers

The objective `½‖r(θ)‖²` is minimised subject to box bounds by one of:

### 5.1 TRF — scipy trust-region (`method="trf"`)

The legacy solver. Builds the **dense** `(M_resid × m)` Jacobian each evaluation and
does a **dense SVD** in the bounded trust-region subproblem. `x_scale='jac'` and 1e-8
tolerances (Stage 1). Robust for non-smooth objectives (the bid-ask/haircut band
hinge) and for the free-left-slope var-swap fits. Used today for: band/haircut fits,
var-swap fits, the banded-march fallback, and as the GN fallback.

### 5.2 GN — matrix-free Gauss-Newton (`affine_gn.py`, the DEFAULT)

A **projected Levenberg-Marquardt** loop that **avoids the dense SVD**. Each step
solves the LM-damped, column-preconditioned linear least squares **matrix-free by
`scipy.sparse.linalg.lsmr`** (no JᵀJ, no SVD):

- **`LinearizedJacobian`** is the operator: a top **dense data block** over an optional
  **sparse CSR regularisation block** (`#3`), exposing `apply_jacobian` (Jv),
  `apply_jacobian_transpose` (Jᵀw), and `column_scale` (the Jacobi preconditioner
  `1/‖col‖` — the missing ingredient behind the earlier unpreconditioned
  `tr_solver='lsmr'` failure). The reg matvec is then `O(nnz)`, not `O(M_reg·m)`.
- **Bounds** via active-set projection (clip + projected-gradient convergence).
- The inner `lsmr` tol is loose-ish (1e-6 in the app): the cheap Numba march makes
  extra *outer* iterations affordable, so accuracy in the inner solve is traded for
  fewer expensive marches; 1e-10 over-solves, 1e-4 misfires the early-stop.
- **Early-stop** (§6.5) terminates at the best *accepted* iterate when the
  option-block misfit stalls; **falls back to dense TRF** on a numerical breakdown.

GN is the default but **gated to the smooth MID fit target with the Numba march
active**; otherwise the fit uses TRF. The trade-off accepted at the default: GN
converges to a slightly *different* local optimum on stiff real data, so its surface
can differ from TRF's by up to **~0.25 vol-bp** (often better) — an inherent
property, not an early-stop artifact.

---

## 6. Shipped optimisations

Roughly chronological. The **eval-cost identity** that organises them: per evaluation,
cost ≈ **optimizer/SVD (≈52% for TRF) + PDE sensitivity march (≈32%) + Jacobian
assembly (≈14%) + value solve (≈2%)** (measured, SPY gridX=20). Total fit cost = (per-
eval) × (eval count). Levers attack one factor each; the wins compound.

### 6.1 Stage 0 — instrumentation
`AffineFitDiagnostics` (counts, optimizer counters, wall-time split) on the result,
never fed back. `solve_affine_dupire(timing=)`. Pure side metadata; golden byte-identical.

### 6.2 Stage 1 — solver scaling & tolerances
`x_scale='jac'` + tolerances 1e-12 → 1e-8 on the TRF path. The fit is governed by quote
noise / vega / bands, so 1e-12 only bought iterations. nfev cut, surface identical.

### 6.3 Stage 2a — warm start from the previous surface
`_seed_theta` seeds `θ₀` from the previous calibrated surface (direct reuse on a matching
grid, else interp), `θ_ref` pinned flat so the **regularisation is unchanged and a flat
seed is byte-identical**. Recalibration nfev 19→1, ~38× faster. This is why
**recalibrations are ~instant** and only *cold* fits are slow.

### 6.4 Stage 2b — parametric Dupire cold-start seed (`#1`)
A **cold** fit seeds θ from the **parametric surface's Dupire local variance** at the
vertices: build the displayed-model total-variance surface `w(k, t)` from the
already-calibrated LQD/SVI/sigmoid slices (cached lookup — never triggers a fit) and
read its Gatheral local variance via `dupire.extract_grid` (`k = log x`, `t` = the τ
vertices, nan-fill + clip). `θ_ref` stays flat (seed-only), so the converged optimum is
unchanged. **Measured:** nfev 84→66 / 64→36 / 159→80 and ~1.7× less lsmr work from the
better-conditioned start ⇒ **~1.3–1.8× on the cold fit**. Data-dependent (large on real
skewed surfaces, neutral on smooth synthetics). Falls back to flat when < 2 parametric
slices are calibrated.

### 6.5 Stage 8 — stall-based early-stop
The cold fit otherwise runs to the 200-eval cap, but its last ~80–120 evals move the
surface < 0.1 vol-bp. The solver now tracks the best **option-block misfit** (the
quote-fit quality, *excluding* the always-changing roughness penalty) and stops once it
has not improved by `stall_rtol` over `stall_window` evals, **returning the best
iterate**. Adaptive: fast-converging names (a clear knee, e.g. NVDA) stop early (→ ~3×),
slow names (no knee, e.g. SPY) run longer (→ ~1.45×), at +0.1–0.25 bp. `stall_window = 0`
⇒ byte-identical. *Fewer evals multiply march + assembly + optimizer together*, so this
is the lever that scales the whole fit. The GN flavour tracks the best **accepted**
iterate only (never a noisy rejected lsmr trial), counts rejects as no-progress, and
uses a more conservative window/rtol (18 / 3e-3 vs TRF's 12 / 5e-3).

### 6.6 Stage 6′ — Numba vectorised-Thomas march (the headline per-eval win)
`affine_march.py` replaces the per-step `scipy.linalg.solve_banded` with one
`@njit(nogil, cache, fastmath)` value+sensitivity march that **beats LAPACK `dgbsv`
~6×** by exploiting structure the general band solver cannot:
- **no-pivot Thomas** (our diagonally-dominant M-matrix needs no pivoting/fill — ~⅓
  of `dgbsv`'s flops; factor once, shared by value + every sensitivity column);
- the **k RHS columns are the contiguous INNER loop** of the forward/back sweeps ⇒
  **SIMD across columns** (the sweeps are sequential only in strike);
- the sensitivity **source fused into the forward sweep** (no dense `rhs_s` temp, no
  per-step scipy call, no per-step allocation).
Numerically exact vs banded (≈1e-15). Measured **6.1–6.9× at 220–440 vtx** (94/139/184
ms → 14/23/29 ms). Engine-gated (`engine="numba"`), self-restricts to the implicit /
no-left-slope / sensitivity path and **falls back to banded** otherwise or when numba is
unavailable. Basis stored contiguous so the banded path indexes views (golden
byte-identical). `numba` is a dependency with a graceful import-guard fallback.

### 6.7 Stage 5 — matrix-free Gauss-Newton (the default solver)
See §5.2. The key story: GN was first judged non-viable (it needs ~1.7× TRF's evals,
and when the *march* dominated, removing the SVD didn't help). Once Stage 6′ made the
march cheap, the profile showed the **optimizer SVD is 52%** of an eval, so GN's
SVD-avoidance finally wins (~1.3–1.65× over TRF). Promoted to the default, mid-mode.

### 6.8 `#3` — sparse reg block in the GN operator
With the SVD gone and the march cheap, the per-eval cost is the assembly + lsmr matvec.
The roughness/convex/front-tie rows are 3-nnz/row but were assembled dense. The
`LinearizedJacobian` now keeps them **sparse** (constant rows as CSR once, the convex
block sparse per-eval). Numerically identical; ~1.03× at 220 vtx but **~1.29× at 440
vtx** (the dense reg matvec is `O(m²)`, so it pays as the grid grows). Behind the
`_GN_SPARSE_REG` rollback flag.

### 6.9 Stage 4′ — source-PDE variance swap
A backward source PDE `g(0,1)` prices the model var-swap as a *local* quantity robust to
a coarse/truncated strike grid (vs the `k⁻²`-weighted static replication), with analytic
`dI/dθ` and `dI/da`. Gated `varSwapMethod`; default static (byte-identical).

### 6.10 Quality fixes (not speed, but shipped on this branch)
- **Strike-grid densification fix**: widest-gap-at-a-time instead of doubling, so
  similar names land on the same `gridXNodes` floor (was 11×21 vs 11×37).
- **Convex-wing × fine-grid regression**: the constraint selected every vertex ≤ 5Δ
  regardless of data; confined to the unquoted extrapolation tail (SPY 26→2.6 bp).
- **Adaptive local-vol cap**, **left-wing linear extrapolation**, **delta strike axis**,
  **spacing-aware roughness**, **√T time axis + front tie** — all detailed in the
  roadmap's "Done & verified" log.
- **Short-dated fit (fixes #1/#2, §4)**: the per-expiry strike coverage floor
  (`gridXMinPerExpiry`) + adaptive PDE step (`_pde_dx`) took a true 6-DTE SPY weekly
  from **108 → 23.5 bp** (better than the parametric ~47 bp), normal names
  byte-identical / slightly better. Diagnosed by the Phase-0 per-expiry
  diagnostics (`api/affine_diag.py`) on a true-weekly Massive capture
  (`capture_massive_weekly.py`).

### 6.11 Cumulative result
Default path (strike-grid fix → Numba march → early-stop → GN → parametric seed → sparse
reg): the LV **cold** fit is roughly **3–6× over the original banded baseline**, scaling
with grid size; **recalibrations were already ~instant** (Stage 2a). Golden example
byte-identical throughout.

---

## 7. What was shelved, and why

Negative results are kept here so they are not re-explored. The recurring lesson: the
per-eval PDE march is *inherent and already efficient*, and the cold-fit cost is
*distributed*, so no single per-eval/per-step trick moves the total — only changing the
problem (fewer evals, fewer steps at equal accuracy) or the dominant factor (the SVD,
once the march is cheap) helps.

| Idea | Verdict | Why |
|---|---|---|
| **Stage 3 — coarse calibration grid** | ❌ reverted | Coarsening the PDE grid biased θ by 0.08–0.47 in variance (up to ~26 vol-pts/node, ≫ tolerance), SPY went nan. The local-vol surface *is* the product output; the publication re-solve can't fix a θ the optimizer biased into the coarse-grid discretisation error. |
| **Stage 6 — first Numba attempt** | ❌ ~1.2×, rebuilt | A column-OUTER scalar Thomas couldn't beat LAPACK's vectorised multi-RHS solve, and its dense `nu` loop lost to BLAS. The *loop order* was the whole problem — fixed in Stage 6′ (column-inner SIMD), which got 6.5×. |
| **Stage 7 — Rannacher (CN) time stepping** | ⚠️ ~1.1×, default OFF | 2nd-order CN (validated 21× more accurate than implicit at dt=0.02) cut N_t 2.7×, but the **CN sensitivity step is ~2× costlier per step** (an explicit-half operator on the previous sensitivities + dual-level sources), ~cancelling the win, and the N_t-independent assembly+optimizer dilute the rest → ~1.12× net. CN is also **not monotone** (no M-matrix) and broke arbitrage-freedom on a coarse-x grid. Kept as a tested opt-in (`timeScheme`). |
| **GN for band/haircut fits** | falls back to TRF | The bid-ask/haircut objective is **non-smooth** (zero gradient inside the band), fragile for GN's smooth LM (it returns the mid surface — a valid but solver-specific in-band solution); TRF's trust region is robust there. |
| **`tr_solver='lsmr'` inside trf** | ❌ diverges | Unpreconditioned LSMR inside scipy's trust-region hit the eval cap. The fix was a *purpose-built preconditioned GN* (Stage 5), a different animal. |
| **Thread / process parallelism** | ❌ GIL / Windows | Intra-fit thread-parallel is GIL-negative (the scipy/PDE loops hold the GIL); process pools are Windows-spawn-hostile and risky for the live backend. A `nogil` Numba march now exists, so across-ticker threads are a viable *future* item. |
| **Stage 5 — GN, first verdict** | reversed | "Removing the SVD made fits slower" was true *only while the march dominated*. Once the march is 6.5× cheaper, the SVD (52%) becomes the thing to avoid — and GN became the default. A caution about trusting synthetic-only perf claims: the clean rail (zero-residual, in-bounds) hid GN's real-data eval-count cost. |

---

## 8. Invariants & testing

- **Golden example is sacred.** `Docs/piecewise_affine_local_variance_calibration.tex`'s
  table is reproduced within tolerance and *byte-identically on the default paths*
  (`test_localvol_affine.py`, `test_affine_grid_design.py`). The local-vol surface *is*
  the product output, so tests pin both price/IV fit **and** nodal-θ stability.
- **Arbitrage-freedom** (`_diagnostics`: min density ≥ 0, no calendar violations) on the
  reconstructed surface; any new pricer/time-stepper must preserve it.
- **Numerical equivalence** of every accelerator to the banded/dense reference: the
  Numba march (≈1e-15), the sparse reg operator (to the bit), the GN solver (objective +
  θ within tol of TRF on golden + heavy). `test_affine_march.py`, `test_affine_gn.py`.
- **Solver robustness**: GN early-stop returns the best accepted iterate (status 4, no
  fallback); a forced GN breakdown falls back to dense TRF.
- **Determinism**: no randomised solvers; `affine_key` caching stays valid.
- Perf claims are gated by `test_perf.py` budget entries and **always benchmarked on the
  real SPY/NVDA Bloomberg fixture** (`backend/lv_benchmark.py`), never synthetic-only.

---

## 9. Where the bottleneck is now, and the open levers

For the **default GN path** the SVD is gone, the march is cheap, and early-stop +
parametric seed cut the eval count. The remaining costs are the Jacobian **assembly**
(the per-quote `sens_at` interpolation, still dense) and the **inherent eval count** on
cold fits. These are *incremental* (~10–30%), not order-of-magnitude:

- vectorise `_model_values`' per-quote `sens_at` (Python-loop overhead);
- a better GN preconditioner (incomplete-Cholesky of the roughness block);
- the future **non-tensor "bowtie" grid** (per-maturity delta point cloud + the note's
  adjoint gradient, O(1) in vertex count) — where m ≳ 1000 and the SVD *genuinely*
  dominates, the originally-imagined Stage-5 regime;
- a **smoothed band objective** so GN can cover bid-ask/haircut fits too (they keep TRF
  + its SVD today) — a research item, not incremental.

The order-of-magnitude wins (compiled march, SVD-avoidance, early-stop) are spent.

**Open quality lever — short-dated robust weighting (fix #3).** After fixes #1/#2
(§4) the residual on a true ~6-DTE weekly (~23 bp) is dominated by a near-ATM
**data-noise outlier** (e.g. a 20.8% IV spiking from a ~13% smile via de-Am / parity
stitching, on otherwise clean 1%-spread markets). The flexible LV chases it; the
rigid parametric form averages through. A robust loss (Huber/Cauchy) on the option
block for short maturities, or defaulting very short expiries to the bid-ask **band**
objective instead of mid, would close the last gap to a visually clean weekly. This
touches the LSQ objective (not just the grid), so it is a deliberate next step, not
incremental — and optional, since the catastrophic under-resolution regime is gone.

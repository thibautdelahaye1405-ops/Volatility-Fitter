# Backtest findings — calibration speed & arbitrage (Q4–Q7) + remediation roadmap

*Diagnostic note, 2026-06-25. Source: the 3-regime offline backtest
(`spike_aug2024`, `high_oct2022`, `low_jul2023`; 8 pilot assets, ~1,576 nodes/
regime) under `backend/backtest/`. This note explains four findings the sweep
surfaced and proposes a prioritized fix roadmap. **No code has been changed.***

The headline ranking is not in dispute: **LQD-10/12 strictly dominate SVI-JW**
(faster *and* 2–3× lower RMS, OOS tracking in-sample) in every regime, and
**Multi-Core SIV overfits**. The items below are the *secondary* issues that
ranking exposed — they affect the fairness of the arb metric, the speed of the
non-LQD models, and one outright crash.

---

## Findings

### F1 (Q4) — LQD calibrates faster than SVI because LQD has an analytic Jacobian and SVI does not

Counterintuitive (LQD-12 has 11+ params vs SVI's 5) but mechanical. Both use
`scipy.optimize.least_squares`; the difference is the Jacobian strategy:

| | LQD | SVI-JW |
|---|---|---|
| Jacobian | **exact analytic** (`models/lqd/jacobian.py`, gated on at `lqd/calibrate.py:248`) | **none** → scipy finite-difference fallback |
| evals / optimizer step | **2** (1 residual + 1 Jacobian), *independent of P* | **1 + P = 6** (1 residual + one perturbation per param) |
| method / tol | `trf`, `1e-10` | `lm`, `1e-15` (5 orders tighter → extra wasted iters) |
| extra residual rows | reg damping (cheap) | 2 no-arb penalties (min-var, Lee slope) re-evaluated every FD step |

So LQD's per-step cost is fixed at 2 evals while SVI's grows to 6, *and* SVI
grinds far below the ~5 vol-bp fit budget chasing `1e-15`. **The per-slice sweep
applies no calendar coupling to either model** (`SPEC.md:107`, `dispatch.py:81`),
so calendar arbitrage is *not* the cause. SVI is not a deliberately slow path —
it is simply the one family that never received the analytic-Jacobian perf work
that LQD got (ROADMAP perf #2).

### F2 (Q5) — Multi-Core SIV is super-linear in cores (no analytic Jacobian × R, three ways)

Fit ms (spike, mid): SIV-0 ≈ 31 → SIV-1 ≈ 215 → SIV-2 ≈ 514 → SIV-3 ≈ 2023.
Each core adds 4 params (dim = 6+4R). There is **no multi-start** — always exactly
two `least_squares` solves regardless of R (`models/sigmoid/calibrate.py:222`).
The blow-up is the product of three R-dependent factors inside a single solve:

1. **Finite-difference Jacobian** (no `jac=` passed, `calibrate.py:171`):
   `6+4R` residual evals per step.
2. **Each residual eval loops over all R cores**, each hat evaluating three
   transcendental functions (`log-cosh`/`tanh`/`sech²`, `sigmoid/kernels.py`).
3. **More trust-region iterations at ~n_params² linear-algebra cost** to converge
   a higher-dimensional, more non-convex problem under tight `xtol/ftol=1e-12`.

Roughly `(6+4R) × R × iterations(R)` → ~3–10× per core. SIV pays the same
missing-Jacobian tax as SVI, multiplied by core count.

### F3 (Q7) — The butterfly-arb column over-counts; de-Am genuinely roughens American wings

LQD is butterfly-arb-free **by construction, everywhere, on any inputs**: it builds
the density `f = u(1-u)·e^{-g(u)}` (structurally positive) with explicit martingale
normalization (`models/lqd/quadrature.py:152-212`); quotes never enter that
machinery. Yet the sweep reports ~0% arb on European indices but ~24% on American
names. Two separable causes:

- **(a) Metric over-count — dominant.** The harness does *not* read arb off LQD's
  analytic density. `_butterfly` (`dispatch.py:129-144`) reconstructs Durrleman
  g(k) numerically: price → Black-invert to implied variance → **two successive
  `np.gradient`** → g. That round-trip is fragile at the *edges of the traded
  range* (the `1/w`, `w''` terms amplify finite-difference noise), and a slice is
  flagged if **even one of 201 grid points** is < 0. Smoking gun: LQD's exact
  `lqd_martingale_dev` is ~0 on the very slices the butterfly column flags. (This
  is *not* the old wide-grid `variance_floor` bug — the grid is already confined to
  `[k_lo, k_hi]`; it is the inner-edge FD noise.)
- **(b) De-Am genuinely roughens American inputs — secondary, real.**
  `_early_exercise_premiums` (`api/quotes.py:113`) de-Americanizes **each strike
  independently** via its own CRR root-find, subtracts `EEP = max(raw − euro, 0)`,
  and applies **no joint convexity/monotonicity projection** across strikes. That
  one-sided clamp + independent inversion can leave the European-equivalent call
  prices slightly **non-convex strike-to-strike** at the wings; flexible LQD-10/12
  faithfully fit the rough wing and the fragile metric trips. European indices have
  no EEP step → smoother wings → ~0%.

### F4 (Q6) — SIV's arb lives in the wings, disproportionately the put (left) wing

316 re-fit SIV-3 spike nodes; 76% have g(k)<0 (matches the report's ~75%). Location
of g<0 points in standardized moneyness `z = k/√w_atm`:

| region | share |
|---|---|
| z < −2 (deep put wing) | **44%** |
| −2 … −1 | 17% |
| −1 … −0.5 | 3% |
| **−0.5 … +0.5 (ATM)** | **4%** |
| +0.5 … 1 | 3% |
| 1 … 2 | 11% |
| z > 2 (deep call wing) | 18% |

**Left wing 64% · ATM 4% · right wing 32%.** The worst (min-g) point per node sits
at **median z = −3.2**; 71% of nodes have their worst violation in the put wing.
Cause: the zero-wing "hat" cores are seeded at the largest residuals and, where the
wings are sparsely quoted, each hat injects a sharp local curvature change that
breaks convexity out in the unquoted tail. The equity put-skew (steeper, more
variance-loaded) makes the same overshoot a larger relative violation on the left.

### Supporting context — LV crash (separate from the parametric sweep)

The Local-Vol surface fit crashed on **6 surfaces across regimes, always NVDA/NDX**:
`AttributeError: 'LinearizedJacobian' object has no attribute 'T'` in the matrix-free
Gauss-Newton path (`affine_gn.py`). Deterministic, not data-dependent noise.

---

## Remediation roadmap (proposed, prioritized)

Ordering = correctness/trust before speed before model-quality. Each item is
independent; ship + golden-test one at a time per the repo convention.

### R1 — Fix the LV `LinearizedJacobian.T` crash  ·  ✅ DONE (commit 91f6d1b)

- **Problem:** matrix-free GN solver calls `.T` on a `LinearizedJacobian` operator
  that has no transpose attribute → hard crash on 6 NVDA/NDX surfaces.
- **Approach:** give `LinearizedJacobian` an explicit `.T` (or `rmatvec`/`matvec`
  `LinearOperator` interface) so the normal-equations assembly `Jᵀr` / `JᵀJ` works
  matrix-free; or route those call sites through the existing banded fallback.
  Inspect `affine_gn.py` to confirm whether the operator already has an `rmatvec`
  that the `.T` site should be using.
- **Files:** `backend/volfit/.../affine_gn.py` (+ the `LinearizedJacobian` class).
- **Acceptance:** the 6 failing (asset, date) surfaces fit cleanly; LV regime
  reports show 0 failures; existing LV golden tests byte-identical.
- **Risk:** low — localized; reproduce with NVDA 2024-07-31 / 2024-08-01 fixtures.

### R2 — Make the butterfly-arb metric trustworthy (analytic-density arb checks)  ·  ✅ DONE

*Shipped as `_analytic_butterfly` in `dispatch.py` + `arb_real`/`bfly_*_an` columns +
`analyze.py` `_arb_mask` (analytic-first, reconstructed fallback for old parquets); no
engine change — SIV's own `gatheral_g`, SVI closed-form w',w'', LQD structural density
positivity. Validated on real American nodes: LQD 28.3%→**0.0%**, SVI 20.8%→9.2%,
SIV-0 22.5%→10.0% (FD over-count removed), SIV-2 **75.8%** (genuine wing arb preserved).
Re-run `run_compute` to populate the new columns in the result tables.*

Original plan:

- **Problem:** the arb column penalizes LQD for finite-difference reconstruction
  noise at the traded-range edges (F3a). It is a numerical artifact, not arbitrage.
- **Approach:**
  1. **LQD:** report arb from the *analytic* density — `density()` ≥ 0 and
     `martingale_check()` (already exposed, `quadrature.py:148-166`). `bfly_min_g`
     becomes a cross-model diagnostic, not LQD's ground truth.
  2. **SVI / SIV:** compute g(k) from **closed-form** `w, w', w''` (these models
     have analytic derivatives) instead of `np.gradient` — removes the
     double-finite-difference amplification entirely.
  3. Keep the reconstructed-IV g(k) only as a model-agnostic fallback; tighten the
     flag from "any 1 of 201 points < 0" to a small negative-*area* / contiguous-run
     threshold so a single FD spike does not condemn a slice.
- **Files:** `backend/backtest/dispatch.py:129-192` (`_butterfly`, `fit_node`),
  `backend/backtest/analyze.py:42` (arb-% aggregation threshold). Surface both
  numbers (analytic + reconstructed) in the parquet so old runs stay comparable.
- **Acceptance:** LQD European/American arb both ≈ its `martingale_dev` (≈0); SIV
  wing arb still flagged (it is real, F4); a synthetic known-arb slice still trips.
- **Risk:** low/medium — metric-only, no engine change; re-run is cheap.

### R3 — Wing-only convex de-Am repair  ·  ✅ DONE (redesign; first attempt reverted)

- **Problem (F3b):** independent per-strike CRR de-Am + `max(EEP,0)` clamp leaves
  the European-equivalent call-price set locally non-convex at American wings —
  genuine (small) arbitrage in the *inputs* fed to **every** model.
- **First attempt (reverted, `ec68c52`):** a GLOBAL convex projection of the whole
  call curve with a free affine part. Repairing a wing re-tilted the baseline and
  moved the ATM call price a sub-penny — huge in ATM IV (vega) → the **ATM smile gap
  seen live on SPY/NVDA**.
- **Redesign (shipped):** `volfit/calib/convex_deam.py` + `quotes.py`. The repair is
  confined to the WINGS and the ATM core (`|z| ≤ Z_CORE=1`) is held **byte-identical**:
  each wing is projected onto `{convex} ∩ {bid/ask band}` (Dykstra alternating
  projection), anchored at its core boundary so the dense high-vega ATM never moves.
  The **band constraint is essential** — plain convex projection of an illiquid
  non-convex wing pushes prices to the no-arb boundary → absurd IVs (a put wing went
  27%→104%, Lee-violating) → catastrophic downstream fits (+5000 bp). Keeping the
  repaired mid inside the QUOTED spread bounds the correction to real uncertainty.
  Gated American-only + a convexity short-circuit (`CONVEX_TOL=1e-3`, calibrated so
  dense liquid chains are untouched and only genuinely arbitraged illiquid wings fire).
- **Measured (spike, American):** ATM IV diff `7e-16` (byte-identical), European diff
  `0.0`; dense names (AAPL/NVDA/JPM) never fire; illiquid EEM/EFA fire on the
  arbitraged nodes and the band clip removed the blow-ups — LQD-8 in-RMS on fired
  nodes **median 211 → 162 bp, improved 89/110, worst-case now +316 bp** (was +5300).
- **Files:** `volfit/calib/convex_deam.py` (new), `volfit/api/quotes.py:189-303`
  (`convex_deam=True`; European/disabled/already-convex ⇒ no-op ⇒ byte-identical).
  Tests: `tests/test_convex_deam.py` (ATM byte-identical guard + band-stay + convex).

### R4 — Analytic Jacobian for SVI  ·  ✅ DONE

- **Problem (F1):** SVI was the slowest baseline only because it lacked an analytic
  Jacobian — scipy's finite-difference fallback costs `1+P=6` residual evals/step and
  re-runs the penalty rows each time.
- **Shipped:** `volfit/models/svi_jw/jacobian.py` (`svi_residual_jacobian`) +
  `calibrate.py`. Closed-form Jacobian of the residual via the reparam chain rule
  (`db/dθ_b=1−e^{−b}`, `dρ/dθ_ρ=1−ρ²`, `dσ/dθ_σ=σ`); covers the mid OR band data term
  + the two no-arb penalty subgradients + the calendar floor; var-swap / strike-gap /
  operator-prior blocks fall back to FD (gated exactly like LQD).
- **Key finding — keep LM, do NOT switch to trf.** The plan suggested mirroring LQD's
  `trf + 1e-10`, but on noisy real chains **trf was measured SLOWER** (more iterations
  through the penalty kinks: 40 ms / 298 nfev vs LM's 26 ms / 193). The win is the
  Jacobian, not the optimizer — so it is a **drop-in**: same LM optimizer + same `1e-15`
  tol, only the Jacobian swapped FD → analytic. Results unchanged to fit precision
  (same nfev), full suite green.
- **Measured (real spike nodes):** **~2.6× faster** (26.3 → 10.2 ms/node) at unchanged
  convergence. FD-agreement guard: `tests/test_svi_jacobian.py` (analytic vs central
  FD over mid / band / calendar / active-penalty configs).

### R5 — Analytic Jacobian for Multi-Core SIV  ·  *priority: low/medium, larger*

- **Problem (F2):** SIV's super-linear cost is dominated by the `6+4R` finite-
  difference Jacobian evals × R-scaled residual cost.
- **Approach:** analytic Jacobian for the base SIV params and each hat core
  (`alpha, c, h, κ` — the kernels have closed-form derivatives in `kernels.py`).
  Reduces per-step evals from `6+4R+1` to ~2 and removes the dominant factor; the
  residual's per-core cost and the linear-algebra growth remain but the model
  becomes usable for R≥1. *Only worth doing if SIV cores are kept at all* — see R6;
  the backtest verdict is that cores overfit, so this may be deprioritized in favor
  of dropping SIV-2/3 from the production menu.
- **Files:** new `backend/volfit/models/sigmoid/jacobian.py`;
  `models/sigmoid/calibrate.py:171`.
- **Acceptance:** SIV-3 fit ms falls by ~the (6+4R) factor; fitted surface unchanged
  vs FD within tolerance; analytic-J agreement test.
- **Risk:** medium/larger — most params, most algebra. Gate behind the R6 decision.

### R6 — Tame SIV's put-wing arbitrage (curvature regularization / shape constraint)  ·  *priority: medium, research-ish*

- **Problem (F4):** SIV manufactures butterfly arb in the unquoted wings, 64% on the
  put side, because the hat cores add unconstrained curvature where no quotes
  discipline them.
- **Approach (options, in increasing intrusiveness):**
  1. **Wing-curvature penalty** — add a soft `∫ max(−g(k), 0)² dk` (Durrleman
     no-butterfly) or a `w''` smoothness penalty evaluated on a moneyness grid that
     **extends past the traded range**, weighted up in the wings (asymmetric: more
     weight on the put side). Cheapest; keeps the model, just regularizes shape.
  2. **Hat amplitude / placement constraint** — bound each core's amplitude by the
     local quote density, or forbid seeding a hat outside the traded `[k_lo,k_hi]`,
     so cores cannot fire into the unquoted tail.
  3. **Lee-slope-style wing cap** — enforce the linear total-variance wing bound
     (as SVI already does via the Lee slope penalty) on the SIV tail so deep wings
     stay arb-admissible.
  4. **Decision input:** given the backtest already shows SIV-2/3 overfit on
     *precision* (OOS gap) independent of arb, the simplest production answer may be
     to **cap the menu at SIV-0/1** and not chase multi-core shape fixes. R6 is the
     "if we keep cores" path.
- **Files:** `models/sigmoid/calibrate.py` (penalty/seed logic), `kernels.py`
  (curvature terms); reuse the analytic g(k) from R2 for the penalty.
- **Acceptance:** SIV-3 wing arb (analytic metric) drops sharply with ≤ small
  in-sample RMS cost; OOS gap narrows; put/call arb asymmetry reduced.
- **Risk:** research — a curvature penalty interacts with the (missing) analytic
  Jacobian and can slow fits further; measure on the captured wing-heavy nodes
  (NVDA/EEM deep expiries) before committing.

---

## Suggested sequencing

```
R1 (LV crash)            ──┐ independent, ship first (small, unblocks LV reports)
R2 (analytic arb metric) ──┴─→ R3 (convex de-Am)   [R3 needs R2 to measure gain]
R4 (SVI Jacobian)          ── independent speed win, any time
R6 decision (cap SIV menu?) ── if "keep cores": R5 (SIV Jacobian) then R6 shape reg
```

R1 + R2 are pure-win, low-risk, and make every subsequent number trustworthy — do
them first. R3 is the one genuine engine change on the shared live path (test
carefully). R4 is a clean isolated speed win. R5/R6 hinge on whether Multi-Core SIV
earns its place at all, which the precision data alone already calls into question.

**Status (2026-06-28):** R1 ✅, R2 ✅, R3 ✅ (wing-only redesign), R4 ✅ (SVI analytic
Jacobian, ~2.6×). Remaining: the **R6 menu decision** (cap SIV at 0/1 vs invest in
R5+R6 shape work; the overfit data argues for the cap). R5 is gated on that decision.

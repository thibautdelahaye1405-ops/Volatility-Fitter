# Committee review — Note 01 (LQD model coordinates), 2026-07-19

Review of `01_lqd_model_coordinates.pdf` by a Head of Quants, a senior equity
derivatives quant, and a senior equity derivatives trader at a bank. Verdict:
**major revision, not rejection** — "a strong mathematical model note and an
unusually effective lecture" whose finite-model universality, tail
identification, numerical inheritance, and live-marking readiness are not yet
established.

This file preserves the review verbatim (below) plus the triage decisions, so
the revision arc can be resumed without the original conversation.

## Triage (agreed 2026-07-19)

Every checkable claim was verified against the code and TeX source and found
correct (endpoint-coupling formulas, ordinary cubic Hermite, raw Euclidean
pseudoinverse, timing table vs figure from different runs).

Key fact the committee did not know: their sharpest structural fix (#2,
endpoint-decoupled body modes) was already shipped as the symmetric-surface
Phase 5 endpoint chart (`volfit/models/lqd/charts.py`) — their proposed basis
spans the IDENTICAL function space (phi_n(u) = P_n(1-2u) - (1-u) - (-1)^n u is
a linear change of basis), so the "model change" is a coordinate change: same
family, same optimum. The one genuinely new piece — A_R = logistic(rho),
killing the A_R < 1 wall — was adopted as the "logistic" chart and made the
production default (committee revision R1).

Workstreams, in agreed order:

1. **R1 — chart promotion** (DONE 2026-07-19): "logistic" chart
   (log A_L, rho, a) with A_R = expit(rho); genuinely unconstrained R^d;
   production default via `FitSettings.lqdCoords`. Chart-equivalence verified
   on the reference live fixture (12 real nodes: worst |dtheta| 3.6e-7,
   worst d(maxIVerr) 1e-4 bp).
2. **R2 — numerical certification harness**: randomized/near-wall theta
   battery (sub-grid strikes, butterflies, parity, digital bounds, vs
   high-precision quadrature), Fritsch–Carlson monotonicity certificate,
   interior-overflow guards, adversarial coefficient tests.
3. **R3 — tail-stability study**: jackknife outer quotes, vary N/lambda,
   1 vol bp perturbations, multi-start; fan of A_L/A_R/Lee slopes/var
   swap/digitals; effective slope at 10-delta/1-delta vs the Lee limit.
4. **R4 — Note 01 revision**: narrowed claims (title-level), endpoint-vanishing
   basis primary, density proposition with topology, perf appendix regenerated
   single-run with dispersion (fix the O(P n_grid) Jacobian caption), soften
   "nothing can fail", all small corrections, Petersen–Müller + metalog
   citations, one-page model card.
5. **R5 — ATM chart v2 + analytic var-swap derivative + calendar violation
   reporting in economic units.**

Deferred: live hedge-P&L evidence vs SVI/eSSVI (backtest-harness campaign);
document split executed as part of R4.

Push-backs recorded: no finite-parameter model represents atoms/gaps (narrow
the claim, don't concede a defect); the fit optimum is chart-independent, so
coupling bites through priors/edits/warm-starts, not through the fit itself;
benchmark-pack + certification artifacts already cover part of the
equal-footing evidence ask.

---

## The review (verbatim)

### Committee verdict

This is a strong mathematical model note and an unusually effective lecture.
The density-first viewpoint, log-odds ruler, upper-share ledger, and
cancellation identity are all memorable. We would recommend a major
revision—not a rejection.

The continuous construction is convincing. What is not yet convincing is that
the finite model is as universal as claimed, that tails are economically
identified, that the numerical implementation inherits the continuous
guarantees, or that the model is ready for live marking.

### The most important challenges

1. **"Coordinates for the space of smiles" is too strong.** The note
   establishes that every admissible LQD vector defines an arbitrage-free
   continuous slice, not that every arbitrage-free slice can be represented by
   LQD. A finite-order LQD slice has a strictly positive, continuous,
   full-support density and exponential tails in X. It cannot exactly
   represent atoms, bounded support, density gaps, default mass at zero, or
   Gaussian/super-exponential tails. "The same space of mean-one laws" should
   be narrowed. There is also still the wall A_R < 1, so the optimizer does
   not literally roam over all R^d. A fairer title-level claim:
   "Unconstrained coordinates for a flexible exponential-tail class of
   arbitrage-free smiles." The density-coordinates comparison is tilted
   (density can also be normalized/translated); benchmark rather than infer
   from constraint counting. With C(0)=1 the price family is a convex set,
   not a cone; monotonicity/convexity are linear functional inequalities.

2. **Body and tails are not actually separated.** A_L = exp(L + sum a_n),
   A_R = exp(R + sum (-1)^n a_n): every body coefficient changes one or both
   tails (a_2 += 0.10 multiplies both tail scales by ~1.105). Conflicts with
   "endpoint terms own the tails", a_4 as a shoulder handle, L/R as readable
   tail handles, and the Jacobian caption. Fitting a shoulder quote can
   silently change the last finite moment and ultimate wing slope. Cleaner:
   g(u) = (1-u) log A_L + u log A_R + sum b_n phi_n(u) with
   phi_n(0)=phi_n(1)=0, A_L = e^l, A_R = logistic(rho); then
   (l, rho, b_2, ...) in R^d is genuinely unconstrained, the wall disappears,
   and body modes cannot alter tail scales. Endpoint-vanishing Legendre modes
   can be formed and re-orthogonalized.

3. **The reported tail parameters are model priors, not observations.**
   A_L, A_R, critical moments, and Lee slopes are weakly identified by
   finite, noisy strike strips. "What the quoted body implied through the
   basis" is too confident — they are what the quotes, basis order, ridge,
   vega floor, initialization, and endpoint coupling jointly selected. Add a
   tail-stability study (remove outer quotes; vary N and lambda; perturb
   quotes 1 vol bp; refit from multiple starts; plot wing, A_L, A_R, Lee
   slope, var swap, digital fan). Show how quickly w(k)/|k| approaches the
   Lee limit; traders care about the effective slope at 10-delta or 1-delta.

4. **The numerical implementation has not inherited the continuous proof.**
   Production Hermite-interpolates Q and G separately; they cease to be
   algebraically consistent between nodes. Ordinary cubic Hermite is not
   automatically monotonicity-preserving. Required validation: randomized
   admissible and near-wall vectors; sub-grid strikes and several butterfly
   widths; call bounds, monotonicity, convexity, parity, digital bounds;
   high-order/event fits; comparison with direct high-precision quadrature.
   Either a shape-preserving interpolant with a proof, or "continuous
   structural guarantee plus numerical tolerance audit."

5. **A_R < 1 is insufficient for computational safety.** Endpoint
   cancellations can leave A_R < 1 while an interior polynomial excursion
   overflows e^g, Q, or e^Q. At z=40, expit(z) rounds to 1 in doubles while
   the reference listing uses u(1-u) and 1-u. Needs log-domain evaluation,
   explicit overflow/underflow policies, adversarial coefficient tests, an
   error bound for the asymptotic tail correction, quadrature error
   estimates.

6. **Calibration capacity is shown; identifiability and market performance
   are not.** Synthetic examples establish approximation power, not
   superiority. Quantify density recovery (L1, Wasserstein, mode
   locations/weights, held-out strikes). For approval: equal-footing
   comparisons with SVI/JW, SSVI/eSSVI, arbitrage-free spline — in-spread %,
   held-out and leave-one-quote-out stability, quiet/stressed/0DTE/earnings/
   sparse regimes, failure and fallback rates, rolling handle/digital/
   density/wing/var-swap stability, next-snapshot repricing and hedge P&L,
   equal parameter count and CPU. Show the Jacobian singular spectrum by N;
   coefficient non-uniqueness belongs in the main calibration analysis.

7. **The ATM chart is not yet a stable trader coordinate system.**
   U = J^T (JJ^T)^{-1} is "cheapest" only under the arbitrary Euclidean
   metric of raw coefficients; not invariant to scaling; JJ^T may be
   ill-conditioned. Use SVD/pseudoinverse with condition reporting and an
   economically meaningful metric (weighted price impact, GN/Fisher, hedge
   risk). The kernel basis V is non-unique and can rotate between
   calibrations — translate controls to ATM, 25/10-delta risk reversals,
   butterflies, wing slope/critical moment, var swap; show cross-talk.

8. **Calendar theory is excellent; enforcement remains layered.** Finite-grid,
   finite-weight, sequential, optional — violations can remain between nodes;
   recalibrating a near expiry can stale later constraints. "Control, not a
   theorem" should appear earlier. Generic solution: joint surface
   calibration, hard convex-order projection, or certified repair. At
   minimum report remaining violation in currency, ticks, bid-ask units and
   identify the cheapest arbitrage trade.

9. **The performance appendix contradicts itself.** Table speed-ups
   (1.59, 1.35, 2.68, 1.55) vs chart labels (1.34, 1.47, 1.60, 1.71) vs
   prose (1.3–1.7x) cannot be one fresh measurement. The analytic Jacobian
   is O(P n_grid), not "one quadrature regardless of P". Replace fastest-of-
   three with median, dispersion, CPU/library details, warm/cold cache,
   iteration counts, scaling in P/grid/quotes/maturities. Benchmark full
   trader configurations; var-swap derivative looks easy to add since
   dQ/dtheta is already available.

10. **Too much operational substance is outsourced.** Split: scientific model
    paper; implementation/traceability appendix; one-page model card.
    Acknowledge the LQD literature (Petersen–Müller log-quantile-density,
    metalog family); do not call the ATM identities, pseudoinverse chart, and
    envelope cancellation genuinely original without fuller comparison.

### Smaller corrections

- Definition 1 needs the derivative boundary at zero for laws on (0, inf).
- The logistic law's martingale-shifted smile is not exactly symmetric.
- "Mass leaves stretched ranks" is imprecise (rank intervals keep their
  probability; the rank-to-return map stretches).
- Figure 3 should not suggest A_L <= 1 (only A_R has the wall).
- Figure 4 should plot delta-sigma and resulting delta-A_L/A_R.
- Figure 11 "W-shaped": displayed IV curve is a single hump; needs a
  low-order comparator.
- Plot the fixed vega floor's effective weight (short-dated wings).
- Warm starts need diffusive scale adjustment + multi-start/event fallbacks.
- Add a forward/dividend bump example (forward error misread as skew).
- Clarify fitted marginals do not pin dynamics for path-dependent products.

### Questions the author must answer

1. Why not endpoint-vanishing body modes and a logistic coordinate for A_R?
2. In what topology, for what class of laws, is the N->inf family dense?
3. How much can tail moments move with all liquid quotes inside bid-ask?
4. What numerical arbitrage tolerance is guaranteed after interpolation?
5. Worst-case quadrature error as a function of N, theta, Z, 1-A_R?
6. How many starts fail or reach materially different minima on real data?
7. What metric makes an ATM-handle move "cheapest"?
8. Can shape controls be stable, expressed as standard RR/BF packages?
9. Deterministic fallback for overflow, wall contact, spiky density,
   evaluation-cap exhaustion?
10. What live evidence beats SVI/eSSVI at comparable complexity and CPU?
11. How is a surface repaired after one earlier expiry changes?
12. Are tail moments/densities approved risk outputs or diagnostics with
    uncertainty bands?

### What should absolutely be preserved

Rank/log-odds intuition; logistic solved example and hand-priced ticket;
moment-strip and Lee derivation; upper-share ledger; ATM digital/density
interpretation; cancellation identity and envelope interpretation; multi-chart
figures, heuristics, caution boxes; candour about synthetic evidence, atoms,
spiky densities, coefficient non-uniqueness, soft calendars.

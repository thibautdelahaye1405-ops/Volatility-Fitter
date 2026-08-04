# Author brief — the LQD paper

Deliverable: `Papers/lqd_paper/lqd_paper.pdf`, a standalone,
publication-ready paper on the LQD smile model. Byline: **Thibaut Delahaye**.
This is NOT a rewrite of any internal note: it cites only public literature,
never mentions the product, the notes, or repo internals. Companion briefs in
this folder: `BRIEF_notes_map.md` (all existing math + what angles are taken)
and `BRIEF_implementation.md` (production facts for the computational
section and the annex). Frozen data: `../data/lqd_paper_snapshot_20260804_0208.json`
(see `../data/README.md`).

## Voice

Claude Shannon writing "A Mathematical Theory of Communication": plain
declarative sentences; every abstraction immediately followed by a concrete
instance; theorems stated cleanly and proved shortly; zero marketing
language; candour about what is NOT claimed. Highly pedagogical AND
absolutely rigorous — when the two conflict, add a paragraph, never drop a
hypothesis. A good undergraduate who knows only Black–Scholes must be able
to read it front to back; a referee must find nothing to strike.

## The angle (new — the four existing arcs are off-limits, see brief 1 §4)

**A smile fitter must manage three separable concerns, and the
representation should separate them:**

1. **Validity** — no static arbitrage. In the LQD representation this is
   *structural*: every point of the (open) parameter set is a genuine
   probability measure with unit mean. Nothing is policed; validity is a
   property of the coordinates, not of the optimizer.
2. **Information** — what the quoted strip actually determines. The body of
   the distribution is pinned by quotes; the tails are selected by the
   basis, the ridge, and the endpoint coupling. The paper says this out
   loud and shows it (identifiability discussion, effective-slope vs Lee
   limit, order-control study).
3. **Convention** — what the fitter chooses where data is silent:
   basis order, regularization, charts, calendar enforcement scope. Each
   convention is explicit, orthogonal to validity, and auditable.

The unifying computational object is the **upper-share ledger**
G(z) = ∫_z^∞ e^{x(t)} ρ(t) dt: pricing (call = two ledger entries),
differentiation (envelope cancellation), the Breeden–Litzenberger density
(one division), the var swap (first moment), and calendar order (convex
order = pointwise ledger order) are five uses of one array. Let that thread
carry the paper the way "entropy" carries Shannon's.

## Section plan (adjust freely, keep the spine)

1. **Introduction.** The fitting problem; the canonical failure (an
   IV-space fit returning a negative butterfly); the design question: in
   which representation is validity free? Contributions list, scope
   sentence ("unconstrained coordinates for a flexible exponential-tail
   class" — never "coordinates for the space of smiles").
2. **The constraint set.** Normalized market (Y = S_T/F_T, E[Y]=1,
   normalized call c(k)); statics: monotone + convex in STRIKE, bounds,
   parity; Breeden–Litzenberger. Why these constraints are awkward in
   IV space (global, nonlinear, coupled).
3. **Heuristic.** From ranks to returns: a distribution is a rule
   assigning a return to each percentile rank; the rank is uniform, the
   log-odds coordinate z removes both endpoint singularities; the model
   parameterizes the log-SPEED of that assignment. Keep it tight (2-3
   pages) and do not reuse the "percentile ruler"/"lottery drum" branding.
4. **The LQD family.** Definition (boxed — the ONE boxed display):
   X = x(Z), x(z) = m + ∫_0^z e^{h(Λ(t))} dt, h ∈ P_N[0,1] in shifted
   Legendre; endpoint-chord chart h(p) = (1-p)L + pR + Σ_{n≥2} a_n P_n(1-2p);
   martingale normalization m; equivalence with the log-quantile-density
   form l(u) = −log u − log(1−u) + g(u). Constant-speed exact solution
   (π s/sin π s via the beta integral, Var(Z) = π²/3, cold start).
5. **Validity theorems.** Density positivity structural; finite-forward
   wall λ₊ < 1 (Proposition + proof from normalizer tails); one-expiry
   no-arbitrage proposition (convex in strike, with the log-strike caveat);
   scope/universality proposition WITH exclusions (atoms, bounded support,
   gaps, super-exponential tails; Wasserstein-p closure for p < 1/λ₊).
6. **Tails and moments.** Endpoint speeds; exact moment strip; Lee's
   theorem and the closed speed-to-slope forms β±(λ±); Benaim–Friz upgrade
   from limsup to limits; the honesty figure: effective slope at 10Δ/1Δ vs
   the asymptotic limit.
7. **The ledger.** G, its derivative, the strike root; call = G(z_k) −
   e^k(1−p_k); parity; c'(k), c''(k); density by one division; var swap
   w = −2E[X] as the ledger's moment (log-contract honesty clause).
8. **The ATM microscope.** Exact level/skew/curvature from (c₀, p*, f*);
   skew = digital mismatch Δ = p* − Φ(a); full implicit differentiation in
   an appendix if long.
9. **Information: calibration.** Objective (vega-normalized price
   residuals + explicit ridge on n≥4); fit-to-mid vs bid-ask band vs
   haircut band (define haircut precisely; degenerate-band behavior);
   what is pinned vs chosen; the order guard (params ≤ quotes/2) with the
   measured latency cliff; warm starts.
10. **The analytic Jacobian.** Envelope-cancellation theorem + proof;
    var-swap row on the same pass; complexity honesty (O(P·n_grid));
    measured 1.4–2.0× with median+IQR methodology.
11. **Calendar.** Convex order ⇔ ledger order (theorem, conjugate-duality
    proof both directions); enforcement as a CONTROL, not a theorem:
    support-confined price rows with C¹ taper, order-scaled constraint
    grid; the live SPY 1d/3d illustration (1840bp vol-space gap at
    k=+0.98 where quotes span ±3% and prices are 1e-20 — why confinement
    is right).
12. **Computation.** Quadrature (logit grid Z=40, 8001/2001 two-grid,
    Simpson, tail corrections); charts (raw / endpoint / logistic — the
    wall becomes unreachable, d log A_R/dρ = 1−A_R); floating-point
    catalogue (expit rounding at z≈36.7, log-space cash leg, u(1−u) =
    expit(z)·expit(−z), interior overflow budget, stable Lee ψ);
    certificates (Fritsch–Carlson margin; dense Durrleman-g belly
    certificate on the traded range); the randomized strike-space audit
    battery with measured worsts; timing table.
13. **Examples.** (a) SPY eight-expiry gallery, haircut bands, fitted
    slices, residual ledgers; (b) a deep-dive node with density and
    a hand-priced ticket in real numbers; (c) NVDA incl. the 1-day node
    (order guard live); (d) synthetic double-hump: N=16 recovers the
    bimodal density, N=6 comparator smooths it away (order-control);
    (e) the constant-speed audit (machine-precision agreement).
14. **Related work.** Breeden–Litzenberger 1978; Lee 2004; Benaim–Friz;
    Gatheral SVI / Gatheral–Jacquier SSVI; arbitrage-free smoothing
    (Fengler); quantile-based modeling (Parzen; Gilchrist; Keelin's
    metalog); log-quantile-density transforms in distributional data
    analysis (Petersen–Müller); log contract / var swaps (Neuberger;
    Demeterfi–Derman–Kamal–Zou; Carr–Madan). Position honestly: the
    ingredients are classical; the contribution is the separation of
    concerns and the single-ledger computation.
15. **Limitations and the contract.** What the model cannot represent;
    tails as priors; calendar as control; discretization earns the
    theorems via certificates; a short "honest contract" table is welcome
    (promises / controls / not claimed).

**Annexes (code lives ONLY here):**
- **A. Implementation.** NumPy-style snippets in paper notation (slice
  build pipeline, call evaluation with log-space cash leg + beyond-grid
  asymptotes, analytic sensitivity pass, Fritsch–Carlson margin), the
  defaults table (N=16 cap 24, grid, tolerances, barrier, ridge), and
  practical recommendations. Source: BRIEF_implementation.md. Snippets are
  adapted for exposition — no repo paths, no internal symbol names that
  leak the product (LQDParams/theta fine; "volfit" never).
- **B. Deferred proofs** (ATM implicit differentiation, universality).
- **C. Data and reproducibility.** The frozen snapshot: source ("a
  delayed consolidated US options feed"), timestamp, universe, haircut
  band, quality stats; how figures regenerate from the frozen file.

## Figures (target 14; hard floor 12) — the figure plan is FIXED for round 1

All produced by `scripts/gen_figures.py` (a separate engineer builds it to
this plan) into `figures/` as PDF, plus `figures/paper_macros.tex` for every
quoted number. Naming: `fig_<slug>.pdf`.

F1 `fig_transport` — 3 panels: logistic score density with percentile
    marks; the transport map x(z) for a constant-speed slice with the
    strike roots of k=0 and one OTM k marked; the resulting flat-ATM smile.
F2 `fig_modes` — 3 panels (log-speed h, IV, density): effect of switching
    on a2 / a3 / a4 = 0.10 one at a time on a symmetric reference.
F3 `fig_exact` — constant-speed audit: model m and x(z) vs the π s/sin(π s)
    closed form across s (error ~1e-15, log scale); inset: cold-start ATM
    variance mismatch (~8%).
F4 `fig_spy_gallery` — 8 small multiples: SPY quotes (haircut band
    whiskers) + fitted LQD slice, per-expiry rms annotated.
F5 `fig_spy_node` — deep dive on SPY 2026-12-18: fit vs band; residual
    ledger in vol bp; fitted density vs ATM-matched normal.
F6 `fig_nvda_nodes` — NVDA 1-day node + one long node: fit + residuals;
    caption carries the order-guard story (effective N from quote count).
F7 `fig_lqd_chart` — a real node in the model's own chart: log q(u) with
    the universal skeleton −log u −log(1−u) dashed and g(u) shaded;
    companion panel: the density.
F8 `fig_tails` — the chain: endpoint speed → last finite moment → Lee
    slope (3 panels), fitted SPY + NVDA values marked.
F9 `fig_lee` — effective slope w(k)/|k| vs |k| for a real node, Lee limit
    dotted, 10Δ/1Δ diamonds; both wings.
F10 `fig_doublehump` — synthetic mixture: IV target + N=16 fit; true vs
    recovered density (two modes).
F11 `fig_order_control` — same target at N=6: IV nearly identical, density
    smoothed (L1 distances annotated) — what the extra order buys.
F12 `fig_jacobian` — analytic vs FD sensitivity columns across strikes +
    max relative error; or heat map + error panel.
F13 `fig_calendar` — SPY total-variance term structure at fixed k values +
    the confinement illustration: the 1d/3d pair, common quote span shaded,
    the vol-space "crossing" far outside it (prices ~1e-20 annotated).
F14 `fig_butterfly` — real-node call curve convex in strike below secant
    chords; discrete butterflies vs the continuous density.

Every number quoted in the text (fit stats, audit worsts, timing, ticket
values) is a macro from `paper_macros.tex`: `\Mac<CamelCaseSlug>` (e.g.
`\MacSpyDecRmsBp`). Write the macro name in the text AND append every macro
you use to `review/REQUESTED_MACROS.md` (name + one-line meaning + where
used); the generator will emit them. Do not hand-type data-derived numbers.

## Style contract (hard rules)

- ONE boxed display (the central model). ONE differentiation convention:
  primes for one-variable functions, subscripted ∂ for partials; declared
  in the notation table. No near-identical symbol pairs.
- Notation ledger table early (§2), symbols per BRIEF_notes_map §5.
  Three-clocks honesty: τ is the variance time used everywhere.
- amsthm environments: Theorem / Proposition / Lemma / Definition / Remark;
  proofs inline when ≤ half a page, else Annex B.
- Figures referenced in text order; captions explain panel by panel what to
  see. Booktabs tables only.
- Committee-honesty items (brief 1 §6) are non-negotiable: scope sentence,
  tails-as-priors, control-not-theorem, discretization-earns-the-theorem,
  median+IQR timing.
- No internal references anywhere. Public citations with a proper .bib.

## Files & build

- Master: `Papers/lqd_paper/lqd_paper.tex` (documentclass article 11pt,
  a4paper; amsmath amssymb amsthm bm graphicx booktabs microtype hyperref
  cleveref; natbib or biblatex — pick one, classic natbib+plainnat is fine).
- Own macro preamble INSIDE the master or a small `paper_preamble.sty`
  (\E, \Prob, \dd, \PhiN, \phin, \Black, \expit, \logit — same meanings as
  brief 1 §5).
- Sections as `sections/NN_slug.tex`, \input from the master. References
  `references.bib`.
- `\input{figures/paper_macros.tex}` near the top; missing figures must not
  break the build — guard every \includegraphics with \IfFileExists giving
  a labeled placeholder box, so text and figures can be built independently.
- The LEAD (not you) compiles with pdflatex×2 and runs the generator; you
  only write files.

## Review protocol

A student challenger (Black–Scholes knowledge only) will read the draft and
file objections; the lead arbitrates and returns a revision list. Expect at
least two rounds. The dialogue is invisible in the paper — where the
student stumbled, the exposition gets better, silently.

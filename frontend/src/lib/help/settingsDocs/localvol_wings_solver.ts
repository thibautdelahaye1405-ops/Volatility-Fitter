// Help Center settings corpus — Local-Vol section, wing / front regularizers,
// PDE lattice and solver (SettingsSectionId "opt-localvol"). One SettingDoc per
// OptionsSettings field that shapes the LV fit beyond the vertex grid: the
// convex-wing hinge and its weight, the front tie, the adaptive local-vol cap,
// the Dupire time scheme and the PDE strike lattice (LV operator arc,
// 2026-09-08), early stop, the compiled march, the solver choice, the
// left-wing extrapolation slope, the lattice right-edge floor and the
// density-smoothness weight. The workspace gate and vertex-grid knobs live in
// localvol_grid.ts; localvol.ts concatenates both into LOCALVOL_DOCS.
//
// Meaning is taken from the `#:` comments of volfit/api/schemas.py
// OptionsSettings (authoritative), Docs/handoff/SETTINGS_REFERENCE.md §2.8,
// Docs/handoff/notes/04_local_volatility_forward.md (§5.2 "Why not
// Crank–Nicolson", Appendix A/B) and the labels / tooltips of
// components/options/LocalVolSection.tsx. Machine facts render from
// settingsSchema.json next to this prose.
//
// Cache discipline: every field here folds into the LV affine key only — none
// ever invalidates a parametric fit.
import type { SettingDoc } from "../types";

export const LV_WINGS_SOLVER_DOCS: SettingDoc[] = [
  {
    key: "convexWing",
    model: "options",
    section: "opt-localvol",
    label: "Convex wing (< 5Δ)",
    summary: "Force the local vol σ(x,t) convex in x below the 5Δ-put strike with a soft hinge.",
    details:
      "Adds a soft hinge √W · relu(−D²σ) per time row at the deep-put vertices, so the " +
      "sparse left wing cannot fit too concave. Its authority is confined to the unquoted " +
      "extrapolation tail: a fine-grid version that fought dense quotes cost 26 bp on SPY, " +
      "which is now a certification case. Off is byte-identical.\n\n" +
      "Turning it on also makes `leftWingSlopeMult` the fixed slope of the left-wing " +
      "extrapolation (off = flat continuation). The resolved-grid readout counts the " +
      "convex-wing vertices.",
    example:
      "Turn it on for a high-vol single name whose 2Δ–5Δ put local vol bends downward: the " +
      "deep-put rows straighten upward, the readout shows the convex-wing vertex count, and " +
      "the quoted region is unchanged.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["convexWingWeight", "leftWingSlopeMult", "lvVolCapMult", "help:guides:localvol"],
    docs: ["04_local_volatility_forward", "09_wings_last_quote"],
  },
  {
    key: "convexWingWeight",
    model: "options",
    section: "opt-localvol",
    label: "Convex-wing weight",
    unit: "weight",
    summary: "Strength W of the convex-wing hinge.",
    details:
      "√W multiplies the hinge residual. 1e3 is stiff enough to hold convexity against the " +
      "roughness penalty, yet as a one-sided hinge it never acts on rows that are already " +
      "convex. Larger values make the constraint near-hard; `0` leaves the hinge inert, " +
      "identical to `convexWing` off.",
    example:
      "Drop it from 1000 to 10 on a concave deep-put wing: the hinge only nudges, the fitted " +
      "rows stay slightly concave and the LV diagnostics still flag the wing.",
    activation: "Read only while `convexWing` is on.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["convexWing", "leftWingSlopeMult"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "frontTie",
    model: "options",
    section: "opt-localvol",
    label: "Front tie (t=0 → first row)",
    summary: "Pull the free t = 0 local-vol row toward the first data-identified row.",
    details:
      "A soft one-sided difference √W · (θ[0,:] − θ[1,:]) per strike column. The quotes at " +
      "the first expiry pin only the INTEGRAL of local variance over [0, τ₁], so every row " +
      "inside that interval is unidentified — the optimizer can ring one row up and the next " +
      "down at no cost in fit (5–30 vol points of measured ringing). The tie turns that " +
      "subspace into a constant continuation and stops the free front leaking into the " +
      "shortest, most curved smile.\n\n" +
      "On by default as a mild stabilizer; off, or weight 0, is byte-identical.",
    example:
      "Switch it off on a chain whose first expiry is three weeks out with 10 time nodes: " +
      "the t = 0 row wanders several vol points away from the first-expiry row with no " +
      "change in the quote fit, and the shortest smile's LV readout turns noisy.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["frontTieWeight", "gridTNodes", "gridXMinPerExpiry"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "frontTieWeight",
    model: "options",
    section: "opt-localvol",
    label: "Front-tie weight",
    unit: "weight",
    summary: "Strength W of the front tie.",
    details:
      "Deliberately small: enough to pick the constant continuation for the unidentified " +
      "front rows, weak enough that the data-identified first row leads. Larger values " +
      "collapse the t = 0 row onto the first-expiry row exactly; very small values bring the " +
      "identifiability ringing back.",
    example:
      "Raise it to 1 and the t = 0 row equals the first-expiry row to three decimals; at " +
      "1e-4 the front row starts drifting again.",
    activation: "Read only while `frontTie` is on.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["frontTie"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "lvVolCapMult",
    model: "options",
    section: "opt-localvol",
    label: "LV cap × (× max IV)",
    unit: "× highest observed IV",
    summary: "Adaptive cap on the nodal local vol: max(60%, this × the highest observed implied vol), never above 400%.",
    details:
      "The old fixed 60% cap clamped the deep-put LOCAL vol of high-vol names such as NVDA " +
      "and starved the put wing: local variance in the wing runs well above implied, so the " +
      "bound must scale with the name. The cap does not apply in the extrapolation region " +
      "below the lowest vertex (see `leftWingSlopeMult`).\n\n" +
      "The resolved-grid readout shows the LV bounds. The FLOOR is not this knob: it adapts " +
      "to a fraction of the smallest ATM implied vol so an increasing term structure stays " +
      "fittable.",
    example:
      "NVDA with a 55% highest IV: 3.0 caps local vol at 165%. Drop it to 1.0 and the cap " +
      "binds at 60% — the bounds readout shows 60%, the deep-put rows sit on the box and the " +
      "put-wing RMS grows.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["convexWing", "leftWingSlopeMult"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "timeScheme",
    model: "options",
    section: "opt-localvol",
    label: "Time stepping (BDF2 / Rannacher / implicit)",
    summary: "Time discretisation of the Dupire march: the second-order BDF2 step on the graded time grid (default), Rannacher (Crank–Nicolson after damped start-up, opt-in), or the first-order implicit Euler legacy.",
    details:
      "`bdf2` is the second-order, L-stable backward-differentiation step on a time grid graded " +
      "from the payoff kink: geometric at the start, every expiry AND every vertex row of the " +
      "sheet a grid point, at least 8 steps per slab between rows, no step above 0.05 years. " +
      "Measured on every fixture (Bloomberg SPY and NVDA, the weekly, the dailies snapshot): " +
      "≤ 5 bp of operator error per expiry where implicit Euler's per-interval rule left " +
      "15–170 bp — error the calibration then bent the fitted sheet to cancel — at 2–3× fewer " +
      "time steps. L-stability damps the stiffest modes, which keeps the monotone behaviour " +
      "Crank–Nicolson lacks, and its sensitivities ride the implicit kernel's single fused " +
      "source, so the compiled march covers it at the implicit march's cost per step.\n\n" +
      "`rannacher` marches the same graded grid and reads a few bp finer on the reprice, but its " +
      "sensitivity step costs ~1.5× and Crank–Nicolson is not monotone (an arbitrage violation " +
      "once appeared on a coarse strike lattice), so it stays opt-in. `implicit` is the " +
      "first-order legacy on its per-interval uniform rule, byte-identical to every historical " +
      "fit. The compiled march (`lvFastKernel`) covers all three. Var-swap fits under Rannacher " +
      "keep implicit; BDF2 applies to them too. The converged reprice, the display wing march " +
      "and the Compare tab's twin ride the fit's scheme. The dialog shows this as a selector.",
    example:
      "A one-month SPY front under `implicit` reads a converged figure tens of bp above its " +
      "in-operator RMS — the sheet is compensating the operator. Under `bdf2` the two figures sit " +
      "within a few bp of each other and the fit marches about a third of the steps; `rannacher` " +
      "moves the reprice by a couple of bp more at ~1.5× the per-step cost.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["lvLattice", "lvEarlyStop", "lvSolver", "lvFastKernel"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "lvLattice",
    model: "options",
    section: "opt-localvol",
    label: "Graded strike lattice",
    summary: "The PDE strike lattice the LV march runs on: one uniform step set by the shortest expiry, or a step graded per expiry over its own support (default).",
    details:
      "This is the lattice of the Dupire march, not the vertex grid of the fitted sheet (the " +
      "resolved-grid readout counts vertices and is untouched).\n\n" +
      "`uniform` is the historical lattice: one step for the whole surface, the SHORTEST " +
      "expiry's 0.15 σ√τ. A same-day or two-day rung then sets the resolution of every expiry — " +
      "a 2-day SPY daily makes the whole surface march ~1700 nodes at a 1/800 step out to " +
      "x = 2.5, which was the \"SPY LV stalls\" wall time.\n\n" +
      "`graded` (the default) gives each expiry its own step over its own support: inside its " +
      "traded range widened to ± 6 σ√τ in log-moneyness the step is that expiry's own 0.15 σ√τ; " +
      "outside every expiry's region the step grows geometrically, by at most 15 % per cell, to " +
      "the wing step 0.02. x = 1 — the ATM row and the var-swap anchor — is a node by " +
      "construction (the lattice is built outward from it). Same near-money resolution where " +
      "the quotes live, a fraction of the nodes where nothing does. Every lattice consumer — " +
      "the density, the diagnostics, the display wing march, the converged reprice and the " +
      "Compare tab's twin — reads the nonuniform second difference; a uniform lattice keeps the " +
      "uniform formula, byte-identical. With a second-order time scheme (`timeScheme`) the " +
      "strike lattice is what remains of the operator error, which is why it stays fine where " +
      "it matters and coarse where nothing lives.",
    example:
      "A SPY universe with a same-day or 2-day expiry among the monthlies: under `uniform` every " +
      "expiry marches ~1700 strike nodes; under `graded` about 400, with the same near-money " +
      "resolution and the same var-swap anchor at x = 1. Calibrate on that universe finishes " +
      "several times faster and the quoted-region fit is unchanged to a few bp.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["timeScheme", "gridXMinPerExpiry", "lvXMaxMin"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "lvEarlyStop",
    model: "options",
    section: "opt-localvol",
    label: "Early-stop cold fit (faster)",
    summary: "Stop the cold LV fit when the data misfit stalls instead of running to the 200-eval cap.",
    details:
      "The tail evals of a full run barely move the surface; stopping at the stall point " +
      "scales the whole fit (march, assembly, optimizer). Measured ~1.45× (slow-converging " +
      "SPY, +0.10 bp) to ~3.3× (fast-converging NVDA, +0.25 bp) on cold fits; warm-started " +
      "recalibrations converge before the stall window and are unaffected.\n\n" +
      "The stall watches option, var-swap and basket rows together (since 2026-08-27 — " +
      "before that a warm fit whose options already fit could stop without moving toward a " +
      "var-swap quote). Windows are 12 evals / 5e-3 under TRF and 18 / 3e-3 under GN.",
    example:
      "Turn it off on NVDA: the cold fit runs all 200 evals for ~3× the time and lands " +
      "within ~0.25 bp of the early-stopped surface.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["lvSolver", "lvFastKernel", "timeScheme"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "lvFastKernel",
    model: "options",
    section: "opt-localvol",
    label: "Fast compiled march (Numba)",
    summary: "Run the Dupire calibration march on the compiled vectorized-Thomas kernel.",
    details:
      "No-pivot Thomas, SIMD across the sensitivity columns, fused source: ~6× the " +
      "scipy/LAPACK banded march, which is the bulk of the per-eval cost. Output matches the " +
      "banded march to ~1e-15. It falls back to the banded march automatically when numba is " +
      "missing and for var-swap fits only — since the 2026-09-08 operator arc the compiled " +
      "march covers every `timeScheme` (BDF2 and Rannacher included).\n\n" +
      "It is also a precondition for the Gauss-Newton solver: with the kernel off, " +
      "`lvSolver = gn` routes to TRF.",
    example:
      "Turn it off: every eval runs the banded march, the cold fit takes several times " +
      "longer, and the solver silently falls back from GN to TRF — the surface is the same " +
      "to numerical precision.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["lvSolver", "lvEarlyStop", "timeScheme"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "lvSolver",
    model: "options",
    section: "opt-localvol",
    label: "LV solver",
    summary: "LV calibration solver: matrix-free Gauss-Newton (default) or scipy trust-region (legacy).",
    details:
      "`gn` avoids TRF's dense SVD — ~52% of an eval once the compiled march made the rest " +
      "cheap. Since 2026-09-09 it runs every fit target with `lvFastKernel` on: Mid on the loop " +
      "shipped in June (~1.3–1.65× over TRF), Bid-Ask and Haircut on an active-set loop in which " +
      "each step is refined so the variance box and the band edges it will meet are part of the " +
      "step it takes, and a step is accepted whenever the true objective falls. On the desk " +
      "fixtures (SPY weeklies, Bloomberg SPY and NVDA, haircut / 20 nodes / convex wing) a band " +
      "Local Vol calibration is 2.5–4× faster than under `trf` at the same target fit. It still " +
      "falls back to TRF for var-swap fits, the robust re-solves and the banded march.\n\n" +
      "Accepted trade-off at the default: GN lands a slightly different local optimum on stiff " +
      "real data (Mid: within ~0.25 vol bp of TRF; band: usually a lower objective than TRF's, " +
      "converged-operator error within ~1 bp). Its first verdict was non-viable; it was reversed " +
      "once the march became cheap, and its band gate fell when the step became active-set aware.",
    example:
      "Pick `trf` with fit target Haircut on a SPY ladder with dailies: the cold Local Vol fit " +
      "takes ~3× longer and reaches a slightly higher objective. Pick `gn` and switch the fit " +
      "target between Mid and Haircut: both calibrate on the fast solver, and a Haircut " +
      "recalibration from the Mid surface relaxes it toward the smoother in-band solution.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["lvFastKernel", "lvEarlyStop", "help:guides:localvol"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "leftWingSlopeMult",
    model: "options",
    section: "opt-localvol",
    label: "Left-wing slope ×",
    unit: "× first-cell slope",
    summary: "Slope of the linear left-wing extrapolation of local variance below the lowest vertex.",
    details:
      "Below x_min the local variance continues linearly toward x = 0 at this multiple of the " +
      "first cell's slope (between the two lowest vertices) instead of clamping flat, so the " +
      "deep-put local variance keeps rising. With `convexWing` on it is the fixed multiple; " +
      "when a var-swap quote is set the slope becomes a FREE calibration variable and this is " +
      "its starting value. The LV cap does not apply in this region.",
    example:
      "With convex wing on, 1.5 → 3.0 steepens the deep-put continuation: the LV var-swap " +
      "level rises and the 1Δ put implied vol in the LV chart climbs while quoted strikes are " +
      "untouched. `0` clamps the wing flat, the legacy behaviour.",
    activation: "Read while `convexWing` is on (fixed multiple) or a var-swap quote is set (initial value).",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["convexWing", "lvVolCapMult", "varSwapMethod"],
    docs: ["04_local_volatility_forward", "08_varswap_representations"],
  },
  {
    key: "lvXMaxMin",
    model: "options",
    section: "opt-localvol",
    label: "Lattice right edge floor (x)",
    unit: "moneyness x = K/F",
    summary: "Floor on the right edge of the LV calibration lattice (its far Dirichlet boundary); the displayed wing no longer depends on it.",
    details:
      "The calibration lattice runs to x_max = max(1.4 × the highest quoted x, this floor) and " +
      "is closed by the Dirichlet condition C(x_max) = 0. Near that edge the marched price is " +
      "pulled linearly to zero (a boundary layer ~1/c wide, c the tail's decay rate), so the " +
      "smile chart used to collapse toward k = ln(x_max) ≈ +0.92 — sharply on short-dated " +
      "slices. Since 2026-09-02 the displayed right wing rides its own buffered display " +
      "lattice out to k = +1.0 and never inverts inside a boundary layer, so this floor only " +
      "moves the CALIBRATION's far boundary. That matters when the true call at 1.4 × the last " +
      "quote is not negligible — high-vol, long-dated names — where the zero boundary otherwise " +
      "bends the fitted wing; it costs O(n_x) on every march. 2.5 (k ≈ +0.92) is the historical " +
      "constant and byte-identical.\n\n" +
      "The dialog row shows the resulting k = ln(x) readout of the calibration lattice.",
    example:
      "A 1-year 60%-vol name quoted out to k ≈ +0.8: the default lattice ends at 1.4 × e^0.8 ≈ 3.1 " +
      "where the true call is still a few basis points of forward. Raise the floor to 6.0 and " +
      "the far boundary stops bending the fitted right wing, at ~2× the strike nodes per eval.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["gridXNodes", "help:guides:localvol"],
    docs: ["04_local_volatility_forward", "09_wings_last_quote"],
  },
  {
    key: "densitySmoothWeight",
    model: "options",
    section: "opt-localvol",
    label: "Density smoothness (μ)",
    unit: "weight (0 = off)",
    summary: "Penalises the slope roughness of each expiry's risk-neutral density; the rows ride the marched sensitivities, so it costs no extra PDE work.",
    details:
      "The affine local-variance fit can ring at the vertex scale — local vol dipping to the floor " +
      "between neighbouring strike vertices — and every dip is a spike in the Breeden–Litzenberger " +
      "density d²C/dx². This penalty adds third differences of the lattice call prices (the density's " +
      "slope) inside each expiry's quoted window ± 2 ATM standard deviations, scaled so a Gaussian " +
      "slice contributes O(μ) whatever the maturity or lattice step. Because a lattice price is a " +
      "linear functional the march already differentiates, the Jacobian is the same stencil on the " +
      "sensitivity block: about a millisecond per evaluation, and the better-posed problem converges " +
      "in fewer evaluations. Unlike the global roughness weight (which trades fit for smoothness " +
      "uniformly), it prices only what shows up in the density.\n\n" +
      "Measured on the SPY weekly fixture at μ = 1: converged RMS 20.2 → 18.5 bp, solver " +
      "evaluations 62 → 43, density extrema on the 1-year rung 5 → 1. 0 reproduces the " +
      "pre-2026-09-03 fit byte-for-byte; 10 starts to cost fit (21.5 bp).",
    example:
      "A 2-week SPY slice whose density shows several bumps between the quoted strikes while the " +
      "local-vol profile saw-tooths between 5% and 13%: at μ = 1 the bumps merge into one mode and " +
      "the fit error does not rise; at 0 the saw-tooth is back.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["gridRegLambda", "gridXNodes", "help:guides:localvol"],
    docs: ["04_local_volatility_forward"],
  },
];

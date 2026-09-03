// Help Center settings corpus — Local-Vol section, wing / front regularizers,
// PDE lattice and solver (SettingsSectionId "opt-localvol"). One SettingDoc per
// OptionsSettings field that shapes the LV fit beyond the vertex grid: the
// convex-wing hinge and its weight, the front tie, the adaptive local-vol cap,
// the Dupire time scheme, early stop, the compiled march, the solver choice,
// the left-wing extrapolation slope and the lattice right-edge floor. The
// workspace gate and vertex-grid knobs live in localvol_grid.ts; localvol.ts
// concatenates both into LOCALVOL_DOCS.
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
    label: "2nd-order time stepping (experimental)",
    summary: "Time discretisation of the Dupire march: implicit Euler, or Rannacher (Crank–Nicolson after damped start-up).",
    details:
      "`rannacher` reaches the same accuracy at ~3× larger time steps, so each eval marches " +
      "fewer steps. It stays opt-in for two measured reasons: net speed-up was only ~1.1× " +
      "(the heavier sensitivity step cancels the win), and Crank–Nicolson is not monotone — " +
      "its explicit factor breaks the CFL-like bound on coarse-x, high-vol lattices, and an " +
      "arbitrage violation appeared on a coarse strike grid. Implicit Euler keeps the " +
      "maximum principle at first order.\n\n" +
      "Var-swap fits keep implicit either way, and the compiled march falls back to the " +
      "banded solver under Rannacher. The real cold-fit lever is fewer evals (`lvEarlyStop`, " +
      "`lvSolver`), not fewer time steps. The dialog shows this as a toggle (on = `rannacher`).",
    example:
      "Turn it on: the eval count is unchanged, wall time is about the same, and on a coarse " +
      "strike grid the LV diagnostics may report a butterfly violation the implicit scheme " +
      "did not produce.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["lvEarlyStop", "lvSolver", "lvFastKernel"],
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
      "missing, for var-swap fits and under `rannacher`.\n\n" +
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
      "cheap — and runs ~1.3–1.65× faster. It engages only for the smooth Mid fit target " +
      "with `lvFastKernel` on, and falls back to TRF for the non-smooth Bid-Ask / Haircut " +
      "band objective, var-swap fits, or the banded march.\n\n" +
      "Accepted trade-off at the default: GN converges to a slightly different local optimum " +
      "on stiff real data, up to ~0.25 vol bp (often better). Its first verdict was " +
      "non-viable; it was reversed once the march became cheap.",
    example:
      "Pick `trf` with fit target Mid on SPY: the cold fit takes ~1.5× longer and the surface " +
      "differs by ≤ 0.25 bp. Pick `gn` while the fit target is Bid-Ask and nothing changes — " +
      "the band objective routes to TRF anyway.",
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

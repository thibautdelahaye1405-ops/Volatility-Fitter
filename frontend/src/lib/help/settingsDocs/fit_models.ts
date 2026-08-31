// Help Center settings corpus — FitSettings, model-family knobs (HELP CENTER
// ARC, H2). One SettingDoc per FitSettings field that picks or shapes a smile
// family: the model selector, the LQD order / chart / damping / tail
// exponents / barrier, the SVI penalties and chart, the MCS cores / ridge /
// chart. The objective-side FitSettings (haircut, weighting, anchors, robust
// loss) live in fit_objective.ts; fit.ts concatenates both into FIT_DOCS.
//
// Meaning is taken from the `#:` comments of volfit/api/schemas.py FitSettings
// (authoritative), the labels of components/HyperparamPanel.tsx and
// PenaltyCoefficients.tsx, and Docs/handoff/SETTINGS_REFERENCE.md. Machine
// facts (type / default / range / enum) come from settingsSchema.json and are
// rendered next to this prose — never restated here as the source of truth.
// Every FitSettings field folds into the fit-cache key ("fit-version").
import type { SettingDoc } from "../types";

export const FIT_MODEL_DOCS: SettingDoc[] = [
  {
    key: "model",
    model: "fit",
    section: "opt-parametric",
    label: "Model (LQD / SVI / MCS)",
    summary: "Choose the smile family the Parametric lens charts and calibrates: LQD, SVI or Multi-Core Sigmoid (MCS).",
    details:
      "`lqd` is the arbitrage-free quantile-density slice and the analytic backbone: it is ALWAYS fitted whatever you pick, so the density, term-structure, local-vol and graph views stay LQD-based. `svi` and `sigmoid` (the MCS button) are overlays calibrated to the same quotes and drawn in the Parametric lens; each carries its own penalty coefficients, and the LQD-only knobs (`nOrder`, damping, tail exponents) do not shape them.\n\n" +
      "Switching the model refits every displayed slice (the fit version bumps) but touches neither the data, the forwards nor the Local-Vol grid — the LV grid is its own Options section, not a parametric family.",
    example:
      "Switch `model` from `lqd` to `svi` on a liquid index: the Parametric chart redraws with the five-parameter SVI overlay and its penalty rows appear below, while the density and term views are unchanged because they still read the LQD backbone.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["nOrder", "nCores", "sviChart", "mcsChart", "help:guides:parametric"],
    docs: ["00_system_overview", "01_lqd_model_lecture", "02_svi_jw_rewrite", "03_multicore_mcs_corrections"],
  },
  {
    key: "nOrder",
    model: "fit",
    section: "opt-parametric",
    label: "Legendre order N",
    unit: "count (body modes)",
    summary: "Number of Legendre body modes in the LQD quantile-density slice — more modes resolve sharper shoulders, fewer keep thin books smooth.",
    details:
      "The default 16 (raised from 6; slider cap 24) comes from a measured residual: N ≤ 12 leaves an equioscillating truncation error of about ±20 bp at the smile shoulder on low-vol wide-z names (SPY LEAPs quoted at 3 bp spreads), and at 24 the shoulder error reaches spread level on the reference SPY surface.\n\n" +
      "The order actually used is capped per slice by the quote count — N+1 ≤ quotes/2, never below min(N, 6) — so a 19-quote 0DTE book still fits at N = 6, stays data-identified (error bars never saturate) and avoids the seconds-long solver meander of an over-parameterized short book. The slider therefore only bites on the wide, dense surfaces that need it. Not the MCS analogue — that is `nCores`.",
    example:
      "Drag `nOrder` from 16 to 8 on a SPY LEAP: the fitted shoulder drifts up to ±20 bp away from the mids in a wave pattern and the node's RMS in Quality rises; on a 14-quote weekly the fit is byte-identical because the quote-count cap already holds N at 6.",
    activation: "LQD only (the backbone fit, always computed); SVI / MCS overlays ignore it.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["regLambda", "regPower", "nCores", "help:guides:parametric"],
    docs: ["01_lqd_model_lecture", "01_lqd_model_coordinates"],
  },
  {
    key: "lqdCoords",
    model: "fit",
    section: "opt-parametric",
    label: "LQD solve coordinates",
    summary: "Pick the coordinate chart the LQD optimizer walks in; the fitted smile is the same to solver tolerance.",
    details:
      "`logistic` (default) solves in (log A_L, logit A_R, body modes): the body modes are endpoint-neutral, so acute central convexity cannot mechanically drag the asymptotic wings, and the admissibility wall A_R < 1 is unreachable, so the solve is unconstrained and covers exactly the admissible set (committee revision R1). `endpoint` is the same chart without the logit; `lr` is the historical raw (L, R, a) vector.\n\n" +
      "All three share one family and one objective, so the optimum is chart-independent: what changes is convergence speed and how often a wild iterate meets the `barrierCenter` barrier. Not a model choice — for that use `model`.",
    example:
      "Set `lqdCoords` to `lr` on a short-dated skewed name and calibrate: the fitted smile matches the `logistic` fit to about 1e-6 in vol, but the solve may take more iterations and the A_R barrier row activates on some trial steps; switch back to `logistic` and those rows go quiet.",
    activation: "LQD only (the backbone fit, always computed).",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["barrierCenter", "barrierScale", "sviChart", "mcsChart"],
    docs: ["01_lqd_model_coordinates", "01_lqd_model_lecture"],
  },
  {
    key: "regLambda",
    model: "fit",
    section: "opt-parametric",
    label: "Damping λ",
    summary: "Strength λ of the high-order LQD damping λ·n^{2r}·a_n² on Legendre modes n ≥ 4.",
    details:
      "The ridge penalizes each body mode amplitude a_n by λ times n^{2r}, so high-order wiggles are damped while the first modes (a_2, a_3) stay free. The default 1e-6 is small enough to be inert on a well-populated smile yet stops a thin or noisy book from oscillating between quotes; `Off` (0) is exact interpolation.\n\n" +
      "Quote weights are normalized to mean 1, so the balance between data and this ridge is the same under every `weightScheme`. It shapes `lqd` fits only; SVI and MCS have their own regularizers (`sviPenaltyWeight`, `sigmoidRidge`).",
    example:
      "Raise `regLambda` to 1e-3 on a 40-quote SPY slice: the smile between the 5Δ and 25Δ puts flattens visibly, the highest Legendre modes collapse toward zero and the RMS to mid rises by a few bp; set it to `Off` on a 12-quote weekly and a small ripple appears between neighbouring strikes.",
    activation: "LQD only (the backbone fit, always computed).",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["regPower", "nOrder", "sigmoidRidge"],
    docs: ["01_lqd_model_lecture"],
  },
  {
    key: "regPower",
    model: "fit",
    section: "opt-parametric",
    label: "Damping power r",
    summary: "The exponent r in the LQD damping n^{2r}: how much harder high modes are penalized than low ones.",
    details:
      "With r = 1 (default) the penalty grows like n², a second-difference-type roughness weight; r = 2 makes it n⁴ and removes the top modes almost outright while leaving n = 4-6 alone; r = 0.5 is a gentle linear ramp.\n\n" +
      "Move it together with `regLambda`: a higher r at fixed λ damps the tail of the spectrum, a higher λ at fixed r damps everything. LQD fits only.",
    example:
      "Set `regPower` to 2.0 with `regLambda` at 1e-6 on a 16-mode slice: the mode-16 weight becomes 256 times the mode-4 weight (it was 16 times), so the shoulder detail carried by modes 12-16 fades while the body fit is unchanged.",
    activation: "LQD only (the backbone fit, always computed).",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["regLambda", "nOrder"],
    docs: ["01_lqd_model_lecture"],
  },
  {
    key: "tailAlphaLeft",
    model: "fit",
    section: "opt-parametric",
    label: "Tail α− (left / put side)",
    unit: "tail exponent α in [0, ½]",
    summary: "Fixed left-tail exponent of the generalized LQD tails: 0 = exponential log-return tail, 0.5 = Gaussian rate.",
    details:
      "The generalized-tails arc lets the LQD slice carry a tail class per side: α = 0 is the historical exponential tail (byte-identical default), 0.25 an intermediate class with every moment finite and a sublinear wing, 0.5 the Gaussian-rate endpoint where total variance tends to a constant — the `Exp` / `Int` / `Gauss` presets set both sides at once.\n\n" +
      "It is a POLICY input, never optimized: the α → 0 limit is nonuniform, so estimating α per slice is ill-conditioned by construction — compare scenarios instead. Moving it changes the deep put wing, the var-swap tail contribution and the extrapolated density; the quoted range is fitted the same way. Overlays (`svi`, `sigmoid`) ignore it; `tailAlphaByTicker` overrides it per underlier.",
    example:
      "Set `tailAlphaLeft` to 0.5 on a 3-month SPY slice: the put wing beyond the last quote bends toward a flat total variance instead of the linear-in-k exponential wing, the deep-tail density thins and the fitted var-swap level drops by a few vol bp, while the quoted strikes still sit on their mids.",
    activation: "LQD only (the backbone fit, always computed); overridden for a ticker present in `tailAlphaByTicker`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["tailAlphaRight", "tailAlphaByTicker", "ledgerTailOrderGate", "help:guides:parametric"],
    docs: ["01_lqd_model_lecture", "09_wings_last_quote"],
  },
  {
    key: "tailAlphaRight",
    model: "fit",
    section: "opt-parametric",
    label: "Tail α+ (right / call side)",
    unit: "tail exponent α in [0, ½]",
    summary: "Fixed right-tail exponent of the generalized LQD tails, the call-side mirror of `tailAlphaLeft`.",
    details:
      "Same classes and same policy status as the left exponent, applied to the call wing; asymmetric pairs are allowed (a light call tail over an exponential put tail is a common equity choice).\n\n" +
      "A positive α+ also moves the LQD admissibility guard: the `barrierCenter` / `barrierScale` pair is rescaled internally so the barrier keeps its relative position against the saddle guard, so you do not retune them. Overlays ignore it.",
    example:
      "Set `tailAlphaRight` to 0.25 and leave α− at 0 on a single name with a fat upside: the call wing beyond the last quote grows more slowly than the exponential fit, the right-tail mass in the density view drops, and the slice's tail pair reads (0, 0.25) in the fit summary.",
    activation: "LQD only (the backbone fit, always computed); overridden for a ticker present in `tailAlphaByTicker`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["tailAlphaLeft", "tailAlphaByTicker", "barrierCenter"],
    docs: ["01_lqd_model_lecture", "09_wings_last_quote"],
  },
  {
    key: "tailAlphaByTicker",
    model: "fit",
    section: "opt-parametric",
    label: "Tail α scope (per underlier)",
    summary: "Per-underlier overrides of the global (α−, α+) pair, keyed by ticker.",
    details:
      "The ratified α scope is one pair per underlier, common across that underlier's expiries: a ticker present here uses its own pair, every other ticker uses `tailAlphaLeft` / `tailAlphaRight`. In the Options dialog the `Global` / `<ticker>` scope toggle next to the tail inputs writes this map for the active smile ticker; the API accepts any map of `ticker -> [α−, α+]` with both values in [0, ½].\n\n" +
      "Switching the scope back to `Global` removes the ticker's entry rather than zeroing it. An unequal α between two adjacent slices of one ticker is irreducible for the calendar tail-order clause, which is why the scope is per underlier and not per expiry.",
    example:
      "With the global pair at (0, 0), set the scope to `NVDA` and enter 0.25 / 0.25: NVDA's expiries refit with intermediate tails and shorter wings, while the SPY and AAPL slices of the same universe refit to byte-identical exponential-tail smiles.",
    activation: "LQD only; read for the tickers listed in the map.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["tailAlphaLeft", "tailAlphaRight", "ledgerTailOrderGate"],
    docs: ["01_lqd_model_lecture", "10_calendar_unnamed_martingale"],
  },
  {
    key: "nCores",
    model: "fit",
    section: "opt-parametric",
    label: "MCS cores R",
    unit: "count (hat kernels)",
    summary: "Number R (0-2) of zero-wing hat kernels added to the Multi-Core Sigmoid base.",
    details:
      "The MCS slice is a sigmoid base plus R localized hat kernels — R is the MCS analogue of the LQD Legendre order. R = 0 is the plain base; each extra core adds four parameters (centre, width, steepness, amplitude), seeded greedily at the largest variance residuals and refined jointly.\n\n" +
      "It is hard-capped at 2 from a measured finding: three or more cores overfit and manufacture wing arbitrage. A persisted desk with a higher value is clamped, not rejected, so old saves still load. Kernel governance may prune a core whose amplitude sits below the quote-noise floor, so the displayed slice can use fewer than R.",
    example:
      "Slide `nCores` from 2 to 0 on an earnings-week single name with a kinked smile: the MCS overlay loses its local bump and reverts to the smooth base, the RMS to mid roughly doubles around the kink, and the `sivWingPenaltyPct` rows go quiet because the base alone cannot break convexity there.",
    activation: "Read only while `model` is `sigmoid`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["sigmoidRidge", "mcsChart", "sivWingPenaltyPct", "nOrder"],
    docs: ["03_multicore_mcs_corrections"],
  },
  {
    key: "barrierCenter",
    model: "fit",
    section: "opt-parametric",
    label: "LQD A_R barrier centre",
    unit: "A_R (right endpoint scale, wall at 1)",
    summary: "Where the soft barrier on the LQD right endpoint scale A_R starts to bite.",
    details:
      "The LQD right wing is admissible only while A_R < 1 (the finite-forward wall). The optimizer carries a softplus barrier `log(1 + exp(barrierScale · (A_R − barrierCenter)))`: negligible below the centre, rising linearly beyond it, so wild trial steps are repelled from the wall. The default 0.90 leaves every ordinary smile unconstrained while guarding the last 10% before the wall.\n\n" +
      "Under the `logistic` chart the wall is unreachable anyway, so the barrier is mostly a safety row for the `lr` and `endpoint` charts; with a positive `tailAlphaRight` the centre is rescaled internally to the saddle guard. It is not a fit target — it never pulls the smile toward anything.",
    example:
      "Lower `barrierCenter` to 0.60 on a steep upside-skew name: the fit can no longer reach the A_R ≈ 0.8 the quotes want, the call wing flattens below the mids and the barrier residual stays active in the fit diagnostics; move it back to 0.90 and the wing snaps onto the quotes.",
    activation: "LQD only (the backbone fit, always computed).",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["barrierScale", "lqdCoords", "tailAlphaRight"],
    docs: ["01_lqd_model_coordinates", "01_lqd_model_lecture"],
  },
  {
    key: "barrierScale",
    model: "fit",
    section: "opt-parametric",
    label: "LQD A_R barrier scale",
    unit: "softplus steepness",
    summary: "Steepness of the A_R soft barrier: how fast the penalty rises past `barrierCenter`.",
    details:
      "The softplus argument is `barrierScale · (A_R − barrierCenter)`, so the scale sets how sharp the transition from inert to active is — 50 (default) turns the barrier on within about ±0.02 of the centre, a near-hard wall placed at 0.90 rather than a gradual push.\n\n" +
      "A smaller value smears the barrier into the admissible region and starts to bias fits with A_R around 0.7-0.9; a larger value only matters for the trust-region step control on wild iterates. Leave it unless you are tuning an `lr`-chart solve.",
    example:
      "Set `barrierScale` to 5 on a name whose fit has A_R ≈ 0.85: the barrier now contributes a visible residual inside the admissible region and the call wing sits a few bp under the mids; at 50 the same fit is unaffected.",
    activation: "LQD only (the backbone fit, always computed).",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["barrierCenter", "lqdCoords"],
    docs: ["01_lqd_model_coordinates"],
  },
  {
    key: "sviPenaltyWeight",
    model: "fit",
    section: "opt-parametric",
    label: "SVI no-arb penalty",
    unit: "weight",
    summary: "Weight of the SVI soft no-arbitrage hinges: minimum total variance ≥ 0 and the Lee wing-slope cap.",
    details:
      "Two hinge rows, `max(−w_min, 0)` and `max(b(1+|ρ|) − leeSlopeMax, 0)`, are multiplied by this weight and appended to the SVI residual vector; both are exactly zero on an admissible slice, so a clean fit never feels them. The default 1e3 is the historical constant that makes a violation cost as much as a large mid miss without stiffening the problem.\n\n" +
      "Under the `structural` chart every iterate is admissible by construction and these rows are inert whatever the weight; the belly-repair hinge (`bellyRepair`) reuses the same weight.",
    example:
      "Set `sviPenaltyWeight` to 0 with `sviChart = raw` on a thin far-dated slice: the optimizer is free to push `b(1+|ρ|)` past 2 to chase a wing quote, Quality flags a Lee-bound break on that node and the density view shows a negative lobe in the wing; restore 1000 and the wing settles at the cap.",
    activation: "Read only while `model` is `svi`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["leeSlopeMax", "sviChart", "bellyRepair", "help:glossary:lee-bound"],
    docs: ["02_svi_jw_rewrite", "02_svi_jw_moments"],
  },
  {
    key: "leeSlopeMax",
    model: "fit",
    section: "opt-parametric",
    label: "SVI Lee slope max",
    unit: "total-variance slope per unit log-strike",
    summary: "Cap on the SVI asymptotic wing slope b(1+|ρ|), buffered strictly under Lee's moment bound of 2.",
    details:
      "Lee's bound says total variance can grow at most like 2|k| in the wings; SVI's steeper wing slope is b(1+|ρ|). The cap was 2.0 and is 1.95 since committee revision R1: β = 2 itself admits negative tail density, and with the hinge sitting at zero exactly on the broken boundary a production fit could land there with no violation reported. 2.0 is reachable only as explicit configuration.\n\n" +
      "Under the `structural` charts (SVI, and MCS when `mcsChart` is `structural`) the wings are lifted logistically against this cap so every iterate is strictly Lee-clean; under the `raw` SVI chart it is enforced through the hinge weighted by `sviPenaltyWeight`.",
    example:
      "Lower `leeSlopeMax` to 1.5 on a high-skew single name: the SVI put wing flattens visibly beyond the 10Δ strike, the far-put mids sit above the fitted curve and the RMS rises there, while the density's left tail thins and stays positive.",
    activation: "Read for `svi` fits, and for `sigmoid` fits under the `structural` MCS chart.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["sviPenaltyWeight", "sviChart", "mcsChart", "help:glossary:lee-bound"],
    docs: ["02_svi_jw_rewrite", "02_svi_jw_moments", "09_wings_last_quote"],
  },
  {
    key: "sviChart",
    model: "fit",
    section: "opt-parametric",
    label: "SVI solve chart",
    summary: "Coordinate chart the SVI optimizer works in: the historical raw vector, or the structural chart that is Lee-clean by construction.",
    details:
      "`structural` solves in (β_L, β_R, k*, w*, κ*) with lifts, so every finite iterate has a strictly positive variance floor and strictly Lee-clean wings — the no-arb penalties become inert. It is the default since the 2026-07-26 benchmark adjudication: better or equal precision in all 12 regime medians, zero breaks, 594 vs 9 472 evaluation-cap exhaustions and about 3× faster; the raw chart's lower headline arbitrage rate turned out to be a survivorship artifact of its non-converged third.\n\n" +
      "`raw` is the (a, b, ρ, m, σ) vector with soft feasibility penalties, kept for comparability and rollback. Same family and objective, so on clean quotes both charts give the same smile to solver tolerance.",
    example:
      "Switch `sviChart` to `raw` on a universe of 40 short-dated slices and recalibrate: the batch takes noticeably longer, a handful of nodes hit the evaluation cap, and Quality may flag a wing-slope break that the structural chart cannot produce.",
    activation: "Read only while `model` is `svi`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["sviPenaltyWeight", "leeSlopeMax", "mcsChart", "lqdCoords"],
    docs: ["02_svi_jw_rewrite"],
  },
  {
    key: "bellyRepair",
    model: "fit",
    section: "opt-parametric",
    label: "Belly repair (SVI / MCS)",
    summary: "When a displayed overlay fit fails the belly butterfly certificate, refit once with a belly hinge and keep the repair only if it certifies.",
    details:
      "The belly certificate checks Durrleman's g(k) ≥ 0 on a dense grid across the traded range. With the toggle on (committee R2 rider), a failing SVI or MCS fit is re-solved a single time with the hinge `penalty · max(−g + margin, 0)` added, the small margin pushing a repaired dip just past zero so the certificate's own tolerance passes cleanly; the repair is kept only if it certifies, otherwise the first fit stands. Clean first fits never see a second solve, so the default costs nothing on liquid names.\n\n" +
      "The Quality card marks a repaired node with `·R` next to its belly min-g. This is not the LQD path (LQD is convex by construction) and not the wing regularizer (`sivWingPenaltyPct`), which acts outside the quoted range. API-only: no control in the Options dialog.",
    example:
      "Set `bellyRepair` false and calibrate a noisy single name in `svi`: a node whose belly min-g reads −0.004 keeps that small butterfly dip and Quality lists it; with the toggle on the same node is re-solved once, its card shows `·R` and min-g ≥ 0.",
    activation: "Read for the displayed `svi` / `sigmoid` overlay fits.",
    cacheEffect: "fit-version",
    surfaced: false,
    related: ["sviPenaltyWeight", "sivWingPenaltyPct", "help:guides:quality"],
    docs: ["02_svi_jw_rewrite", "03_multicore_mcs_corrections"],
  },
  {
    key: "sigmoidRidge",
    model: "fit",
    section: "opt-parametric",
    label: "MCS hat ridge",
    unit: "weight",
    summary: "Ridge weight on the Multi-Core Sigmoid hat-kernel amplitudes.",
    details:
      "Each hat core's amplitude a_j enters the residual vector as √ridge · a_j — a mild pull toward zero that stops two cores from taking large opposite amplitudes to fit one noisy quote. The default 1e-2 is the historical constant; it is small against unit-mean quote weights, so a well-supported bump survives while an unsupported one shrinks, and the kernel-governance step then prunes an amplitude below the noise floor entirely.\n\n" +
      "Not the same object as `regLambda` (the LQD Legendre damping) or `sivWingPenaltyPct` (the put-wing convexity penalty).",
    example:
      "Raise `sigmoidRidge` to 1.0 on an earnings-week smile: the fitted hat amplitudes halve, the local bump around the pinned strike flattens toward the base, and the RMS to mid on those three strikes rises by a few vol bp.",
    activation: "Read only while `model` is `sigmoid`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["nCores", "mcsChart", "sivWingPenaltyPct", "regLambda"],
    docs: ["03_multicore_mcs_corrections"],
  },
  {
    key: "mcsChart",
    model: "fit",
    section: "opt-parametric",
    label: "MCS solve chart",
    summary: "Coordinate chart of the Multi-Core Sigmoid optimizer: the historical raw vector, or the wing-admissible structural chart.",
    details:
      "`raw` (default) is the historical base-plus-kernels vector with soft feasibility penalties — byte-identical to the fits the benchmark pack was adjudicated on. `structural` solves the base in (β_L, β_R, z*, v*, κ_p, κ_c) with the k-space Lee wing slopes lifted logistically against the buffered `leeSlopeMax` cap, so every iterate has strictly Lee-clean base wings by construction (the `sviChart` precedent), but it is about 20× slower at R = 2.\n\n" +
      "The default stays `raw` until the MCS adjudication sweep ratifies a flip — the same pre-registered-benchmark-then-flip path `sviChart` took.",
    example:
      "Set `mcsChart` to `structural` on a single 6-month slice: the fitted smile matches the raw fit within solver tolerance on clean quotes, the solve takes several seconds instead of a fraction of one, and the base wings can never breach the Lee cap.",
    activation: "Read only while `model` is `sigmoid`.",
    cacheEffect: "fit-version",
    surfaced: true,
    related: ["sviChart", "leeSlopeMax", "nCores", "sigmoidRidge"],
    docs: ["03_multicore_mcs_corrections", "02_svi_jw_rewrite"],
  },
];

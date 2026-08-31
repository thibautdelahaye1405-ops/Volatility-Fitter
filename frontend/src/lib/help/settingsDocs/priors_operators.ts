// Help Center settings corpus — Prior persistence section, modes + strike
// anchor + quote operators (SettingsSectionId "opt-prior"). One SettingDoc per
// OptionsSettings field that picks the persistence mode, places the strike-gap
// anchor, selects the quote operators and tunes the shared activation gate
// (required precision, gap exponent, support bandwidth, covariance mode,
// two-pass, collar sign). The smile factors and the tail carriers (deep-tail
// anchor, var-swap carrier, wing-slope operators, active-filter carve-out)
// live in priors_tails.ts; priors.ts concatenates both into PRIOR_DOCS.
//
// Meaning is taken from the `#:` comments of volfit/api/schemas.py
// OptionsSettings (authoritative), Docs/handoff/SETTINGS_REFERENCE.md §2.6,
// Docs/handoff/notes/13_prior_flat_directions.md (§6 "The policy layer",
// §6.1 two-pass, Appendix A) and the labels / tooltips of
// components/PriorPersistencePanel.tsx. Machine facts render from
// settingsSchema.json next to this prose.
//
// Cache discipline: every field bumps the options version (parametric refits)
// except the legacy `autoLoadPrior`, which no longer gates anything.
import type { SettingDoc } from "../types";

export const PRIOR_OPERATOR_DOCS: SettingDoc[] = [
  {
    key: "autoLoadPrior",
    model: "options",
    section: "opt-prior",
    label: "Auto-load prior (legacy)",
    summary: "LEGACY switch kept only to migrate settings saved before the persistence modes existed.",
    details:
      "`priorPersistenceMode` is the single source of truth for prior gating; this field no " +
      "longer gates calibration and is not shown in the dialog. It survives so a pre-mode " +
      "persisted blob restores its exact behaviour: on store load a blob without " +
      "`priorPersistenceMode` becomes `strike_gap` when this was true and `off` otherwise, " +
      "instead of jumping to the new `hybrid` default. It also round-trips for API " +
      "back-compat.\n\n" +
      "Toggling it today changes nothing in any fit and busts no cache.",
    example:
      "A desk saved in 2026-05 with `autoLoadPrior = true` reloads as " +
      "`priorPersistenceMode = strike_gap` — the same data-gap anchor it had — while a fresh " +
      "install with no blob starts in `hybrid`.",
    cacheEffect: "display-only",
    surfaced: false,
    related: ["priorPersistenceMode", "priorAnchorWeightPct", "help:guides:priors"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorPersistenceMode",
    model: "options",
    section: "opt-prior",
    label: "Prior persistence",
    summary: "Choose how a fetched prior is persisted into today's calibration.",
    details:
      "`off`: no overlay, no penalty — pure current market. `overlay`: draw the dotted " +
      "transported prior only. `strike_gap`: the legacy data-gap anchors at the " +
      "`priorAnchorDeltas`. `quote_operator`: persist ATM / RR / BF / var-swap only where " +
      "today's quotes do not identify them. `smile_factor`: persist ATM level / skew / " +
      "curvature the same way. `hybrid` (recommended default): operators plus a residual " +
      "deep-tail strike anchor — quotes own the level, operator legs carry the shape as far " +
      "as they reach, tail anchors hold the wing beyond. `graph_only`: lit calibration stays " +
      "market-pure and the graph baseline carries the prior to dark nodes.\n\n" +
      "Every operator, factor and anchor is gap-gated: a well-observed coordinate gets ZERO " +
      "prior weight, so persistence never damps a move the market shows. Under an `active` " +
      "observation filter the builders overlapping the filtered handles are auto-excluded. " +
      "Applies once a prior has been fetched (Save / Fetch priors).",
    example:
      "Switch a wing-sparse node from `hybrid` to `off`: the dotted prior disappears, the " +
      "fitted 2Δ put wing swings to the model's own extrapolation, and the Evidence tab lists " +
      "no active operators.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorSet", "priorTailAnchorStrengthPct", "observationFilterMode",
      "help:guides:priors", "help:guides:graph"],
    docs: ["13_prior_flat_directions", "14_graph_three_priors"],
  },
  {
    key: "priorAnchorWeightPct",
    model: "options",
    section: "opt-prior",
    label: "Anchor weight (%)",
    unit: "% of summed quote weights",
    summary: "Budget of the strike-gap prior anchor, as a percentage of the node's summed quote weights.",
    details:
      "The total weight given to the data-gap anchor, distributed across the delta-locations " +
      "in proportion to the observed-vs-desired quote-density deficit: dense zones ignore the " +
      "prior, sparse wings lean on it. 50% means an unquoted wing is held with half the " +
      "weight of the whole quoted chain — strong enough to keep the wing shape, weak enough " +
      "that any real quote there wins.",
    example:
      "At 50% on a node quoted only between the 20Δ strikes, the 2/5/10Δ anchors hold the " +
      "prior wing at half the summed quote weight; at 0 the wings float on the model's own " +
      "extrapolation.",
    activation: "Read only in `strike_gap` mode.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorAnchorDeltas", "priorTailAnchorStrengthPct", "priorPersistenceMode"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorAnchorDeltas",
    model: "options",
    section: "opt-prior",
    label: "Anchor Δ (%, per side)",
    unit: "forward Black delta in (0, 0.5)",
    summary: "Per-side delta locations where the strike anchors are placed.",
    details:
      "Each value is a forward Black delta; ATM is always added and the var-swap prior " +
      "carries the aggregate tail below the smallest delta. Values are deduplicated, sorted " +
      "and kept strictly inside (0, 0.5); an empty list falls back to the default set.\n\n" +
      "In `hybrid` the panel labels it \"Tail Δ\": only the deltas strictly below the " +
      "shallowest active wing operator (2/5/10Δ with RR25/BF25; {2, 5}Δ if the set has no " +
      "wing operator) become deep-tail anchors. The WingL / WingR operators measure the slope " +
      "between the two outermost of these deltas.",
    example:
      "Enter `2, 5` in `hybrid` with RR25/BF25 active: the deep-tail anchor holds only the 2Δ " +
      "and 5Δ strikes and the 10Δ region is left to the smile between the operator legs and " +
      "the tail. Add `45` and the hybrid rule drops it (it sits above the 25Δ legs).",
    activation: "Read in `strike_gap` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorAnchorWeightPct", "priorTailAnchorStrengthPct", "priorOperatorSet"],
    docs: ["13_prior_flat_directions", "09_wings_last_quote"],
  },
  {
    key: "priorOperatorSet",
    model: "options",
    section: "opt-prior",
    label: "Operators",
    summary: "Quote operators the prior may persist: ATM, RR25/BF25, RR10/BF10, WingL/WingR, VarSwap.",
    details:
      "RR = call-delta minus put-delta vol (sign per `collarSign`), BF = wings minus ATM, " +
      "VarSwap = the var-swap companion row. WingL / WingR persist each side's deep-wing vol " +
      "SLOPE between the two outermost `priorAnchorDeltas` — the tail shape without pinning " +
      "its level — with a budget share set by `priorWingSlopeScale`. Unknown names are " +
      "dropped; an empty set falls back to the default.\n\n" +
      "Every operator is gap-gated by the shared activation gate, so adding one to a densely " +
      "quoted name costs nothing: its gap reads 0 and its λ is 0 in the Evidence tab.",
    example:
      "Add `WingL` on a single name whose 2Δ–5Δ puts are rarely quoted: the Evidence table " +
      "shows a WingL row with gap ≈ 1 and a λ share of the operator budget. On SPY, where " +
      "those strikes are dense, the same row shows gap 0 and λ 0.",
    activation: "Read in `quote_operator` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorStrengthPct", "priorWingSlopeScale", "collarSign",
      "wingOperatorsUnderActiveFilter"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorOperatorStrengthPct",
    model: "options",
    section: "opt-prior",
    label: "Operator strength (%)",
    unit: "% of summed quote weights",
    summary: "Base operator-prior budget, as a percentage of the node's summed quote weights.",
    details:
      "The budget is split across the active operators by their shares and each row is then " +
      "multiplied by its activation gap, so a fully observed operator receives zero whatever " +
      "this says. 50% puts the whole operator block at half the market's weight where the " +
      "market is silent, the same order as the strike-gap default.",
    example:
      "Set 200% on a thin single name: the RR25 row's λ quadruples where its gap is 1 and " +
      "the fitted skew tracks yesterday's more closely; the ATM row still gets zero while " +
      "today's ATM quotes are tight.",
    activation: "Read in `quote_operator` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorSet", "priorOperatorRequiredPrecision", "priorFactorStrengthPct"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorOperatorRequiredPrecision",
    model: "options",
    section: "opt-prior",
    label: "Required precision",
    summary: "Observation-precision threshold π_req above which an operator's or factor's prior row turns off.",
    details:
      "The activation gate is gap = max(1 − obs / req, 0)^γ: once today's quotes identify a " +
      "coordinate at least this precisely, its prior weight is exactly zero — the \"do not " +
      "damp the signal\" rule. One scalar serves every operator and factor (per-operator " +
      "multipliers live in code). Raising it opens gates, so priors act even where quotes " +
      "exist; lowering it closes them.",
    example:
      "Raise it from 1 to 3: an operator whose quote-support precision reads 1.5 flips from " +
      "gap 0 (off) to gap 0.5 — half its budget now pulls today's fit toward the prior. " +
      "Watch the gap column of the Evidence tab.",
    activation: "Read in `quote_operator`, `smile_factor` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorGapExponent", "priorOperatorBandwidth", "priorDataOnlyPrepass"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorOperatorGapExponent",
    model: "options",
    section: "opt-prior",
    label: "Gap exponent γ",
    summary: "Sharpness γ of the activation gate gap = max(1 − obs/req, 0)^γ.",
    details:
      "γ = 1 is a linear ramp between fully observed (gap 0) and unobserved (gap 1). Above 1 " +
      "the gate stays nearly closed until precision is well below requirement, concentrating " +
      "the prior in the truly empty regions; below 1 it opens quickly, so even half-observed " +
      "coordinates take most of their budget.",
    example:
      "γ = 3 with obs/req = 0.5: the gap falls from 0.5 to 0.125 — the prior barely acts in " +
      "half-observed regions and puts its weight where there are no quotes at all.",
    activation: "Read in `quote_operator`, `smile_factor` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorRequiredPrecision", "priorOperatorBandwidth"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorOperatorBandwidth",
    model: "options",
    section: "opt-prior",
    label: "Support bandwidth / step",
    unit: "log-moneyness",
    summary: "Kernel bandwidth b of the quote-support measure around each operator leg; also the smile-factor stencil step.",
    details:
      "How far away a quote still counts toward identifying an operator leg. It doubles as " +
      "the stencil step of the smile factors (legs at k = 0, ±b; wing stencils at ±3b). " +
      "0.06 matches the observation filter's stencil half-width, so factors and filter " +
      "handles speak the same coordinates.\n\n" +
      "Wider: more quotes support each leg, precision rises, gates close and the prior " +
      "recedes. Narrower: a leg between two quotes finds none and its gate opens.",
    example:
      "Widen it to 0.15 on a chain quoted every 0.05 in k: every leg finds several quotes in " +
      "its kernel and the gaps close — the prior mostly disappears. At 0.02 a leg halfway " +
      "between two quotes reads unobserved and its row comes back.",
    activation: "Read in `quote_operator`, `smile_factor` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorRequiredPrecision", "priorFactorSet"],
    docs: ["13_prior_flat_directions", "15_kalman_computed_trust"],
  },
  {
    key: "priorOperatorCovarianceMode",
    model: "options",
    section: "opt-prior",
    label: "Operator covariance",
    summary: "Declared operator covariance model: per-operator diagonal, or Jacobian-propagated full.",
    details:
      "Only the diagonal covariance is ever persisted today. `full` is reserved for a later " +
      "upgrade and is cache-key only: changing it bumps the options version (every node " +
      "refits) and changes nothing else — the surfaces come back identical. Not shown in the " +
      "dialog.",
    example:
      "Set `full` through the API: all lit nodes refit and every fitted parameter matches " +
      "the `diagonal` run.",
    cacheEffect: "options-version",
    surfaced: false,
    related: ["priorOperatorSet", "filterCovarianceMode"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorDataOnlyPrepass",
    model: "options",
    section: "opt-prior",
    label: "Two-pass (don't damp signal)",
    summary: "Fit data-only first, measure each operator's realized precision, then refit with priors only on the under-observed ones.",
    details:
      "The default single pass gates on quote SUPPORT — a proxy for how well the fit will pin " +
      "each coordinate. The two-pass form measures the realized precision from a data-only " +
      "fit, so a well-observed move is never pulled back, at ~2× cost per node.\n\n" +
      "Same cost trade-off as `filterDataOnlyPrepass`; the two are independent fits.",
    example:
      "After a 3-vol-point ATM jump with tight quotes on only four near-ATM strikes, the " +
      "single pass may leave a small ATM gap open and damp the jump by a fraction; two-pass " +
      "measures the ATM as precisely pinned, drops the row and lands on today's level.",
    activation: "Read in `quote_operator`, `smile_factor` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorRequiredPrecision", "filterDataOnlyPrepass"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "collarSign",
    model: "options",
    section: "opt-prior",
    label: "Collar sign",
    summary: "Risk-reversal sign convention: call minus put, or put minus call.",
    details:
      "`call_put` = σ(call Δ) − σ(put Δ), `put_call` the opposite — a desk convention. The " +
      "operator and its prior value flip together, so the persisted information is the same " +
      "either way; what changes is the sign of the RR rows in the Evidence tab and in the " +
      "diagnostics.",
    example:
      "Switch to `put_call` on an equity index: the RR25 prior value in the Evidence table " +
      "reads +3.2 instead of −3.2 vol points and the fitted smile is unchanged.",
    activation: "Read in `quote_operator` and `hybrid` modes.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorSet"],
    docs: ["13_prior_flat_directions"],
  },
];

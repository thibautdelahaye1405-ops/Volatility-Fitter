// Help Center settings corpus — Prior persistence section, smile factors +
// tail carriers (SettingsSectionId "opt-prior"). One SettingDoc per
// OptionsSettings field of the `smile_factor` branch (factor set, budget) and
// of the tail-persistence arc: the hybrid deep-tail anchor budget, the prior
// var-swap carrier, the WingL / WingR slope scale and the Note 15 §6.3
// carve-out that lets the wing rows survive an active observation filter. The
// mode selector, strike anchor and quote operators live in
// priors_operators.ts; priors.ts concatenates both into PRIOR_DOCS.
//
// Meaning is taken from the `#:` comments of volfit/api/schemas.py
// OptionsSettings (authoritative), Docs/handoff/SETTINGS_REFERENCE.md §2.6,
// Docs/handoff/notes/13_prior_flat_directions.md, Note 15 §6 (the active-MAP
// auto-exclusion), the ROADMAP tail-persistence wrap and the labels /
// tooltips of components/PriorPersistencePanel.tsx. Machine facts render from
// settingsSchema.json next to this prose.
//
// Cache discipline: every field here bumps the options version.
import type { SettingDoc } from "../types";

export const PRIOR_TAIL_DOCS: SettingDoc[] = [
  {
    key: "priorFactorSet",
    model: "options",
    section: "opt-prior",
    label: "Factors",
    summary: "Smile factors the prior may persist in `smile_factor` mode: ATM, skew, curvature, wing slopes, VarSwap.",
    details:
      "The factors are read on a stencil at k = 0 and ±b (`priorOperatorBandwidth`), the " +
      "wing slopes at ±3b, so on a locally quadratic smile they are exact. Each is gap-gated " +
      "like an operator. Unknown names are dropped; an empty set falls back to the default.",
    example:
      "Drop `curvature` from the set on a node with five quotes: yesterday's curvature no " +
      "longer holds the belly and the fitted smile follows today's few quotes — watch the " +
      "belly widen.",
    activation: "Read only in `smile_factor` mode.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorFactorStrengthPct", "priorOperatorBandwidth", "priorOperatorSet"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorFactorStrengthPct",
    model: "options",
    section: "opt-prior",
    label: "Factor strength (%)",
    unit: "% of summed quote weights",
    summary: "Base factor-prior budget, as a percentage of the node's summed quote weights.",
    details:
      "The `smile_factor` counterpart of `priorOperatorStrengthPct`: split across the active " +
      "factors and multiplied by each factor's activation gap, so a well-observed factor " +
      "receives zero regardless of the budget.",
    example:
      "At 100% on a node with two quotes, the skew and curvature factors carry yesterday's " +
      "shape at the full weight of the market; at 10% the two quotes bend the smile freely " +
      "and the prior only whispers.",
    activation: "Read only in `smile_factor` mode.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorFactorSet", "priorOperatorStrengthPct"],
    docs: ["13_prior_flat_directions"],
  },
  {
    key: "priorTailAnchorStrengthPct",
    model: "options",
    section: "opt-prior",
    label: "Tail-anchor weight (%)",
    unit: "% of summed quote weights",
    summary: "Budget of the residual deep-tail strike anchor in `hybrid` mode.",
    details:
      "The strike-gap machinery restricted to the `priorAnchorDeltas` strictly below the " +
      "shallowest active wing operator, applied only where no operator or quote covers the " +
      "tail. It is smaller than the operator budget (20% vs 50%) because it only holds the " +
      "region the operators leave flat.\n\n" +
      "Under an `active` observation filter this anchor is what survives of persistence " +
      "(the filter carries the body); on the LV path it is nested inside the operators " +
      "branch, so LV gets no tail anchor there unless `wingOperatorsUnderActiveFilter` is on.",
    example:
      "Raise it to 100% on a name with no quotes below 10Δ: the 2Δ/5Δ put wing pins to the " +
      "transported prior nearly exactly. At 0 the wing is the model's own Lee-bounded " +
      "extrapolation.",
    activation: "Read only in `hybrid` mode.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorAnchorDeltas", "priorAnchorWeightPct", "wingOperatorsUnderActiveFilter"],
    docs: ["13_prior_flat_directions", "09_wings_last_quote"],
  },
  {
    key: "priorVarSwapMode",
    model: "options",
    section: "opt-prior",
    label: "Var-swap carrier",
    summary: "What the PRIOR var-swap companion row matches: the absolute var-swap vol, or its spread over ATM vol.",
    details:
      "`absolute` (historical) holds yesterday's var-swap vol level. `atm_spread` holds " +
      "(σ_vs − σ_atm) minus the prior spread — the tail-mass-over-body carrier: a level move " +
      "(for instance a filter-driven ATM update) carries the tail along instead of fighting a " +
      "stale absolute level.\n\n" +
      "MARKET var-swap quotes are always absolute — they are the truth. The LQD analytic " +
      "Jacobian carries the spread row; SVI / Multi-Core ride their finite-difference path; " +
      "Local Vol falls back to `absolute`.",
    example:
      "Filter active, ATM up 2 vol points overnight: `absolute` pulls the var-swap back " +
      "toward yesterday's 22% and flattens the wings; `atm_spread` keeps yesterday's " +
      "1.5-point spread and the var-swap follows to ~23.5%.",
    activation: "Read in any mode with a calibration prior (`strike_gap`, `quote_operator`, `smile_factor`, `hybrid`).",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorSet", "varSwapWeightPct", "varSwapHardPin", "observationFilterMode"],
    docs: ["08_varswap_representations", "13_prior_flat_directions"],
  },
  {
    key: "priorWingSlopeScale",
    model: "options",
    section: "opt-prior",
    label: "Wing slope scale",
    summary: "Budget share of the WingL / WingR slope rows relative to the body operators.",
    details:
      "λ ∝ scale · gap for the two wing rows, with the total operator budget conserved, so " +
      "raising it takes weight from ATM / RR / BF. `0` drops the wing rows. A degenerate " +
      "delta geometry (fewer than two usable outer deltas) silently drops them as well.",
    example:
      "At 2.0 each wing row takes twice the share of a body operator with the same gap; at 0 " +
      "they vanish from the Evidence table and ATM / RR / BF split the whole budget.",
    activation: "Read only while `WingL` or `WingR` is in `priorOperatorSet`.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorSet", "priorOperatorStrengthPct", "wingOperatorsUnderActiveFilter"],
    docs: ["13_prior_flat_directions", "09_wings_last_quote"],
  },
  {
    key: "wingOperatorsUnderActiveFilter",
    model: "options",
    section: "opt-prior",
    label: "Wings survive an active filter",
    summary: "Keep the WingL / WingR slope rows beside the Kalman MAP rows when the observation filter is active.",
    details:
      "Under an `active` filter the resolver drops every persistence builder that overlaps " +
      "the filtered handles (ATM / skew / curvature on the ±0.06 stencil) — two anchors to " +
      "the same previous state would count yesterday twice. The deep-wing SLOPE between the " +
      "two outermost anchor deltas is disjoint from that stencil, so the wing rows may " +
      "persist alongside the MAP rows without double counting (Note 15 §6.3 carve-out).\n\n" +
      "Off is the historical switch: the wings drop with ATM / RR / BF. Inert unless a Wing " +
      "operator is in `priorOperatorSet`. On the LV path it also unlocks the hybrid tail " +
      "anchor under an active filter.",
    example:
      "Filter active, `WingL` in the set. Off: the Evidence table shows only the MAP rows and " +
      "the deep-tail anchor. On: a WingL row reappears with its gap and λ, and the 2Δ–5Δ put " +
      "slope holds yesterday's shape while ATM follows the filter.",
    activation: "Read only while `observationFilterMode` is `active` and a Wing operator is in `priorOperatorSet`.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["priorOperatorSet", "priorWingSlopeScale", "observationFilterMode",
      "help:guides:filter", "help:glossary:handle"],
    docs: ["15_kalman_computed_trust", "13_prior_flat_directions"],
  },
];

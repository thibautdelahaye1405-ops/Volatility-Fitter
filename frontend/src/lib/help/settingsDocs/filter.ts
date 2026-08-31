// Help Center settings docs — the Observation filter section of the Options
// dialog (SettingsSectionId "opt-filter"): the 14 OptionsSettings fields of
// the time-series Kalman filter over the fitted smile handles (ATM vol, skew,
// curvature per node) — mode, measurement covariance route, process-noise
// budget, safety caps, the clock it accrues on and the measurement prepass.
// Prose only: type / default / range / enum render from settingsSchema.json.
//
// Sources (authoritative first): volfit/api/schemas.py OptionsSettings field
// comments; Docs/handoff/SETTINGS_REFERENCE.md §2.7; Docs/handoff/notes/
// 15_kalman_computed_trust.md (§3.3 inflation, §4 prediction budget, §4.1
// clock, §4.2 adaptive gate, §4.3 resets, Appendix A); UI labels from
// components/ObservationFilterPanel.tsx.
//
// Cache discipline: only the off <-> active transition of the mode changes a
// fit (options version); every other knob bumps the lightweight filter version.
import type { SettingDoc } from "../types";

export const FILTER_DOCS: SettingDoc[] = [
  {
    key: "observationFilterMode",
    model: "options",
    section: "opt-filter",
    label: "Observation filter",
    summary: "Run the Kalman filter over the smile handles: off, drawn as an overlay, or entering the fit as a MAP prior.",
    details:
      "`off`: the feature is absent — byte-identical fits, no handle state carried between " +
      "fetches. `overlay`: predict and update per snapshot and DRAW the filtered handles and " +
      "band on the smile; the calibration is untouched (the pilot mode). `active`: the " +
      "Kalman prediction enters the fit as a one-stage MAP residual block on the ±0.06 " +
      "stencil — never a second pass over the same quotes; the committed fit IS the " +
      "posterior. The panel labels `active` as pending validation.\n\n" +
      "Only the off ↔ active transition affects fits and bumps the options version; " +
      "off ↔ overlay only bumps the lightweight filter version. In `active` mode the " +
      "persistence builders overlapping the handles are auto-excluded (see " +
      "`wingOperatorsUnderActiveFilter`).",
    example:
      "Switch from `off` to `overlay` on a node fetched twice today: no refit happens, a " +
      "filtered band appears around the smile and the diagnostics table fills with per-expiry " +
      "gains. Switch to `active` and every lit node refits with the prediction as a prior.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["filterCovarianceMode", "filterProcessVolBpSqrtDay", "priorPersistenceMode",
      "help:guides:filter", "help:glossary:handle"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterCovarianceMode",
    model: "options",
    section: "opt-filter",
    label: "Covariance route",
    summary: "How the measurement covariance R of today's fitted handles is built.",
    details:
      "`jacobian`: R = ρ · G (JᵀWJ)⁺ Gᵀ, propagated from the fit's solution Jacobian — it " +
      "measures which handle directions today's quote locations identify, and in band modes " +
      "the in-spread quotes contribute nothing (their hinge rows differentiate to zero), " +
      "matching \"inside the spread the market is a set\". It is the backtested default.\n\n" +
      "`factors`: the cheap precision-factor builder (fit RMS × density × spread × " +
      "freshness) — the fallback when no Jacobian was retained (cached fits) and the A/B " +
      "column of the sweeps. It carries no separate ρ inflation (the RMS factor already " +
      "holds the misfit). The diagnostics table's route column shows which one actually ran.",
    example:
      "Pick `factors` on a Bid-Ask fit: the route column reads factors and in-band quotes " +
      "now count as identifying the mid through the scalar spread factor — the ATM gain " +
      "rises on a wide-spread chain where the Jacobian route had trusted the fit less.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterResidualInflation", "observationFilterMode", "priorOperatorCovarianceMode"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterProcessVolBpSqrtDay",
    model: "options",
    section: "opt-filter",
    label: "ATM noise (bp/√day)",
    unit: "vol bp/√day",
    summary: "ATM-level process noise q: how far the ATM handle may have walked per √day since the last observation.",
    details:
      "The clock term of the prediction budget, Q_clock = q² Δt. Higher q trusts today's fit " +
      "more (gain up, the filter follows the market); lower q smooths harder and lags.\n\n" +
      "The default is 30, up from the design note's 10, because the three-regime backtest " +
      "was one-sided: at 30 the posterior is calibrated (ζ std 0.8–1.9 versus 1.3–6.2 at 10) " +
      "and shock lag drops 3–8×, in every regime and on both covariance routes. The " +
      "sub-day campaign ran 90 on the session clock.",
    example:
      "Drop it to 10: the K(ATM) column falls (roughly 0.75 → 0.4 across a one-day gap) and " +
      "a 3-point overnight jump is followed only partly until the adaptive gate fires.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterProcessSkewSqrtDay", "filterProcessCurvSqrtDay", "filterClock",
      "filterAdaptiveSigma"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterProcessSkewSqrtDay",
    model: "options",
    section: "opt-filter",
    label: "Skew noise (/√day)",
    unit: "skew (dσ/dk) per √day",
    summary: "Process noise of the ATM skew handle per √day.",
    details:
      "The skew counterpart of the ATM clock term. The handle is the ATM slope dσ/dk, so " +
      "0.02 per √day means about two vol points of skew across one unit of log-moneyness. " +
      "At the defaults the sub-day campaign read skew ζ ≈ 1.8 — a little overconfident on " +
      "short-dated nodes, where 30-minute skew moves are larger than a daily clock expects.",
    example:
      "Raise it to 0.05 on a 0DTE-heavy universe: K(skew) rises toward 1 and the filtered " +
      "skew stops lagging the intraday repricing; on monthlies the band simply widens.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterProcessVolBpSqrtDay", "filterProcessCurvSqrtDay"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterProcessCurvSqrtDay",
    model: "options",
    section: "opt-filter",
    label: "Curvature noise (/√day)",
    unit: "curvature (d²σ/dk²) per √day",
    summary: "Process noise of the ATM curvature handle per √day.",
    details:
      "The curvature counterpart of the ATM clock term. Curvature is the least identified " +
      "handle — a stale close strike can force a large one — so its stated measurement noise " +
      "is usually what governs its gain, not this knob. The sub-day campaign read curvature " +
      "ζ ≈ 6.4 at the default, worst on short-dated nodes (30-minute curvature std 13.9 on " +
      "dailies), a recorded residual for a later pass.",
    example:
      "Raise it to 0.2 on dailies: the curvature prediction band widens, K(curv) climbs and " +
      "the filtered belly follows the intraday chain instead of yesterday's.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterProcessVolBpSqrtDay", "filterProcessSkewSqrtDay", "filterResidualInflation"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterTransportNoiseScale",
    model: "options",
    section: "opt-filter",
    label: "Transport noise ×",
    unit: "std per unit |log-forward| move",
    summary: "Extra process std added per unit of forward transport distance |h| = |log(F_now / F_prev)|.",
    details:
      "The mean is transported to today's forward by the spot-vol rule (ATM shifts by SSR · " +
      "skew · h, skew by curvature · h); this term prices the uncertainty of that transport, " +
      "proportional to |h| in each handle's typical move scale — the same intuition as the " +
      "prior-persistence transport factor. A quiet day (h ≈ 0) adds nothing; a large spot " +
      "move widens the prediction and hands the update to today's fit.",
    example:
      "Spot −4% overnight: at 1.0 the transport term dwarfs the clock term and the gains go " +
      "almost fully to today's fit; at 0.1 the clock term dominates and the filter still " +
      "blends yesterday's transported handles in.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterProcessVolBpSqrtDay", "dynamicsRegime", "ssr"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterResidualInflation",
    model: "options",
    section: "opt-filter",
    label: "Residual inflation",
    summary: "Inflate the measurement covariance by the fit's realized inconsistency ρ = clip(χ² / (m − d), 1, 25).",
    details:
      "The covariance from the Jacobian measures geometry — which directions the quote " +
      "locations identify — not whether the quotes agree. A dense cluster that cannot be " +
      "fitted within its stated noise is loud and wrong; ρ says so, and the cap keeps one " +
      "broken chain from poisoning the state. No threshold, no veto: the misfit turns the " +
      "dial.\n\n" +
      "Only the Jacobian route applies it — the factor route's RMS term already carries the " +
      "misfit. A rejected kink is not a rejected move: a coherent repricing across handles " +
      "goes through the adaptive gate instead.",
    example:
      "Kink two adjacent strikes of a clean 21-quote chain by ±3 vol points: ρ climbs from 1 " +
      "to 25, the curvature gain falls from 0.73 to 0.20 while the ATM gain stays at 0.74. " +
      "Off, the kink is trusted like a clean chain.",
    activation: "Read while the filter is `overlay` or `active` and the route is `jacobian`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterCovarianceMode", "filterAdaptiveSigma"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterAdaptiveSigma",
    model: "options",
    section: "opt-filter",
    label: "Adaptive gate (σ)",
    unit: "standardized innovation (σ)",
    summary: "Innovation gate above which the prediction covariance is inflated so a surprise reads as ~this many σ.",
    details:
      "A fixed clock cannot span calm and spike regimes — a genuine 5-point overnight jump is " +
      "~50σ under a 30 bp/√day prior. When a handle's standardized innovation |ν| / √(P⁻ + R) " +
      "exceeds the gate, P⁻ is inflated by (ζ / gate)², capped, and the gain rises toward the " +
      "data. Clean days never trip it (byte-identical below the gate); a contradictory chain " +
      "does not either, because its ρ-inflated R already shrinks the innovation. `0` " +
      "disables it.\n\n" +
      "`overlay` gates on today's innovation. `active` prices the surprise before the fit: " +
      "the level row through a fit-free ATM probe of the prepared mids, the shape rows " +
      "through the previous step's innovation. Measured on the spike fixtures: shock win rate " +
      "0.42 → 1.00, ζ std 3.8 → 0.8. Not shown in the dialog.",
    example:
      "Set it to 0 and refetch after a 5-point jump: K(ATM) stays near its clock value and " +
      "the filtered ATM lags the market by most of the jump for several steps; at 3 the gate " +
      "fires on the first step and the posterior lands within a fraction of a point.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: false,
    related: ["filterProcessVolBpSqrtDay", "filterResidualInflation", "filterMaxGain"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterMaxGain",
    model: "options",
    section: "opt-filter",
    label: "Max gain (1 = free)",
    unit: "gain",
    summary: "Pilot safety cap on the diagonalized per-handle Kalman gains.",
    details:
      "The update itself keeps every gain in [0, 1], so at 1.0 the cap never binds — it is " +
      "a pilot fence, not a tuning knob. Lowering it forces the filter to keep at least " +
      "(1 − cap) of the prediction whatever the data says, which defeats the computed-trust " +
      "design; use it only to demonstrate the lag.",
    example:
      "Set 0.5: every K column is clipped at 0.5, and a chain that fully identified its ATM " +
      "still lands halfway between prediction and fit — the filtered level trails a 2-point " +
      "move by one point.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterAdaptiveSigma", "filterProcessVolBpSqrtDay"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterResetHours",
    model: "options",
    section: "opt-filter",
    label: "Reset after (hours)",
    unit: "hours",
    summary: "Longest data gap the filter will predict across; a longer gap resets the state as stale.",
    details:
      "Predicting across a long dark period is worse than reseeding, so past this gap the " +
      "state resets with reset reason `stale` and reseeds from the transported saved prior " +
      "(or the committed fit's own handles at bootstrap precision). 96 hours spans a weekend " +
      "plus a holiday. The rule runs on calendar hours regardless of `filterClock`: staleness " +
      "is about data age, not variance accrual.\n\n" +
      "Other resets are not governed here: a manual quote edit resets the node, a source or " +
      "as-of change wipes the store. Every reset records its reason in the diagnostics table.",
    example:
      "Set 24 and fetch Monday morning: every node shows `stale` in the reset column and the " +
      "first Monday update is a reseed, not a blend with Friday's state. At 96 the weekend " +
      "is predicted across.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["filterClock", "observationFilterMode"],
    docs: ["15_kalman_computed_trust"],
  },
  {
    key: "filterClock",
    model: "options",
    section: "opt-filter",
    label: "Process-noise clock",
    summary: "Clock the process noise accrues on: wall-clock calendar days, or the intraday session variance clock.",
    details:
      "`calendar` is the legacy convention and byte-identical. `session` accrues " +
      "`filterSessionShare` of a day's variance inside the exchange session and " +
      "`filterNonTradingWeight` per closed day. Measured on the 2026-07 0DTE campaign (936 " +
      "measurements): 30-minute steps move ATM ~19.5 bp, one overnight ~55 bp and a whole " +
      "WEEKEND also ~55 bp — a closed market adds nothing an overnight does not already " +
      "contain, so no calendar q calibrates all three cadences (best ζ 1.04 / 0.53 / 0.23), " +
      "while share 0.60 / weight 0.0 at q = 90 bp gives ζ 0.95 / 0.89 / 0.84.\n\n" +
      "It is the sub-day workflow's setting. Do not confuse it with the maturity clock " +
      "(`intradayClock`, `sessionVarShare`, `nonTradingWeight`) — that one prices time to " +
      "expiry and carries different defaults for a nesting property. `filterResetHours` " +
      "stays on calendar hours. Not shown in the dialog.",
    example:
      "Switch to `session` with `filterProcessVolBpSqrtDay = 90` on a 30-minute fetch " +
      "cadence: the Monday-morning prediction band is as wide as one overnight's, not three " +
      "days', and K(ATM) after the weekend matches the overnight value instead of ~1.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: false,
    related: ["filterSessionShare", "filterNonTradingWeight", "filterProcessVolBpSqrtDay",
      "intradayClock", "filterResetHours"],
    docs: ["15_kalman_computed_trust", "11_event_market_clock"],
  },
  {
    key: "filterSessionShare",
    model: "options",
    section: "opt-filter",
    label: "Session share",
    unit: "fraction of a day's variance",
    summary: "Share of a day's process variance that accrues inside the exchange session under the session clock.",
    details:
      "0.60 is the filter's own measured value from the 0DTE campaign — the remaining 0.40 is " +
      "the overnight. It is deliberately not the maturity clock's `sessionVarShare` (6.5/24), " +
      "which is tuned so the legacy day convention nests. Not shown in the dialog.",
    example:
      "Set 0.9: nearly all of a day's variance accrues during the session, so the intraday " +
      "bands widen and the overnight prediction band shrinks — the 55 bp overnight move then " +
      "reads as a ~3σ surprise and trips the adaptive gate.",
    activation: "Read only while `filterClock` is `session`.",
    cacheEffect: "filter-version",
    surfaced: false,
    related: ["filterClock", "filterNonTradingWeight", "sessionVarShare"],
    docs: ["15_kalman_computed_trust", "11_event_market_clock"],
  },
  {
    key: "filterNonTradingWeight",
    model: "options",
    section: "opt-filter",
    label: "Non-trading day weight",
    unit: "day-weight",
    summary: "Variance weight of a closed calendar day (weekend, holiday) under the session clock.",
    details:
      "0.0 is the measured answer: a whole weekend moved the ATM handle ~55 bp, the same as " +
      "one overnight, so closed days should add no process variance. 1.0 recovers the " +
      "calendar behaviour where a 3-day weekend costs three full days of variance. Distinct " +
      "from the maturity clock's `nonTradingWeight` (default 1.0). Not shown in the dialog.",
    example:
      "Set 1.0 with the session clock: the Monday prediction band is three times an " +
      "overnight's and the weekend ζ drops toward 0.23 — error bars four times too wide.",
    activation: "Read only while `filterClock` is `session`.",
    cacheEffect: "filter-version",
    surfaced: false,
    related: ["filterClock", "filterSessionShare", "nonTradingWeight"],
    docs: ["15_kalman_computed_trust", "11_event_market_clock"],
  },
  {
    key: "filterDataOnlyPrepass",
    model: "options",
    section: "opt-filter",
    label: "Data-only prepass",
    summary: "Fit data-only first so the measurement fed to the filter is a clean market observation.",
    details:
      "With persistence priors on, the committed fit's handles are already pulled toward " +
      "yesterday, and feeding them to the filter would count the prior twice. On: an extra " +
      "data-only fit produces the measurement z_t, then the committed fit runs as usual " +
      "(~2× cost per node). Off: the committed fit's handles are reused and the step is " +
      "flagged contaminated (the ⚠ column) instead.\n\n" +
      "Same cost trade-off as `priorDataOnlyPrepass`; the two are independent fits.",
    example:
      "Turn it on in `hybrid` persistence: the ⚠ flags in the diagnostics table clear and " +
      "the innovation column grows on nodes whose fit the prior had been damping; calibrate " +
      "time roughly doubles.",
    activation: "Read while the filter is `overlay` or `active`.",
    cacheEffect: "filter-version",
    surfaced: true,
    related: ["priorDataOnlyPrepass", "priorPersistenceMode", "observationFilterMode"],
    docs: ["15_kalman_computed_trust", "13_prior_flat_directions"],
  },
];

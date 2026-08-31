// Help Center settings corpus — OptionsSettings, calibration group (HELP
// CENTER ARC, H2). One SettingDoc per OptionsSettings field of the Options ▸
// Calibration card (fit target, calendar coupling and its solver / floors /
// weight, the extrapolation guard, the tail-order gate, the band relaxation
// diagnostic, the variance-swap feature) plus the two API-only joint-carry
// knobs and the MCS wing penalty, which the Parametric card renders because
// it is MCS-only. Other OptionsSettings groups (events, prior, filter, LV
// grid, graph, workflow, dynamics) live in their own modules.
//
// Meaning is taken from the `#:` comments of volfit/api/schemas.py
// OptionsSettings (authoritative — including which fields bump the options
// version), the labels / hints of components/options/CalibrationSection.tsx,
// ParametricSection.tsx and VarSwapPanel.tsx, Docs/handoff/SETTINGS_REFERENCE.md
// and the ROADMAP.md session wraps. Machine facts come from settingsSchema.json.
import type { SettingDoc } from "../types";

export const CALIBRATION_DOCS: SettingDoc[] = [
  {
    key: "fitMode",
    model: "options",
    section: "opt-calibration",
    label: "Fit target",
    summary: "The persisted default fit target — Mid, Bid-Ask band or Haircut band — the session seeds from on load.",
    details:
      "`mid` penalizes |mid − model| only. `bidask` lets the curve sit anywhere inside [bid, ask] for free, pulls it back hard outside and centres it softly on mid (`midAnchorWeight`); `haircut` does the same on a band trimmed by `haircut` vol points per side.\n\n" +
      "The live target is a per-request parameter every fit receives, so the backend only stores this value and changing it never bumps the options version — the fit-cache key carries the mode itself. Save as default remembers it. The band targets are where `bandTickFloorTicks`, `midAnchorTauRef` and the `bandRelaxationDiagnostic` become active.",
    example:
      "Set the fit target to `bidask` on a wide-spread single name: the fitted curve stops chasing every mid, RMS to mid rises from 8 to 20 bp while band violations in Quality drop to zero, and the density gets smoother. Save as default and the next session opens in Bid-Ask.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["haircut", "midAnchorWeight", "bandTickFloorTicks", "help:guides:options"],
    docs: ["07_calibration_objective_measure"],
  },
  {
    key: "enforceCalendar",
    model: "options",
    section: "opt-calibration",
    label: "Arbitrage fix",
    summary: "Calendar-couple the Calibrate job so adjacent expiries of a ticker keep convex (no-calendar-arbitrage) order.",
    details:
      "When on, the background Calibrate couples each ticker's lit expiries: with the `symmetric` solver every slice is fitted independently, adjacent pairs are screened for an identified violation and only the violating runs are jointly repaired; with `sequential` each slice threads the previous one as a floor. Off, every expiry fits alone and calendar crossings are only measured in Quality, never repaired.\n\n" +
      "It gates `surfaceSolver`, `calendarFloorPadZ`, `calendarOnRefit` and `calendarWeight`. It changes calibration output, so it bumps the options version. Not the butterfly (within-slice) side — that is the model's own convexity plus the `bellyRepair` and `sivWingPenaltyPct` rows.",
    example:
      "Turn `enforceCalendar` off and calibrate a 12-expiry SPY surface with a data glitch on the 3rd expiry: the term view shows total variance dipping there and Quality lists a calendar crossing; turn it back on and the joint repair lifts the 3rd slice by the few bp needed while the other eleven refit byte-identically.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["surfaceSolver", "calendarWeight", "calendarOnRefit", "calendarFloorPadZ", "help:guides:quality"],
    docs: ["10_calendar_unnamed_martingale"],
  },
  {
    key: "surfaceSolver",
    model: "options",
    section: "opt-calibration",
    label: "Surface solver",
    summary: "How the calendar coupling is solved: symmetric screen-and-joint-repair (default) or the historical sequential front-to-back floor.",
    details:
      "`symmetric` fits every expiry independently, screens each adjacent interface for an identified violation (normalized-call order on the common quote support), then Gauss-Newton-repairs only the violation-connected components jointly — no traversal-order bias, and the correction is shared between the two slices by their data precision. `sequential` is the historical nearest-to-farthest pass where each slice inherits the previous one as a one-sided floor, so an early noisy slice pushes every later one up.\n\n" +
      "With the symmetric solver, `extrapEnforce` also arms the LQD tail contract rows in the joint repair. Changes calibration output, so it bumps the options version.",
    example:
      "Switch `surfaceSolver` to `sequential` on a surface whose front weekly is quoted 30 bp too rich: every later expiry is floored above it and the whole term structure lifts; back on `symmetric`, only the front pair is repaired and the correction lands mostly on the thin weekly.",
    activation: "Read only while `enforceCalendar` is on.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["enforceCalendar", "calendarWeight", "extrapEnforce", "ledgerTailOrderGate"],
    docs: ["10_calendar_unnamed_martingale"],
  },
  {
    key: "extrapEnforce",
    model: "options",
    section: "opt-calibration",
    label: "Extrapolation guard",
    summary: "Tapered no-arbitrage enforcement beyond the quoted strikes for the SVI / MCS overlays, plus the LQD tail contract under the symmetric solver.",
    details:
      "The overlay fits gain three hinge blocks in the extrapolated region: a butterfly hinge on the time-value envelope, a tapered calendar hinge against the previous displayed slice, and the wing-slope-order hinge — weighted like a handful of extra quotes, so they lean on the fit without outvoting the data. With the `symmetric` solver it also adds the LQD tail contract to the joint repair: per-interface seam price ordering and linear wing-slope (log endpoint scale) ordering rows.\n\n" +
      "Off (default) is byte-identical; the Quality tab's advisory measurement of the extrapolated region runs either way. Bumps the options version.",
    example:
      "Turn `extrapEnforce` on for a `svi` surface whose 1-month and 2-month put wings cross 3σ out: the 1-month wing bends under the 2-month one in the extrapolated zone of the smile chart, the Quality extrapolated-region calendar flag clears, and the quoted strikes move by under 1 bp.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["surfaceSolver", "ledgerTailOrderGate", "sivWingPenaltyPct", "help:guides:quality"],
    docs: ["09_wings_last_quote", "10_calendar_unnamed_martingale"],
  },
  {
    key: "ledgerTailOrderGate",
    model: "options",
    section: "opt-calibration",
    label: "Tail-order gate",
    summary: "Promote the full-line certificate's tail-order clause from advisory to a gate that the repair, Quality readiness and the publish export enforce.",
    details:
      "The full-line calendar certificate carries a tail-order clause (`ledgerTailOrderOk`): the limiting tail order of adjacent slices. With the gate on, the active-set exchange treats a tail-order failure like a ledger-gap failure — the λ± seam rows at common α are its repair path (unequal α between the two slices is irreducible by construction) — the Quality readiness list names it and the publish export blocks on it.\n\n" +
      "Off (default) is the Phase-0 advisory policy, byte-identical. It affects the surface repair, so it bumps the options version. Keep α common across a ticker's expiries (`tailAlphaByTicker`) so the seam rows have a repair path.",
    example:
      "Turn `ledgerTailOrderGate` on for a ticker whose 6-month slice has a heavier put tail than its 9-month: the repair adds seam rows that shorten the 6-month wing by a few bp, Quality shows the node ready again, and the export no longer stops on it.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["surfaceSolver", "extrapEnforce", "tailAlphaByTicker", "help:guides:quality"],
    docs: ["10_calendar_unnamed_martingale", "09_wings_last_quote"],
  },
  {
    key: "bandRelaxationDiagnostic",
    model: "options",
    section: "opt-calibration",
    label: "Band relaxation diagnostic",
    summary: "After the surface pass, report the smallest symmetric quote-band widening under which each uncertified adjacent pair would certify.",
    details:
      "For every adjacent pair the active-set exchange could not certify, the diagnostic bisects the smallest symmetric widening of the quote bands (in vol) that makes the pair calendar-feasible and reports it as `bandRelaxationVol` on the Quality node and in the export notes — the book's smallest quote-band relaxation needed for feasibility.\n\n" +
      "Advisory only: the accepted surface is untouched and it never bumps the options version. It runs only in the band fit targets on uncertified pairs, so on a clean surface it costs nothing.",
    example:
      "Turn `bandRelaxationDiagnostic` on in Bid-Ask mode on a surface with one stubborn front pair: the Quality card shows a band relaxation of 0.8 vol pt on that node — the quotes themselves are inconsistent by that much — while every certified pair shows nothing.",
    activation: "Runs only in the band fit targets (`bidask` / `haircut`), on adjacent pairs the exchange could not certify.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["enforceCalendar", "surfaceSolver", "fitMode", "help:guides:quality"],
    docs: ["10_calendar_unnamed_martingale"],
  },
  {
    key: "calendarFloorPadZ",
    model: "options",
    section: "opt-calibration",
    label: "Winged floors (σ pad)",
    unit: "σ_ref·√T beyond the common quote support",
    summary: "Extend both overlay families' calendar floor and ceiling grids this many σ√T beyond the common quote support.",
    details:
      "Historically the SVI calendar floor and ceiling lived only on the COMMON quote support of the two slices and MCS was winged at 2σ, so displayed smiles could keep calendar order across the quotes yet cross optically in the upside wing where the stacked IVs meet. With a value set, both families build their floor / ceiling grids winged that many σ_ref√T past the common support, so order holds out into the wing.\n\n" +
      "Empty is the historical per-family scope, byte-identical. Calibration-affecting, so it bumps the options version.",
    example:
      "Set `calendarFloorPadZ` to 2.0 on a `svi` single-name surface where the 1-week and 2-week call wings cross 15% above spot: the crossing disappears from the stacked smile chart, the 1-week upside wing lowers by a few bp beyond its last quote, and the quoted strikes are essentially unchanged.",
    activation: "Read only while `enforceCalendar` is on; shapes the `svi` / `sigmoid` overlays.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["enforceCalendar", "calendarOnRefit", "extrapEnforce", "model"],
    docs: ["10_calendar_unnamed_martingale"],
  },
  {
    key: "calendarOnRefit",
    model: "options",
    section: "opt-calibration",
    label: "Calendar on refit",
    summary: "Keep the calendar coupling on single-node refits by threading the adjacent committed slices as a confined floor and ceiling.",
    details:
      "An independent recompute of one node (an auto-calibrate tick, a quote edit, an undo) has no cross-expiry context, so it silently voids the surface pass's coupling until the next full Calibrate. With this on, a single-node fit reads the ADJACENT committed displayed slices read-only — previous expiry as floor, next as ceiling (LQD price floor, overlay variance floor / ceiling) — the sequential-pass construction; a stale neighbour is skipped, never refit.\n\n" +
      "A neighbour's content fingerprint joins the fit key only while the toggle is on, so a changed neighbour marks this node stale for free; the recorded consequence is that a surface sweep leaves earlier nodes stale-badged once later neighbours commit. Off is byte-identical; bumps the options version.",
    example:
      "Turn `calendarOnRefit` on, then delete one quote on the 2-month slice of a coupled SPY surface: the single-node refit still respects the 1-month floor and the 3-month ceiling (a crossing that would have appeared is crushed about 2000×), and the 1-month and 3-month tabs show a stale badge until you recalibrate.",
    activation: "Read only while `enforceCalendar` is on.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["enforceCalendar", "surfaceSolver", "autoCalibrate", "help:guides:workflow"],
    docs: ["10_calendar_unnamed_martingale"],
  },
  {
    key: "calendarWeight",
    model: "options",
    section: "opt-calibration",
    label: "Calendar weight",
    unit: "weight",
    summary: "Quadratic weight of the calendar-slack rows folded into coupled surface slice fits.",
    details:
      "In a coupled fit the previous slice's floor enters as hinge rows `√calendarWeight · max(floor − model, 0)`; 1e6 is the codebase's stiff-row idiom for an equality-like constraint — the same order `varSwapHardPin` uses — so the floor holds to solver tolerance rather than trading off against quotes.\n\n" +
      "Lower it and calendar order becomes a soft preference the quotes can outvote; raise it and the trust-region step only gets stiffer. Historically the one field that changed calibration output, so it bumps the options version.",
    example:
      "Cut `calendarWeight` to 1e2 on a surface with a rich front weekly: the joint repair no longer fully lifts the crossing, Quality shows a residual calendar violation of a few bp on the front pair, and the weekly's quotes fit a little tighter; at 1e6 the crossing is closed exactly.",
    activation: "Read only while `enforceCalendar` is on.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["enforceCalendar", "surfaceSolver", "varSwapHardPin"],
    docs: ["10_calendar_unnamed_martingale"],
  },
  {
    key: "varSwapEnabled",
    model: "options",
    section: "opt-calibration",
    label: "Variance-swaps",
    summary: "Surface variance-swap levels and let a var-swap quote pull the calibrated slice through a penalty row.",
    details:
      "On, the Smile / Term / Table views show each node's fair var-swap level (the log-contract replication of the fitted surface) and accept a var-swap quote; a quoted node gets one extra residual row pulling its model var-swap to the quote with weight `varSwapWeightPct`. Off hides the levels, ignores any quotes and drops the rows — fits without var-swap quotes are byte-identical either way.\n\n" +
      "Gates `varSwapWeightPct`, `varSwapHardPin` and `varSwapMethod`. The prior's var-swap carrier row is a separate feature (`priorOperatorSet`). Bumps the options version.",
    example:
      "Turn `varSwapEnabled` on and enter a 19.5 var-swap quote on a SPY 3-month node whose fitted level reads 18.9: the slice's wings lift a few bp to move the replicated variance toward 19.5 (how far depends on `varSwapWeightPct`), and the Term view's var-swap curve shows the quote marker.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["varSwapWeightPct", "varSwapHardPin", "varSwapMethod", "help:guides:parametric"],
    docs: ["08_varswap_representations"],
  },
  {
    key: "varSwapWeightPct",
    model: "options",
    section: "opt-calibration",
    label: "Var-swap weight (%)",
    unit: "% of the node's summed option-quote weights",
    summary: "Weight of the var-swap penalty row as a percentage of the node's summed option-quote weights.",
    details:
      "At 100% one active var-swap quote weighs as much as all of the node's option quotes combined; the default 10% makes it a firm nudge on the tail mass without overriding the quoted strikes. Option weights are normalized to mean 1, so the percentage means the same thing under every `weightScheme`.\n\n" +
      "`varSwapHardPin` overrides it with a stiff row. Bumps the options version.",
    example:
      "Raise `varSwapWeightPct` from 10 to 100 on a node quoted 0.6 vol pt above its fitted var-swap: the fitted level closes most of the gap, the unquoted put wing steepens to supply the missing variance and the quoted strikes drift 1-3 bp; at 10 the gap only closes by about a fifth.",
    activation: "Read only while `varSwapEnabled` is on and the node carries a var-swap quote.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["varSwapEnabled", "varSwapHardPin", "weightScheme"],
    docs: ["08_varswap_representations", "07_calibration_objective_measure"],
  },
  {
    key: "varSwapHardPin",
    model: "options",
    section: "opt-calibration",
    label: "Hard pin (var-swap panel)",
    summary: "Escalate the market var-swap row to a stiff equality so the fitted var-swap matches the quote to solver tolerance.",
    details:
      "The MARKET var-swap row's weight is multiplied by the stiff-row factor (10⁴× the node's summed quote weights — the same idiom as the 1e6 calendar rows), so the fit lands on the quote to within about 2e-5 vol where the soft row leaves more than 5e-4. It is a stiff row, not a true constraint. PRIOR var-swap rows stay soft on purpose: pinning to a stale prior would be dangerous.\n\n" +
      "The toggle lives in the Var-swap panel of the Parametric lens (not the Options dialog) and shows a `pinned` chip; it applies on the next refit, so the stale badge shows until then. Off is byte-identical; bumps the options version.",
    example:
      "Turn on `Hard pin` on a node quoted 21.0 while the soft fit reads 20.7: after the refit the panel shows `pinned` and a fitted level of 21.00, the wings have moved to supply the variance, and the option RMS rises slightly where the strikes had to give.",
    activation: "Read only while `varSwapEnabled` is on and the node carries a market var-swap quote.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["varSwapEnabled", "varSwapWeightPct", "calendarWeight"],
    docs: ["08_varswap_representations"],
  },
  {
    key: "varSwapMethod",
    model: "options",
    section: "opt-calibration",
    label: "Var-swap pricing",
    summary: "How the Local-Vol fit prices the model variance swap: static log-contract replication or the backward source PDE.",
    details:
      "`static` is the log-contract strike replication of the option surface (the k⁻²-weighted integral) — the route the parametric models always use — and it is sensitive to how far and how finely the strike grid extends into the wings. `source_pde` prices g(0,1) with the backward source PDE, a LOCAL quantity far less sensitive to coarsening or truncating the strike grid, which matters once the LV calibration grid is coarsened for speed.\n\n" +
      "Parametric (LQD / SVI / MCS) fits ignore it and stay on static replication. Calibration-affecting for LV, so it bumps the options version.",
    example:
      "Switch `varSwapMethod` to `source_pde` with a 12-node LV strike grid and a quoted var-swap: the LV fit's var-swap residual stops jumping by a few tenths of a vol point when you change `gridXNodes`, and the LV var-swap level agrees with the LQD replicated level to a few bp.",
    activation: "Read only while `varSwapEnabled` is on; Local-Vol fits only.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["varSwapEnabled", "gridXNodes", "lvXMaxMin", "help:guides:localvol"],
    docs: ["08_varswap_representations", "04_local_volatility_forward"],
  },
  {
    key: "jointCarry",
    model: "options",
    section: "opt-calibration",
    label: "Joint carry (borrow / de-Am)",
    summary: "Route the joint borrow / de-Americanization fixed point's converged forward and discount into the forwards every fit consumes.",
    details:
      "American chains hide the borrow inside early-exercise premium; the joint fixed point de-Americanizes at the split carry and iterates to the parity / theoretical fixed point per expiry. With this on, the converged (forward, discount) replaces the resolved forward for the fits — per expiry, and only when the converged |borrow| reaches `jointCarryEngageBp`; below that the parity forward is kept EXACTLY, so ordinary names stay byte-identical even with the toggle on. European chains are never touched.\n\n" +
      "API-only today: the Forwards lens `Joint carry` checkbox only adds the diagnostic Joint / ±σ columns to the ladder, it does not set this field. Resolved forwards feed every fit, so it bumps the options version.",
    example:
      "Set `jointCarry` true on a hard-to-borrow single name whose 3-month expiry converges to −180 bp of borrow: that expiry's forward drops by the borrow, the put-call IV split in the smile chart closes and the ATM kink disappears, while the front weekly (converged borrow 12 bp) keeps its parity forward.",
    activation: "American-exercise chains only; engages per expiry above `jointCarryEngageBp`.",
    cacheEffect: "options-version",
    surfaced: false,
    related: ["jointCarryEngageBp", "help:guides:forwards"],
    docs: ["05_deamericanization_stopping", "06_forwards_dividends_inference"],
  },
  {
    key: "jointCarryEngageBp",
    model: "options",
    section: "opt-calibration",
    label: "Joint carry engage threshold",
    unit: "bp of converged borrow",
    summary: "Materiality gate: the joint carry engages on an expiry only when its converged |borrow| is at least this many basis points.",
    details:
      "Below the threshold the parity forward is kept exactly, so the toggle costs nothing on names with ordinary carry; the default 25 bp is about the parity-forward noise of a liquid screen. Lower it to let small borrows through (more expiries move, more forward noise), raise it to engage only on hard-to-borrow expiries.\n\n" +
      "API-only, like `jointCarry`. Both knobs bump the options version because resolved forwards feed every fit.",
    example:
      "Lower `jointCarryEngageBp` from 25 to 5 on a universe of large-cap names: several expiries with 8-20 bp converged borrows now take the joint forward and their ATM vols shift by 1-3 bp; at 25 only the true hard-to-borrow names moved.",
    activation: "Read only while `jointCarry` is on.",
    cacheEffect: "options-version",
    surfaced: false,
    related: ["jointCarry", "help:guides:forwards"],
    docs: ["05_deamericanization_stopping", "06_forwards_dividends_inference"],
  },
  {
    key: "sivWingPenaltyPct",
    model: "options",
    section: "opt-parametric",
    label: "MCS wing penalty %",
    unit: "% of the base penalty weight",
    summary: "Strength of the Multi-Core Sigmoid put-wing no-butterfly regularizer, as a percentage of the base weight.",
    details:
      "Zero-wing hat kernels can break convexity (Durrleman g < 0) in the UNQUOTED tail. A soft penalty `√λ · max(−g(z), 0)` on a grid extending two z-units past the traded range pushes g ≥ 0 where no quote disciplines it, with the put side weighted twice (about 64% of measured violations were put-side). 100 is the default Durrleman penalty; 0 is off and byte-identical.\n\n" +
      "It is exactly zero on an arbitrage-free slice, so liquid names are untouched whatever the value. Rendered in the Parametric card because it is MCS-only. Not the belly certificate (`bellyRepair`), which acts inside the traded range.",
    example:
      "Set `sivWingPenaltyPct` to 0 on a 2-core MCS fit of a thin single name: the density view shows a negative lobe beyond the last put quote and Quality flags butterfly arbitrage in the extrapolated region; at 100 the lobe is gone and the quoted strikes move under 1 bp.",
    activation: "Read only while `model` is `sigmoid`.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["nCores", "sigmoidRidge", "bellyRepair", "extrapEnforce"],
    docs: ["03_multicore_mcs_corrections"],
  },
];

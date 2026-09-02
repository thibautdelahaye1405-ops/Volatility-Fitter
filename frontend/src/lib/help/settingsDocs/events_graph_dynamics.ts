// Settings documentation — the three short Options sections (HELP CENTER
// ARC, H1): Events (the variance clock + the 0DTE session clock), Graph (the
// solver defaults the Graph lens seeds from) and Spot-vol dynamics (the
// scenario transport regime). Prose only: type / default / range / enum are
// rendered from settingsSchema.json next to each entry, so a default is
// mentioned here only to explain WHY it is what it is.
//
// Sources: volfit/api/schemas.py (OptionsSettings field comments — the
// authoritative meaning), Docs/handoff/SETTINGS_REFERENCE.md §2.4 / §2.10 /
// §2.11, Docs/handoff/notes/11, 14, 12, and the Options-dialog labels in
// components/options/SmallSections.tsx.
import type { SettingDoc } from "../types";

// ---------------------------------------------------------------------------
// Events — the event-weighted variance clock and the intraday session clock.
// All five fields change every node's (t, tau), so they bump the options
// version: every lit node refits when one of them moves.
// ---------------------------------------------------------------------------

export const EVENTS_DOCS: SettingDoc[] = [
  {
    key: "eventsEnabled",
    model: "options",
    section: "opt-events",
    label: "Event variance clock",
    summary: "Turn the event-weighted variance clock on or off for every fit, view and table.",
    details:
      "When on, each ticker's event calendar (edited in Parametric ▸ Term) adds day-weights to the variance clock: an earnings day before an expiry is one calendar day carrying several days of variance, so that expiry is valued over more variance-days and its working IV drops at a fixed price. Prices never move — the clock only enters as a denominator — so the toggle cannot create or remove arbitrage; it changes the ruler, not the quotes.\n\n" +
      "On by default because event-time vol is the comparable signal across names and dates (pre- and post-earnings surfaces line up); with an empty calendar the clock is the calendar exactly, so nothing changes. Every fit, the Local Vol grid, the term structure and the option tables read the same clock.\n\n" +
      "Do not confuse it with the observation filter's session clock (`filterClock`), which budgets handle drift *between* snapshots; this clock dilates maturity *within* one fit.",
    example:
      "AAPL with a 4-extra-day earnings event 3 months out: the 0.30y expiry's variance time becomes 0.311y and its working ATM vol drops by about 36 vol bp at 20% — the event hump in the term structure flattens while every option price is unchanged.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["normalizeEvents", "intradayClock", "filterClock", "help:glossary:event-clock"],
    docs: ["11_event_market_clock"],
  },
  {
    key: "normalizeEvents",
    model: "options",
    section: "opt-events",
    label: "Normalize events",
    summary: "Rescale every day-weight so the one-year variance budget stays 365 days with the events inside it.",
    details:
      "Un-normalized (the default), events add variance on top of a one-per-day baseline: cumulative weight exceeds the day count, and every maturity past an event reads a little lower in vol — the 1Y included. Normalized, all days (events included) are scaled by one global factor 365 / (365 + Σ event days within the year), so the 1Y vol matches a no-event year exactly and events *redistribute* variance within the year instead of adding it.\n\n" +
      "This is a desk convention, not an inference: it changes sub-year readings, never prices, never a fit's arbitrage properties, and never the auto-calibrator's solved event sizes (one global factor cancels in every forward-variance ratio it compares). Off by default to keep the plain 'events are extra variance' reading.",
    example:
      "One 4-day event at 0.25y: switch it on and the 1Y ATM vol returns to its no-event value exactly, while the 6M expiry reads slightly higher than under the un-normalized clock because its dilation shrank.",
    activation: "Read only while eventsEnabled is on",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["eventsEnabled", "help:glossary:event-clock"],
    docs: ["11_event_market_clock"],
  },
  {
    key: "intradayClock",
    model: "options",
    section: "opt-events",
    label: "Intraday clock (0DTE research)",
    summary: "Value sub-day maturities from the chain snapshot's timestamp to the exact settlement instant on a session-weighted clock.",
    details:
      "Two things change when it is on. *Where maturity ends*: each node is valued from the chain snapshot's timestamp to the expiry's exact settlement instant (the stored settlement map — AM/PM settlement, half-days — with NYSE session rules as fallback) instead of a whole number of calendar days. *How a day accrues*: variance time flows through the session profile set by `sessionVarShare` and `nonTradingWeight`.\n\n" +
      "Off by default and byte-identical off: maturities stay day-granular and a same-day expiry has zero days, so it cannot be fit. With the nesting defaults, any close-to-close span of N calendar days still integrates to exactly N day-weights, so switching the clock on changes sub-day reads and nothing else.\n\n" +
      "Bumps the options version — every node's (t, tau) moves. It is a different subsystem from the observation filter's session clock (`filterClock`, `filterSessionShare`), which shares the intraday primitive and nothing else.",
    example:
      "A 0DTE SPY chain fetched at 11:00 ET: off, the node has zero days and is skipped; on, it is valued over the 5 remaining session hours and its smile calibrates like any other slice.",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["sessionVarShare", "nonTradingWeight", "eventsEnabled", "filterClock"],
    docs: ["11_event_market_clock"],
  },
  {
    key: "sessionVarShare",
    model: "options",
    section: "opt-events",
    label: "Session variance share",
    unit: "ratio",
    summary: "Set the fraction of a trading day's variance that accrues during the exchange session.",
    details:
      "The session runs 09:30 ET to the close (half-day sessions scale it). The default 6.5/24 ≈ 0.271 is the flat-density share — variance accrues at the same rate around the clock — chosen so the intraday clock nests the legacy day convention to the day. Research values around 0.7–0.9 concentrate variance in trading hours: a live 0DTE's clock becomes 'remaining trading minutes' and the overnight is cheap.\n\n" +
      "Raising it gives a same-day expiry more variance time for the hours left in the session, so the same price implies a lower working vol; the after-close portion of any expiry is worth correspondingly less. Bumps the options version.",
    example:
      "At 0.85 a 0DTE fetched at 14:00 ET has about 0.26 of a day's variance left instead of 0.083 under 0.271, so the same option prices imply a lower working IV across the whole smile.",
    activation: "Read only while intradayClock is on",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["intradayClock", "nonTradingWeight", "filterSessionShare"],
    docs: ["11_event_market_clock"],
  },
  {
    key: "nonTradingWeight",
    model: "options",
    section: "opt-events",
    label: "Non-trading day weight",
    unit: "ratio",
    summary: "Weight a weekend or holiday day on the intraday clock relative to a trading day.",
    details:
      "1.0 (the default) keeps the legacy convention: a three-day weekend costs three full days of variance. Lower it to study the weekend effect — in the stored intraday campaign one overnight and an entire three-day weekend both moved ATM vol about 55 bp, which no clock proportional to calendar time can fit and a session-weighted one can.\n\n" +
      "Lowering the weight shortens the variance time of every expiry that spans a weekend, so their working IV rises at fixed price; the first expiry after the weekend moves most and the Friday→Monday kink in the term structure flattens. Bumps the options version.",
    example:
      "At 0.3 the span from Friday's close to Monday's close is 1.6 day-weights instead of 3, so a Friday-afternoon fetch values the Monday expiry over roughly half the variance time and its working vol rises.",
    activation: "Read only while intradayClock is on",
    cacheEffect: "options-version",
    surfaced: true,
    related: ["intradayClock", "sessionVarShare", "filterNonTradingWeight"],
    docs: ["11_event_market_clock"],
  },
];

// ---------------------------------------------------------------------------
// Graph — request DEFAULTS for the graph extrapolator. state.py's affects_fit
// list does not name any of them: they seed the Graph lens's Solver panel
// (state/useGraph.ts seedSolverParams, only while the sliders are untouched)
// and travel in each solve request's body, so they never touch a fit cache.
// ---------------------------------------------------------------------------

export const GRAPH_DOCS: SettingDoc[] = [
  {
    key: "graphKappaScale",
    model: "options",
    section: "opt-graph",
    label: "κ prior strength",
    summary: "Seed the Graph lens's local stiffness κ, the precision that pins each dark node to its transported-prior baseline.",
    details:
      "In the smooth-field operator the increment field is penalized by a local-smallness term D_κ: higher κ keeps dark nodes closer to their baseline and lets a lit innovation spread less, and their credible bands narrow toward the baseline. It is a scale on the solver's data-derived precision tiers, not an absolute precision.\n\n" +
      "This is a request default: the Graph lens's Solver panel ('Local stiffness κ') is seeded from it while its sliders are untouched, and every graph solve sends the value in its request body — changing it never bumps a fit cache. Under `precision_messages` the κ/η/λ/ν dials are inert: the message operator's anchors come from the edge relations, not from these knobs.",
    example:
      "Set 3.0: a +2 vol-pt SPY 3M innovation moves the dark QQQ 3M node by less than it did at 1.0, and the dark nodes' bands sit tighter around their baselines.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["graphEtaScale", "graphPropagationMode", "help:guides:graph"],
    docs: ["14_graph_messages", "14_graph_three_priors"],
  },
  {
    key: "graphEtaScale",
    model: "options",
    section: "opt-graph",
    label: "η reach",
    summary: "Seed the Graph lens's propagation reach η, the directed-smoothness weight that carries a lit move across edges.",
    details:
      "η multiplies the directed neighbour-prediction residual (a row-normalized trust kernel with the edge amplitudes β): how strongly each node is expected to follow what its informers predict. Higher η lets a lit innovation reach further and dark nodes follow their neighbours more tightly; 0 disconnects the graph so every dark node rests on its baseline. Reach and stiffness are coupled dials — the ratio η/κ sets the effective reach.\n\n" +
      "Request default only ('Propagation reach η' in the Solver panel); no cache is touched. Smooth-field operator only.",
    example:
      "With a single lit SPY 6M node, η 0.1 barely moves the dark SPY 3M and 1Y nodes; at 1.0 they carry most of the calendar-scaled move.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["graphKappaScale", "graphLambdaScale", "graphPropagationMode", "help:guides:graph"],
    docs: ["14_graph_messages", "14_graph_three_priors"],
  },
  {
    key: "graphLambdaScale",
    model: "options",
    section: "opt-graph",
    label: "λ OT flux (0 = off)",
    summary: "Seed the optimal-transport flux weight λ of the smooth-field operator, where zero switches the transport term off.",
    details:
      "λ adds the unbalanced-optimal-transport tangent term λ (A_ρ + νI)⁻¹ — a belief that innovations flow along the graph like mass, penalizing fields that need a large flux to explain. Shipped at 0, the adjudicated default: the stored benchmarks did not earn the term a place in the default and it costs a dense solve.\n\n" +
      "Any value above 0 lights the ν control in the Graph lens ('OT flux λ' reads a number instead of 'off'). Request default only; no cache is touched.",
    example:
      "λ 1.0 with ν 0.1: the solver now discourages an innovation appearing on a dark node with no lit neighbour to have carried it, and the OT flux row in the Solver panel reads 1.0.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["graphNu", "graphEtaScale", "help:guides:graph"],
    docs: ["14_graph_three_priors"],
  },
  {
    key: "graphNu",
    model: "options",
    section: "opt-graph",
    label: "ν OT source",
    summary: "Seed the source-and-sink allowance ν of the optimal-transport term.",
    details:
      "ν is the regularizer inside (A_ρ + νI)⁻¹: how much innovation may be created or absorbed at a node rather than carried across edges. Small ν forces the field to be nearly conserved — moves must flow in from lit nodes; large ν lets nodes source their own moves and the term relaxes toward a plain ridge. Default 0.1 is a mild allowance.\n\n" +
      "Inert while λ = 0 — the Graph lens greys 'Source allowance ν' out. Request default only; no cache is touched.",
    example:
      "λ 1.0, ν 0.01: the OT term is strict and a dark node with no lit neighbour barely moves; raise ν to 1.0 and the solve drifts back toward the plain κ/η field.",
    activation: "Read only while graphLambdaScale is above 0",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["graphLambdaScale", "help:guides:graph"],
    docs: ["14_graph_three_priors"],
  },
  {
    key: "graphPropagationMode",
    model: "options",
    section: "opt-graph",
    label: "Propagation operator",
    summary: "Choose the default operator the graph solve uses to carry lit innovations to dark nodes.",
    details:
      "`precision_messages` (the default, user-ratified 2026-07-27): every edge is a contract z_i ≈ β z_j at a stated relation precision. A receiver inherits the full configured amplitude whatever the trust, competing messages are precision-weighted votes (never sums), distance costs confidence but never amplitude, and a silent neighbour costs nothing.\n\n" +
      "`smooth_field` is the legacy increment prior (the κ/η/λ/ν committee) — the explicit rollback, byte-identical to the pre-message product, and still the *wire* default on a bare solve request so replay, byte-identity locks and the backtest harness are untouched. `hybrid` adds the smoothing term to the message factors; it is configuration-only and not offered in the dialog.\n\n" +
      "Why the flip: at the daily horizon the two operators tie on RMS, but on the intraday replay messages carry the signal at 65.8 bp where smooth-field is nearly inert (168.6 bp against a pure-transport 172.7). The recorded daily-horizon price is graph bands about 2× narrower and wing medians about +5 bp. Seeds the Graph lens's mode selector; a store that ever saved Options keeps its explicit value until re-saved. No cache is touched.",
    example:
      "Switch to smooth_field on a six-node SPY/QQQ universe with SPY 6M lit: the dark nodes' moves shrink toward zero at day-scale stiffness, where precision_messages carried the full β-scaled move with wider bands.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["graphKappaScale", "graphEtaScale", "help:guides:graph"],
    docs: ["14_graph_messages"],
  },
];

// ---------------------------------------------------------------------------
// Spot-vol dynamics — the scenario / spot-move transport regime. Applied at
// READ time to the cached anchor (state.dynamics_regime()), never to the
// stored fit, so both fields are display-only.
// ---------------------------------------------------------------------------

export const DYNAMICS_DOCS: SettingDoc[] = [
  {
    key: "dynamicsRegime",
    model: "options",
    section: "opt-dynamics",
    label: "Spot-vol dynamics regime",
    summary: "Pick how the smile moves with spot between calibrations — the regime every transported view and the spot scenario apply.",
    details:
      "The regimes are points on one dial, the skew-stickiness ratio R. `sticky_moneyness` (R = 0): the smile rides the forward, unchanged in moneyness. `sticky_strike` (R = 1): each fixed strike keeps its vol, so ATM rises by the skew when spot falls. `sticky_local_vol` (R ≈ 2): the Hagan map of a local-vol surface frozen in absolute strike — ATM overshoots by twice the skew, with strike-dependent wings. `sticky_local_vol_grid`: the exact frozen-grid Dupire reprice, one PDE solve, with the realized SSR reported as an output (2.09 at seven weeks, 2.00 at eighteen months). `custom`: the numeric `ssr`.\n\n" +
      "Default sticky-strike — Derman's fixed-strike rule, the book convention. The transport is applied at read time to the cached anchor, never to the stored fit: a spot move re-labels quotes and moves the curve without recalibration, so switching regimes refreshes every view instantly and busts nothing. The transported prior and the graph baseline move under the same regime, so the choice also shapes the graph's innovation.\n\n" +
      "The stakes are hedge ratios, not display: on the live long-dated SPY smile the R = 0 and R = 2 deltas of one OTM put differ by 19.7 delta points.",
    example:
      "SPY 1Y with ATM skew −0.35 per unit log-moneyness and a −5% move: sticky-strike lifts ATM vol by about 1.8 vol pts, sticky-moneyness leaves it unchanged, sticky-local-vol lifts it by about 3.5.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["ssr", "streamFreezeFit", "help:guides:parametric"],
    docs: ["12_spotvol_missing_derivative"],
  },
  {
    key: "ssr",
    model: "options",
    section: "opt-dynamics",
    label: "SSR value",
    unit: "ratio",
    summary: "Set the numeric skew-stickiness ratio the custom regime applies to spot moves.",
    details:
      "R is the fraction of the skew realized as an ATM-vol change per unit log-spot move: 0 is sticky-moneyness, 1 sticky-strike, 2 the short-dated sticky-local-vol limit, and any value in between or beyond is realized by the same one-line transport. Bergomi's short-dated bounds put one-factor stochastic-vol models between 1 and 2.\n\n" +
      "Default 2.0 so that switching to `custom` starts at the empirically common short-dated regime. Read only while `dynamicsRegime` is `custom`; a read-time view, so no cache is touched.",
    example:
      "custom with 1.5 and a −2% SPY move on a −0.35 skew: ATM vol rises about 1.05 vol pts, halfway between the sticky-strike and sticky-local-vol answers.",
    activation: "Read only while dynamicsRegime is custom",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["dynamicsRegime"],
    docs: ["12_spotvol_missing_derivative"],
  },
];

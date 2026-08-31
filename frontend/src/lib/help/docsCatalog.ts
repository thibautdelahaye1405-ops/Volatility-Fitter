// Documentation catalog (HELP CENTER ARC, H1): one entry per shipped
// document — the numbered technical notes (reference edition, PDF), their
// lecture editions (Markdown + PDF pairs), the book, the LQD paper, the
// handoff pack and the engineering notes under Docs/. PURE DATA; the Docs
// page renders it and the backend serves the files:
//   markdown  GET /help/docs/{id}            root "notes-md" = Docs/handoff/notes
//   pdf       GET /help/files/{root}/{name}  roots "notes-pdf" = Docs/notes,
//             "handoff" = Docs/handoff, "docs" = Docs, "book" = Papers/book,
//             "paper" = Papers/lqd_paper
// Order: the primary notes 00 → 15, then the lecture editions (supplements)
// by number, then book, paper, handoff, docs. Abstracts are one to three
// sentences distilled from each document's own opening.
import type { DocEntry } from "./types";

const MD = "notes-md";
const PDF = "notes-pdf";

const md = (name: string) => ({ root: MD, name });
const pdf = (name: string) => ({ root: PDF, name });

export const DOCS_CATALOG: DocEntry[] = [
  // ---- Primary notes (reference editions) ---------------------------------
  {
    id: "00_system_overview", number: "00", kind: "note", topic: "Overview",
    title: "System Overview, Conventions & Hyperparameter Atlas",
    abstract: "The map of the territory: what the fitter does, the market and normalization conventions shared by every note, the end-to-end pipeline (fetch, forwards, prepare, fit, views, graph), the smile graph, and an index of every principal control cross-linked to the note that derives it.",
    markdown: md("00_system_overview.md"), pdf: pdf("00_system_overview.pdf"),
    related: ["01_lqd_model", "14_graph_extrapolation", "handoff_settings"],
  },
  {
    id: "01_lqd_model", number: "01", kind: "note", topic: "LQD",
    title: "The LQD Model",
    abstract: "The log-quantile-density smile model: the logarithm of the quantile density of the log-forward return is two universal boundary terms plus a Legendre expansion, so every parameter vector prices from a genuine law and the slice is butterfly-free by construction. Pricing, tails, ATM identities, the analytic Jacobian and calibration.",
    pdf: pdf("01_lqd_model.pdf"),
    related: ["01_lqd_model_lecture", "01_lqd_model_coordinates", "lqd_paper"],
  },
  {
    id: "02_svi_jw", number: "02", kind: "note", topic: "SVI-JW",
    title: "SVI and SVI-JW",
    abstract: "Raw SVI as a tilted hyperbola in total variance and its jump-wing re-coordinatization in trader vocabulary. The structural optimization chart, the buffered Lee cap (1.95), the belly butterfly certificate and the one-shot repair that gate publish.",
    pdf: pdf("02_svi_jw.pdf"),
    related: ["02_svi_jw_rewrite", "02_svi_jw_moments", "09_wings_lee_bounds"],
  },
  {
    id: "03_multicore_siv", number: "03", kind: "note", topic: "MCS",
    title: "Multi-Core Sigmoid (MCS)",
    abstract: "The sigmoid family: a six-parameter log-cosh base owning level, skew, convexity and asymmetric wing steepness, plus signed zero-wing hat kernels that add body detail (W-shaped event smiles) without moving the wings. The Durrleman wing penalty that fences the put side.",
    pdf: pdf("03_multicore_siv.pdf"),
    related: ["03_multicore_mcs_corrections", "09_wings_lee_bounds"],
  },
  {
    id: "04_local_volatility", number: "04", kind: "note", topic: "Local vol",
    title: "Piecewise-Affine Local Volatility",
    abstract: "A continuous piecewise-affine local-variance surface calibrated jointly across maturities and strikes through the forward Dupire PDE as an implicit pricing map. Positivity by box bounds, the M-matrix maximum principle, the delta-placed strike grid, the coverage floors and the Gauss-Newton / Numba solver.",
    pdf: pdf("04_local_volatility.pdf"),
    related: ["04_local_volatility_forward", "docs_localvol_methodology"],
  },
  {
    id: "05_deamericanization", number: "05", kind: "note", topic: "De-Am",
    title: "De-Americanization",
    abstract: "Listed equity options are American; feeding their prices to a European inversion biases the smile upward where vega is small. The CRR tree + bisection conversion to European-equivalent IV, the Numba batch kernel, the content-digest cache, and the wing-confined convexity repair.",
    pdf: pdf("05_deamericanization.pdf"),
    related: ["05_deamericanization_stopping", "06_forwards_dividends"],
  },
  {
    id: "06_forwards_dividends", number: "06", kind: "note", topic: "Forwards",
    title: "Forwards, Discounting and Dividends",
    abstract: "Every smile is forward-normalized, so a wrong forward gaps it at the money. The put-call parity regression for F and D, the discount clamp against feed noise, the near-ATM American de-bias loop, discrete and continuous dividends, and the zero-carry pin for synthesized chains.",
    pdf: pdf("06_forwards_dividends.pdf"),
    related: ["06_forwards_dividends_inference", "05_deamericanization"],
  },
  {
    id: "07_calibration_objective", number: "07", kind: "note", topic: "Objective",
    title: "The Calibration Objective",
    abstract: "The shared machinery every model minimizes: a vega-normalized price residual, per-quote weights (equal or density-corrected time value), and the fit target — mid, the bid-ask band, or the haircut band with its mid anchor. Robust losses and the tick floor.",
    pdf: pdf("07_calibration_objective.pdf"),
    related: ["07_calibration_objective_measure", "08_variance_swaps"],
  },
  {
    id: "08_variance_swaps", number: "08", kind: "note", topic: "Var-swap",
    title: "Variance-Swap Targets",
    abstract: "A var-swap quote is one number per node that pins the wing share scattered option quotes leave free. The log-contract replication, the LQD closed form, the source PDE for the LV surface, and how the quote enters each model as a soft (or hard-pinned) target.",
    pdf: pdf("08_variance_swaps.pdf"),
    related: ["08_varswap_representations", "09_wings_lee_bounds"],
  },
  {
    id: "09_wings_lee_bounds", number: "09", kind: "note", topic: "Wings",
    title: "Wings, Lee Bounds and Tail Control",
    abstract: "The wing treatment shared by the four models. Lee's moment formula caps the total-variance wing slope at 2; the buffered cap, the confinement principle (a constraint comparing two curves is sampled only where data pins both), and the extrapolated-region measurements.",
    pdf: pdf("09_wings_lee_bounds.pdf"),
    related: ["09_wings_last_quote", "02_svi_jw", "docs_generalized_tails"],
  },
  {
    id: "10_calendar_arbitrage", number: "10", kind: "note", topic: "Calendar",
    title: "Calendar-Arbitrage Prevention",
    abstract: "Calendar-freedom as four equivalent statements (normalized calls, convex order, integrated quantiles, total variance), the model-agnostic soft hinge, the price-space floor, and the symmetric surface solver that screens and jointly repairs violating runs.",
    pdf: pdf("10_calendar_arbitrage.pdf"),
    related: ["10_calendar_unnamed_martingale", "docs_generalized_tails"],
  },
  {
    id: "11_event_variance_clock", number: "11", kind: "note", topic: "Events",
    title: "Event Time Dilation and the Variance Clock",
    abstract: "Variance does not accrue uniformly: a scheduled event packs several days of variance onto one. Two clocks — calendar t and dilated variance time tau — with each event adding extra equivalent days; fits live on tau, prices and total variance are untouched.",
    pdf: pdf("11_event_variance_clock.pdf"),
    related: ["11_event_market_clock"],
  },
  {
    id: "12_spot_vol_dynamics", number: "12", kind: "note", topic: "Dynamics",
    title: "Spot-Vol Dynamics: SSR and Smile Transport",
    abstract: "How the smile moves with spot between calibrations. The skew-stickiness ratio organizes the regimes — sticky moneyness, sticky strike, sticky local vol — realized as a one-line transport, and the frozen local-vol grid derives its own answer.",
    pdf: pdf("12_spot_vol_dynamics.pdf"),
    related: ["12_spotvol_missing_derivative", "04_local_volatility"],
  },
  {
    id: "13_bayesian_prior_persistence", number: "13", kind: "note", topic: "Priors",
    title: "Bayesian Prior Persistence",
    abstract: "Yesterday's surface enters today's fit as extra least-squares rows, admitted only where today's quotes fail to identify the coordinate. The seven-mode menu (operator, factor, hybrid, graph-only, ...), the activation gate with its dead zone, and the two-pass option.",
    pdf: pdf("13_bayesian_prior_persistence.pdf"),
    related: ["13_prior_flat_directions", "docs_prior_persistence"],
  },
  {
    id: "14_graph_extrapolation", number: "14", kind: "note", topic: "Graph",
    title: "Graph Smile-Extrapolation",
    abstract: "The headline differentiator: a transported prior plus the lit-node innovation propagate through a directed Bayesian graph to reconstruct the dark nodes. A Gaussian inverse problem on increments with an optional optimal-transport regularization, retargeting of full smiles from three handles, and the leave-one-out backtest.",
    pdf: pdf("14_graph_extrapolation.pdf"),
    related: ["14_graph_messages", "14_graph_three_priors", "docs_graph_precision_messages"],
  },
  {
    id: "15_kalman_filtering", number: "15", kind: "note", topic: "Filter",
    title: "Observation Kalman Filtering",
    abstract: "A temporal state estimator on the three ATM handles, distinct from prior persistence (a gap regularizer). Per-handle gains, the Jacobian measurement covariance, residual inflation, the innovation-gated adaptive process noise, and the off / overlay / active modes.",
    pdf: pdf("15_kalman_filtering.pdf"),
    related: ["15_kalman_computed_trust", "docs_observation_filter"],
  },

  // ---- Lecture editions (supplements) -------------------------------------
  {
    id: "01_lqd_model_lecture", number: "01", kind: "supplement", topic: "LQD",
    title: "The LQD Model, from Distribution to Smile",
    abstract: "An alternative lecture: a smile is a probability distribution in option-market clothes. Builds LQD from a logistic slice, proves the one-expiry no-butterfly result, derives pricing, tails, ATM identities and the analytic Jacobian, then follows the production calibrator through deterministic approximation cases.",
    markdown: md("01_lqd_model_lecture.md"), pdf: pdf("01_lqd_model_lecture.pdf"),
    related: ["01_lqd_model"],
  },
  {
    id: "01_lqd_model_coordinates", number: "01", kind: "supplement", topic: "LQD",
    title: "The LQD Model: Unconstrained Coordinates for Arbitrage-Free Smiles",
    abstract: "LQD as the answer to a coordinate problem: find the chart in which a class of laws rich enough for equity smiles becomes all of coordinate space, so the optimizer roams freely and every point already prices from a genuine law.",
    markdown: md("01_lqd_model_coordinates.md"), pdf: pdf("01_lqd_model_coordinates.pdf"),
    related: ["01_lqd_model"],
  },
  {
    id: "01_lqd_model_percentile_ruler", number: "01", kind: "supplement", topic: "LQD",
    title: "From Ranks to Smiles",
    abstract: "LQD told as a monotone transport: a logistic draw and an increasing rubber ruler that says how fast probability ranks travel through log-return space. Option pricing becomes the difference of two tail ledgers; the same ledger supplies the Jacobian and the calendar test.",
    markdown: md("01_lqd_model_percentile_ruler.md"), pdf: pdf("01_lqd_model_percentile_ruler.pdf"),
    related: ["01_lqd_model"],
  },
  {
    id: "02_svi_jw_rewrite", number: "02", kind: "supplement", topic: "SVI-JW",
    title: "SVI-JW: One Hyperbola, Two Languages",
    abstract: "Raw geometry and trader coordinates for the same hyperbola: the JW handles in their natural units, the full image of the coordinate map, its singular stratum and poor conditioning, and the four statements about arbitrage that are often conflated.",
    markdown: md("02_svi_jw_rewrite.md"), pdf: pdf("02_svi_jw_rewrite.pdf"),
    related: ["02_svi_jw"],
  },
  {
    id: "02_svi_jw_moments", number: "02", kind: "supplement", topic: "SVI-JW",
    title: "The Wings and the Belly",
    abstract: "SVI as a moment-controlled smile. The wing slopes are exactly what Lee's bound constrains, the boundary beta = 2 is a trap, and the belly needs a certificate the wings cannot give — the origin of the 801-point Durrleman check.",
    markdown: md("02_svi_jw_moments.md"), pdf: pdf("02_svi_jw_moments.pdf"),
    related: ["02_svi_jw", "09_wings_lee_bounds"],
  },
  {
    id: "03_multicore_mcs_corrections", number: "03", kind: "supplement", topic: "MCS",
    title: "Base and Correction",
    abstract: "How to add detail in the body of a smile without disturbing the tails: a convex log-cosh base owns the wings, signed corrections add humps or notches, and a centred second difference makes every correction kernel vanish in both tails.",
    markdown: md("03_multicore_mcs_corrections.md"), pdf: pdf("03_multicore_mcs_corrections.pdf"),
    related: ["03_multicore_siv"],
  },
  {
    id: "04_local_volatility_forward", number: "04", kind: "supplement", topic: "Local vol",
    title: "Local Volatility, Forward",
    abstract: "Read Dupire as a pricing map, not a formula: a finite-element sheet reduces positivity to box bounds, the implicit step has a maximum principle at any step size, and the surface becomes the unknown of a well-posed inverse problem.",
    markdown: md("04_local_volatility_forward.md"), pdf: pdf("04_local_volatility_forward.pdf"),
    related: ["04_local_volatility"],
  },
  {
    id: "05_deamericanization_stopping", number: "05", kind: "supplement", topic: "De-Am",
    title: "The Premium You Never Observe",
    abstract: "Early exercise as optimal stopping: where the premium vanishes (Merton), where it concentrates (deep ITM puts under rates, calls near dividends), and de-Americanization as the removal of an unobservable nuisance with a model in which it cancels.",
    markdown: md("05_deamericanization_stopping.md"), pdf: pdf("05_deamericanization_stopping.pdf"),
    related: ["05_deamericanization"],
  },
  {
    id: "06_forwards_dividends_inference", number: "06", kind: "supplement", topic: "Forwards",
    title: "One Straight Line",
    abstract: "Forward and discount as the two parameters of one straight line, read as statistical inference: least squares pins the level superbly and the slope poorly, and every production robustness device is a response to that asymmetry.",
    markdown: md("06_forwards_dividends_inference.md"), pdf: pdf("06_forwards_dividends_inference.pdf"),
    related: ["06_forwards_dividends"],
  },
  {
    id: "07_calibration_objective_measure", number: "07", kind: "supplement", topic: "Objective",
    title: "What the Optimizer Sees",
    abstract: "The objective as three choices made before any model runs: the units the residual is measured in, the measure the residuals are summed against, and the tolerance inside which a residual counts as zero.",
    markdown: md("07_calibration_objective_measure.md"), pdf: pdf("07_calibration_objective_measure.pdf"),
    related: ["07_calibration_objective"],
  },
  {
    id: "08_varswap_representations", number: "08", kind: "supplement", topic: "Var-swap",
    title: "One Number, Three Integrals",
    abstract: "The var-swap as a linear functional with three exact representations — against option prices, against the quantile function, against the local-variance field — and the representation where each model finds it cheap.",
    markdown: md("08_varswap_representations.md"), pdf: pdf("08_varswap_representations.pdf"),
    related: ["08_variance_swaps"],
  },
  {
    id: "09_wings_last_quote", number: "09", kind: "supplement", topic: "Wings",
    title: "Beyond the Last Quote",
    abstract: "Half the drawn strike range lies beyond the quoted board. What a fitter can prove (beta <= 2), what it must choose (each wing is a stated contract) and what it has to police in the extrapolated region.",
    markdown: md("09_wings_last_quote.md"), pdf: pdf("09_wings_last_quote.pdf"),
    related: ["09_wings_lee_bounds"],
  },
  {
    id: "10_calendar_unnamed_martingale", number: "10", kind: "supplement", topic: "Calendar",
    title: "The Unnamed Martingale",
    abstract: "Calendar order as an existence theorem (Kellerer): butterfly-free slices increasing in convex order admit a martingale with those marginals. Four inspection coordinates, where the order is checked, and who pays to restore it.",
    markdown: md("10_calendar_unnamed_martingale.md"), pdf: pdf("10_calendar_unnamed_martingale.pdf"),
    related: ["10_calendar_arbitrage"],
  },
  {
    id: "11_event_market_clock", number: "11", kind: "supplement", topic: "Events",
    title: "The Market Keeps Its Own Clock",
    abstract: "The event clock from Dambis-Dubins-Schwarz: an event is a known acceleration of the intrinsic clock, the vol crush is a reading error, and estimating the clock from term-structure kinks has sharp, measured limits.",
    markdown: md("11_event_market_clock.md"), pdf: pdf("11_event_market_clock.pdf"),
    related: ["11_event_variance_clock"],
  },
  {
    id: "12_spotvol_missing_derivative", number: "12", kind: "supplement", topic: "Dynamics",
    title: "The Missing Derivative",
    abstract: "A snapshot gives sigma(k,T) at one spot; hedging needs its spot derivative, which no surface contains. The SSR as the single free scalar, the delta it moves, and the regime that answers instead of asks.",
    markdown: md("12_spotvol_missing_derivative.md"), pdf: pdf("12_spotvol_missing_derivative.pdf"),
    related: ["12_spot_vol_dynamics"],
  },
  {
    id: "13_prior_flat_directions", number: "13", kind: "supplement", topic: "Priors",
    title: "Where the Likelihood Is Flat",
    abstract: "Prior persistence as estimation in the flat directions of today's data: yesterday may speak only where today is silent. The activation gate's dead zone, the information price of a persisted basket, and coordinates that keep yesterday out of what today measured.",
    markdown: md("13_prior_flat_directions.md"), pdf: pdf("13_prior_flat_directions.pdf"),
    related: ["13_bayesian_prior_persistence"],
  },
  {
    id: "14_graph_messages", number: "14", kind: "supplement", topic: "Graph",
    title: "Every Edge Is a Contract",
    abstract: "Precision-message propagation: every edge is a contract z_i ~ beta z_j at a stated relation variance. Amplitude by contract, confidence by measurement, competing messages precision-averaged never added, and a silent neighbour costs nothing.",
    markdown: md("14_graph_messages.md"), pdf: pdf("14_graph_messages.pdf"),
    related: ["14_graph_extrapolation", "docs_graph_precision_messages"],
  },
  {
    id: "14_graph_three_priors", number: "14", kind: "supplement", topic: "Graph",
    title: "Three Priors for a Dark Universe",
    abstract: "The three propagation modes as three priors ordered by how much structure the desk asserts: smooth field (smoothness only), messages (relations), layered dynamic-harmonic (dependencies through time) — one solver family, three statements.",
    markdown: md("14_graph_three_priors.md"), pdf: pdf("14_graph_three_priors.pdf"),
    related: ["14_graph_extrapolation", "docs_graph_dynamic_harmonic"],
  },
  {
    id: "15_kalman_computed_trust", number: "15", kind: "supplement", topic: "Filter",
    title: "Trust Is Computed",
    abstract: "The filter's gain is an output, not a dial: the ratio of a measurement covariance propagated from the fit in stated noise units and a prediction covariance grown by a process clock that must itself be right — with standardized residuals as the check.",
    markdown: md("15_kalman_computed_trust.md"), pdf: pdf("15_kalman_computed_trust.pdf"),
    related: ["15_kalman_filtering"],
  },

  // ---- Book · paper -------------------------------------------------------
  {
    id: "book", kind: "book", topic: "Book",
    title: "The Volatility Surface as a Field of Probability Laws",
    abstract: "The textbook edition of the series: a volatility surface is a family of risk-neutral laws, one per (underlying, T), coupled by butterfly and calendar order and tied together by a Bayesian prior. Chapter 2 carries the generalized tails and the full-line calendar certificate the app enforces.",
    pdf: { root: "book", name: "book.pdf" },
    related: ["00_system_overview", "lqd_paper"],
  },
  {
    id: "lqd_paper", kind: "paper", topic: "LQD",
    title: "The LQD Model (standalone paper)",
    abstract: "The log-quantile-density smile model as a self-contained monograph chapter: construction, arbitrage-freedom by construction, tails and Lee slopes, pricing and Jacobian, calibration and the production evidence.",
    pdf: { root: "paper", name: "lqd_paper.pdf" },
    related: ["01_lqd_model", "book"],
  },

  // ---- Handoff pack -------------------------------------------------------
  {
    id: "handoff_readme", kind: "handoff", topic: "Handoff",
    title: "Handoff pack — README",
    abstract: "Front door of the Markdown-only transfer pack: what each file is for, the reading order, and how the notes, settings reference, API inventory and pitfalls fit together.",
    markdown: { root: "handoff", name: "README.md" },
    related: ["handoff_rebuild", "handoff_settings"],
  },
  {
    id: "handoff_settings", kind: "handoff", topic: "Settings",
    title: "Settings reference — every tunable, its default, unit and activation",
    abstract: "The exact, exhaustive control surface of the application, extracted from the validated settings schemas: each Fit, Options and Market field with its default, range, unit, activation condition and cache effect.",
    markdown: { root: "handoff", name: "SETTINGS_REFERENCE.md" },
    related: ["00_system_overview"],
  },
  {
    id: "handoff_api_ui", kind: "handoff", topic: "API",
    title: "API surface and UI inventory",
    abstract: "The route list of the backend (107 routes) grouped by capability, the read/write discipline of each, and a per-lens inventory of what the UI shows — a completeness checklist.",
    markdown: { root: "handoff", name: "API_AND_UI_INVENTORY.md" },
  },
  {
    id: "handoff_pitfalls", kind: "handoff", topic: "Case files",
    title: "Pitfalls and adjudications",
    abstract: "Every production incident now frozen as a named certification case, and every pre-registered benchmark whose verdict set a default. The fastest way to learn the system is to read these first.",
    markdown: { root: "handoff", name: "PITFALLS_AND_ADJUDICATIONS.md" },
    related: ["00_system_overview"],
  },
  {
    id: "handoff_rebuild", kind: "handoff", topic: "Spec",
    title: "Clean-room rebuild specification",
    abstract: "The product and engineering contract: rebuild a capability-equivalent surface fitter from first principles using the notes as the mathematical specification.",
    markdown: { root: "handoff", name: "VOL_FITTER_CLEAN_ROOM_REBUILD.md" },
  },

  // ---- Engineering notes under Docs/ --------------------------------------
  {
    id: "docs_bloomberg_setup", kind: "guide", topic: "Data",
    title: "Bloomberg data source — setup & troubleshooting",
    abstract: "Operator note for getting the Bloomberg (xbbg) source live and reading its Data Source light; the entitlement gate that blocks data account-side.",
    markdown: { root: "docs", name: "bloomberg_setup.md" },
    related: ["docs_exchange_delayed"],
  },
  {
    id: "docs_exchange_delayed", kind: "guide", topic: "Data",
    title: "Exchange-published delayed option chains — source catalog",
    abstract: "Why the exchanges' own delayed books (Cboe, Nasdaq, ASX, HKEX, SGX, Eurex) carry a full bid/ask Yahoo does not, and the one adapter seam that ingests them.",
    markdown: { root: "docs", name: "exchange_delayed_sources.md" },
    related: ["docs_bloomberg_setup"],
  },
  {
    id: "docs_localvol_methodology", kind: "guide", topic: "Local vol",
    title: "Local-volatility calibration — methodology & optimisation",
    abstract: "The LV calibration as it stands: model, pricing map, objective, grid, the two solvers, every shipped optimisation and everything tried and shelved with the reason.",
    markdown: { root: "docs", name: "localvol_calibration_methodology.md" },
    related: ["04_local_volatility"],
  },
  {
    id: "docs_graph_precision_messages", kind: "guide", topic: "Graph",
    title: "Precision-message graph propagation — framework",
    abstract: "Design specification of the messages operator: relation factors, per-edge precisions as policy objects, the draft/active lifecycle, preflight, and the golden acceptance contracts.",
    markdown: { root: "docs", name: "graph_precision_message_framework.md" },
    related: ["14_graph_messages"],
  },
  {
    id: "docs_graph_dynamic_harmonic", kind: "guide", topic: "Graph",
    title: "Dynamic directed-harmonic graph extrapolation — framework",
    abstract: "The opt-in layered operator: directed state through time, residual memory with a half-life, harmonic completion, and the decision record of its A/B campaigns.",
    markdown: { root: "docs", name: "dynamic_directed_harmonic_graph_framework.md" },
    related: ["14_graph_three_priors"],
  },
  {
    id: "docs_generalized_tails", kind: "guide", topic: "Wings",
    title: "Generalized LQD tails + full-line calendar — roadmap",
    abstract: "The tails+calendar arc: per-underlier tail exponents alpha+/-, the full-line calendar certificate and its tail-order clause, the active-set exchange, and the Quality columns they feed.",
    markdown: { root: "docs", name: "generalized_tails_calendar_roadmap.md" },
    related: ["09_wings_lee_bounds", "10_calendar_arbitrage", "book"],
  },
  {
    id: "docs_observation_filter", kind: "guide", topic: "Filter",
    title: "Observation Kalman filter — implementation roadmap",
    abstract: "Phase log of the observation filter build (complete): modes, covariance routes, the session clock, the active-mode gate, and the verdicts F1-F11.",
    markdown: { root: "docs", name: "observation_filter_roadmap.md" },
    related: ["15_kalman_filtering"],
  },
  {
    id: "docs_prior_persistence", kind: "guide", topic: "Priors",
    title: "Prior persistence — implementation roadmap",
    abstract: "The phased build of the seven persistence modes, the precision vocabulary, two-pass activation and the diagnostics table.",
    markdown: { root: "docs", name: "prior_persistence_roadmap.md" },
    related: ["13_bayesian_prior_persistence"],
  },
  {
    id: "docs_forward_roadmap", kind: "guide", topic: "Roadmap",
    title: "Forward roadmap v3",
    abstract: "Fifteen proposals surveyed against the codebase and ordered into implementation phases — the current plan of record.",
    markdown: { root: "docs", name: "forward_roadmap_v3.md" },
  },
];

const BY_ID: Record<string, DocEntry> = Object.fromEntries(DOCS_CATALOG.map((d) => [d.id, d]));

/** Catalog lookup; undefined for an unknown id (links are validated in tests). */
export function docEntry(id: string): DocEntry | undefined {
  return BY_ID[id];
}

// Help Center settings corpus — Local-Vol section, workspace gate + vertex
// grid (SettingsSectionId "opt-localvol"). One SettingDoc per OptionsSettings
// field that decides WHETHER the LV stage runs and WHERE the local-variance
// surface carries its parameters: the strike axis mode, strike / time vertex
// floors, the per-expiry coverage floor and the roughness penalty. The wing /
// front regularizers, PDE lattice and solver knobs live in
// localvol_wings_solver.ts; localvol.ts concatenates both into LOCALVOL_DOCS.
//
// Meaning is taken from the `#:` comments of volfit/api/schemas.py
// OptionsSettings (authoritative), Docs/handoff/SETTINGS_REFERENCE.md §2.8,
// Docs/handoff/notes/04_local_volatility_forward.md (§4 "What the grids must
// resolve", Appendix A) and the labels of components/options/LocalVolSection.tsx.
// Machine facts (type / default / range / enum) render from settingsSchema.json
// next to this prose; defaults are named here only to explain WHY.
//
// Cache discipline: the workspace toggle is a pure workflow gate; every grid
// knob folds into the LV affine key only and never invalidates a parametric fit.
import type { SettingDoc } from "../types";

export const LV_GRID_DOCS: SettingDoc[] = [
  {
    key: "localVolEnabled",
    model: "options",
    section: "opt-localvol",
    label: "Local-Vol workspace",
    summary: "Turn the Local Vol lens and the LV stage of the combined Calibrate on or off.",
    details:
      "On: the Local Vol lens is available in the activity bar, the combined Calibrate " +
      "(\"Parametric + LV\") appends the LV stage after the parametric one, and the " +
      "\"Local-Vol only\" stale-ticker badge counts LV surfaces whose inputs drifted. " +
      "Off: the lens is greyed out, the combined Calibrate stops after the parametric " +
      "stage and the LV stale count reads 0.\n\n" +
      "The explicit \"Local-Vol only\" verb in the Calibrate menu runs regardless of this " +
      "toggle. It is a pure workflow gate: flipping it never touches a fit — parametric " +
      "slices stay as they are and a previously built LV surface is still served when " +
      "you re-enable. Do not confuse it with the LV grid knobs below, which do refit the " +
      "LV surface.",
    example:
      "Turn it off on a 40-ticker universe while you iterate on parametric settings: " +
      "Calibrate finishes after the parametric stage and the Local Vol icon greys out. " +
      "Turn it back on and the next Calibrate rebuilds the LV surfaces without refitting " +
      "a single parametric slice.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["gridXNodes", "lvSolver", "help:guides:localvol", "help:guides:workflow"],
    docs: ["04_local_volatility_forward", "00_system_overview"],
  },
  {
    key: "gridStrikeMode",
    model: "options",
    section: "opt-localvol",
    label: "Delta strike axis",
    summary: "Place the strike vertices on the symmetric delta axis or uniformly in moneyness.",
    details:
      "`delta` puts vertices at the put deltas {1, 2, 5, 10, 25, 40, 50}% and their call " +
      "mirrors, clipped to the traded range — dense near the money where optionality " +
      "lives, with controlled reach into the wings. It is the default because the " +
      "uniform axis left the put wing with one or two vertices and the deep-put local vol " +
      "under-resolved. `linear` is the legacy uniform-in-x spacing.\n\n" +
      "In `delta` mode `gridXNodes` is a floor; in `linear` mode it is the exact count. " +
      "The roughness operator is spacing-aware, so the tightly spaced ATM vertices are not " +
      "penalized like the wide wing cells. The dialog shows this as a toggle (on = `delta`).",
    example:
      "Switch to `linear` on SPY with 12 nodes: the resolved-grid readout still shows 12 " +
      "strike vertices, but the region below the 10Δ put — four delta vertices before — " +
      "keeps one or two, and the fitted deep-put local vol loses its curvature.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["gridXNodes", "gridXMinPerExpiry", "gridRegLambda", "help:guides:localvol"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "gridXNodes",
    model: "options",
    section: "opt-localvol",
    label: "Strike nodes (floor)",
    unit: "count",
    summary: "Number of strike vertices of the LV variance surface — a floor in delta mode, exact in linear mode.",
    details:
      "In `delta` mode the ~13-vertex delta set drives placement and midpoints are inserted " +
      "only when this number exceeds it, so at the default the delta set is what you get. " +
      "In `linear` mode it is the exact count. Every vertex is a free parameter per time " +
      "row, so more vertices chase quote and de-Am noise unless `gridRegLambda` rises with " +
      "them.\n\n" +
      "The \"Optimal size (≈ # quotes)\" button sizes this and `gridTNodes` to the ticker's " +
      "observed quotes; the resolved-grid readout under the rows shows nT × nX = vertices " +
      "after Apply. Short-dated coverage is a separate rule (`gridXMinPerExpiry`), not this " +
      "count.",
    example:
      "Raise it to 24 on a name with ~40 quotes per expiry: the vertex readout roughly " +
      "doubles, the LV RMS drops and each eval costs about twice as much. On a 12-quote " +
      "name the same setting fits noise — leave it at 12 and let `gridXMinPerExpiry` add " +
      "vertices only where a short expiry needs them.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["gridStrikeMode", "gridTNodes", "gridXMinPerExpiry", "gridRegLambda"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "gridXMinPerExpiry",
    model: "options",
    section: "opt-localvol",
    label: "Min strike vertices per expiry",
    unit: "count",
    summary: "Guarantee at least this many strike vertices inside each expiry's own traded range.",
    details:
      "The shared delta axis is sized to the LONGEST expiry and clipped to the global strike " +
      "range, so a narrow short-dated smile can land only a few vertices on its sharpest " +
      "curvature — a two-day smile at 20% vol is ~1.5% wide, an order of magnitude narrower " +
      "than a one-year smile. After the axis is built, the widest in-range gaps are split " +
      "until every expiry holds at least this many vertices.\n\n" +
      "Only under-resolved short-front expiries gain vertices; well-covered expiries are " +
      "untouched, often byte-identically. Even gap-filling was chosen over clustering the " +
      "expiry's own delta nodes, which left wing gaps and stalled at 37 bp. `0` disables the " +
      "rule (legacy axis). Not surfaced in the dialog — set it through the API or the palette.",
    example:
      "Set it to 0 on a universe with a 6-day SPY weekly: that expiry lands ~3 vertices on " +
      "its curvature and its LV RMS jumps from ~28 bp (at 8) to ~108 bp, while the monthly " +
      "expiries fit exactly as before.",
    cacheEffect: "lv-affine-key",
    surfaced: false,
    related: ["gridXNodes", "gridStrikeMode", "frontTie", "help:guides:localvol"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "gridTNodes",
    model: "options",
    section: "opt-localvol",
    label: "Time nodes (floor; 0 = per expiry)",
    unit: "count",
    summary: "Floor on the number of positive time vertices over the base set of lit expiries.",
    details:
      "The base set is always t = 0, one node before the first expiry and every lit expiry. " +
      "This floor adds rows by splitting the widest √T gaps until it is met; it never drops " +
      "an expiry. `0` keeps the base set only.\n\n" +
      "Extra rows between expiries are only weakly identified — the quotes at each expiry " +
      "pin the integral of local variance up to that maturity — so they lean on the " +
      "roughness penalty (`gridRegLambda`, `gridRegRho`) for their shape. Rows below the " +
      "first expiry are held by `frontTie`.",
    example:
      "With 6 lit expiries, 10 adds 4 rows in the widest √T gaps (typically between the 3M " +
      "and 1Y expiries) and the term structure of local variance between them curves; `0` " +
      "leaves the 6 expiry rows plus the pre-front node — faster, with straight affine " +
      "interpolation in between.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["gridXNodes", "gridRegRho", "frontTie"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "gridRegLambda",
    model: "options",
    section: "opt-localvol",
    label: "Roughness λ",
    summary: "Strength of the second-difference roughness penalty on the nodal local-variance surface.",
    details:
      "The penalty is λ‖Lθ‖² where L stacks second differences along strike within each time " +
      "row and along time within each strike column (the time rows scaled by `gridRegRho`), " +
      "evaluated on the real vertex spacing so the delta axis does not over-smooth its " +
      "wings. Larger λ gives smoother local variance and more quote misfit; smaller λ lets " +
      "the flexible surface chase quote and de-Am noise and ring between quotes.\n\n" +
      "The production default is 1e-2 (the model layer's own signature default is 1e-4 — " +
      "production passes this value). It is LV-only: unrelated to the parametric penalties " +
      "such as `calendarWeight`.",
    example:
      "Raise λ from 0.01 to 1 on NVDA: the local-vol rows in the LV chart lose their " +
      "strike-to-strike wiggles and the quote RMS climbs by a few bp. Drop it to 1e-4 and " +
      "the short-dated rows start ringing between quotes.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["gridRegRho", "gridXNodes", "frontTie", "help:guides:localvol"],
    docs: ["04_local_volatility_forward"],
  },
  {
    key: "gridRegRho",
    model: "options",
    section: "opt-localvol",
    label: "Roughness ρ (t vs x)",
    summary: "Weight of the time-direction second differences relative to the strike direction in the roughness penalty.",
    details:
      "ρ multiplies the time-column stencil of the roughness operator. `1` weighs both " +
      "directions equally; above 1 the term structure of local variance is forced smoother " +
      "(rows resemble their neighbours); below 1 each maturity row moves more freely and the " +
      "penalty acts mostly along strike. `0` removes time smoothing entirely — only " +
      "`frontTie` still couples rows.",
    example:
      "Set ρ to 3 on a name with an earnings expiry: the local-variance bump at the event " +
      "row spreads into the neighbouring rows. Set it to 0.3 and the bump stays confined to " +
      "that expiry.",
    cacheEffect: "lv-affine-key",
    surfaced: true,
    related: ["gridRegLambda", "gridTNodes"],
    docs: ["04_local_volatility_forward"],
  },
];

// What's new (HELP CENTER ARC, H2): release notes in USER language, newest
// first, derived from the ROADMAP session wraps of 2026-08-20 … 2026-08-31.
// Bullets name UI surfaces and behaviour, never code identifiers (except
// where the identifier IS the UI name). Rendered by WhatsNewPage.tsx.
import type { WhatsNewEntry } from "./types";

export const WHATS_NEW: WhatsNewEntry[] = [
  {
    date: "2026-08-31",
    title: "Help Center",
    items: [
      "Help ▾ is now a full Help Center: Welcome, Guides per lens, Command reference, Settings reference, Keyboard shortcuts, Glossary, Tips & tricks, Documentation, Ask @Vol-Fitter and What's new — one dialog, searchable, with back / forward.",
      "A 12-step spotlight **Walkthrough** over the live shell (Next / Back / Skip, resumable); the Welcome page opens once on a first run.",
      "**F1** opens the guide of the active lens or dialog. **Ctrl+Shift+/** asks @Vol-Fitter — answered from the help corpus at once, and by Claude when the server has an Anthropic key.",
      "Every command and every Fit / Options / Market field is documented with an example; settings show type, default, range, unit, when they are read and what they invalidate, with an *Open in Options* button.",
      "Documentation in-app: the technical notes in Markdown, PDFs of the notes, the book and the LQD paper, the handoff pack.",
      "About VolFit gains build info and a **Copy diagnostics** button for support requests.",
    ],
  },
  {
    date: "2026-08-31",
    title: "Short-dated smiles draw clean wings",
    items: [
      "2–4 day smiles no longer show a ragged far upside or a flat far downside: the price-to-vol conversion of the display now inverts the out-of-the-money side with a tail-accurate map.",
      "The Local-Vol smile and surface views apply the same fix — deep-left wings no longer show gaps or phantom vols.",
      "Calibrations are unchanged; only what is drawn changed.",
    ],
  },
  {
    date: "2026-08-28",
    title: "Three editor groups, and the app rolls over at midnight",
    items: [
      "Ctrl+\\ now cycles one, two, three editor groups and folds back; Ctrl+Shift+\\ splits down. Each group can run its own lens; the tab menu offers *Move to group 1 / 2 / 3*.",
      "Tabs reopen after a refresh and from workspace files again.",
      "A long-running server now rolls its reference date at the exchange's midnight: tenors, expired rungs, dividends and caches follow the new day; a pinned historical as-of is never rolled.",
      "Deep-wing slope anchors can now stay active under an active Kalman filter (Options ▸ Prior, off by default).",
      "The graph pairs cross-venue nodes with nearby expiries when asked (Cross-expiry tolerance, per block-rule pair too).",
    ],
  },
  {
    date: "2026-08-27",
    title: "Per-node as-of, fetch coverage preview, eSSVI in Compare",
    items: [
      "The Nodes pane shows the HH:MM of the chain serving each node, amber when it is not the as-of you asked for, with a ≠ as-of pill on the ticker.",
      "Fetch ▾ previews coverage before you pull: \"9/12 nodes exact · 3 fall back to Close\". An optional as-of mismatch gate (Options ▸ Calibration) turns an inexact node into a publish blocker.",
      "Compare gains a fourth family, eSSVI, as a lazy chip.",
      "Local Vol: the var-swap hard pin now reaches the quote; a robust loss and an ATM-spread var-swap row are available for LV too.",
      "The status bar labels the auto-fetch countdown \"Next snapshot\" when the unified timer is on.",
    ],
  },
  {
    date: "2026-08-27",
    title: "One fetch verb, tail-order gate, var-swap decomposition",
    items: [
      "Fetch ▾ carries a single **Snapshot (quotes + spot)** verb plus the as-of rows; the split verbs survive in Ctrl+K as \"(legacy)\". The auto timer can run the same unified pull (Options ▸ Workflow).",
      "The Local-Vol smile shows the fit target (bid-ask or haircut ribbon) under its quotes, with a persisted Target chip.",
      "The Var-swap card reads \"replication strip 92 % · tails L 5 % / R 3 %\" for parametric and LV nodes.",
      "A tail-order gate can make a wing-order failure a publish blocker; a band-relaxation diagnostic says how much wider the quote band would have to be for a pair to certify.",
      "Kalman-filter history is kept in workspace files, and the Prior Evidence and Filter Timeline panels can show replay evidence.",
    ],
  },
  {
    date: "2026-08-27",
    title: "Workbench wave 3: files, 3D charts, palette, split editors",
    items: [
      "**File ▾**: New, Open (Ctrl+O or drop a .json), Save (Ctrl+S), Save as…, Save to server…, Open from server, Recent — the whole configuration as a file. **Save / Open snapshot…** keeps quotes and fits and loads back as a File data source.",
      "**Export ▸**: surfaces JSON / CSV, quality report, the active chart as PNG.",
      "3D surfaces: zoom at the cursor, pan, pitch, ⌂ reset, and a crosshair that lifts the smile at T and the term curve at k, linked across the ticker's surface charts.",
      "Keyboard navigation in the Nodes pane, per-tab view memory (Layout ▸ Remember view per tab), split editors (Ctrl+\\), the Ctrl+K command palette over every menu row, drag a node onto the Graph canvas to light it.",
    ],
  },
  {
    date: "2026-08-27",
    title: "Workbench wave 2: lens icons, Compare chips, Priors ▾",
    items: [
      "Custom lens icons; menus reordered to Options · Universe ▾ · Help ▾ with Universe ▾ kept slim (manage / save / load).",
      "The Manage-universe dialog gains a Data-sources card (the market pill is now a passive readout); the as-of rows moved into Fetch ▾.",
      "Compare shows the prevailing model at once and fits the other families lazily from chips.",
      "Parametric and Local Vol read alike: NODE / TICKER view groups, the layer rail at the right of the chart, Y-center / Y-fit as overlay buttons, the x-axis unit in the chart footer, three stacked cards on the right (Spot move · Var-swap · Fit diagnostics).",
      "Priors ▾ with three save scopes; Density view with Density / Log Q-density / CDF; Ctrl+P quick open; middle-click a node for a pinned tab.",
    ],
  },
  {
    date: "2026-08-26",
    title: "The workbench",
    items: [
      "A VS Code-like shell replaces the tabbed top bar: activity bar with five lenses (Alt+1…5), a Nodes pane (Ctrl+B) with lit / dark dots, quality glyphs and RMS, one tab per node with preview / pin semantics, and a status bar that narrates the engine and keeps the last action with its timestamp.",
      "Lenses are tab-driven: the forward ladder, the LV per-expiry table, the term chart, the graph canvas and the Quality rows all open or activate the matching tab.",
      "Options is a dialog with a section rail; View ▾ and Layout ▾ hold display preferences and panes.",
    ],
  },
  {
    date: "2026-08-26",
    title: "Tail persistence and short-dated fits — new opt-in knobs",
    items: [
      "Prior wing-slope anchors (WingL / WingR) with their own scale; the prior var-swap row can carry the tail as a spread over ATM; a hard pin for the market var-swap quote.",
      "Short-dated smiles: winged calendar floors, refits that read their committed neighbours, a tick-size floor on the band width, a maturity-aware mid anchor, a robust loss (Huber / Cauchy), and vega-normalised price residuals for SVI-JW and MCS.",
      "Every new knob defaults to the previous behaviour; the Settings reference explains each.",
    ],
  },
  {
    date: "2026-08-25",
    title: "Auto-scaled smiles, weighting schemes, cross-expiry graph edges",
    items: [
      "Smile chart Y center / Y fit chips keep the y-axis on the visible x-range; crosshairs on the overlay, LV smile and forward-curve charts.",
      "Two new quote-weighting schemes (vega density, delta density) beside the existing ones.",
      "The graph can pair nearby expiries across venues (Cross-expiry tolerance in the Cross-asset card).",
      "Compare shows each family's wing law in a Tails column; stacked-IV and 3D grids densify over the quoted span.",
      "Bloomberg chains can include dailies and weeklies; Eurex live quotes require a two-sided book during session hours.",
    ],
  },
  {
    date: "2026-08-21",
    title: "Two comparable frames, three calibrate scopes, exchange delayed chains",
    items: [
      "The smile chart shows the prevailing quotes and the fit rolled to the prevailing spot; Calib. quotes and Calib. fit add the frame the last calibration used. The Quote Table joins both frames per strike.",
      "Calibrate offers three scopes as peers — Parametric + LV, Parametric only, Local-Vol only — and the face runs the last one chosen.",
      "Every RMS and max error scores the chosen fit target (mid, bid-ask or haircut band), in the tiles, the LV column, Compare and the report.",
      "New data sources with real bid / ask from the exchanges' delayed feeds: Cboe, Nasdaq, ASX, HKEX, SGX and Eurex (with its end-of-day settlement tier).",
      "Live quote beams no longer ghost when zooming the smile in Chrome.",
    ],
  },
  {
    date: "2026-08-20",
    title: "Live streaming: Bloomberg push feed, live table and chart bands",
    items: [
      "Bloomberg streams through its subscription service (no daily quota); a universe edit updates the subscription in place on Bloomberg and Massive.",
      "The Quote Table ticks live between refits from a per-node stream; the smile chart draws live bid / ask beams from the same stream.",
      "The replay-day campaign exposed and fixed two graph-edge defects (hub tickers, weight scaling).",
    ],
  },
];

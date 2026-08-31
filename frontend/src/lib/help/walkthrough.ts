// Walkthrough (HELP CENTER ARC, H2/H5): the spotlight tour drawn over the live
// shell. TOUR_ANCHORS names every `data-tour="<id>"` attribute the shell
// carries (one label each, shown when an anchor is missing at runtime — pane
// hidden — so the step can say what to show); TOUR_STEPS is the ordered
// 12-step script: brand → File → Options → Universe → command center →
// activity bar → Nodes pane → tabs → workspace → View / Layout → status bar →
// Help. Locks (walkthrough.test.ts): every step anchor is declared, ids unique,
// exactly twelve steps. Try-it actions are safe and reversible only.
import type { TourAnchor, TourStep } from "./types";

export const TOUR_ANCHORS: Record<TourAnchor, string> = {
  brand: "VolFit brand mark",
  "menu.file": "File menu",
  "menu.options": "Options button",
  "menu.universe": "Universe menu",
  "menu.help": "Help menu",
  center: "Fetch · Calibrate · Priors · market pill",
  "menu.view": "View menu",
  "menu.layout": "Layout menu",
  activity: "Activity bar (lenses)",
  nodes: "Nodes pane",
  tabs: "Tab strip",
  main: "Lens workspace",
  status: "Status bar",
};

export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    anchor: "brand",
    title: "Welcome to VolFit",
    body: "VolFit fits implied-volatility surfaces from option quotes and extrapolates sparse observations to every smile of the universe through a graph of (underlying, expiry) nodes.\n\nThe daily loop has four steps: build the universe, fetch quotes, calibrate, then read the graph and publish. This tour walks the shell from left to right; Next moves on, Skip closes and you can resume later from Help ▸ Walkthrough.",
    placement: "bottom",
  },
  {
    id: "file",
    anchor: "menu.file",
    title: "Files",
    body: "A **workspace** file is the whole configuration — Options, universe picks, quote edits, priors, tabs, layout. Ctrl+S saves it to its last target, Ctrl+O opens one, or drop a .json anywhere on the shell.\n\nA **snapshot** file (Ctrl+Alt+S) holds the fetched quotes and the committed fits; reopened, it becomes the File data source. Export ▸ writes surfaces as JSON / CSV, the quality report and the active chart as PNG.",
    placement: "bottom",
  },
  {
    id: "options",
    anchor: "menu.options",
    title: "Options",
    body: "Ctrl+, opens the settings dialog: Parametric, Local Vol, Calibration, Prior, Kalman filter, Events, Graph, Workflow and Dynamics sections, with Apply, Save default and Reset.\n\nA field that affects fits marks the affected nodes stale when applied; the Settings reference in Help explains every field with its default, range and effect.",
    placement: "bottom",
  },
  {
    id: "universe",
    anchor: "menu.universe",
    title: "Universe",
    body: "Manage universe (Ctrl+Shift+U) is where tickers are added, each ticker's expiries chosen, nodes set lit (observed) or dark (extrapolated), and the data source picked.\n\nSave the set under a name and load it back later from this menu or Ctrl+K.",
    placement: "bottom",
  },
  {
    id: "center",
    anchor: "center",
    title: "Fetch · Calibrate · Priors",
    body: "**Fetch ▾** pulls chains and spots in one Snapshot, at the as-of chosen in its rows (Live, Previous close, a day and moment); a coverage line says how many nodes the source serves exactly.\n\n**Calibrate** runs the last scope you chose — Parametric + LV, Parametric only or Local-Vol only — and names it on its face. **Priors ▾** saves the visible tab, all open tabs or every calibrated fit, and fetches priors back. The pill at the right is the active source and as-of.",
    placement: "bottom",
    action: { command: "fetch.snapshot", label: "Try it: fetch a snapshot" },
  },
  {
    id: "activity",
    anchor: "activity",
    title: "Lenses",
    body: "Five lenses, Alt+1 to Alt+5: Graph, Forwards, Parametric, Local Vol, Quality. A lens is a way of looking at the open tabs — switch it and every tab re-renders.\n\nGraph and Quality are universe-level: they render without a tab and highlight the active one.",
    placement: "right",
  },
  {
    id: "nodes",
    anchor: "nodes",
    title: "The Nodes pane",
    body: "The universe as a tree: tickers with lit / total counts, then expiries with the lit / dark dot (click to toggle), the tenor, the HH:MM of the chain serving the node, the RMS in bp and a quality glyph.\n\nClick previews a node, double-click pins it, Ctrl+B hides or focuses the pane; letters jump to a ticker. Drag a row onto the Graph canvas to light it.",
    placement: "right",
  },
  {
    id: "tabs",
    anchor: "tabs",
    title: "Node tabs",
    body: "One tab per node. Preview tabs are italic and get replaced by the next click; pinned tabs show a pin. Alt+← / Alt+→ cycle, Alt+W closes, middle-click closes too.\n\nCtrl+P quick-opens any node by typing part of it; Ctrl+\\ splits the editor into side-by-side groups.",
    placement: "bottom",
    action: { command: "tab.quickOpen", label: "Try it: quick open a node" },
  },
  {
    id: "main",
    anchor: "main",
    title: "The workspace",
    body: "The active lens for the active tab. On Parametric and Local Vol the toolbar groups NODE views (Smile, Density, Compare, Table) and TICKER views (Term, Densities, Stacked IV, Surfaces); the layer rail at the right of the chart toggles Target, Calib. quotes, Calib. fit and Weights.\n\nWheel zooms, drag pans, double-click resets; on 3D surfaces Shift+drag pans and Ctrl+drag pitches. Press F1 anywhere for the guide of the lens you are on.",
    placement: "left",
  },
  {
    id: "view",
    anchor: "menu.view",
    title: "View and Layout",
    body: "**View ▾** holds the colour scheme (Dark, Light, High contrast, Warm), contrast and brightness, and the expiry label format — live preview, kept only after Save the look as default.\n\n**Layout ▾**, next to it, toggles the Nodes pane, the diagnostics aside and the status bar, zen mode, per-tab view memory, and resets the layout.",
    placement: "bottom",
    action: { command: "view.expiryFormat:cycle", label: "Try it: cycle the expiry format" },
  },
  {
    id: "status",
    anchor: "status",
    title: "Status bar",
    body: "Left: what the engine is doing, with a gauge during a calibration, then the active lens and node. Right: the workspace name and unsaved marker, nodes lit / stale, the next auto-fetch, the as-of, the source light, the quote age, the **Last** action with its timestamp, and the clock.\n\nWhen something looks unchanged, read the Last chip first.",
    placement: "top",
  },
  {
    id: "help",
    anchor: "menu.help",
    title: "You are set",
    body: "Three keys to remember: **F1** opens the guide of the view you are on, **Ctrl+K** lists every command, **Ctrl+Shift+/** asks @Vol-Fitter a question.\n\nThe Help Center also has the Command and Settings references, the Glossary, Tips & tricks, the Documentation and What's new. This tour is always here under Help ▸ Walkthrough.",
    placement: "bottom",
    action: { command: "help.welcome", label: "Open the Help Center" },
  },
];

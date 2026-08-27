// Keyboard-shortcut table of the workbench (UI SHELL v2, S5). ONE list feeds
// both the global handler (state/useShellShortcuts.ts) and the Help ▸
// Keyboard shortcuts dialog, so what is documented is what fires.
//
// Browser-reserved chords are avoided on purpose: Chrome/Edge keep Ctrl+1…9,
// Ctrl+T/N/W and Ctrl+PageUp/PageDown for their own tabs, so the lens
// switch rides Alt+1…5 and tab cycling rides Alt+←/→ (intercepted).

export interface Shortcut {
  keys: string;
  label: string;
}

export interface ShortcutGroup {
  title: string;
  items: Shortcut[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Workbench",
    items: [
      { keys: "Ctrl+P", label: "Quick open — fuzzy-find a node, Enter opens its tab (Shift+Enter pins)" },
      { keys: "Ctrl+K", label: "Command palette — every menu row and verb (also Ctrl+Shift+P, or type > in quick open)" },
      { keys: "Ctrl+B", label: "Show / hide the Nodes pane" },
      { keys: "Alt+1 … Alt+5", label: "Lens: Graph · Forwards · Parametric · Local Vol · Quality" },
      { keys: "Alt+← / Alt+→", label: "Previous / next node tab" },
      { keys: "Alt+W", label: "Close the active tab" },
      { keys: "Double-click a tab or node", label: "Pin a preview tab" },
      { keys: "Middle-click a node", label: "Open it as a pinned tab" },
      { keys: "Middle-click a tab", label: "Close that tab" },
      { keys: "Ctrl+,", label: "Options (settings dialog)" },
      { keys: "Ctrl+Shift+U", label: "Manage universe" },
      { keys: "Ctrl+O", label: "Open a workspace file (or drop a .json onto the shell)" },
      { keys: "Ctrl+S", label: "Save the workspace to its last target (file / server)" },
      { keys: "Ctrl+Shift+S", label: "Save the workspace as… (download / Chromium file picker)" },
      { keys: "Ctrl+Alt+S", label: "Save a snapshot file (quotes + prevailing calibrations); File ▸ Open snapshot… loads one as the File data source" },
      { keys: "Ctrl+/", label: "This shortcut list" },
      { keys: "Esc", label: "Close the open dialog / menu" },
    ],
  },
  {
    title: "Nodes tree (focus it with Ctrl+B or a click)",
    items: [
      { keys: "↑ / ↓ · Home / End", label: "Move the focused row" },
      { keys: "← / →", label: "Collapse / expand a ticker (→ enters it, ← climbs back to it)" },
      { keys: "Letters", label: "Type-ahead — jump to the next ticker starting with them" },
      { keys: "Enter", label: "Open the node as a preview tab" },
      { keys: "Shift+Enter / Space", label: "Open it as a pinned tab" },
      { keys: "Ctrl+Enter", label: "Open it in the other editor group (split)" },
      { keys: "L", label: "Toggle the node lit / dark" },
      { keys: "Tab", label: "Jump to the filter box" },
    ],
  },
  {
    title: "Smile editing (Parametric lens, Smile view)",
    items: [
      { keys: "Click a quote", label: "Select it" },
      { keys: "Del / Backspace", label: "Exclude / restore the selected quote" },
      { keys: "↑ / ↓", label: "Amend the selected mid by 0.1 vol pt (Shift = 0.5)" },
      { keys: "Ctrl+Z / Ctrl+Y", label: "Undo / redo the last quote edit (Ctrl+Shift+Z = redo)" },
      { keys: "Esc", label: "Deselect the quote" },
    ],
  },
  {
    title: "Charts",
    items: [
      { keys: "Wheel", label: "Zoom x and y around the cursor" },
      { keys: "Shift+wheel / Alt+wheel", label: "Zoom x only / y only (Alt bypasses the y auto-scale)" },
      { keys: "Drag", label: "Pan (3D surface: rotate · Shift+drag or middle-drag: pan · Ctrl+drag: pitch)" },
      { keys: "Hover a 3D surface", label: "Crosshair: the smile at T and the term curve at k, linked across the surface charts of the ticker" },
      { keys: "Double-click", label: "Reset the zoom (3D: yaw · pitch · zoom · pan)" },
      { keys: "Range brush", label: "Drag the strike-window handles under the smile" },
    ],
  },
  {
    title: "Graph canvas",
    items: [
      { keys: "Click a node / edge", label: "Inspect it (manual what-if: pulse / unpulse)" },
      { keys: "Double-click a node", label: "Open its smile (Parametric lens, GRAPH overlay)" },
      { keys: "Drag / wheel", label: "Pan / zoom the universe" },
      { keys: "Drop a node (from the Nodes pane)", label: "Light it (calibrations) / pulse it +1 vol pt (manual what-if); dropped on the tab strip = pinned tab" },
    ],
  },
];

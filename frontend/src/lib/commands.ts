// Command registry (UI SHELL v2 wave 3, C4) — the single list of everything
// a menu row or the Ctrl+K palette can do: id, label, category, chord hint,
// optional argument prompt. PURE DATA: the runtime binding (what each command
// does, whether it is enabled / active) lives in state/commands.tsx, and the
// menus render their rows through components/shell/CommandRow from this same
// list, so the palette can never drift from the menus. Dynamic entries (saved
// universes, server workspaces, recent files) are generated at runtime with
// ids under the prefixes below. Locked by commands.test.ts: ids unique, every
// chord documented in lib/shortcuts.ts.

export type CommandCategory =
  | "File" | "Universe" | "Fetch" | "Calibrate" | "Priors" | "Lens" | "Layout" | "View" | "Tabs" | "Help";

export interface CommandDef {
  id: string;
  label: string;
  category: CommandCategory;
  /** Keyboard chord hint (must appear in lib/shortcuts.ts). */
  shortcut?: string;
  /** Muted annotation (menus + palette). */
  detail?: string;
  /** The command takes a typed argument (the palette prompts for it). */
  arg?: { placeholder: string };
}

/** Dynamic-command id prefixes (runtime-generated rows). */
export const DYNAMIC = {
  universeLoad: "universe.load:",
  workspaceServer: "file.openServer:",
  workspaceDelete: "file.deleteServer:",
  workspaceRecent: "file.recent:",
} as const;

export const COMMANDS = [
  // File
  { id: "file.new", label: "New workspace", category: "File", detail: "defaults" },
  { id: "file.open", label: "Open workspace…", category: "File", shortcut: "Ctrl+O", detail: "or drop a .json" },
  { id: "file.save", label: "Save workspace", category: "File", shortcut: "Ctrl+S" },
  { id: "file.saveAs", label: "Save workspace as…", category: "File", shortcut: "Ctrl+Shift+S" },
  { id: "file.saveToServer", label: "Save workspace to server…", category: "File", arg: { placeholder: "workspace name" } },
  { id: "file.saveSnapshot", label: "Save snapshot…", category: "File", shortcut: "Ctrl+Alt+S", detail: "quotes + calibrations" },
  { id: "file.openSnapshot", label: "Open snapshot…", category: "File", detail: "becomes the File data source" },
  // Universe
  { id: "universe.manage", label: "Manage universe…", category: "Universe", shortcut: "Ctrl+Shift+U", detail: "tickers · expiries · sources" },
  { id: "universe.saveAs", label: "Save universe as…", category: "Universe", arg: { placeholder: "universe name" } },
  // Fetch
  { id: "fetch.snapshot", label: "Fetch snapshot (quotes + spot)", category: "Fetch" },
  { id: "fetch.spots", label: "Fetch spots", category: "Fetch" },
  { id: "fetch.options", label: "Fetch option quotes", category: "Fetch" },
  // Calibrate
  { id: "calibrate.both", label: "Calibrate — Parametric + LV", category: "Calibrate" },
  { id: "calibrate.parametric", label: "Calibrate — Parametric only", category: "Calibrate" },
  { id: "calibrate.lv", label: "Calibrate — Local-Vol only", category: "Calibrate" },
  // Priors
  { id: "priors.saveVisible", label: "Save prior — visible tab", category: "Priors" },
  { id: "priors.saveOpen", label: "Save priors — all open tabs", category: "Priors" },
  { id: "priors.saveAll", label: "Save priors — all calibrated", category: "Priors" },
  { id: "priors.fetch", label: "Fetch priors", category: "Priors" },
  // Lens
  { id: "lens.graph", label: "Lens: Graph", category: "Lens", shortcut: "Alt+1" },
  { id: "lens.forwards", label: "Lens: Forwards", category: "Lens", shortcut: "Alt+2" },
  { id: "lens.parametric", label: "Lens: Parametric", category: "Lens", shortcut: "Alt+3" },
  { id: "lens.localvol", label: "Lens: Local Vol", category: "Lens", shortcut: "Alt+4" },
  { id: "lens.quality", label: "Lens: Quality", category: "Lens", shortcut: "Alt+5" },
  // Layout
  { id: "layout.nodesPane", label: "Nodes pane", category: "Layout", shortcut: "Ctrl+B" },
  { id: "layout.aside", label: "Diagnostics aside", category: "Layout", detail: "fit / config side panels" },
  { id: "layout.statusBar", label: "Status bar", category: "Layout" },
  { id: "layout.zen", label: "Zen mode", category: "Layout", detail: "charts only" },
  { id: "layout.rememberView", label: "Remember view per tab", category: "Layout" },
  { id: "layout.reset", label: "Reset layout", category: "Layout", detail: "panes + widths" },
  // Tabs
  { id: "tab.closeAll", label: "Close all tabs", category: "Tabs" },
  { id: "tab.close", label: "Close the active tab", category: "Tabs", shortcut: "Alt+W" },
  { id: "tab.next", label: "Next tab", category: "Tabs", shortcut: "Alt+→" },
  { id: "tab.prev", label: "Previous tab", category: "Tabs", shortcut: "Alt+←" },
  { id: "tab.quickOpen", label: "Quick open a node…", category: "Tabs", shortcut: "Ctrl+P" },
  // View
  { id: "view.scheme:dark", label: "Colour scheme: Dark", category: "View" },
  { id: "view.scheme:light", label: "Colour scheme: Light", category: "View" },
  { id: "view.scheme:contrast", label: "Colour scheme: High contrast", category: "View" },
  { id: "view.scheme:warm", label: "Colour scheme: Warm", category: "View" },
  { id: "view.expiryFormat:cycle", label: "Cycle the expiry format", category: "View" },
  { id: "view.saveDefault", label: "Save the look as default", category: "View" },
  { id: "view.reset", label: "Reset the look", category: "View" },
  // Help / dialogs
  { id: "options.open", label: "Options…", category: "Help", shortcut: "Ctrl+,", detail: "settings dialog" },
  { id: "help.shortcuts", label: "Keyboard shortcuts", category: "Help", shortcut: "Ctrl+/" },
  { id: "help.api", label: "API reference", category: "Help", detail: "OpenAPI /docs" },
  { id: "help.report", label: "Quality report", category: "Help", detail: "HTML export" },
  { id: "help.about", label: "About VolFit", category: "Help" },
  { id: "help.palette", label: "Command palette", category: "Help", shortcut: "Ctrl+K" },
] as const satisfies readonly CommandDef[];

export type CommandId = (typeof COMMANDS)[number]["id"];

const BY_ID: Record<string, CommandDef> = Object.fromEntries(COMMANDS.map((c) => [c.id, c]));

/** Definition lookup (throws on an unknown static id — a programming error). */
export function commandDef(id: CommandId): CommandDef {
  const d = BY_ID[id];
  if (!d) throw new Error(`unknown command ${id}`);
  return d;
}

/** Subsequence fuzzy match: every query char appears in order; score favours
 *  contiguous runs and early hits (0 = no match). Shared with quick open. */
export function fuzzyScore(hay: string, q: string): number {
  if (q === "") return 1;
  let hi = 0, score = 0, run = 0;
  for (const ch of q) {
    const idx = hay.indexOf(ch, hi);
    if (idx < 0) return 0;
    run = idx === hi ? run + 1 : 1;
    score += run * 2 + (idx < 3 ? 2 : 0);
    hi = idx + 1;
  }
  return score;
}

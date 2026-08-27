// Runtime binding of the command registry (UI SHELL v2 wave 3, C4).
//
// lib/commands.ts is the pure list; this provider turns every definition into
// a runnable Command (enabled / active / run) over the live contexts —
// workbench, workflow verbs, workspace files, named universes, view
// preferences — and appends the DYNAMIC rows (saved universes, server
// workspaces, recent files). Menus (components/shell/CommandRow) and the
// Ctrl+K palette both read this one list, so they cannot drift apart.
import { createContext, useCallback, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { COMMANDS, DYNAMIC } from "../lib/commands";
import type { CommandDef } from "../lib/commands";
import { ACTIVITIES, useWorkbench } from "./workbench";
import type { Activity } from "./workbench";
import { useWorkflowContext } from "./workflowContext";
import { useWorkspaceFile } from "./workspaceFile";
import { useSnapshotFile } from "./snapshotFile";
import { useUniverse } from "./useUniverse";
import { useViewSettings } from "./viewSettings";
import type { ColorScheme } from "./viewSettings";
import { useExpiryFormat } from "./expiryFormat";
import { useSmileSession } from "./smileSession";
import { API_BASE_URL } from "./api";
import { saveNodePriors } from "../components/topbar/PriorsMenu";
import { chartBackground, chartPngFilename, findActiveChartSvg, svgToPngBlob } from "../lib/chartPng";
import { downloadBlob } from "../lib/fileHandles";

export interface Command extends CommandDef {
  enabled: boolean;
  /** Toggle state (menu ✓ / palette chip); undefined for plain verbs. */
  active?: boolean;
  run: (arg?: string) => void;
}

interface CommandsValue {
  commands: Command[];
  byId: (id: string) => Command | undefined;
  run: (id: string, arg?: string) => void;
}

const Ctx = createContext<CommandsValue | null>(null);

/** Mount inside WorkspaceFileProvider (needs every shell context). */
export function CommandsProvider({ children }: { children: ReactNode }) {
  const wb = useWorkbench();
  const { live, workflow } = useWorkflowContext();
  const ws = useWorkspaceFile();
  const snap = useSnapshotFile();
  const uni = useUniverse();
  const view = useViewSettings();
  const expiry = useExpiryFormat();
  const session = useSmileSession();
  const { layout } = wb;
  const zen = !layout.nodesPane && !layout.aside && !layout.statusBar;
  const busy = workflow.busy;
  const openUrl = (url: string) => window.open(url, "_blank", "noopener");
  /** Chart as PNG (A3): the active chart card's SVG → canvas → download,
   *  named after the active node and the lens's current sub-view. */
  const exportChartPng = () => {
    const svg = findActiveChartSvg();
    if (svg === null) { workflow.noteAction("Export chart: no chart on the active lens", false); return; }
    const tab = wb.activeTab;
    const lensView = wb.viewMemory[tab?.key ?? ""]?.[wb.activity] as { view?: string } | undefined;
    const name = chartPngFilename(tab?.ticker ?? wb.activity, tab?.expiry ?? "", lensView?.view ?? wb.activity);
    void svgToPngBlob(svg, chartBackground(svg))
      .then((blob) => { downloadBlob(name, blob); workflow.noteAction(`Exported ${name}`); })
      .catch((err: unknown) => workflow.noteAction(`Export chart failed: ${err instanceof Error ? err.message : String(err)}`, false));
  };

  const commands = useMemo<Command[]>(() => {
    const bind = (id: string, run: (arg?: string) => void, enabled = true, active?: boolean): Command => {
      const def = COMMANDS.find((c) => c.id === id);
      if (!def) throw new Error(`unknown command ${id}`);
      return { ...def, enabled, active, run };
    };
    const lens = (a: Activity) => bind(`lens.${a}`, () => wb.setActivity(a), true, wb.activity === a);
    const tabs = wb.tabs;
    const list: Command[] = [
      // File
      bind("file.new", () => void ws.newWorkspace(), live && !ws.busy),
      bind("file.open", () => void ws.openPicker(), live && !ws.busy),
      bind("file.save", () => void ws.save(), live && !ws.busy),
      bind("file.saveAs", () => void ws.saveAs(), live && !ws.busy),
      bind("file.saveToServer", (arg) => { if (arg?.trim()) void ws.saveToServer(arg.trim()); }, live && ws.server.storeEnabled && !ws.busy),
      bind("file.saveSnapshot", () => void snap.saveSnapshot(), live && !snap.busy),
      bind("file.openSnapshot", () => void snap.openPicker(), live && !snap.busy),
      // Export (A3): the publish artifacts + the active chart
      bind("export.surfacesJson", () => openUrl(`${API_BASE_URL}/export/surfaces`), live),
      bind("export.surfacesCsv", () => openUrl(`${API_BASE_URL}/export/surfaces?format=csv`), live),
      bind("export.report", () => openUrl(`${API_BASE_URL}/export/report`), live),
      bind("export.chartPng", exportChartPng),
      ...ws.server.entries.map((e) => ({
        id: `${DYNAMIC.workspaceServer}${e.name}`, label: `Open workspace from server: ${e.name}`,
        category: "File" as const, detail: e.savedTs, enabled: live && !ws.busy,
        active: ws.target?.kind === "server" && ws.target.name === e.name,
        run: () => void ws.openFromServer(e.name),
      })),
      ...ws.server.entries.map((e) => ({
        id: `${DYNAMIC.workspaceDelete}${e.name}`, label: `Delete workspace from server: ${e.name}`,
        category: "File" as const, enabled: live && !ws.busy, run: () => void ws.deleteFromServer(e.name),
      })),
      ...ws.recent.map((r) => ({
        id: `${DYNAMIC.workspaceRecent}${r.kind}:${r.name}`, label: `Open recent: ${r.name}`,
        category: "File" as const, detail: r.kind === "server" ? "server" : "file", enabled: live && !ws.busy,
        run: () => void ws.openRecent(r),
      })),
      // Universe
      bind("universe.manage", () => wb.openDialog("universe")),
      bind("universe.saveAs", (arg) => { if (arg?.trim()) void uni.saveUniverse(arg.trim()); }, live && uni.saved.storeEnabled && uni.busy === null),
      ...uni.saved.names.map((n) => ({
        id: `${DYNAMIC.universeLoad}${n}`, label: `Load universe: ${n}`, category: "Universe" as const,
        enabled: live && uni.busy === null, run: () => void uni.loadUniverse(n),
      })),
      // Fetch / calibrate / priors (the command-center verbs)
      bind("fetch.snapshot", () => void workflow.fetchSnapshot(), live && !busy),
      bind("fetch.spots", () => void workflow.fetchSpots(), live && !busy),
      bind("fetch.options", () => void workflow.fetchOptions(), live && !busy),
      bind("calibrate.both", () => void workflow.calibrate(), live && !busy),
      bind("calibrate.parametric", () => void workflow.calibrateParametric(), live && !busy),
      bind("calibrate.lv", () => void workflow.calibrateLv(), live && !busy),
      bind("priors.saveVisible", () => void session.savePrior().then(() => workflow.noteAction("Saved prior (visible tab)")).catch(() => {}), live && wb.activeTab !== null),
      bind("priors.saveOpen", () => void saveNodePriors(tabs).then((r) => { workflow.noteAction(`Saved priors (${r.saved} tab${r.saved === 1 ? "" : "s"}${r.failed ? `, ${r.failed} failed` : ""})`, r.failed === 0); session.reload(); }), live && tabs.length > 0),
      bind("priors.saveAll", () => void workflow.savePriors(), live && !busy),
      bind("priors.fetch", () => void workflow.fetchPriors(), live && !busy),
      // Lenses
      ...ACTIVITIES.map((a) => lens(a.id)),
      // Layout
      bind("layout.nodesPane", () => (layout.nodesPane ? wb.setLayout({ nodesPane: false }) : wb.focusNodesPane()), true, layout.nodesPane),
      bind("layout.aside", () => wb.setLayout({ aside: !layout.aside }), true, layout.aside),
      bind("layout.statusBar", () => wb.setLayout({ statusBar: !layout.statusBar }), true, layout.statusBar),
      bind("layout.zen", () => wb.setLayout(zen ? { nodesPane: true, aside: true, statusBar: true } : { nodesPane: false, aside: false, statusBar: false }), true, zen),
      bind("layout.rememberView", () => wb.setLayout({ rememberView: !layout.rememberView }), true, layout.rememberView),
      bind("layout.reset", () => wb.resetLayout()),
      // Tabs
      bind("tab.closeAll", () => wb.closeAll(), tabs.length > 0),
      bind("tab.close", () => { if (wb.activeTab) wb.closeTab(wb.activeTab.key); }, wb.activeTab !== null),
      bind("tab.next", () => wb.cycleTab(1), tabs.length > 1),
      bind("tab.prev", () => wb.cycleTab(-1), tabs.length > 1),
      bind("tab.quickOpen", () => wb.openDialog("quickopen")),
      // View
      ...(["dark", "light", "contrast", "warm"] as ColorScheme[]).map((s) =>
        bind(`view.scheme:${s}`, () => view.setScheme(s), true, view.scheme === s)),
      bind("view.expiryFormat:cycle", () => expiry.cycle()),
      bind("view.saveDefault", () => { view.saveDefault(); expiry.saveDefault(); }, view.dirty || expiry.dirty),
      bind("view.reset", () => view.reset()),
      // Help / dialogs
      bind("options.open", () => wb.openDialog("options"), true, wb.dialog === "options"),
      bind("help.shortcuts", () => wb.openDialog("shortcuts")),
      bind("help.api", () => openUrl(`${API_BASE_URL}/docs`)),
      bind("help.report", () => openUrl(`${API_BASE_URL}/export/report`), live),
      bind("help.about", () => wb.openDialog("about")),
      bind("help.palette", () => wb.openDialog("commands")),
    ];
    return list;
  }, [wb, live, workflow, ws, snap, uni, view, expiry, session, layout, zen, busy]);

  const byId = useCallback((id: string) => commands.find((c) => c.id === id), [commands]);
  const run = useCallback((id: string, arg?: string) => { const c = byId(id); if (c && c.enabled) c.run(arg); }, [byId]);
  const value = useMemo<CommandsValue>(() => ({ commands, byId, run }), [commands, byId, run]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCommands(): CommandsValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useCommands must be used within CommandsProvider");
  return ctx;
}

/** Null outside the provider (tests / legacy mounts). */
export function useOptionalCommands(): CommandsValue | null {
  return useContext(Ctx);
}

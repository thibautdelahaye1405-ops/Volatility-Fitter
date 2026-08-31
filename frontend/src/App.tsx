// App shell (UI SHELL v2 — workbench, 2026-08-26): a fixed-viewport frame in
// the VS Code × Affinity grammar.
//
//   TopBar        main menu (Universe ▾ · Options · Help ▾) · command center
//                 (Fetch / Calibrate / Priors / market pill) · View ▾ · Layout ▾
//   ActivityBar   the lens: Graph · Forwards · Parametric · Local Vol · Quality
//   NodesPane     the universe tree (lit/dark, quality glyphs), 1/5 wide
//   MainPane      one tab per node + the lens rendered for the active node
//   StatusBar     engine narration, summary chips, last action, clock
//   ShellDialogs  Universe manager · Options · Help Center · About · Ctrl+P /
//                 Ctrl+K palette (nodes / the command registry)
//   Walkthrough   the Help ▸ Walkthrough spotlight tour (overlay, HELP CENTER ARC)
//   (File ▾ in the top bar saves / opens the whole configuration as a
//   workspace file; a .json dropped anywhere on the shell opens it.)
//
// Provider order matters: the smile session is the root of truth (universe +
// selection), the workflow context polls the engine, the lit map and quality
// contexts share one fetch each across the tree and the lenses, and the
// workbench reconciles its tabs with the session selection.
import TopBar from "./components/shell/TopBar";
import ActivityBar from "./components/shell/ActivityBar";
import NodesPane from "./components/shell/NodesPane";
import MainPane from "./components/shell/MainPane";
import StatusBar from "./components/shell/StatusBar";
import Resizer from "./components/shell/Resizer";
import ShellDialogs from "./components/shell/dialogs/ShellDialogs";
import { SmileSessionProvider } from "./state/smileSession";
import { GraphFocusProvider } from "./state/graphFocus";
import { WorkflowProvider } from "./state/workflowContext";
import { ExpiryFormatProvider } from "./state/expiryFormat";
import { ViewSettingsProvider } from "./state/viewSettings";
import { LitMapProvider } from "./state/litMap";
import { QualityProvider } from "./state/qualityContext";
import { NODES_WIDTH, WorkbenchProvider, useWorkbench } from "./state/workbench";
import { WorkspaceFileProvider, useWorkspaceFile } from "./state/workspaceFile";
import { SnapshotFileProvider, useSnapshotFile } from "./state/snapshotFile";
import { CommandsProvider } from "./state/commands";
import { HelpProvider } from "./state/help";
import Walkthrough from "./components/help/Walkthrough";
import { classifyBundle } from "./lib/snapshotFile";
import { snapshotNameOf } from "./lib/snapshotFile";
import { workspaceNameOf } from "./lib/workspaceFile";
import { useShellShortcuts } from "./state/useShellShortcuts";

/** The frame itself (needs the workbench context, hence a child of the providers). */
function Shell() {
  const { layout, setLayout, resetLayout } = useWorkbench();
  const ws = useWorkspaceFile();
  const snap = useSnapshotFile();
  useShellShortcuts();

  // Drop a .json anywhere on the shell: a workspace file (A1) or a snapshot
  // file (A2), routed by its schema family.
  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    const file = Array.from(e.dataTransfer.files).find((f) => /\.json$/i.test(f.name));
    if (!file) return;
    e.preventDefault();
    void file.text().then((text) => {
      let raw: unknown = null;
      try { raw = JSON.parse(text); } catch { /* the workspace opener reports it */ }
      if (classifyBundle(raw) === "snapshot") void snap.openText(text, snapshotNameOf(file.name));
      else void ws.openFile(new File([text], `${workspaceNameOf(file.name)}.volfit.json`, { type: "application/json" }));
    });
  };
  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    if (Array.from(e.dataTransfer.types).includes("Files")) e.preventDefault();
  };

  return (
    <div className="flex h-full flex-col overflow-hidden" onDrop={onDrop} onDragOver={onDragOver}>
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <ActivityBar />
        {layout.nodesPane && (
          <>
            <NodesPane />
            <Resizer
              width={layout.nodesWidth}
              min={NODES_WIDTH.min}
              max={NODES_WIDTH.max}
              onResize={(w) => setLayout({ nodesWidth: w })}
              onReset={resetLayout}
            />
          </>
        )}
        <MainPane />
      </div>
      {layout.statusBar && <StatusBar />}
      <ShellDialogs />
      <Walkthrough />
    </div>
  );
}

export default function App() {
  return (
    <ViewSettingsProvider>
    <ExpiryFormatProvider>
    <SmileSessionProvider>
    <GraphFocusProvider>
    <WorkflowProvider>
    <LitMapProvider>
    <QualityProvider>
    <WorkbenchProvider>
    <HelpProvider>
    <WorkspaceFileProvider>
    <SnapshotFileProvider>
    <CommandsProvider>
      <Shell />
    </CommandsProvider>
    </SnapshotFileProvider>
    </WorkspaceFileProvider>
    </HelpProvider>
    </WorkbenchProvider>
    </QualityProvider>
    </LitMapProvider>
    </WorkflowProvider>
    </GraphFocusProvider>
    </SmileSessionProvider>
    </ExpiryFormatProvider>
    </ViewSettingsProvider>
  );
}

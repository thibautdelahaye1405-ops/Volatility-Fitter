// App shell (UI SHELL v2 — workbench, 2026-08-26): a fixed-viewport frame in
// the VS Code × Affinity grammar.
//
//   TopBar        main menu (Universe ▾ · Options · Help ▾) · command center
//                 (Fetch / Calibrate / Priors / market pill) · View ▾ · Layout ▾
//   ActivityBar   the lens: Graph · Forwards · Parametric · Local Vol · Quality
//   NodesPane     the universe tree (lit/dark, quality glyphs), 1/5 wide
//   MainPane      one tab per node + the lens rendered for the active node
//   StatusBar     engine narration, summary chips, last action, clock
//   ShellDialogs  Universe manager · Options · Shortcuts · About
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
import { useShellShortcuts } from "./state/useShellShortcuts";

/** The frame itself (needs the workbench context, hence a child of the providers). */
function Shell() {
  const { layout, setLayout, resetLayout } = useWorkbench();
  useShellShortcuts();

  return (
    <div className="flex h-full flex-col overflow-hidden">
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
      <Shell />
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

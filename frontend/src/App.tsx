// App shell: top bar with tab navigation, simple state-based routing.
// The smile session is provided here so its data (and the backend fit
// session it mirrors) survives switching between workspace tabs.
import { useState } from "react";
import TopBar from "./components/TopBar";
import StatusBar from "./components/StatusBar";
import ErrorBoundary from "./components/ErrorBoundary";
import SmileViewer from "./views/SmileViewer";
import LocalVolViewer from "./views/LocalVolViewer";
import ForwardsViewer from "./views/ForwardsViewer";
import OptionsViewer from "./views/OptionsViewer";
import GraphViewer from "./views/GraphViewer";
import QualityViewer from "./views/QualityViewer";
import UniverseManager from "./views/UniverseManager";
import ViewSettingsViewer from "./views/ViewSettingsViewer";
import { SmileSessionProvider } from "./state/smileSession";
import { GraphFocusProvider } from "./state/graphFocus";
import { WorkflowProvider } from "./state/workflowContext";
import { ExpiryFormatProvider } from "./state/expiryFormat";
import { ViewSettingsProvider } from "./state/viewSettings";

/** The top-level workspaces of the application (ROADMAP Phase 10).
 *  Parametric = the model-fit workspace (Smile / Density / Term / Surface /
 *  Table sub-tabs); Term-Structure is now a Parametric sub-tab, not a top tab. */
export type TabId =
  | "parametric"
  | "localvol"
  | "forwards"
  | "options"
  | "graph"
  | "quality"
  | "universe"
  | "view";

export interface TabDef {
  id: TabId;
  label: string;
}

export const TABS: TabDef[] = [
  { id: "parametric", label: "Parametric" },
  { id: "localvol", label: "Local Vol" },
  { id: "forwards", label: "Forwards" },
  { id: "options", label: "Options" },
  { id: "graph", label: "Graph" },
  { id: "quality", label: "Quality" },
  { id: "universe", label: "Universe" },
  { id: "view", label: "View" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("parametric");

  return (
    <ViewSettingsProvider>
    <ExpiryFormatProvider>
    <SmileSessionProvider>
    <GraphFocusProvider>
    <WorkflowProvider>
      <div className="flex h-full flex-col">
        <TopBar tabs={TABS} activeTab={activeTab} onSelect={setActiveTab} />

        {/* Main workspace area; each tab renders its dedicated view, wrapped in
            an error boundary (keyed by tab) so a render crash in one view never
            white-screens the whole app and the error stays visible. */}
        <main className="flex-1 overflow-auto">
          <ErrorBoundary key={activeTab} label={TABS.find((t) => t.id === activeTab)?.label}>
            {activeTab === "parametric" && <SmileViewer />}
            {activeTab === "localvol" && <LocalVolViewer />}
            {activeTab === "quality" && <QualityViewer />}
            {activeTab === "universe" && <UniverseManager />}
            {activeTab === "forwards" && <ForwardsViewer />}
            {activeTab === "options" && <OptionsViewer />}
            {activeTab === "view" && <ViewSettingsViewer />}
            {activeTab === "graph" && (
              // Drill-in: GraphViewer points the shared smile session at a
              // node, then asks the shell to switch to the Parametric workspace.
              <GraphViewer onNavigateToSmile={() => setActiveTab("parametric")} />
            )}
          </ErrorBoundary>
        </main>

        {/* Bottom status bar: what the engine is doing (fetch / calibrate /
            term / density / LV), with gauges; an idle "Ready" + summary. */}
        <StatusBar />
      </div>
    </WorkflowProvider>
    </GraphFocusProvider>
    </SmileSessionProvider>
    </ExpiryFormatProvider>
    </ViewSettingsProvider>
  );
}

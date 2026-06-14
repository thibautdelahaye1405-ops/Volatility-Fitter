// App shell: top bar with tab navigation, simple state-based routing.
// The smile session is provided here so its data (and the backend fit
// session it mirrors) survives switching between workspace tabs.
import { useState } from "react";
import TopBar from "./components/TopBar";
import SmileViewer from "./views/SmileViewer";
import LocalVolViewer from "./views/LocalVolViewer";
import ForwardsViewer from "./views/ForwardsViewer";
import OptionsViewer from "./views/OptionsViewer";
import GraphViewer from "./views/GraphViewer";
import UniverseManager from "./views/UniverseManager";
import { SmileSessionProvider } from "./state/smileSession";

/** The top-level workspaces of the application (ROADMAP Phase 10).
 *  Parametric = the model-fit workspace (Smile / Density / Term / Surface /
 *  Table sub-tabs); Term-Structure is now a Parametric sub-tab, not a top tab. */
export type TabId =
  | "parametric"
  | "localvol"
  | "forwards"
  | "options"
  | "graph"
  | "universe";

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
  { id: "universe", label: "Universe" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("parametric");

  return (
    <SmileSessionProvider>
      <div className="flex h-full flex-col">
        <TopBar tabs={TABS} activeTab={activeTab} onSelect={setActiveTab} />

        {/* Main workspace area; each tab renders its dedicated view. */}
        <main className="flex-1 overflow-auto">
          {activeTab === "parametric" && <SmileViewer />}
          {activeTab === "localvol" && <LocalVolViewer />}
          {activeTab === "universe" && <UniverseManager />}
          {activeTab === "forwards" && <ForwardsViewer />}
          {activeTab === "options" && <OptionsViewer />}
          {activeTab === "graph" && (
            // Drill-in: GraphViewer points the shared smile session at a
            // node, then asks the shell to switch to the Parametric workspace.
            <GraphViewer onNavigateToSmile={() => setActiveTab("parametric")} />
          )}
        </main>
      </div>
    </SmileSessionProvider>
  );
}

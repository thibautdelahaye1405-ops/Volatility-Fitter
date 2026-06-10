// App shell: top bar with tab navigation, simple state-based routing.
import { useState } from "react";
import TopBar from "./components/TopBar";
import SmileViewer from "./views/SmileViewer";
import TermStructureViewer from "./views/TermStructureViewer";
import GraphViewer from "./views/GraphViewer";

/** The three top-level workspaces of the application. */
export type TabId = "smile" | "term" | "graph";

export interface TabDef {
  id: TabId;
  label: string;
}

export const TABS: TabDef[] = [
  { id: "smile", label: "Smile" },
  { id: "term", label: "Term Structure" },
  { id: "graph", label: "Graph" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("smile");

  return (
    <div className="flex h-full flex-col">
      <TopBar tabs={TABS} activeTab={activeTab} onSelect={setActiveTab} />

      {/* Main workspace area; each tab renders its dedicated view. */}
      <main className="flex-1 overflow-auto">
        {activeTab === "smile" && <SmileViewer />}
        {activeTab === "term" && <TermStructureViewer />}
        {activeTab === "graph" && <GraphViewer />}
      </main>
    </div>
  );
}

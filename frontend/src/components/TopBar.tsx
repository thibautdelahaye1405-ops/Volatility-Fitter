// Top navigation bar, three zones (ROADMAP Phase 10 / 2026-07 declutter):
//   left    σ VolFit ▾ brand menu (Options / View settings live here)
//   centre  grouped workspaces — Surfaces ▾ · Universe ▾ · Quality
//   right   workflow actions (Fetch ▾ · Calibrate · Priors ▾) + the market
//           pill (source status light · as-of timestamp) — live backend only.
import { useEffect } from "react";
import type { TabDef, TabId } from "../App";
import { useSmileSession } from "../state/smileSession";
import { useWorkflowContext } from "../state/workflowContext";
import BrandMenu from "./topbar/BrandMenu";
import NavMenus from "./topbar/NavMenus";
import MarketMenu from "./topbar/MarketMenu";
import WorkflowControls from "./WorkflowControls";

interface TopBarProps {
  /** Kept for the App shell's routing metadata (labels for error boundaries). */
  tabs: TabDef[];
  activeTab: TabId;
  onSelect: (tab: TabId) => void;
}

export default function TopBar({ activeTab, onSelect }: TopBarProps) {
  const { loading } = useSmileSession();
  // Shared workflow state (single poll loop feeds both the TopBar and the
  // bottom StatusBar). The detailed progress narration lives in the StatusBar.
  const { live, workflow, dataSources, asof } = useWorkflowContext();
  // Local-Vol master switch (polled on the scheduler status). When off, the
  // Local Vol workspace is disabled; bounce away if it's the active tab.
  const localVolEnabled = workflow.sched?.localVolEnabled ?? true;
  useEffect(() => {
    if (!localVolEnabled && activeTab === "localvol") onSelect("parametric");
  }, [localVolEnabled, activeTab, onSelect]);

  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-slate-800 bg-surface-900 px-4">
      <BrandMenu activeTab={activeTab} onSelect={onSelect} />

      <NavMenus
        activeTab={activeTab}
        onSelect={onSelect}
        localVolEnabled={localVolEnabled}
      />

      {/* Right side: workflow actions + market pill (live) or a status badge */}
      <div className="ml-auto flex items-center gap-3 text-xs">
        {loading ? (
          <span className="flex items-center gap-2 text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-500 animate-pulse" />
            Connecting…
          </span>
        ) : !live ? (
          <span className="flex items-center gap-2 text-amber-400">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Mock data
          </span>
        ) : (
          <>
            <WorkflowControls workflow={workflow} dataAge={dataSources.dataAge} />
            <MarketMenu dataSources={dataSources} asofHook={asof} />
          </>
        )}
      </div>
    </header>
  );
}

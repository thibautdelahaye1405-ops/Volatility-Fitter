// Top bar v2 (UI SHELL v2, S2) — three zones, VS Code title bar × Affinity:
//   LEFT    σ VolFit brand · Universe ▾ · Options · Help ▾   (the main menu)
//   CENTRE  command center: Fetch ▾ · Calibrate·scope ▾ · Priors ▾ · market
//           pill (source light + as-of) — live backend; a Connecting / Mock
//           badge otherwise
//   RIGHT   View ▾ (display preferences) · Layout ▾ (panes)
import { SlidersHorizontal } from "lucide-react";
import MenuButton from "./menus/MenuButton";
import UniverseMenu from "./menus/UniverseMenu";
import HelpMenu from "./menus/HelpMenu";
import ViewMenu from "./menus/ViewMenu";
import LayoutMenu from "./menus/LayoutMenu";
import MarketMenu from "../topbar/MarketMenu";
import WorkflowControls from "../WorkflowControls";
import { useSmileSession } from "../../state/smileSession";
import { useWorkflowContext } from "../../state/workflowContext";
import { useWorkbench } from "../../state/workbench";

export default function TopBar() {
  const { loading } = useSmileSession();
  const { live, workflow, dataSources, asof } = useWorkflowContext();
  const wb = useWorkbench();

  return (
    <header className="flex h-10 shrink-0 items-center gap-0.5 border-b border-slate-800 bg-surface-950 px-2">
      {/* Brand */}
      <button
        onClick={() => wb.openDialog("about")}
        title="About VolFit"
        className="mr-1 flex items-center gap-2 rounded-md px-1.5 py-1 text-slate-100 transition-colors hover:bg-slate-800/60"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-accent-600/20 font-mono text-sm font-bold text-accent-400">
          σ
        </span>
        <span className="text-sm font-semibold tracking-wide">VolFit</span>
      </button>

      {/* Main menu */}
      <UniverseMenu />
      <MenuButton
        label="Options"
        active={wb.dialog === "options"}
        title="Calibration & model settings (Ctrl+,)"
        onClick={() => wb.openDialog("options")}
      >
        <SlidersHorizontal size={13} strokeWidth={1.75} className="opacity-80" />
      </MenuButton>
      <HelpMenu />

      {/* Command center */}
      <div className="mx-auto flex items-center gap-3 text-xs">
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

      {/* View & layout */}
      <ViewMenu />
      <LayoutMenu />
    </header>
  );
}

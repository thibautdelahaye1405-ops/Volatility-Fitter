// Main pane (UI SHELL v2, S2): the node tab strip plus the active LENS
// rendered for the active tab's node. Graph and Quality are universe-level
// lenses (they render with no tab and highlight the active node); the three
// per-node lenses show an empty state until a node is opened. Each lens is
// wrapped in an error boundary keyed by the lens (NOT the tab) so switching
// tabs keeps the lens's view state and a crash in one lens never takes the
// shell down.
import ErrorBoundary from "../ErrorBoundary";
import TabStrip from "./TabStrip";
import SmileViewer from "../../views/SmileViewer";
import LocalVolViewer from "../../views/LocalVolViewer";
import ForwardsViewer from "../../views/ForwardsViewer";
import GraphViewer from "../../views/GraphViewer";
import QualityViewer from "../../views/QualityViewer";
import { ACTIVITIES, UNIVERSE_ACTIVITIES, useWorkbench } from "../../state/workbench";
import { useSmileSession } from "../../state/smileSession";
import { primaryButtonClass } from "../../lib/ui";

function EmptyState() {
  const wb = useWorkbench();
  const { universe } = useSmileSession();
  const first = universe?.tickers.map((t) => ({ t, e: universe.expiries[t]?.[0] })).find((x) => x.e);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <p className="text-sm font-semibold text-slate-200">No node open</p>
      <p className="max-w-sm text-xs leading-relaxed text-slate-500">
        Pick a node in the Nodes pane on the left (single click = preview, double click = pin).
        {!wb.layout.nodesPane && " The pane is hidden — press Ctrl+B to show it."}
      </p>
      {first?.e && (
        <button
          className={primaryButtonClass}
          onClick={() => wb.openNode({ ticker: first.t, expiry: first.e!.expiry })}
        >
          Open {first.t} {first.e.expiry}
        </button>
      )}
    </div>
  );
}

export default function MainPane() {
  const wb = useWorkbench();
  const { activity, activeTab } = wb;
  const label = ACTIVITIES.find((a) => a.id === activity)?.label;
  const needsTab = !UNIVERSE_ACTIVITIES.has(activity) && activeTab === null;

  let lens: React.ReactNode;
  if (needsTab) lens = <EmptyState />;
  else if (activity === "parametric") lens = <SmileViewer />;
  else if (activity === "localvol") lens = <LocalVolViewer />;
  else if (activity === "forwards") lens = <ForwardsViewer />;
  else if (activity === "graph") lens = <GraphViewer onNavigateToSmile={() => wb.setActivity("parametric")} />;
  else lens = <QualityViewer />;

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-surface-900">
      <TabStrip />
      <main className="min-h-0 flex-1 overflow-hidden">
        <ErrorBoundary key={activity} label={label}>
          {lens}
        </ErrorBoundary>
      </main>
    </section>
  );
}

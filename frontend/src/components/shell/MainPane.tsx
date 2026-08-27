// Main pane (UI SHELL v2, S2 / wave 3 C3): ONE or TWO editor groups side by
// side, each with its own tab strip + the lens for ITS active tab, rendered
// inside a node scope (state/nodeScope) so the two groups can show two
// nodes at once — the focused group is the session selection, the other
// fetches its own node. Universe-level lenses (Graph · Quality) render single-
// group and highlight the focused tab. Ctrl+\ splits / unsplits; dragging a
// tab (or a Nodes-pane row) onto the right 20 % of the pane opens it in a
// new right-hand group; the last tab closed in a group unsplits. A click
// anywhere in a group focuses it. Each lens sits in an error boundary keyed
// by the lens (NOT the tab) so switching tabs keeps the lens's view state
// and a crash in one lens never takes the shell down.
import { useState } from "react";
import type { DragEvent } from "react";
import ErrorBoundary from "../ErrorBoundary";
import TabStrip from "./TabStrip";
import SmileViewer from "../../views/SmileViewer";
import LocalVolViewer from "../../views/LocalVolViewer";
import ForwardsViewer from "../../views/ForwardsViewer";
import GraphViewer from "../../views/GraphViewer";
import QualityViewer from "../../views/QualityViewer";
import { ACTIVITIES, UNIVERSE_ACTIVITIES, useWorkbench } from "../../state/workbench";
import type { Activity } from "../../state/workbench";
import { useSmileSession } from "../../state/smileSession";
import { NodeScopeProvider } from "../../state/nodeScope";
import { NODE_MIME, decodeNodeDrag, isNodeDrag } from "../../lib/nodeDnd";
import { activeTab } from "../../lib/workbenchTabs";
import { primaryButtonClass } from "../../lib/ui";

function EmptyState({ group }: { group: number }) {
  const wb = useWorkbench();
  const { universe } = useSmileSession();
  const first = universe?.tickers.map((t) => ({ t, e: universe.expiries[t]?.[0] })).find((x) => x.e);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <p className="text-sm font-semibold text-slate-200">No node open{group > 0 ? " in this group" : ""}</p>
      <p className="max-w-sm text-xs leading-relaxed text-slate-500">
        Pick a node in the Nodes pane on the left (single click = preview, double click = pin
        {group > 0 ? ", Ctrl+Enter = this group" : ""}).
        {!wb.layout.nodesPane && " The pane is hidden — press Ctrl+B to show it."}
      </p>
      {first?.e && (
        <button className={primaryButtonClass} onClick={() => wb.openNodeIn(group, { ticker: first.t, expiry: first.e!.expiry })}>
          Open {first.t} {first.e.expiry}
        </button>
      )}
    </div>
  );
}

function lensFor(activity: Activity, onGraphSmile: () => void) {
  if (activity === "parametric") return <SmileViewer />;
  if (activity === "localvol") return <LocalVolViewer />;
  if (activity === "forwards") return <ForwardsViewer />;
  if (activity === "graph") return <GraphViewer onNavigateToSmile={onGraphSmile} />;
  return <QualityViewer />;
}

/** One editor group: tab strip + the group's lens under its node scope. */
function EditorGroupPane({ index }: { index: number }) {
  const wb = useWorkbench();
  const group = wb.groups[index];
  const focused = wb.focusedGroup === index;
  const activity = wb.activityOf(index);
  const tab = activeTab(group.tabs);
  const node = tab ? { ticker: tab.ticker, expiry: tab.expiry } : null;
  const label = ACTIVITIES.find((a) => a.id === activity)?.label;
  const needsTab = !UNIVERSE_ACTIVITIES.has(activity) && node === null;
  const split = wb.groups.length > 1;
  return (
    <section
      data-editor-group={index}
      aria-label={`Editor group ${index + 1}`}
      onPointerDownCapture={() => { if (!focused) wb.focusGroup(index); }}
      className={[
        "flex min-w-0 flex-1 flex-col bg-surface-900",
        split ? (index === 0 ? "border-r border-slate-800" : "") : "",
        split && focused ? "ring-1 ring-inset ring-accent-500/25" : "",
      ].join(" ")}
    >
      <TabStrip group={index} />
      <main className="min-h-0 flex-1 overflow-hidden">
        <NodeScopeProvider group={index} node={node} focused={focused} split={split}
          openHere={(n) => wb.openNodeIn(index, n, { preview: true })}>
          <ErrorBoundary key={activity} label={label}>
            {needsTab ? <EmptyState group={index} /> : lensFor(activity, () => wb.setActivity("parametric"))}
          </ErrorBoundary>
        </NodeScopeProvider>
      </main>
    </section>
  );
}

export default function MainPane() {
  const wb = useWorkbench();
  const [splitHalo, setSplitHalo] = useState(false);
  const universeLens = UNIVERSE_ACTIVITIES.has(wb.activity);
  const canSplit = wb.groups.length < 2 && !universeLens;
  // The right 20 % of the pane accepts a dragged tab / node while unsplit.
  const dragOn = canSplit && (wb.draggingTab !== null || splitHalo);
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!canSplit || (wb.draggingTab === null && !isNodeDrag(e.dataTransfer.types))) return;
    const r = e.currentTarget.getBoundingClientRect();
    const inZone = e.clientX > r.left + r.width * 0.8;
    if (inZone) e.preventDefault();
    if (inZone !== splitHalo) setSplitHalo(inZone);
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    if (!splitHalo) return;
    setSplitHalo(false);
    e.preventDefault();
    const node = decodeNodeDrag(e.dataTransfer.getData(NODE_MIME));
    if (node) { wb.openBeside(node); return; }
    const key = wb.draggingTab;
    if (key === null) return;
    wb.split();
    wb.moveTabToGroup(key, 1);
    wb.setDraggingTab(null);
  };

  return (
    <div className="relative flex min-w-0 flex-1" onDragOver={onDragOver} onDragLeave={() => setSplitHalo(false)} onDrop={onDrop}>
      {universeLens ? <EditorGroupPane index={0} /> : wb.groups.map((_, i) => <EditorGroupPane key={i} index={i} />)}
      {dragOn && (
        <div
          data-drop-zone="split"
          className={[
            "pointer-events-none absolute inset-y-0 right-0 w-1/5 border-l-2 transition-colors",
            splitHalo ? "border-accent-400 bg-accent-500/15" : "border-dashed border-slate-600/60 bg-slate-500/5",
          ].join(" ")}
        >
          <span className="absolute top-3 right-3 rounded-md border border-accent-500/50 bg-surface-900/90 px-2 py-0.5 text-[10px] font-medium text-accent-300">
            Drop to split (Ctrl+\)
          </span>
        </div>
      )}
    </div>
  );
}

// Canvas toolbar of the Graph lens (GRAPH ERGONOMICS ARC, E3): the vertical
// cluster at the top-right of the canvas — zoom in / out / fit, the Connect
// tool (drag node → node draws a relation; Shift-drag works without the
// tool), collapse / expand every ticker pod, and Focus (hide the side panes
// so the graph gets the whole lens). Pure presentation.
import { ChevronsDownUp, ChevronsUpDown, Link2, Maximize2, Minimize2 } from "lucide-react";

interface GraphCanvasToolbarProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  /** Connect tool (absent = the canvas is read-only for relations). */
  connectTool?: boolean;
  onToggleConnect?: () => void;
  /** Pod collapse controls (absent when the universe has one ticker). */
  allCollapsed?: boolean;
  onCollapseAll?: () => void;
  onExpandAll?: () => void;
  focused?: boolean;
  onToggleFocus?: () => void;
}

const btn =
  "flex items-center justify-center px-2 py-1.5 text-slate-300 transition-colors hover:bg-slate-700/40 hover:text-slate-100";
const active = "bg-accent-600/30 text-accent-300";

export default function GraphCanvasToolbar({
  onZoomIn,
  onZoomOut,
  onFit,
  connectTool,
  onToggleConnect,
  allCollapsed,
  onCollapseAll,
  onExpandAll,
  focused,
  onToggleFocus,
}: GraphCanvasToolbarProps) {
  return (
    <div className="absolute right-3 top-3 z-20 flex flex-col items-end gap-2">
      <div className="flex flex-col overflow-hidden rounded-md border border-slate-700 bg-surface-800">
        <button onClick={onZoomIn} title="Zoom in" className={btn + " text-sm leading-none"}>+</button>
        <button onClick={onZoomOut} title="Zoom out" className={btn + " text-sm leading-none"}>−</button>
        <button onClick={onFit} title="Fit graph to view" className={btn + " border-t border-slate-700 text-xs leading-none"}>⤢</button>
      </div>
      {(onToggleConnect !== undefined || onCollapseAll !== undefined || onToggleFocus !== undefined) && (
        <div className="flex flex-col overflow-hidden rounded-md border border-slate-700 bg-surface-800">
          {onToggleConnect !== undefined && (
            <button
              onClick={onToggleConnect}
              title={
                connectTool
                  ? "Connect tool ON — drag from an informer node to a receiver node to add a relation (Esc exits)"
                  : "Connect tool — drag node → node to add a relation (or hold Shift and drag)"
              }
              aria-pressed={connectTool === true}
              data-testid="tool-connect"
              className={btn + (connectTool ? " " + active : "")}
            >
              <Link2 size={13} strokeWidth={1.75} />
            </button>
          )}
          {onCollapseAll !== undefined && onExpandAll !== undefined && (
            <button
              onClick={allCollapsed ? onExpandAll : onCollapseAll}
              title={allCollapsed ? "Expand every ticker pod" : "Collapse every ticker to one node (click a ticker label for one pod)"}
              data-testid="tool-collapse"
              className={btn + " border-t border-slate-700"}
            >
              {allCollapsed ? <ChevronsUpDown size={13} strokeWidth={1.75} /> : <ChevronsDownUp size={13} strokeWidth={1.75} />}
            </button>
          )}
          {onToggleFocus !== undefined && (
            <button
              onClick={onToggleFocus}
              title={focused ? "Show the side panes (Esc)" : "Focus the canvas — hide the side panes"}
              aria-pressed={focused === true}
              data-testid="tool-focus"
              className={btn + " border-t border-slate-700" + (focused ? " " + active : "")}
            >
              {focused ? <Minimize2 size={13} strokeWidth={1.75} /> : <Maximize2 size={13} strokeWidth={1.75} />}
            </button>
          )}
        </div>
      )}
      {connectTool && (
        <span className="rounded-md border border-accent-500/50 bg-accent-500/15 px-2 py-0.5 text-[10px] font-medium text-accent-300">
          drag informer → receiver
        </span>
      )}
    </div>
  );
}

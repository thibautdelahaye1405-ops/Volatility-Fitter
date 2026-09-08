// Canvas toolbar of the Graph lens (GRAPH ERGONOMICS ARC, E3): ONE horizontal
// row at the top-right of the canvas, so a short graph pane never clips it
// (user report 2026-09-08: the vertical column's last button — Focus — fell
// below the pane's edge behind the hint strip). Order = what a small pane
// needs first: Focus (give the graph the whole lens), the Connect tool (drag
// node → node draws a relation; a plain drag or Shift does it without the
// tool), collapse / expand every ticker pod, then zoom in / out / fit.
// Pure presentation.
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
  "flex h-7 min-w-7 items-center justify-center px-2 text-slate-300 transition-colors hover:bg-slate-700/40 hover:text-slate-100";
const active = "bg-accent-600/30 text-accent-300";
const group = "flex overflow-hidden rounded-md border border-slate-700 bg-surface-800";

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
  const hasTools = onToggleFocus !== undefined || onToggleConnect !== undefined || onCollapseAll !== undefined;
  return (
    <div className="absolute right-3 top-3 z-20 flex flex-col items-end gap-1.5" data-testid="canvas-toolbar">
      <div className="flex items-center gap-1.5">
        {hasTools && (
          <div className={group}>
            {onToggleFocus !== undefined && (
              <button
                onClick={onToggleFocus}
                title={focused ? "Show the side panes again (F or Esc)" : "Focus — give the graph the whole lens (F)"}
                aria-pressed={focused === true}
                data-testid="tool-focus"
                className={btn + (focused ? " " + active : "")}
              >
                {focused ? <Minimize2 size={13} strokeWidth={1.75} /> : <Maximize2 size={13} strokeWidth={1.75} />}
              </button>
            )}
            {onToggleConnect !== undefined && (
              <button
                onClick={onToggleConnect}
                title={
                  connectTool
                    ? "Connect tool ON — drag from an informer node to a receiver node to add a relation (Esc exits)"
                    : "Connect tool — drag node → node to add a relation (a plain drag or Shift-drag does it too)"
                }
                aria-pressed={connectTool === true}
                data-testid="tool-connect"
                className={btn + " border-l border-slate-700" + (connectTool ? " " + active : "")}
              >
                <Link2 size={13} strokeWidth={1.75} />
              </button>
            )}
            {onCollapseAll !== undefined && onExpandAll !== undefined && (
              <button
                onClick={allCollapsed ? onExpandAll : onCollapseAll}
                title={allCollapsed ? "Expand every ticker pod" : "Collapse every ticker to one node (click a ticker label for one pod)"}
                data-testid="tool-collapse"
                className={btn + " border-l border-slate-700"}
              >
                {allCollapsed ? <ChevronsUpDown size={13} strokeWidth={1.75} /> : <ChevronsDownUp size={13} strokeWidth={1.75} />}
              </button>
            )}
          </div>
        )}
        <div className={group}>
          <button onClick={onZoomOut} title="Zoom out" className={btn + " text-sm leading-none"}>−</button>
          <button onClick={onZoomIn} title="Zoom in" className={btn + " border-l border-slate-700 text-sm leading-none"}>+</button>
          <button onClick={onFit} title="Fit graph to view" className={btn + " border-l border-slate-700 text-xs leading-none"}>⤢</button>
        </div>
      </div>
      {connectTool && (
        <span className="rounded-md border border-accent-500/50 bg-accent-500/15 px-2 py-0.5 text-[10px] font-medium text-accent-300">
          drag informer → receiver
        </span>
      )}
    </div>
  );
}

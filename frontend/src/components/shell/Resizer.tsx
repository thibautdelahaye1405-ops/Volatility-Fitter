// Vertical drag handle between the Nodes pane and the main pane (UI SHELL
// v2, S2). Pointer-captured drag reports the new width; double-click resets
// to the default (1/5 of the viewport). Purely presentational otherwise.
import { useRef } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

interface ResizerProps {
  /** Current width of the pane on the LEFT of the handle. */
  width: number;
  min: number;
  max: number;
  onResize: (width: number) => void;
  onReset: () => void;
}

export default function Resizer({ width, min, max, onResize, onReset }: ResizerProps) {
  const start = useRef<{ x: number; w: number } | null>(null);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    start.current = { x: e.clientX, w: width };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (start.current === null) return;
    const next = start.current.w + (e.clientX - start.current.x);
    onResize(Math.max(min, Math.min(max, next)));
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    start.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      title="Drag to resize · double-click to reset"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onDoubleClick={onReset}
      className="group relative w-1 shrink-0 cursor-col-resize bg-slate-800/80 transition-colors hover:bg-accent-500/60"
    >
      {/* Wider invisible hit area so the 1px seam is easy to grab. */}
      <span className="absolute inset-y-0 -left-1 -right-1" />
    </div>
  );
}

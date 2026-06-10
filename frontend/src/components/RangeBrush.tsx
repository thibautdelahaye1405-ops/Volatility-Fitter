// Slim two-handle range slider used as a strike-window brush under charts.
// Pure React + pointer events, no dependencies. Fully controlled component.
import { useCallback, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { clamp } from "../lib/chartScale";

interface RangeBrushProps {
  /** Full extent of the brushable domain. */
  min: number;
  max: number;
  /** Current selected window [lo, hi]. */
  value: readonly [number, number];
  onChange: (next: [number, number]) => void;
  /** Smallest allowed window, as a fraction of (max - min). Default 5%. */
  minWindowFrac?: number;
  /** Label formatter for the handle values. */
  format?: (v: number) => string;
}

/** Which part of the brush is being dragged. */
type DragTarget = "lo" | "hi" | "pan" | null;

export default function RangeBrush({
  min,
  max,
  value,
  onChange,
  minWindowFrac = 0.05,
  format,
}: RangeBrushProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<DragTarget>(null);
  // Offset between the pointer and the window's lo edge when panning.
  const panOffset = useRef(0);

  const span = max - min;
  const minWindow = span * minWindowFrac;
  const [lo, hi] = value;
  const toFrac = (v: number) => (span === 0 ? 0 : (v - min) / span);

  /** Convert a pointer event to a domain value along the track. */
  const valueAt = useCallback(
    (clientX: number): number => {
      const el = trackRef.current;
      if (!el) return min;
      const rect = el.getBoundingClientRect();
      const frac = clamp((clientX - rect.left) / rect.width, 0, 1);
      return min + frac * span;
    },
    [min, span],
  );

  const beginDrag = (target: Exclude<DragTarget, null>) =>
    (e: ReactPointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      e.currentTarget.setPointerCapture(e.pointerId);
      if (target === "pan") panOffset.current = valueAt(e.clientX) - lo;
      setDrag(target);
    };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const v = valueAt(e.clientX);
    if (drag === "lo") {
      onChange([clamp(v, min, hi - minWindow), hi]);
    } else if (drag === "hi") {
      onChange([lo, clamp(v, lo + minWindow, max)]);
    } else {
      // Pan: slide the whole window, preserving its width.
      const width = hi - lo;
      const nextLo = clamp(v - panOffset.current, min, max - width);
      onChange([nextLo, nextLo + width]);
    }
  };

  const endDrag = () => setDrag(null);

  const handleClass =
    "absolute top-1/2 z-10 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 " +
    "cursor-ew-resize rounded-full border border-accent-400 bg-surface-800 " +
    "shadow shadow-black/40 transition-transform hover:scale-110";

  return (
    <div className="flex items-center gap-3 select-none">
      {format && (
        <span className="w-12 shrink-0 text-right font-mono text-[10px] text-slate-500">
          {format(lo)}
        </span>
      )}

      {/* Track */}
      <div
        ref={trackRef}
        className="relative h-5 flex-1 touch-none"
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-surface-700" />

        {/* Selected window (draggable to pan) */}
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 cursor-grab rounded-full bg-accent-600/70 active:cursor-grabbing"
          style={{
            left: `${toFrac(lo) * 100}%`,
            width: `${(toFrac(hi) - toFrac(lo)) * 100}%`,
          }}
          onPointerDown={beginDrag("pan")}
        />

        {/* Handles */}
        <div
          className={handleClass}
          style={{ left: `${toFrac(lo) * 100}%` }}
          onPointerDown={beginDrag("lo")}
          role="slider"
          aria-label="Lower strike bound"
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={lo}
        />
        <div
          className={handleClass}
          style={{ left: `${toFrac(hi) * 100}%` }}
          onPointerDown={beginDrag("hi")}
          role="slider"
          aria-label="Upper strike bound"
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={hi}
        />
      </div>

      {format && (
        <span className="w-12 shrink-0 font-mono text-[10px] text-slate-500">
          {format(hi)}
        </span>
      )}
    </div>
  );
}

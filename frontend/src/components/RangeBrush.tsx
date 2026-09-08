// Slim two-handle range slider used as a window brush under (or beside)
// charts — the strike window of the 2-D charts and, since 2026-09-08, both
// axes of the 3D surfaces: `orientation="vertical"` lays the same brush
// along the side of a plot with the LOW value at the BOTTOM (a maturity axis
// reads upward, as the sheet's far edge sits at the top of the frame).
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
  /** Track direction: along x (default) or along y with `min` at the bottom. */
  orientation?: "horizontal" | "vertical";
  /** Accessible names of the two handles (default: strike bounds). */
  ariaLabels?: readonly [string, string];
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
  orientation = "horizontal",
  ariaLabels = ["Lower strike bound", "Upper strike bound"],
}: RangeBrushProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<DragTarget>(null);
  // Offset between the pointer and the window's lo edge when panning.
  const panOffset = useRef(0);
  const vertical = orientation === "vertical";

  const span = max - min;
  const minWindow = span * minWindowFrac;
  const [lo, hi] = value;
  const toFrac = (v: number) => (span === 0 ? 0 : (v - min) / span);
  /** A CSS percentage without floating-point tails (19.999…% → 20%). */
  const pct = (f: number) => `${Number((f * 100).toFixed(4))}%`;

  /** Convert a pointer position to a domain value along the track (a vertical
   *  track counts from its BOTTOM edge). */
  const valueAt = useCallback(
    (clientX: number, clientY: number): number => {
      const el = trackRef.current;
      if (!el) return min;
      const rect = el.getBoundingClientRect();
      const frac = vertical
        ? clamp((rect.bottom - clientY) / (rect.height || 1), 0, 1)
        : clamp((clientX - rect.left) / (rect.width || 1), 0, 1);
      return min + frac * span;
    },
    [min, span, vertical],
  );

  const beginDrag = (target: Exclude<DragTarget, null>) =>
    (e: ReactPointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      e.currentTarget.setPointerCapture(e.pointerId);
      if (target === "pan") panOffset.current = valueAt(e.clientX, e.clientY) - lo;
      setDrag(target);
    };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag) return;
    const v = valueAt(e.clientX, e.clientY);
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
    "absolute z-10 h-3.5 w-3.5 rounded-full border border-accent-400 bg-surface-800 " +
    "shadow shadow-black/40 transition-transform hover:scale-110 " +
    (vertical
      ? "left-1/2 -translate-x-1/2 -translate-y-1/2 cursor-ns-resize"
      : "top-1/2 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize");
  /** Position style of a handle at fraction f (a vertical track grows upward). */
  const at = (f: number) => (vertical ? { top: pct(1 - f) } : { left: pct(f) });
  const label = (v: number, align: string) =>
    format ? (
      <span className={`shrink-0 font-mono text-[10px] text-slate-500 ${align}`}>{format(v)}</span>
    ) : null;

  return (
    <div
      className={vertical ? "flex h-full min-h-0 flex-col items-center gap-1 select-none" : "flex items-center gap-3 select-none"}
      data-orientation={orientation}
    >
      {vertical ? label(hi, "text-center") : label(lo, "w-12 text-right")}

      {/* Track */}
      <div
        ref={trackRef}
        className={vertical ? "relative min-h-0 w-5 flex-1 touch-none" : "relative h-5 flex-1 touch-none"}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div
          className={
            vertical
              ? "absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 rounded-full bg-surface-700"
              : "absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-surface-700"
          }
        />

        {/* Selected window (draggable to pan) */}
        <div
          className={
            vertical
              ? "absolute left-1/2 w-1 -translate-x-1/2 cursor-grab rounded-full bg-accent-600/70 active:cursor-grabbing"
              : "absolute top-1/2 h-1 -translate-y-1/2 cursor-grab rounded-full bg-accent-600/70 active:cursor-grabbing"
          }
          style={
            vertical
              ? { bottom: pct(toFrac(lo)), height: pct(toFrac(hi) - toFrac(lo)) }
              : { left: pct(toFrac(lo)), width: pct(toFrac(hi) - toFrac(lo)) }
          }
          onPointerDown={beginDrag("pan")}
        />

        {/* Handles */}
        <div
          className={handleClass}
          style={at(toFrac(lo))}
          onPointerDown={beginDrag("lo")}
          role="slider"
          aria-label={ariaLabels[0]}
          aria-orientation={orientation}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={lo}
        />
        <div
          className={handleClass}
          style={at(toFrac(hi))}
          onPointerDown={beginDrag("hi")}
          role="slider"
          aria-label={ariaLabels[1]}
          aria-orientation={orientation}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={hi}
        />
      </div>

      {vertical ? label(lo, "text-center") : label(hi, "w-12")}
    </div>
  );
}

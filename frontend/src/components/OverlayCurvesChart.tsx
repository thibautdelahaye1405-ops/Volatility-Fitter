// Generic overlaid multi-series line chart (ROADMAP Phase 10).
//
// Backs the Parametric "Stacked densities" and "Stacked IV" views: every
// selected expiry is one curve on shared axes, colour-graded near→far by
// maturity, so the eye reads positivity (densities ≥ 0) or non-crossing
// (total-variance curves) directly. Hand-rolled SVG following the SmileChart /
// DistributionChart conventions (grid, axes, legend); no chart deps.
import { useLayoutEffect, useRef, useState } from "react";
import { formatAxisNumber, linearScale, niceTicks } from "../lib/chartScale";

/** One plottable curve. */
export interface OverlaySeries {
  label: string;
  xs: number[];
  ys: number[];
  /** Stroke colour (the wrapper grades these by maturity). */
  color: string;
}

interface OverlayCurvesChartProps {
  series: OverlaySeries[];
  xLabel: string;
  yLabel: string;
  /** Draw a y = 0 baseline (used by the density view to anchor positivity). */
  zeroBaseline?: boolean;
}

const MARGIN = { top: 14, right: 16, bottom: 34, left: 56 } as const;

/** Track the pixel size of a container element (same as the other charts). */
function useElementSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}

/** Min/max across all series for one accessor, or null when there's no data. */
function domain(series: OverlaySeries[], pick: (s: OverlaySeries) => number[]) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of series) {
    for (const v of pick(s)) {
      if (!Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return lo <= hi ? { lo, hi } : null;
}

export default function OverlayCurvesChart({
  series,
  xLabel,
  yLabel,
  zeroBaseline = false,
}: OverlayCurvesChartProps) {
  const { ref, size } = useElementSize();

  if (series.length === 0) {
    return (
      <div ref={ref} className="h-full w-full">
        <div className="flex h-full items-center justify-center text-xs text-slate-500">
          No curves to display.
        </div>
      </div>
    );
  }

  const innerW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  const xd = domain(series, (s) => s.xs);
  const yd0 = domain(series, (s) => s.ys);
  // Pad the y-domain a touch; include 0 when a baseline is requested.
  const ydLo = zeroBaseline ? Math.min(0, yd0?.lo ?? 0) : (yd0?.lo ?? 0);
  const ydHi = (yd0?.hi ?? 1) * 1.04;

  const ready = size.width > 0 && size.height > 0 && xd !== null && yd0 !== null;
  const xScale = linearScale([xd?.lo ?? 0, xd?.hi ?? 1], [0, innerW]);
  const yScale = linearScale([ydLo, ydHi], [innerH, 0]);

  const xTicks = ready ? niceTicks(xd!.lo, xd!.hi, 6) : [];
  const yTicks = ready ? niceTicks(ydLo, ydHi, 5) : [];

  const pathOf = (s: OverlaySeries): string => {
    let d = "";
    let started = false;
    for (let i = 0; i < s.xs.length; i++) {
      const x = s.xs[i];
      const y = s.ys[i];
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        started = false;
        continue;
      }
      const px = xScale.map(x);
      const py = yScale.map(y);
      d += `${started ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`;
      started = true;
    }
    return d;
  };

  return (
    <div ref={ref} className="h-full w-full">
      {ready && (
        <svg width={size.width} height={size.height} className="block">
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {/* Y grid + labels */}
            {yTicks.map((t) => {
              const y = yScale.map(t);
              return (
                <g key={`y${t}`}>
                  <line x1={0} x2={innerW} y1={y} y2={y} stroke="#1f2937" strokeWidth={1} />
                  <text x={-8} y={y} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[10px]">
                    {formatAxisNumber(t)}
                  </text>
                </g>
              );
            })}
            {/* X grid + labels */}
            {xTicks.map((t) => {
              const x = xScale.map(t);
              return (
                <g key={`x${t}`}>
                  <line x1={x} x2={x} y1={0} y2={innerH} stroke="#1f2937" strokeWidth={1} />
                  <text x={x} y={innerH + 18} textAnchor="middle" className="fill-slate-500 text-[10px]">
                    {formatAxisNumber(t)}
                  </text>
                </g>
              );
            })}
            {/* Zero baseline (densities) */}
            {zeroBaseline && ydLo < 0 === false && (
              <line x1={0} x2={innerW} y1={yScale.map(0)} y2={yScale.map(0)} stroke="#334155" strokeWidth={1} />
            )}

            {/* Curves, near→far */}
            {series.map((s) => (
              <path key={s.label} d={pathOf(s)} fill="none" stroke={s.color} strokeWidth={1.5} opacity={0.9} />
            ))}

            {/* Axis labels */}
            <text x={innerW} y={innerH + 30} textAnchor="end" className="fill-slate-600 text-[10px]">
              {xLabel}
            </text>
            <text x={2} y={-4} className="fill-slate-600 text-[10px]">
              {yLabel}
            </text>

            {/* Legend (maturity-graded) */}
            <g transform={`translate(${innerW - 4},6)`}>
              {series.map((s, i) => (
                <g key={s.label} transform={`translate(0,${i * 14})`}>
                  <line x1={-26} x2={-12} y1={0} y2={0} stroke={s.color} strokeWidth={2} />
                  <text x={-30} y={0} dy="0.32em" textAnchor="end" className="fill-slate-400 text-[10px]">
                    {s.label}
                  </text>
                </g>
              ))}
            </g>
          </g>
        </svg>
      )}
    </div>
  );
}

/** Maturity-graded stroke colour: near = bright accent/cyan, far = indigo.
 *  ``frac`` in [0,1] is the maturity rank (0 = nearest). */
export function maturityColor(frac: number): string {
  // Hue 190 (cyan) → 265 (indigo); keep saturation/lightness readable on dark.
  const hue = 190 + frac * 75;
  const light = 65 - frac * 15;
  return `hsl(${hue.toFixed(0)}, 80%, ${light.toFixed(0)}%)`;
}

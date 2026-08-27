// Generic overlaid multi-series line chart (ROADMAP Phase 10).
//
// Backs the Parametric "Stacked densities" and "Stacked IV" views: every
// selected expiry is one curve on shared axes, colour-graded near→far by
// maturity. Hand-rolled SVG following the SmileChart conventions; no chart deps.
// Supports wheel-zoom (x by default; +Shift x-only / +Alt y-only when zoomY),
// drag-pan and double-click / ⌂ reset — zoom-out reveals beyond the data.
// Linked hover (wave 3, B2): with `link` set and the x-axis in log-moneyness,
// hovering publishes (ticker, k = x, T of the nearest curve) on the surface
// hover store, and a point published by another chart of the ticker shows
// here as a highlighted curve (nearest T) + a marker at k.
import { useEffect, useId, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { clamp, formatAxisNumber, linearScale, niceTicks } from "../lib/chartScale";
import { useElementSize } from "../lib/useElementSize";
import { useZoom } from "../lib/useZoom";
import { crosshairLabel, crosshairPoint } from "../lib/crosshair";
import type { CrosshairPoint } from "../lib/crosshair";
import { interpolateY, nearestByT, nearestCurveAt } from "../lib/overlayLink";
import { useSurfaceHover } from "../state/surfaceHover";
import { CrosshairBadge, CrosshairGuides } from "./CrosshairOverlay";

/** One plottable curve. */
export interface OverlaySeries {
  label: string;
  xs: number[];
  ys: number[];
  /** Stroke colour (the wrapper grades these by maturity). */
  color: string;
  /** Maturity (years) — enables the linked hover for this curve. */
  t?: number;
  /** Fill sub-zero excursions of this series in red (arb evidence: Δ-mode
   *  calendar crossings, signed density dips). Off by default. */
  fillNegative?: boolean;
}

/** One circle marker on the shared axes with a native hover tooltip —
 *  the arb-evidence pins (calendar-cross location, density-dip minimum). */
export interface OverlayMarker {
  x: number;
  y: number;
  label: string;
  /** Stroke colour; defaults to the evidence rose. */
  color?: string;
}

interface OverlayCurvesChartProps {
  series: OverlaySeries[];
  xLabel: string;
  yLabel: string;
  /** Draw a y = 0 baseline (used by the density view to anchor positivity). */
  zeroBaseline?: boolean;
  /** Allow zooming the y-axis too (Stacked IV); otherwise wheel zooms x only. */
  zoomY?: boolean;
  /** X tick-label formatter (display units, e.g. "25Δ"/"120%"); default numeric. */
  formatX?: (v: number) => string;
  /** Evidence circles (optional, additive — no behavior change when absent). */
  markers?: OverlayMarker[];
  /** Linked (k, T) hover: set only when the x-axis IS log-moneyness. */
  link?: { ticker: string; chartId: string };
}

/** Evidence-rose used for sub-zero fills and default marker strokes. */
const EVIDENCE_ROSE = "rgb(244 63 94)";

const MARGIN = { top: 14, right: 16, bottom: 34, left: 56 } as const;

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
  zoomY = false,
  formatX = formatAxisNumber,
  markers,
  link,
}: OverlayCurvesChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const clipId = useId();
  const zoom = useZoom();
  /** Crosshair position, or null when the pointer is outside / panning. */
  const [cross, setCross] = useState<CrosshairPoint | null>(null);
  const hoverLink = useSurfaceHover(link?.chartId ?? "overlay");
  const setCrossLinked = (pt: CrosshairPoint | null) => {
    setCross(pt);
    if (!link) return;
    if (pt === null) { hoverLink.publish(null); return; }
    const idx = nearestCurveAt(series, pt.x, pt.y, (v) => yScale.map(v));
    const t = idx === null ? undefined : series[idx].t;
    if (t !== undefined) hoverLink.publish({ ticker: link.ticker, k: pt.x, t });
  };
  useEffect(() => () => hoverLink.publish(null), [hoverLink]);

  const innerW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  // Wheel zoom (native, non-passive so preventDefault works).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      if (innerW <= 0 || innerH <= 0) return;
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const fx = clamp((e.clientX - rect.left - MARGIN.left) / innerW, 0, 1);
      const fy = clamp((e.clientY - rect.top - MARGIN.top) / innerH, 0, 1);
      const axis = !zoomY ? "x" : e.shiftKey ? "x" : e.altKey ? "y" : "both";
      zoom.zoomAt(fx, fy, e.deltaY, axis);
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoom, innerW, innerH, zoomY]);

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (d && innerW > 0 && innerH > 0) {
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) {
        zoom.panBy(dx / innerW, dy / innerH, zoomY ? "both" : "x");
        drag.current = { x: e.clientX, y: e.clientY, moved: true };
      }
    }
    // Crosshair rides the same handler (hover-only, hidden while panning).
    const svg = svgRef.current;
    if (!svg) return;
    if (drag.current?.moved) {
      setCrossLinked(null);
      return;
    }
    setCrossLinked(
      crosshairPoint(e.clientX, e.clientY, svg.getBoundingClientRect(), MARGIN,
        innerW, innerH, xScale.invert, yScale.invert),
    );
  };
  const onPointerUp = () => {
    drag.current = null;
  };
  const onPointerLeave = () => {
    drag.current = null;
    setCrossLinked(null);
  };
  // A point published by another chart of this ticker → curve + marker here.
  const h = hoverLink.hover;
  const linkedIdx =
    link && cross === null && h !== null && h.source !== link.chartId && h.ticker === link.ticker
      ? nearestByT(series.map((s) => s.t ?? NaN).map((t) => (Number.isFinite(t) ? t : Infinity)), h.t)
      : null;
  const linkedY = linkedIdx !== null && h !== null ? interpolateY(series[linkedIdx], h.k) : null;

  if (series.length === 0) {
    return (
      <div ref={ref} className="h-full w-full">
        <div className="flex h-full items-center justify-center text-xs text-slate-500">
          No curves to display.
        </div>
      </div>
    );
  }

  const xd = domain(series, (s) => s.xs);
  const yd0 = domain(series, (s) => s.ys);
  // Pad the y-domain a touch; include 0 when a baseline is requested.
  const baseYLo = zeroBaseline ? Math.min(0, yd0?.lo ?? 0) : (yd0?.lo ?? 0);
  const baseYHi = (yd0?.hi ?? 1) * 1.04;

  const ready = size.width > 0 && size.height > 0 && xd !== null && yd0 !== null;

  // Apply zoom to the base domains.
  const [vxLo, vxHi] = zoom.viewX([xd?.lo ?? 0, xd?.hi ?? 1]);
  const [vyLo, vyHi] = zoom.viewY([baseYLo, baseYHi]);
  const xScale = linearScale([vxLo, vxHi], [0, innerW]);
  const yScale = linearScale([vyLo, vyHi], [innerH, 0]);

  const xTicks = ready ? niceTicks(Math.min(vxLo, vxHi), Math.max(vxLo, vxHi), 6) : [];
  const yTicks = ready ? niceTicks(Math.min(vyLo, vyHi), Math.max(vyLo, vyHi), 5) : [];

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

  /** Sub-zero fill of a series: the polyline of min(y, 0) closed along y = 0 —
   *  regions with y >= 0 collapse onto the baseline (zero area), so only the
   *  negative excursions read as red. */
  const negativeFillPath = (s: OverlaySeries): string => {
    const y0 = yScale.map(0);
    let d = "";
    let firstPx: number | null = null;
    let lastPx: number | null = null;
    for (let i = 0; i < s.xs.length; i++) {
      const x = s.xs[i];
      const y = s.ys[i];
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      const px = xScale.map(x);
      const py = yScale.map(Math.min(y, 0));
      d += `${d === "" ? "M" : "L"}${px.toFixed(1)},${py.toFixed(1)}`;
      if (firstPx === null) firstPx = px;
      lastPx = px;
    }
    if (d === "" || firstPx === null || lastPx === null) return "";
    return `${d}L${lastPx.toFixed(1)},${y0.toFixed(1)}L${firstPx.toFixed(1)},${y0.toFixed(1)}Z`;
  };

  return (
    <div ref={ref} className="relative h-full w-full">
      {ready && (
        <svg
          ref={svgRef}
          width={size.width}
          height={size.height}
          className="block touch-none select-none"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerLeave}
          onDoubleClick={zoom.reset}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={0} y={0} width={innerW} height={innerH} />
            </clipPath>
          </defs>
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {/* Y grid + labels */}
            {yTicks.map((t) => {
              const y = yScale.map(t);
              return (
                <g key={`y${t}`}>
                  <line x1={0} x2={innerW} y1={y} y2={y} stroke="var(--color-surface-700)" strokeWidth={1} />
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
                  <line x1={x} x2={x} y1={0} y2={innerH} stroke="var(--color-surface-700)" strokeWidth={1} />
                  <text x={x} y={innerH + 18} textAnchor="middle" className="fill-slate-500 text-[10px]">
                    {formatX(t)}
                  </text>
                </g>
              );
            })}

            <g clipPath={`url(#${clipId})`}>
              {/* Zero baseline (densities) */}
              {zeroBaseline && (
                <line x1={0} x2={innerW} y1={yScale.map(0)} y2={yScale.map(0)} stroke="var(--color-slate-700)" strokeWidth={1} />
              )}
              {/* Sub-zero excursion fills (arb evidence), UNDER the curves */}
              {series
                .filter((s) => s.fillNegative === true)
                .map((s) => {
                  const d = negativeFillPath(s);
                  return d !== "" ? (
                    <path key={`${s.label}·neg`} d={d} fill="rgb(244 63 94 / 0.22)" stroke="none" />
                  ) : null;
                })}
              {/* Curves, near→far (the linked curve reads bolder) */}
              {series.map((s, i) => (
                <path key={s.label} d={pathOf(s)} fill="none" stroke={s.color}
                  strokeWidth={i === linkedIdx ? 2.75 : 1.5} opacity={linkedIdx === null || i === linkedIdx ? 0.95 : 0.45} />
              ))}
              {/* Linked hover marker (a point published by a surface chart) */}
              {linkedIdx !== null && linkedY !== null && h !== null && (
                <g pointerEvents="none">
                  <line x1={xScale.map(h.k)} x2={xScale.map(h.k)} y1={0} y2={innerH} stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                  <circle cx={xScale.map(h.k)} cy={yScale.map(linkedY)} r={4.5} fill="rgb(15 23 42)" stroke={series[linkedIdx].color} strokeWidth={1.75} />
                </g>
              )}
              {/* Evidence circles (calendar cross / density dip) + hover title */}
              {(markers ?? [])
                .filter((m) => Number.isFinite(m.x) && Number.isFinite(m.y))
                .map((m, i) => (
                  <g key={`marker${i}`}>
                    <circle
                      cx={xScale.map(m.x)}
                      cy={yScale.map(m.y)}
                      r={4.5}
                      fill="rgb(244 63 94 / 0.15)"
                      stroke={m.color ?? EVIDENCE_ROSE}
                      strokeWidth={1.75}
                    >
                      <title>{m.label}</title>
                    </circle>
                    <circle
                      cx={xScale.map(m.x)}
                      cy={yScale.map(m.y)}
                      r={1.4}
                      fill={m.color ?? EVIDENCE_ROSE}
                      pointerEvents="none"
                    />
                  </g>
                ))}
            </g>

            {/* Crosshair guides (hover-only) */}
            {cross !== null && <CrosshairGuides point={cross} plotW={innerW} plotH={innerH} />}

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

      {/* Crosshair readout badge (x in display units, y in axis units) */}
      {cross !== null && (
        <CrosshairBadge label={crosshairLabel(cross, formatX, formatAxisNumber)} />
      )}

      {zoom.zoomed && (
        <button
          onClick={zoom.reset}
          title="Reset zoom (or double-click)"
          className="absolute bottom-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2 py-0.5 text-[10px] text-slate-300 shadow hover:text-slate-100"
        >
          ⌂ reset
        </button>
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

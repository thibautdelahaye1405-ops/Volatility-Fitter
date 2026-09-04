// Generic overlaid multi-series line chart (ROADMAP Phase 10).
//
// Backs the Parametric / Local-Vol "Densities" and "Stacked IV" views and the
// Compare view: every series is one curve on shared axes (the ladder views
// colour-grade near→far by maturity). Hand-rolled SVG on the SmileChart
// conventions, with the SAME interaction stack (lib/useChartZoom): wheel-zoom
// (+Shift x-only / +Alt y-only), drag-pan, double-click / ⌂ reset, the Y
// center / Y fit overlay buttons whose policy owns y (the y BASE auto-fits
// the points inside the x view, like the Smile), and a coarse x-window brush
// under the plot — controlled in the caller's units (the Compare view shares
// the smile's k-window) or internal in display units over the data extent.
// Linked hover (wave 3, B2): with `link` set and the x-axis in log-moneyness,
// hovering publishes (ticker, k = x, T of the nearest curve) on the surface
// hover store, and a point published by another chart of the ticker shows
// here as a highlighted curve (nearest T) + a marker at k.
import { useEffect, useId, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { formatAxisNumber, linearScale, niceTicks } from "../lib/chartScale";
import { useElementSize } from "../lib/useElementSize";
import { useChartZoom } from "../lib/useChartZoom";
import type { AutoScaleToggles } from "../lib/autoScaleY";
import { crosshairLabel, crosshairPoint } from "../lib/crosshair";
import type { CrosshairPoint } from "../lib/crosshair";
import { interpolateY, nearestByT, nearestCurveAt } from "../lib/overlayLink";
import { fullDomain, inViewYDomain, negativeFillPath, seriesPath } from "../lib/overlayPaths";
import { useSurfaceHover } from "../state/surfaceHover";
import { CrosshairBadge, CrosshairGuides } from "./CrosshairOverlay";
import ZoomOverlay from "./charts/ZoomOverlay";
import RangeBrush from "./RangeBrush";

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
  /** SVG stroke-dasharray ("5 3") — a reference curve drawn dashed so it
   *  never reads as one of the calibrated families. Solid when absent. */
  dash?: string;
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

/** A CONTROLLED coarse x-window brush in the caller's units: `toX` maps a
 *  bound to display x (the Compare chart brushes in log-moneyness k while its
 *  geometry sits in the selected axis coordinate). */
export interface OverlayBrush {
  min: number;
  max: number;
  value: readonly [number, number];
  onChange: (next: [number, number]) => void;
  toX?: (v: number) => number;
  format?: (v: number) => string;
}

interface OverlayCurvesChartProps {
  series: OverlaySeries[];
  xLabel: string;
  yLabel: string;
  /** Draw a y = 0 baseline (used by the density view to anchor positivity). */
  zeroBaseline?: boolean;
  /** X tick-label formatter (display units, e.g. "25Δ"/"120%"); default numeric. */
  formatX?: (v: number) => string;
  /** Y tick-label formatter (e.g. a vol percentage); default numeric. */
  formatY?: (v: number) => string;
  /** Crosshair y readout; defaults to `formatY`. */
  formatHoverY?: (v: number) => string;
  /** Evidence circles (optional, additive — no behavior change when absent). */
  markers?: OverlayMarker[];
  /** Linked (k, T) hover: set only when the x-axis IS log-moneyness. */
  link?: { ticker: string; chartId: string };
  /** The coarse x-window brush under the plot: a controlled OverlayBrush,
   *  `false` to hide it (small embedded charts), or absent for the internal
   *  brush in display units over the data extent (reset when the extent
   *  changes — new data, another axis mode). */
  xBrush?: OverlayBrush | false;
  /** Y auto-scale toggles (lib/autoScaleY) + their toggler: with a toggler
   *  the Y center / Y fit buttons show on the plot. Both ON by default. */
  autoScaleY?: AutoScaleToggles;
  onToggleAutoScale?: (key: keyof AutoScaleToggles) => void;
}

/** Evidence-rose used for sub-zero fills and default marker strokes. */
const EVIDENCE_ROSE = "rgb(244 63 94)";

const MARGIN = { top: 14, right: 16, bottom: 34, left: 56 } as const;

export default function OverlayCurvesChart({
  series,
  xLabel,
  yLabel,
  zeroBaseline = false,
  formatX = formatAxisNumber,
  formatY = formatAxisNumber,
  formatHoverY,
  markers,
  link,
  xBrush,
  autoScaleY,
  onToggleAutoScale,
}: OverlayCurvesChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const clipId = useId();
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

  // The coarse x window: controlled (caller units through toX) or internal
  // in display units over the data extent — reset whenever that extent
  // changes (new data, another axis mode), adjusted during render so the
  // chart never paints a stale window.
  const xd = fullDomain(series, (s) => s.xs);
  const extentKey = xd === null ? "" : `${xd.lo},${xd.hi}`;
  const [innerWin, setInnerWin] = useState<[number, number] | null>(null);
  const [prevExtentKey, setPrevExtentKey] = useState(extentKey);
  if (extentKey !== prevExtentKey) {
    setPrevExtentKey(extentKey);
    setInnerWin(null);
  }
  const brush: OverlayBrush | null =
    xBrush === false
      ? null
      : (xBrush ??
        (xd === null
          ? null
          : { min: xd.lo, max: xd.hi, value: innerWin ?? [xd.lo, xd.hi], onChange: setInnerWin, format: formatX }));
  const toX = brush?.toX ?? ((v: number) => v);
  const winLo = brush ? toX(brush.value[0]) : (xd?.lo ?? 0);
  const winHi = brush ? toX(brush.value[1]) : (xd?.hi ?? 1);
  const baseX: [number, number] = [Math.min(winLo, winHi), Math.max(winLo, winHi)];

  const cz = useChartZoom(svgRef, {
    plotW: innerW, plotH: innerH, marginLeft: MARGIN.left, marginTop: MARGIN.top,
    autoScaleY, xBaseKey: `${baseX[0]},${baseX[1]}`,
  });
  const { zoom } = cz;

  // Scales: x = the brushed window, zoomed; y auto-fits the points inside the
  // x view (the base the Y center / Y fit policy rides on), then zoomed.
  const [vxLo, vxHi] = zoom.viewX(baseX);
  const yBase = inViewYDomain(series, vxLo, vxHi, zeroBaseline);
  const [vyLo, vyHi] = zoom.viewY([yBase.lo, yBase.hi]);
  const xScale = linearScale([vxLo, vxHi], [0, innerW]);
  const yScale = linearScale([vyLo, vyHi], [innerH, 0]);

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => cz.beginDrag(e);
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    // Crosshair rides the same handler (hover-only, hidden while panning).
    if (cz.dragMove(e)) {
      setCrossLinked(null);
      return;
    }
    setCrossLinked(
      crosshairPoint(e.clientX, e.clientY, svg.getBoundingClientRect(), MARGIN,
        innerW, innerH, xScale.invert, yScale.invert),
    );
  };
  const onPointerUp = () => cz.endDrag();
  const onPointerLeave = () => {
    cz.cancelDrag();
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

  const ready = size.width > 0 && size.height > 0 && xd !== null;
  const xTicks = ready ? niceTicks(Math.min(vxLo, vxHi), Math.max(vxLo, vxHi), 6) : [];
  const yTicks = ready ? niceTicks(Math.min(vyLo, vyHi), Math.max(vyLo, vyHi), 5) : [];
  const px = (x: number) => xScale.map(x);
  const py = (y: number) => yScale.map(y);

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div ref={ref} className="relative min-h-0 flex-1">
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
                      {formatY(t)}
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
                    const d = negativeFillPath(s, px, py);
                    return d !== "" ? (
                      <path key={`${s.label}·neg`} d={d} fill="rgb(244 63 94 / 0.22)" stroke="none" />
                    ) : null;
                  })}
                {/* Curves, near→far (the linked curve reads bolder) */}
                {series.map((s, i) => (
                  <path key={s.label} d={seriesPath(s, px, py)} fill="none" stroke={s.color} strokeDasharray={s.dash}
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
                      <circle cx={xScale.map(m.x)} cy={yScale.map(m.y)} r={4.5}
                        fill="rgb(244 63 94 / 0.15)" stroke={m.color ?? EVIDENCE_ROSE} strokeWidth={1.75}>
                        <title>{m.label}</title>
                      </circle>
                      <circle cx={xScale.map(m.x)} cy={yScale.map(m.y)} r={1.4} fill={m.color ?? EVIDENCE_ROSE} pointerEvents="none" />
                    </g>
                  ))}
              </g>

              {/* Crosshair guides (hover-only) */}
              {cross !== null && <CrosshairGuides point={cross} plotW={innerW} plotH={innerH} />}

              {/* Axis titles: x at the axis's right end, y rotated along the
                  y-axis (the plot's top-left corner belongs to the Y buttons) */}
              <text x={innerW} y={innerH + 30} textAnchor="end" className="fill-slate-600 text-[10px]">
                {xLabel}
              </text>
              <text transform={`translate(${-MARGIN.left + 10},${innerH / 2}) rotate(-90)`} textAnchor="middle"
                className="fill-slate-600 text-[10px]">
                {yLabel}
              </text>

              {/* Legend (maturity-graded) */}
              <g transform={`translate(${innerW - 4},6)`}>
                {series.map((s, i) => (
                  <g key={s.label} transform={`translate(0,${i * 14})`}>
                    <line x1={-26} x2={-12} y1={0} y2={0} stroke={s.color} strokeWidth={2} strokeDasharray={s.dash} />
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
          <CrosshairBadge label={crosshairLabel(cross, formatX, formatHoverY ?? formatY)} />
        )}

        <ZoomOverlay autoScaleY={autoScaleY} onToggleAutoScale={onToggleAutoScale}
          zoomed={zoom.zoomed} onReset={zoom.reset} left={MARGIN.left} />
      </div>

      {/* Coarse x-window brush (display units, or the caller's units) */}
      {brush !== null && (
        <div className="mt-2 shrink-0 px-1">
          <RangeBrush min={brush.min} max={brush.max} value={brush.value} onChange={brush.onChange}
            format={brush.format ?? formatX} />
        </div>
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

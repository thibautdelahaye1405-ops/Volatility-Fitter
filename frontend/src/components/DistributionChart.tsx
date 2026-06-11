// Fitted risk-neutral distribution chart for the Smile Viewer: either the
// density pdf(x) over log-returns x = ln(S_T / F), or the quantile function
// Q(u) over probabilities u in [0, 1]. Hand-rolled SVG following the
// SmileChart conventions (grid, crosshair, hover badge) minus the brush —
// the backend's full grid is always shown.
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import type { DistributionCurve } from "../state/useScenario";
import { clamp, formatAxisNumber, linearScale, niceTicks } from "../lib/chartScale";

interface DistributionChartProps {
  kind: "density" | "quantile";
  current: DistributionCurve;
  /** Saved prior's distribution, drawn dashed for comparison (optional). */
  prior: DistributionCurve | null;
}

/** One plottable series extracted from a distribution payload. */
interface Series {
  xs: number[];
  ys: number[];
}

const MARGIN = { top: 14, right: 14, bottom: 30, left: 52 } as const;

/** Track the pixel size of a container element (same as SmileChart's). */
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

/** Pull the (xs, ys) series matching the requested view from a payload. */
function seriesOf(curve: DistributionCurve, kind: "density" | "quantile"): Series {
  return kind === "density"
    ? { xs: curve.x, ys: curve.density }
    : { xs: curve.u, ys: curve.quantile };
}

/** Linear interpolation of ys over an ascending xs grid at position x. */
function interpAt(xs: number[], ys: number[], x: number): number | null {
  const n = Math.min(xs.length, ys.length);
  if (n === 0) return null;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[n - 1]) return ys[n - 1];
  for (let i = 1; i < n; i++) {
    if (x <= xs[i]) {
      const t = (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
      return ys[i - 1] + t * (ys[i] - ys[i - 1]);
    }
  }
  return ys[n - 1];
}

export default function DistributionChart({
  kind,
  current,
  prior,
}: DistributionChartProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  /** Hover position in x-domain units, or null when outside the plot. */
  const [hoverXv, setHoverXv] = useState<number | null>(null);

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  const cur = useMemo(() => seriesOf(current, kind), [current, kind]);
  const pri = useMemo(
    () => (prior !== null ? seriesOf(prior, kind) : null),
    [prior, kind],
  );

  // Domains: density spans the union of the x grids with the pdf anchored
  // at zero; quantile spans u in [0, 1] with a padded Q extent.
  const { xScale, yScale } = useMemo(() => {
    let xMin = Infinity, xMax = -Infinity;
    let yMin = Infinity, yMax = -Infinity;
    for (const s of pri !== null ? [cur, pri] : [cur]) {
      for (const v of s.xs) { xMin = Math.min(xMin, v); xMax = Math.max(xMax, v); }
      for (const v of s.ys) { yMin = Math.min(yMin, v); yMax = Math.max(yMax, v); }
    }
    if (!Number.isFinite(xMin)) { xMin = 0; xMax = 1; yMin = 0; yMax = 1; }
    if (kind === "quantile") { xMin = 0; xMax = 1; }
    const pad = Math.max(1e-9, (yMax - yMin) * 0.08);
    const yLo = kind === "density" ? 0 : yMin - pad; // pdf is anchored at 0
    return {
      xScale: linearScale([xMin, xMax], [0, plotW]),
      yScale: linearScale([yLo, yMax + pad], [plotH, 0]),
    };
  }, [cur, pri, kind, plotW, plotH]);

  /** Build an SVG polyline path for a series. */
  const pathOf = (s: Series): string => {
    let d = "";
    const n = Math.min(s.xs.length, s.ys.length);
    for (let i = 0; i < n; i++) {
      const x = xScale.map(s.xs[i]).toFixed(2);
      const y = yScale.map(s.ys[i]).toFixed(2);
      d += d === "" ? `M${x},${y}` : `L${x},${y}`;
    }
    return d;
  };
  const curPath = useMemo(() => pathOf(cur), [cur, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const priPath = useMemo(() => (pri !== null ? pathOf(pri) : ""), [pri, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps

  // Density only: soft area fill under the current pdf down to zero.
  const curArea = useMemo(() => {
    if (kind !== "density" || curPath === "" || cur.xs.length === 0) return "";
    const y0 = yScale.map(0).toFixed(2);
    const x0 = xScale.map(cur.xs[0]).toFixed(2);
    const x1 = xScale.map(cur.xs[cur.xs.length - 1]).toFixed(2);
    return `${curPath}L${x1},${y0}L${x0},${y0}Z`;
  }, [kind, curPath, cur, xScale, yScale]);

  const xTicks = niceTicks(xScale.domain[0], xScale.domain[1], 8);
  const yTicks = niceTicks(yScale.domain[0], yScale.domain[1], 6);

  /* ---------------- crosshair ---------------- */

  const onMouseMove = (e: ReactMouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = e.clientX - rect.left - MARGIN.left;
    if (px < 0 || px > plotW) { setHoverXv(null); return; }
    setHoverXv(clamp(xScale.invert(px), xScale.domain[0], xScale.domain[1]));
  };

  const hoverYv = hoverXv !== null ? interpAt(cur.xs, cur.ys, hoverXv) : null;
  const hoverPx = hoverXv !== null ? xScale.map(hoverXv) : 0;
  const hoverLabel =
    hoverXv !== null && hoverYv !== null
      ? kind === "density"
        ? `x ${hoverXv.toFixed(3)} · pdf ${formatAxisNumber(hoverYv)}`
        : `u ${hoverXv.toFixed(2)} · Q ${hoverYv.toFixed(3)}`
      : null;

  /* ---------------- render ---------------- */

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend */}
      <div className="mb-1 flex shrink-0 items-center gap-5 px-1 text-[11px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 rounded bg-accent-400" /> Current fit
        </span>
        {pri !== null && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dashed border-slate-500" /> Prior
          </span>
        )}
        <span className="ml-auto font-mono text-slate-500">
          {kind === "density" ? "pdf of x = ln(S_T / F)" : "Q(u): quantile of x"}
        </span>
      </div>

      {/* Plot area (measured for responsive SVG) */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {size.width > 0 && size.height > 0 && (
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            className="absolute inset-0 cursor-crosshair"
            onMouseMove={onMouseMove}
            onMouseLeave={() => setHoverXv(null)}
          >
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {/* Gridlines */}
              {yTicks.map((t) => (
                <line key={`gy${t}`} x1={0} x2={plotW} y1={yScale.map(t)} y2={yScale.map(t)}
                  stroke="rgb(255 255 255 / 0.05)" />
              ))}
              {xTicks.map((t) => (
                <line key={`gx${t}`} x1={xScale.map(t)} x2={xScale.map(t)} y1={0} y2={plotH}
                  stroke="rgb(255 255 255 / 0.04)" />
              ))}

              {/* Reference line: x = 0 (forward) / u = 0.5 (median) */}
              {(() => {
                const refX = kind === "density" ? 0 : 0.5;
                if (refX < xScale.domain[0] || refX > xScale.domain[1]) return null;
                return (
                  <line x1={xScale.map(refX)} x2={xScale.map(refX)} y1={0} y2={plotH}
                    stroke="rgb(148 163 184 / 0.25)" strokeDasharray="2 4" />
                );
              })()}

              {/* Axes labels */}
              {yTicks.map((t) => (
                <text key={`ly${t}`} x={-8} y={yScale.map(t)} dy="0.32em" textAnchor="end"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatAxisNumber(t)}
                </text>
              ))}
              {xTicks.map((t) => (
                <text key={`lx${t}`} x={xScale.map(t)} y={plotH + 16} textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatAxisNumber(t)}
                </text>
              ))}

              {/* Density only: soft fill under the current pdf */}
              {curArea !== "" && (
                <path d={curArea} fill="var(--color-accent-400)" opacity={0.07} />
              )}

              {/* Prior: dashed slate */}
              {priPath !== "" && (
                <path d={priPath} fill="none" stroke="rgb(100 116 139 / 0.9)"
                  strokeWidth={1.5} strokeDasharray="5 4" />
              )}

              {/* Current fit: accent */}
              <path d={curPath} fill="none" stroke="var(--color-accent-400)"
                strokeWidth={2} strokeLinejoin="round" />

              {/* Crosshair: vertical guide + marker on the current curve */}
              {hoverXv !== null && hoverYv !== null && (
                <g pointerEvents="none">
                  <line x1={hoverPx} x2={hoverPx} y1={0} y2={plotH}
                    stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                  <circle cx={hoverPx} cy={yScale.map(hoverYv)} r={3.5}
                    fill="var(--color-accent-400)" stroke="#0e131c" strokeWidth={1.5} />
                </g>
              )}
            </g>
          </svg>
        )}

        {/* Tooltip readout badge (top-right corner) */}
        {hoverLabel && (
          <div className="pointer-events-none absolute top-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1 font-mono text-[11px] text-slate-200 shadow-lg shadow-black/40">
            {hoverLabel}
          </div>
        )}
      </div>
    </div>
  );
}

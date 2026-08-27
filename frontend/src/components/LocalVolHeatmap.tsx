// Nodal local-volatility heatmap for the Local Vol workspace.
//
// Renders the calibrated piecewise-affine surface as a vertex matrix: one
// cell per (t-node, x-node) vertex, coloured by local vol on the shared vol
// colormap (lib/volColormap — the same ramp as the 3D SurfaceMesh). Rows are
// vertex maturities (t = 0 at top), columns vertex strikes x = K/F. Hovering
// a cell reveals its exact (t, x, σ) and publishes the point on the linked
// hover store (wave 3, B2: k = ln x), so the 3D meshes / overlays of the same
// ticker show the matching crosshair — and a point published elsewhere
// highlights the matching cell here. Pure SVG, no chart deps.
import { useState } from "react";
import { formatPct } from "../lib/chartScale";
import { useElementSize } from "../lib/useElementSize";
import { VOL_GRADIENT_CSS, volColor } from "../lib/volColormap";
import { nearestGridPoint, useSurfaceHover } from "../state/surfaceHover";

interface LocalVolHeatmapProps {
  tNodes: number[];
  xNodes: number[];
  /** value[i][j] at (tNodes[i], xNodes[j]) — local vol, or reconstructed IV. */
  localVol: number[][];
  /** Legend caption (defaults to the local-vol surface; the IV surface
   *  sub-tab passes its own). */
  legendLabel?: string;
  /** Hover/legend count caption suffix (e.g. "vertices" vs "cells"). */
  cellLabel?: string;
  /** Linked hover: the ticker + this chart's id. */
  ticker?: string;
  chartId?: string;
}

const MARGIN = { top: 8, right: 10, bottom: 26, left: 38 };

export default function LocalVolHeatmap({
  tNodes,
  xNodes,
  localVol,
  legendLabel = "σ_loc(t, x)",
  cellLabel = "vertices",
  ticker = "",
  chartId = "lv-heatmap",
}: LocalVolHeatmapProps) {
  const { ref, size } = useElementSize();
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null);
  const link = useSurfaceHover(chartId);

  const nT = tNodes.length;
  const nX = xNodes.length;
  const flat = localVol.flat();
  const vMin = flat.length ? Math.min(...flat) : 0;
  const vMax = flat.length ? Math.max(...flat) : 1;
  const vSpan = vMax - vMin || 1;

  // A point published by another chart of this ticker → the matching cell.
  const linked =
    hover === null && link.hover !== null && link.hover.source !== chartId && link.hover.ticker === ticker
      ? nearestGridPoint(xNodes.map((x) => Math.log(x)), tNodes, link.hover.k, link.hover.t)
      : null;
  const shown = hover ?? linked;

  const enter = (i: number, j: number) => {
    setHover({ i, j });
    link.publish({ ticker, k: Math.log(xNodes[j]), t: tNodes[i] });
  };
  const leave = () => {
    setHover(null);
    link.publish(null);
  };

  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);
  const cw = nX > 0 ? plotW / nX : 0;
  const ch = nT > 0 ? plotH / nT : 0;

  // Label strides: keep ~8 labels per axis at most.
  const xStride = Math.max(1, Math.ceil(nX / 8));
  const tStride = Math.max(1, Math.ceil(nT / 8));

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend */}
      <div className="mb-1 flex shrink-0 items-center gap-3 px-1 text-[11px] text-slate-400">
        <span className="font-mono text-slate-500">{legendLabel}</span>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
          {formatPct(vMin)}
          <span className="h-2 w-24 rounded" style={{ background: VOL_GRADIENT_CSS }} />
          {formatPct(vMax)}
        </span>
        <span className="text-[10px] text-slate-500">
          {nT}×{nX} {cellLabel}
        </span>
        <span className={`ml-auto font-mono text-[10px] ${hover ? "text-slate-300" : "text-slate-500"}`}>
          {shown
            ? `t ${tNodes[shown.i].toFixed(2)}y · x ${xNodes[shown.j].toFixed(2)} · ${formatPct(
                localVol[shown.i][shown.j],
              )}${hover ? "" : " (linked)"}`
            : "hover a cell"}
        </span>
      </div>

      {/* Matrix */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {plotW > 0 && plotH > 0 && (
          <svg width={size.width} height={size.height} className="absolute inset-0" onMouseLeave={leave}>
            {localVol.map((row, i) =>
              row.map((v, j) => {
                const active = shown?.i === i && shown?.j === j;
                return (
                  <rect
                    key={`${i}-${j}`}
                    x={MARGIN.left + j * cw}
                    y={MARGIN.top + i * ch}
                    width={cw + 0.5}
                    height={ch + 0.5}
                    fill={volColor((v - vMin) / vSpan)}
                    stroke={active ? (hover ? "rgb(226 232 240)" : "rgb(56 189 248)") : "rgb(15 23 42 / 0.35)"}
                    strokeWidth={active ? 1.5 : 0.5}
                    onMouseEnter={() => enter(i, j)}
                  />
                );
              }),
            )}

            {/* Strike (x) axis labels */}
            {xNodes.map((x, j) =>
              j % xStride === 0 ? (
                <text
                  key={`x-${j}`}
                  x={MARGIN.left + (j + 0.5) * cw}
                  y={size.height - 14}
                  textAnchor="middle"
                  className="fill-slate-500 font-mono text-[9px]"
                >
                  {x.toFixed(2)}
                </text>
              ) : null,
            )}
            <text
              x={MARGIN.left + plotW / 2}
              y={size.height - 2}
              textAnchor="middle"
              className="fill-slate-600 font-mono text-[9px]"
            >
              x = K/F
            </text>

            {/* Maturity (t) axis labels */}
            {tNodes.map((t, i) =>
              i % tStride === 0 ? (
                <text
                  key={`t-${i}`}
                  x={MARGIN.left - 5}
                  y={MARGIN.top + (i + 0.5) * ch + 3}
                  textAnchor="end"
                  className="fill-slate-500 font-mono text-[9px]"
                >
                  {t.toFixed(2)}
                </text>
              ) : null,
            )}
          </svg>
        )}
      </div>
    </div>
  );
}

// Nodal local-volatility heatmap for the Local Vol workspace.
//
// Renders the calibrated piecewise-affine surface as a vertex matrix: one
// cell per (t-node, x-node) vertex, coloured by local vol on a
// blue→cyan→amber→red map (the same ramp as the 3D SurfaceChart). Rows are
// vertex maturities (t = 0 at top), columns vertex strikes x = K/F. Hovering a
// cell reveals its exact (t, x, σ). Pure SVG, no chart deps.
import { useLayoutEffect, useRef, useState } from "react";
import { formatPct } from "../lib/chartScale";

interface LocalVolHeatmapProps {
  tNodes: number[];
  xNodes: number[];
  /** sqrt(nodal variance): localVol[i][j] at (tNodes[i], xNodes[j]). */
  localVol: number[][];
}

/** Colormap stops: blue → cyan → amber → red over the vol range. */
const STOPS: { u: number; rgb: [number, number, number] }[] = [
  { u: 0, rgb: [59, 130, 246] },
  { u: 0.34, rgb: [34, 211, 238] },
  { u: 0.67, rgb: [251, 191, 36] },
  { u: 1, rgb: [239, 68, 68] },
];

/** Piecewise-linear colormap lookup, u in [0, 1]. */
function volColor(u: number): string {
  const x = Math.min(1, Math.max(0, u));
  for (let i = 1; i < STOPS.length; i++) {
    if (x <= STOPS[i].u) {
      const a = STOPS[i - 1];
      const b = STOPS[i];
      const f = (x - a.u) / (b.u - a.u);
      const c = a.rgb.map((v, j) => Math.round(v + f * (b.rgb[j] - v)));
      return `rgb(${c[0]} ${c[1]} ${c[2]})`;
    }
  }
  return "rgb(239 68 68)";
}

/** Track the pixel size of a container element. */
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

const MARGIN = { top: 8, right: 10, bottom: 26, left: 38 };

export default function LocalVolHeatmap({ tNodes, xNodes, localVol }: LocalVolHeatmapProps) {
  const { ref, size } = useElementSize();
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null);

  const nT = tNodes.length;
  const nX = xNodes.length;
  const flat = localVol.flat();
  const vMin = flat.length ? Math.min(...flat) : 0;
  const vMax = flat.length ? Math.max(...flat) : 1;
  const vSpan = vMax - vMin || 1;

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
        <span className="font-mono text-slate-500">σ_loc(t, x)</span>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
          {formatPct(vMin)}
          <span
            className="h-2 w-24 rounded"
            style={{
              background:
                "linear-gradient(90deg, rgb(59 130 246), rgb(34 211 238), rgb(251 191 36), rgb(239 68 68))",
            }}
          />
          {formatPct(vMax)}
        </span>
        <span className="text-[10px] text-slate-500">
          {nT}×{nX} vertices
        </span>
        <span className="ml-auto font-mono text-[10px] text-slate-300">
          {hover
            ? `t ${tNodes[hover.i].toFixed(2)}y · x ${xNodes[hover.j].toFixed(2)} · ${formatPct(
                localVol[hover.i][hover.j],
              )}`
            : "hover a cell"}
        </span>
      </div>

      {/* Matrix */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {plotW > 0 && plotH > 0 && (
          <svg width={size.width} height={size.height} className="absolute inset-0">
            {localVol.map((row, i) =>
              row.map((v, j) => {
                const active = hover?.i === i && hover?.j === j;
                return (
                  <rect
                    key={`${i}-${j}`}
                    x={MARGIN.left + j * cw}
                    y={MARGIN.top + i * ch}
                    width={cw + 0.5}
                    height={ch + 0.5}
                    fill={volColor((v - vMin) / vSpan)}
                    stroke={active ? "rgb(226 232 240)" : "rgb(15 23 42 / 0.35)"}
                    strokeWidth={active ? 1.5 : 0.5}
                    onMouseEnter={() => setHover({ i, j })}
                    onMouseLeave={() => setHover(null)}
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

// Smile-universe graph chart. Hand-rolled SVG, no chart deps.
// The universe is a structured ticker × expiry lattice, not a free-form
// graph, so nodes are laid out on a grid: one column per ticker, one row
// per expiry (ordered by year-fraction). Edges communicate the propagation
// topology: strong vertical calendar chains within a ticker, faint
// horizontal links between same-expiry nodes of adjacent tickers.
//
// Node states:
//   dark            slate fill, subtle border (no information yet)
//   lit (observed)  amber ring + glow, carries a user dAtmVol observation
//   solved          fill on a diverging blue -> slate -> red scale from the
//                   posterior shift (bp), plus an outer halo whose radius /
//                   fade encode the posterior sd (bigger + fainter = more
//                   uncertain). Lit nodes keep the amber ring on top.
import { useMemo, useRef, useState } from "react";
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import { nodeKey } from "../state/useGraph";
import { clamp, formatPct } from "../lib/chartScale";

interface GraphChartProps {
  nodes: GraphNodeBase[];
  /** Lit nodes: key -> dAtmVol observation (decimal vol). */
  lit: Record<string, number>;
  /** Posterior nodes keyed like `lit`, or null before the first solve. */
  results: Record<string, GraphSolveNode> | null;
  /** Single click: light/dim a node. */
  onToggle: (key: string) => void;
  /** Lasso: light every node enclosed by a drag-rectangle on the background. */
  onLasso: (keys: string[]) => void;
  /** Double click: drill into the node's smile. */
  onOpenSmile: (ticker: string, expiry: string) => void;
}

/** Drag distance (px) below which a background press counts as a click, not a
 *  lasso — keeps an accidental 1–2px drag from selecting nothing/everything. */
const LASSO_MIN_DRAG = 4;

/** An in-progress lasso rectangle, in SVG user coordinates. */
interface LassoBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

// Grid geometry. Written generically: any number of tickers / expiries;
// the parent provides a scroll container when the lattice outgrows it.
const MARGIN = { top: 44, right: 28, bottom: 20, left: 122 } as const;
const COL_W = 150;
const ROW_H = 92;
const NODE_R = 16;
/** Maximum extra halo radius for the most uncertain node. */
const HALO_MAX = 14;

/* ---------------- diverging shift colour scale ---------------- */

type Rgb = readonly [number, number, number];
const NEG: Rgb = [59, 130, 246]; // blue-500: vols marked down
const MID: Rgb = [71, 85, 105]; //  slate-600: no shift
const POS: Rgb = [239, 68, 68]; //  red-500: vols marked up

/**
 * Map a posterior shift (bp) to a colour: blue -> slate -> red, clamped at
 * ±maxAbs (the largest |shift| of the current solve). Plain RGB lerp.
 */
function shiftColor(shiftBp: number, maxAbs: number): string {
  const t = maxAbs > 0 ? clamp(shiftBp / maxAbs, -1, 1) : 0;
  const end = t < 0 ? NEG : POS;
  const a = Math.abs(t);
  const ch = (i: number) => Math.round(MID[i] + (end[i] - MID[i]) * a);
  return `rgb(${ch(0)} ${ch(1)} ${ch(2)})`;
}

/** Signed basis-point label, e.g. "+12.3 bp". */
function formatBp(bp: number): string {
  return `${bp >= 0 ? "+" : ""}${bp.toFixed(1)} bp`;
}

export default function GraphChart({
  nodes,
  lit,
  results,
  onToggle,
  onLasso,
  onOpenSmile,
}: GraphChartProps) {
  /** Key of the hovered node, for the tooltip readout. */
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  /** Live lasso rectangle while dragging on the background, else null. */
  const [lasso, setLasso] = useState<LassoBox | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Derive the lattice: ticker columns (order of first appearance) and
  // expiry rows (sorted by year-fraction), then pin every node to a cell.
  const layout = useMemo(() => {
    const tickers: string[] = [];
    const rowByExpiry = new Map<string, { expiry: string; t: number }>();
    for (const n of nodes) {
      if (!tickers.includes(n.ticker)) tickers.push(n.ticker);
      if (!rowByExpiry.has(n.expiry))
        rowByExpiry.set(n.expiry, { expiry: n.expiry, t: n.t });
    }
    const rows = [...rowByExpiry.values()].sort((a, b) => a.t - b.t);

    const colX = (c: number) => MARGIN.left + (c + 0.5) * COL_W;
    const rowY = (r: number) => MARGIN.top + (r + 0.5) * ROW_H;
    const pos = new Map<string, { x: number; y: number }>();
    // Per-ticker calendar chains (nodes sorted by t) for the vertical edges.
    const chains = new Map<string, GraphNodeBase[]>();
    for (const n of nodes) {
      const c = tickers.indexOf(n.ticker);
      const r = rows.findIndex((row) => row.expiry === n.expiry);
      pos.set(nodeKey(n.ticker, n.expiry), { x: colX(c), y: rowY(r) });
      const chain = chains.get(n.ticker) ?? [];
      chain.push(n);
      chains.set(n.ticker, chain);
    }
    for (const chain of chains.values()) chain.sort((a, b) => a.t - b.t);

    return {
      tickers,
      rows,
      pos,
      chains,
      colX,
      width: MARGIN.left + tickers.length * COL_W + MARGIN.right,
      height: MARGIN.top + rows.length * ROW_H + MARGIN.bottom,
    };
  }, [nodes]);

  // Solve-wide normalisers: colours clamp at max |shift|, halos at max sd.
  const { maxAbsShift, maxSd } = useMemo(() => {
    let shift = 0;
    let sd = 0;
    for (const r of Object.values(results ?? {})) {
      shift = Math.max(shift, Math.abs(r.shiftBp));
      sd = Math.max(sd, r.sd);
    }
    return { maxAbsShift: shift, maxSd: sd };
  }, [results]);

  const hoverNode = hoverKey !== null
    ? nodes.find((n) => nodeKey(n.ticker, n.expiry) === hoverKey)
    : undefined;
  const hoverPos = hoverKey !== null ? layout.pos.get(hoverKey) : undefined;
  const hoverResult = hoverKey !== null ? results?.[hoverKey] : undefined;

  /* ------------------------- lasso selection ------------------------- */
  // The SVG box maps 1:1 to user units (width/height = intrinsic size, no
  // viewBox), so a viewport delta from its bounding rect is an SVG coordinate.
  const svgPoint = (e: React.MouseEvent): { x: number; y: number } => {
    const rect = svgRef.current?.getBoundingClientRect();
    return rect ? { x: e.clientX - rect.left, y: e.clientY - rect.top } : { x: 0, y: 0 };
  };

  const startLasso = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // left button only; nodes stop propagation
    const { x, y } = svgPoint(e);
    setLasso({ x0: x, y0: y, x1: x, y1: y });
  };

  const moveLasso = (e: React.MouseEvent) => {
    if (lasso === null) return;
    const { x, y } = svgPoint(e);
    setLasso((prev) => (prev ? { ...prev, x1: x, y1: y } : prev));
  };

  const endLasso = () => {
    if (lasso === null) return;
    const box = lasso;
    setLasso(null);
    if (Math.abs(box.x1 - box.x0) < LASSO_MIN_DRAG && Math.abs(box.y1 - box.y0) < LASSO_MIN_DRAG)
      return; // a background click, not a drag-select
    const loX = Math.min(box.x0, box.x1);
    const hiX = Math.max(box.x0, box.x1);
    const loY = Math.min(box.y0, box.y1);
    const hiY = Math.max(box.y0, box.y1);
    const keys = nodes
      .map((n) => nodeKey(n.ticker, n.expiry))
      .filter((key) => {
        const p = layout.pos.get(key);
        return p !== undefined && p.x >= loX && p.x <= hiX && p.y >= loY && p.y <= hiY;
      });
    if (keys.length > 0) onLasso(keys);
  };

  return (
    // Scrollable viewport; the inner div is sized to the lattice so the
    // tooltip (absolute) tracks node coordinates even when scrolled.
    <div className="h-full overflow-auto">
      <div
        className="relative"
        style={{ width: layout.width, height: layout.height }}
      >
        <svg
          ref={svgRef}
          width={layout.width}
          height={layout.height}
          onMouseDown={startLasso}
          onMouseMove={moveLasso}
          onMouseUp={endLasso}
          onMouseLeave={endLasso}
          className={lasso ? "select-none" : undefined}
        >
          {/* Column headers: one per ticker */}
          {layout.tickers.map((t, c) => (
            <text
              key={t}
              x={layout.colX(c)}
              y={22}
              textAnchor="middle"
              className="fill-slate-300 text-[11px] font-semibold tracking-wide"
            >
              {t}
            </text>
          ))}

          {/* Row labels: expiry date + year-fraction */}
          {layout.rows.map((row, r) => (
            <g key={row.expiry}>
              <text
                x={MARGIN.left - 14}
                y={MARGIN.top + (r + 0.5) * ROW_H - 2}
                textAnchor="end"
                className="fill-slate-400 font-mono text-[10px]"
              >
                {row.expiry}
              </text>
              <text
                x={MARGIN.left - 14}
                y={MARGIN.top + (r + 0.5) * ROW_H + 11}
                textAnchor="end"
                className="fill-slate-600 font-mono text-[9px]"
              >
                T={row.t.toFixed(2)}y
              </text>
            </g>
          ))}

          {/* Edges (under the nodes). Calendar chains: strong; cross-ticker
              same-expiry links between adjacent columns: faint. */}
          <g stroke="rgb(148 163 184)">
            {[...layout.chains.values()].flatMap((chain) =>
              chain.slice(1).map((n, i) => {
                const a = layout.pos.get(nodeKey(chain[i].ticker, chain[i].expiry));
                const b = layout.pos.get(nodeKey(n.ticker, n.expiry));
                if (!a || !b) return null;
                return (
                  <line
                    key={`cal-${n.ticker}-${n.expiry}`}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    strokeWidth={2} opacity={0.35}
                  />
                );
              }),
            )}
            {layout.tickers.slice(1).map((t, c) =>
              layout.rows.map((row) => {
                const a = layout.pos.get(nodeKey(layout.tickers[c], row.expiry));
                const b = layout.pos.get(nodeKey(t, row.expiry));
                if (!a || !b) return null;
                return (
                  <line
                    key={`x-${t}-${row.expiry}`}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    strokeWidth={1} opacity={0.12}
                  />
                );
              }),
            )}
          </g>

          {/* Nodes */}
          {nodes.map((n) => {
            const key = nodeKey(n.ticker, n.expiry);
            const p = layout.pos.get(key);
            if (!p) return null;
            const isLit = key in lit;
            const result = results?.[key];
            const fill = result ? shiftColor(result.shiftBp, maxAbsShift) : "var(--color-surface-700)";
            // Uncertainty halo: radius grows and fades with the posterior sd
            // (normalised by the solve's max sd, extra radius <= HALO_MAX).
            const sdFrac = result && maxSd > 0 ? clamp(result.sd / maxSd, 0, 1) : 0;
            // Centre label: lit pre-solve -> observation in vol pts;
            // post-solve -> posterior shift in whole bp.
            const label = result
              ? `${result.shiftBp >= 0 ? "+" : ""}${Math.round(result.shiftBp)}`
              : isLit
                ? `${(lit[key] ?? 0) >= 0 ? "+" : ""}${((lit[key] ?? 0) * 100).toFixed(1)}`
                : null;
            return (
              // Click toggles lit/dark; double-click opens the smile (the
              // two single clicks of a dblclick toggle twice, i.e. net
              // no-op, so drill-in never leaves a stray observation).
              <g
                key={key}
                className="cursor-pointer"
                // Stop the press from starting a background lasso so a plain
                // click still toggles this node.
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => onToggle(key)}
                onDoubleClick={() => onOpenSmile(n.ticker, n.expiry)}
                onMouseEnter={() => setHoverKey(key)}
                onMouseLeave={() => setHoverKey(null)}
              >
                {result && sdFrac > 0 && (
                  <circle
                    cx={p.x} cy={p.y}
                    r={NODE_R + sdFrac * HALO_MAX}
                    fill={fill}
                    opacity={0.3 - 0.18 * sdFrac}
                  />
                )}
                <circle
                  cx={p.x} cy={p.y} r={NODE_R}
                  fill={fill}
                  stroke={isLit ? "#fbbf24" : "rgb(148 163 184 / 0.35)"}
                  strokeWidth={isLit ? 2 : 1}
                  style={
                    isLit
                      ? { filter: "drop-shadow(0 0 6px rgb(251 191 36 / 0.55))" }
                      : undefined
                  }
                />
                {label !== null && (
                  <text
                    x={p.x} y={p.y} dy="0.34em" textAnchor="middle"
                    pointerEvents="none"
                    className={[
                      "font-mono text-[9px] font-medium",
                      result ? "fill-slate-100" : "fill-amber-300",
                    ].join(" ")}
                  >
                    {label}
                  </text>
                )}
              </g>
            );
          })}

          {/* Live lasso rectangle (drawn above nodes, ignores pointer) */}
          {lasso && (
            <rect
              x={Math.min(lasso.x0, lasso.x1)}
              y={Math.min(lasso.y0, lasso.y1)}
              width={Math.abs(lasso.x1 - lasso.x0)}
              height={Math.abs(lasso.y1 - lasso.y0)}
              fill="rgb(129 140 248 / 0.12)"
              stroke="rgb(129 140 248 / 0.9)"
              strokeWidth={1}
              strokeDasharray="4 3"
              pointerEvents="none"
            />
          )}
        </svg>

        {/* Hover readout: posterior detail after a solve, baseline handles
            before. Absolutely positioned next to the hovered node. */}
        {hoverNode && hoverPos && (
          <div
            className="pointer-events-none absolute z-10 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-slate-200 shadow-lg shadow-black/40"
            style={{ left: hoverPos.x + NODE_R + 8, top: hoverPos.y - 14 }}
          >
            <div className="font-semibold text-slate-100">
              {hoverNode.ticker} · {hoverNode.expiry}
              {hoverResult?.observed && (
                <span className="ml-2 rounded border border-amber-500/40 bg-amber-500/10 px-1 py-px text-[9px] font-semibold tracking-wider text-amber-400">
                  OBSERVED
                </span>
              )}
            </div>
            {hoverResult ? (
              <>
                <div>
                  {formatPct(hoverResult.baseAtmVol, 2)} →{" "}
                  {formatPct(hoverResult.postAtmVol, 2)}{" "}
                  <span style={{ color: shiftColor(hoverResult.shiftBp, maxAbsShift) }}>
                    {formatBp(hoverResult.shiftBp)}
                  </span>
                </div>
                <div className="text-slate-400">
                  ± band [{formatPct(hoverResult.bandLo, 2)},{" "}
                  {formatPct(hoverResult.bandHi, 2)}] · sd{" "}
                  {formatPct(hoverResult.sd, 2)}
                </div>
              </>
            ) : (
              <div className="text-slate-400">
                ATM {formatPct(hoverNode.atmVol, 2)} · skew{" "}
                {hoverNode.skew.toFixed(3)} · curv{" "}
                {hoverNode.curvature.toFixed(2)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

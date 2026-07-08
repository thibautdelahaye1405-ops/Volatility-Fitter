// Presentation helpers for GraphNetworkChart, split out to respect the
// 400-line file policy: pan/zoom fit, bundle Bézier geometry, node-key
// adjacency, arrowhead markers, and the two hover tooltips. Everything here
// is stateless — the chart owns all interaction state.
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import { nodeKey } from "../state/useGraph";
import { clamp, formatPct } from "../lib/chartScale";
import { shiftColor, formatBp } from "../lib/graphColor";
import type {
  BundleEdge,
  CalendarEdge,
  GraphLayout,
  LayoutEdgeIn,
} from "../lib/graphLayout";

export const NODE_R = 13;
/** Maximum extra halo radius for the most uncertain node. */
export const HALO_MAX = 12;
export const K_MIN = 0.35;
export const K_MAX = 3;
const FIT_PAD = 24;
export const SLATE_400 = "rgb(148 163 184)";

/** Pan/zoom: scene coords map to screen as (tx + k·x, ty + k·y). */
export interface Transform {
  k: number;
  tx: number;
  ty: number;
}
export interface Size {
  w: number;
  h: number;
}

/** Per-bundle geometry, precomputed once per layout (no hover-time work). */
export interface BundleGeo {
  b: BundleEdge;
  key: string; // "FROM→TO" — matches the nodeBundles adjacency sets
  d: string; // Bézier path
  width: number;
  mx: number; // curve midpoint (t = 0.5), anchors the hover tooltip
  my: number;
}

/** Fit the layout bbox (origin 0,0) into the container with FIT_PAD margins. */
export function fitTransform(size: Size, layout: GraphLayout): Transform {
  const w = Math.max(1, layout.width);
  const h = Math.max(1, layout.height);
  const k = clamp(
    Math.min((size.w - 2 * FIT_PAD) / w, (size.h - 2 * FIT_PAD) / h),
    K_MIN,
    K_MAX,
  );
  return { k, tx: (size.w - k * w) / 2, ty: (size.h - k * h) / 2 };
}

/** Bundle geometry: control point offset 12% of the chord length along the
 *  perpendicular (fixed side, so the arc is stable across re-renders). */
export function bundleGeometry(b: BundleEdge, maxLogW: number): BundleGeo {
  const dx = b.x2 - b.x1;
  const dy = b.y2 - b.y1;
  // Perpendicular offset of 0.12·len along (-dy, dx)/len simplifies to
  // (-0.12·dy, +0.12·dx) — no length needed.
  const cx = (b.x1 + b.x2) / 2 - 0.12 * dy;
  const cy = (b.y1 + b.y2) / 2 + 0.12 * dx;
  return {
    b,
    key: `${b.fromTicker}→${b.toTicker}`,
    d: `M ${b.x1} ${b.y1} Q ${cx} ${cy} ${b.x2} ${b.y2}`,
    width: 1 + 2.5 * (maxLogW > 0 ? Math.log1p(b.totalWeight) / maxLogW : 0),
    // Quadratic Bézier at t=0.5: (P0 + 2C + P2) / 4.
    mx: (b.x1 + 2 * cx + b.x2) / 4,
    my: (b.y1 + 2 * cy + b.y2) / 4,
  };
}

/** Node-key adjacency for hover focus: individual edges (both directions)
 *  plus own-pod calendar-spine neighbours; and, per node, the set of bundle
 *  keys (both orientations) its cross-ticker edges feed. */
export function buildAdjacency(
  edges: LayoutEdgeIn[],
  calendar: CalendarEdge[],
): { adj: Map<string, Set<string>>; nodeBundles: Map<string, Set<string>> } {
  const adj = new Map<string, Set<string>>();
  const nodeBundles = new Map<string, Set<string>>();
  const link = (m: Map<string, Set<string>>, k: string, v: string) => {
    const s = m.get(k) ?? new Set<string>();
    s.add(v);
    m.set(k, s);
  };
  for (const e of edges) {
    const from = nodeKey(e.fromTicker, e.fromExpiry);
    const to = nodeKey(e.toTicker, e.toExpiry);
    link(adj, from, to);
    link(adj, to, from);
    if (e.fromTicker !== e.toTicker) {
      // Register both orientations — the bundle's canonical key may be either.
      for (const bk of [`${e.fromTicker}→${e.toTicker}`, `${e.toTicker}→${e.fromTicker}`]) {
        link(nodeBundles, from, bk);
        link(nodeBundles, to, bk);
      }
    }
  }
  for (const c of calendar) {
    link(adj, nodeKey(c.ticker, c.fromExpiry), nodeKey(c.ticker, c.toExpiry));
    link(adj, nodeKey(c.ticker, c.toExpiry), nodeKey(c.ticker, c.fromExpiry));
  }
  return { adj, nodeBundles };
}

/** Small arrowhead marker (shared defs); auto-start-reverse flips at starts. */
export function ArrowMarker({ id, px }: { id: string; px: number }) {
  return (
    <marker
      id={id}
      viewBox="0 0 8 8"
      refX="7"
      refY="4"
      markerWidth={px}
      markerHeight={px}
      orient="auto-start-reverse"
    >
      <path d="M0 0L8 4L0 8Z" fill={SLATE_400} />
    </marker>
  );
}

/** Node hover readout: posterior detail after a solve, baseline handles
 *  before (same markup as the lattice GraphChart). Positioned at the node's
 *  SCREEN coordinates via the current pan/zoom transform. */
export function NodeTooltip({
  node,
  result,
  pos,
  t,
  maxAbsShift,
}: {
  node: GraphNodeBase;
  result: GraphSolveNode | undefined;
  pos: { x: number; y: number };
  t: Transform;
  maxAbsShift: number;
}) {
  return (
    <div
      className="pointer-events-none absolute z-10 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-slate-200 shadow-lg shadow-black/40"
      style={{
        left: t.tx + t.k * (pos.x + NODE_R) + 8,
        top: t.ty + t.k * pos.y - 14,
      }}
    >
      <div className="font-semibold text-slate-100">
        {node.ticker} · {node.expiry}
        {result?.observed && (
          <span className="ml-2 rounded border border-amber-500/40 bg-amber-500/10 px-1 py-px text-[9px] font-semibold tracking-wider text-amber-400">
            OBSERVED
          </span>
        )}
      </div>
      {result ? (
        <>
          <div>
            {formatPct(result.baseAtmVol, 2)} → {formatPct(result.postAtmVol, 2)}{" "}
            <span style={{ color: shiftColor(result.shiftBp, maxAbsShift) }}>
              {formatBp(result.shiftBp)}
            </span>
          </div>
          <div className="text-slate-400">
            ± band [{formatPct(result.bandLo, 2)}, {formatPct(result.bandHi, 2)}]
            · sd {formatPct(result.sd, 2)}
          </div>
        </>
      ) : (
        <div className="text-slate-400">
          ATM {formatPct(node.atmVol, 2)} · skew {node.skew.toFixed(3)} · curv{" "}
          {node.curvature.toFixed(2)}
        </div>
      )}
    </div>
  );
}

/** Bundle hover readout ("SPX ↔ NDX · 12 edges · Σw 24.0"), anchored at the
 *  Bézier midpoint in screen coordinates. */
export function BundleTooltip({ geo, t }: { geo: BundleGeo; t: Transform }) {
  return (
    <div
      className="pointer-events-none absolute z-10 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1.5 font-mono text-[11px] text-slate-200 shadow-lg shadow-black/40"
      style={{ left: t.tx + t.k * geo.mx + 10, top: t.ty + t.k * geo.my - 14 }}
    >
      {geo.b.fromTicker} {geo.b.bidirectional ? "↔" : "→"} {geo.b.toTicker} ·{" "}
      {geo.b.count} {geo.b.count === 1 ? "edge" : "edges"} · Σw{" "}
      {geo.b.totalWeight.toFixed(1)}
    </div>
  );
}

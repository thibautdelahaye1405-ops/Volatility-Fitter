// Geometry + state helpers for GraphNetworkChart, split out to respect the
// 400-line file policy: pan/zoom fit, bundle Bézier geometry, node-key
// adjacency, the reveal-wave state contract and its lit-node pulse style.
// Everything here is stateless — the chart owns all interaction state. The
// node layer lives in GraphNodeLayer.tsx, the arrows in GraphEdgeLayer.tsx and
// the hover readouts in GraphNetworkChart.tooltips.tsx (GRAPH ERGONOMICS ARC,
// E3 split).
import { nodeKey } from "../state/useGraph";
import { clamp } from "../lib/chartScale";
import type { BundleEdge, CalendarEdge, GraphLayout, LayoutEdgeIn } from "../lib/graphLayout";

export const NODE_R = 13;
/** Radius of a collapsed ticker pod's single node. */
export const COLLAPSED_R = 18;
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
  /** Control point (for the tangent-aware arrow heads). */
  cx: number;
  cy: number;
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

/** Zoom by factor `f` about the screen point (cx, cy). */
export function zoomAbout(prev: Transform, f: number, cx: number, cy: number): Transform {
  const k = clamp(prev.k * f, K_MIN, K_MAX);
  const s = k / prev.k; // keep the scene point under (cx, cy) fixed
  return { k, tx: cx - (cx - prev.tx) * s, ty: cy - (cy - prev.ty) * s };
}

/** Screen → scene coordinates under a transform. */
export function toScene(t: Transform, sx: number, sy: number): { x: number; y: number } {
  return { x: (sx - t.tx) / t.k, y: (sy - t.ty) / t.k };
}

/** Bundle geometry: control point offset 12% of the chord length along the
 *  perpendicular (fixed side, so the arc is stable across re-renders). */
export function bundleGeometry(b: BundleEdge): BundleGeo {
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
    cx,
    cy,
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

/** Reveal-wave state threaded from the viewer: real BFS hops (lib/graphWave)
 *  plus the paced timeline (state/useWaveTimeline). Absent = no gating. */
export interface WaveState {
  hopOf: Map<string, number>;
  revealedHop: number;
  animating: boolean;
  skip: () => void;
}

/** Hover-focus set: the hovered node + everything adjacent stays at full
 *  opacity; every other element dims (group opacity, multiplicative). */
export interface FocusSet {
  keep: Set<string>;
  tickers: Set<string>;
  bundles: Set<string>;
}

export function focusOf(
  hoverKey: string | null,
  adj: Map<string, Set<string>>,
  nodeBundles: Map<string, Set<string>>,
): FocusSet | null {
  if (hoverKey === null) return null;
  const keep = new Set<string>([hoverKey]);
  for (const k of adj.get(hoverKey) ?? []) keep.add(k);
  const tickers = new Set<string>();
  for (const k of keep) tickers.add(k.split("|")[0] ?? "");
  return { keep, tickers, bundles: nodeBundles.get(hoverKey) ?? new Set<string>() };
}

/** One-shot lit-node pulse for the reveal wave, scoped to this chart via a
 *  <style> in the svg defs (the house avoids global css edits). transform-box
 *  makes the scale run about each circle's own centre, not the svg origin. */
export function WavePulseStyle() {
  return (
    <style>{`
      @keyframes gnc-lit-pulse {
        0% { transform: scale(1); }
        45% { transform: scale(1.4); }
        100% { transform: scale(1); }
      }
      .gnc-lit-pulse {
        transform-box: fill-box;
        transform-origin: center;
        animation: gnc-lit-pulse 700ms ease-out 1;
      }
    `}</style>
  );
}

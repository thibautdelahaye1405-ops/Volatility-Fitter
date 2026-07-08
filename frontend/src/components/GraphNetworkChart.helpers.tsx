// Presentation helpers for GraphNetworkChart, split out to respect the
// 400-line file policy: pan/zoom fit, bundle Bézier geometry, node-key
// adjacency, arrowhead markers, the node layer (with its reveal-wave gating),
// and the two hover tooltips. Everything here is stateless — the chart owns
// all interaction state.
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

/** Reveal-wave state threaded from the viewer: real BFS hops (lib/graphWave)
 *  plus the paced timeline (state/useWaveTimeline). Absent = no gating. */
export interface WaveState {
  hopOf: Map<string, number>;
  revealedHop: number;
  animating: boolean;
  skip: () => void;
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

/** Node layer, extracted so the chart stays under the 400-line policy.
 *
 *  Reveal-wave gating: when `wave` is present, a node's posterior rendering
 *  (shift fill / bp label / sd halo) only applies once the wave has reached
 *  its BFS hop — until then it keeps the pre-solve look (slate fill, lit ring
 *  if lit). Fill and halo opacity move via style transitions (400 ms) so each
 *  hop ring blooms rather than pops; while the wave is animating, lit nodes
 *  carry the one-shot pulse class. */
export function GraphNodes({
  nodes,
  layout,
  lit,
  results,
  maxAbsShift,
  maxSd,
  focusKeep,
  wave,
  onToggle,
  onOpenSmile,
  onHover,
}: {
  nodes: GraphNodeBase[];
  layout: GraphLayout;
  lit: Record<string, number>;
  results: Record<string, GraphSolveNode> | null;
  maxAbsShift: number;
  maxSd: number;
  focusKeep: ReadonlySet<string> | null;
  wave: WaveState | undefined;
  onToggle: (key: string) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
  onHover: (key: string | null) => void;
}) {
  return (
    <>
      {nodes.map((n) => {
        const key = nodeKey(n.ticker, n.expiry);
        const p = layout.nodePos.get(key);
        if (!p) return null;
        const isLit = key in lit;
        // The posterior exists but stays hidden until the reveal wave reaches
        // this node's hop; until then the node keeps the pre-solve look.
        const raw = results?.[key];
        const revealed =
          wave === undefined || (wave.hopOf.get(key) ?? 0) <= wave.revealedHop;
        const result = revealed ? raw : undefined;
        const fill = result
          ? shiftColor(result.shiftBp, maxAbsShift)
          : "var(--color-surface-700)";
        // Uncertainty halo: radius grows and fades with the posterior sd
        // (normalised by the solve's max sd, extra radius <= HALO_MAX). Kept
        // mounted at opacity 0 pre-reveal so it fades in instead of popping.
        const sdFrac = raw && maxSd > 0 ? clamp(raw.sd / maxSd, 0, 1) : 0;
        // Centre label: lit pre-solve (or pre-reveal) -> observation in vol
        // pts; revealed -> posterior shift in whole bp.
        const label = result
          ? `${result.shiftBp >= 0 ? "+" : ""}${Math.round(result.shiftBp)}`
          : isLit
            ? `${(lit[key] ?? 0) >= 0 ? "+" : ""}${((lit[key] ?? 0) * 100).toFixed(1)}`
            : null;
        return (
          // Click toggles lit/dark; double-click opens the smile (the two
          // single clicks of a dblclick toggle twice, i.e. net no-op).
          <g
            key={key}
            className="cursor-pointer"
            opacity={focusKeep === null || focusKeep.has(key) ? 1 : 0.15}
            // Stop the press from starting a background pan so a plain
            // click still toggles this node.
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onToggle(key)}
            onDoubleClick={() => onOpenSmile(n.ticker, n.expiry)}
            onMouseEnter={() => onHover(key)}
            onMouseLeave={() => onHover(null)}
          >
            {raw && sdFrac > 0 && (
              <circle
                cx={p.x} cy={p.y}
                r={NODE_R + sdFrac * HALO_MAX}
                fill={shiftColor(raw.shiftBp, maxAbsShift)}
                style={{
                  opacity: revealed ? 0.3 - 0.18 * sdFrac : 0,
                  transition: "opacity 400ms ease-out",
                }}
              />
            )}
            <circle
              cx={p.x} cy={p.y} r={NODE_R}
              className={
                wave !== undefined && wave.animating && isLit
                  ? "gnc-lit-pulse"
                  : undefined
              }
              stroke={isLit ? "#fbbf24" : "rgb(148 163 184 / 0.35)"}
              strokeWidth={isLit ? 2 : 1}
              style={{
                fill,
                transition: "fill 400ms ease-out",
                ...(isLit
                  ? { filter: "drop-shadow(0 0 6px rgb(251 191 36 / 0.55))" }
                  : undefined),
              }}
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
            {/* Expiry shorthand beside the node (MM-DD of an ISO date) */}
            <text
              x={p.x + 17} y={p.y} dy="0.32em"
              pointerEvents="none"
              className="fill-slate-500 font-mono text-[8px]"
            >
              {n.expiry.slice(5)}
            </text>
          </g>
        );
      })}
    </>
  );
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

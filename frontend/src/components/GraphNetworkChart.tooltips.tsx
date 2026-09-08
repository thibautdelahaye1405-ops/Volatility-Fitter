// Hover readouts of the smile-universe canvas (GRAPH ERGONOMICS ARC, E3 —
// moved out of GraphNetworkChart.helpers): the node tooltip (posterior detail
// after a solve, baseline handles before; a collapsed pod's member count),
// the bundle tooltip (pair overview: relation count, Σp as a mean σ, mean β)
// and the relation tooltip (one arrow: informer → receiver · β · σ). All are
// positioned at SCREEN coordinates via the current pan/zoom transform and
// FLIP to the left of their anchor near the right edge, so they never cover
// the toolbar cluster (user report 2026-09-08).
import type { CSSProperties } from "react";
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import type { GraphLayout } from "../lib/graphLayout";
import type { RelationHover } from "./GraphEdgeLayer";
import { formatPct } from "../lib/chartScale";
import { fmtSigmaPts } from "../lib/precisionUnits";
import { shiftColor, formatBp } from "../lib/graphColor";
import { isCollapsedKey } from "../lib/graphCollapse";
import { nodeKey } from "../state/useGraph";
import { NODE_R, type BundleGeo, type Size, type Transform } from "./GraphNetworkChart.helpers";

const box =
  "pointer-events-none absolute z-10 max-w-72 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-slate-200 shadow-lg shadow-black/40";

/** Estimated readout width (px) — decides the flip side. */
const EST_WIDTH = 280;
/** Keep the toolbar column (right edge) clear. */
const TOOLBAR_CLEARANCE = 60;

/** Anchor a readout beside a scene point: to the right by default, to the
 *  LEFT when it would overflow the container's right edge (toolbar side). */
export function anchorStyle(
  x: number,
  y: number,
  t: Transform,
  bounds: Size | null,
  gap = 8,
): CSSProperties {
  const sx = t.tx + t.k * x;
  const sy = t.ty + t.k * y;
  const top = Math.max(2, sy - 14);
  if (bounds !== null && sx + gap + EST_WIDTH > bounds.w - TOOLBAR_CLEARANCE) {
    return { right: Math.max(2, bounds.w - sx + gap), top };
  }
  return { left: sx + gap, top };
}

export function NodeTooltip({
  node,
  result,
  pos,
  t,
  bounds,
  maxAbsShift,
  memberCount,
}: {
  node: GraphNodeBase;
  result: GraphSolveNode | undefined;
  pos: { x: number; y: number };
  t: Transform;
  bounds: Size | null;
  maxAbsShift: number;
  memberCount: number;
}) {
  const collapsed = isCollapsedKey(nodeKey(node.ticker, node.expiry));
  const r = collapsed ? NODE_R + 5 : NODE_R;
  const style = anchorStyle(pos.x + r, pos.y, t, bounds);
  // Flipped: measure from the node's LEFT edge instead of its right edge.
  if ("right" in style) Object.assign(style, anchorStyle(pos.x - r, pos.y, t, bounds));
  return (
    <div className={box} style={style}>
      <div className="font-semibold text-slate-100">
        {node.ticker}
        {collapsed ? (
          <span className="ml-1 text-slate-400">· {memberCount} expiries (collapsed)</span>
        ) : (
          <> · {node.expiry}</>
        )}
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
            {collapsed && <span className="text-slate-500"> (mean)</span>}
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
          {collapsed && " (means)"}
        </div>
      )}
      {collapsed && (
        <div className="text-[10px] text-slate-500">click the ticker label to expand</div>
      )}
    </div>
  );
}

/** Bundle hover readout ("SPX ↔ NDX · 12 relations · σ̄ 0.9 pt · β̄ 1.02"),
 *  anchored at the Bézier midpoint in screen coordinates. */
export function BundleTooltip({ geo, t, bounds }: { geo: BundleGeo; t: Transform; bounds: Size | null }) {
  const b = geo.b;
  const meanP = b.count > 0 ? b.totalWeight / b.count : 0;
  return (
    <div className={box} style={anchorStyle(geo.mx, geo.my, t, bounds, 10)}>
      {b.fromTicker} {b.bidirectional ? "↔" : "→"} {b.toTicker} ·{" "}
      {b.count} {b.count === 1 ? "relation" : "relations"} · σ̄ {fmtSigmaPts(meanP)} pt
      · β̄ {b.meanBeta.toFixed(2)}
      <div className="text-[10px] text-slate-500">click to expand · click an arrow to edit</div>
    </div>
  );
}

/** One-arrow readout: informer → receiver · β · σ (no solver context needed). */
export function RelationTooltip({
  label,
  beta,
  precision,
  x,
  y,
  t,
  bounds,
}: {
  label: string;
  beta: number;
  precision: number;
  x: number;
  y: number;
  t: Transform;
  bounds: Size | null;
}) {
  return (
    <div className={box} style={anchorStyle(x, y, t, bounds, 10)}>
      {label} · β {beta.toFixed(2)} · σ {fmtSigmaPts(precision)} pt
      <div className="text-[10px] text-slate-500">click to edit · Delete removes</div>
    </div>
  );
}

/** The three readouts, resolved from the chart's hover state. */
export function CanvasReadouts({
  hoverKey,
  nodes,
  layout,
  results,
  members,
  hoverBundle,
  hoverRelation,
  t,
  bounds,
  maxAbsShift,
}: {
  hoverKey: string | null;
  nodes: GraphNodeBase[];
  layout: GraphLayout;
  results: Record<string, GraphSolveNode> | null;
  members: Map<string, string[]>;
  hoverBundle: BundleGeo | null;
  hoverRelation: RelationHover | null;
  t: Transform;
  bounds: Size | null;
  maxAbsShift: number;
}) {
  const hoverNode = hoverKey !== null ? nodes.find((n) => nodeKey(n.ticker, n.expiry) === hoverKey) : undefined;
  const hoverPos = hoverKey !== null ? layout.nodePos.get(hoverKey) : undefined;
  return (
    <>
      {hoverNode && hoverPos && (
        <NodeTooltip
          node={hoverNode}
          result={results?.[hoverKey ?? ""]}
          pos={hoverPos}
          t={t}
          bounds={bounds}
          maxAbsShift={maxAbsShift}
          memberCount={members.get(hoverKey ?? "")?.length ?? 0}
        />
      )}
      {hoverBundle && hoverRelation === null && <BundleTooltip geo={hoverBundle} t={t} bounds={bounds} />}
      {hoverRelation && (
        <RelationTooltip
          label={hoverRelation.label}
          beta={hoverRelation.beta}
          precision={hoverRelation.precision}
          x={hoverRelation.x}
          y={hoverRelation.y}
          t={t}
          bounds={bounds}
        />
      )}
    </>
  );
}

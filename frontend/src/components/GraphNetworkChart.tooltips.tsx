// Hover readouts of the smile-universe canvas (GRAPH ERGONOMICS ARC, E3 —
// moved out of GraphNetworkChart.helpers): the node tooltip (posterior detail
// after a solve, baseline handles before; a collapsed pod's member count),
// the bundle tooltip (pair overview: relation count, Σp as a mean σ, mean β)
// and the relation tooltip (one arrow: informer → receiver · β · σ). All are
// positioned at SCREEN coordinates via the current pan/zoom transform.
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import { formatPct } from "../lib/chartScale";
import { fmtSigmaPts } from "../lib/precisionUnits";
import { shiftColor, formatBp } from "../lib/graphColor";
import { isCollapsedKey } from "../lib/graphCollapse";
import { nodeKey } from "../state/useGraph";
import { NODE_R, type BundleGeo, type Transform } from "./GraphNetworkChart.helpers";

const box =
  "pointer-events-none absolute z-10 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-slate-200 shadow-lg shadow-black/40";

export function NodeTooltip({
  node,
  result,
  pos,
  t,
  maxAbsShift,
  memberCount,
}: {
  node: GraphNodeBase;
  result: GraphSolveNode | undefined;
  pos: { x: number; y: number };
  t: Transform;
  maxAbsShift: number;
  memberCount: number;
}) {
  const collapsed = isCollapsedKey(nodeKey(node.ticker, node.expiry));
  return (
    <div
      className={box}
      style={{
        left: t.tx + t.k * (pos.x + NODE_R) + 8,
        top: t.ty + t.k * pos.y - 14,
      }}
    >
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
export function BundleTooltip({ geo, t }: { geo: BundleGeo; t: Transform }) {
  const b = geo.b;
  const meanP = b.count > 0 ? b.totalWeight / b.count : 0;
  return (
    <div
      className={box}
      style={{ left: t.tx + t.k * geo.mx + 10, top: t.ty + t.k * geo.my - 14 }}
    >
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
}: {
  label: string;
  beta: number;
  precision: number;
  x: number;
  y: number;
  t: Transform;
}) {
  return (
    <div className={box} style={{ left: t.tx + t.k * x + 10, top: t.ty + t.k * y - 14 }}>
      {label} · β {beta.toFixed(2)} · σ {fmtSigmaPts(precision)} pt
      <div className="text-[10px] text-slate-500">click to edit · Delete removes</div>
    </div>
  );
}

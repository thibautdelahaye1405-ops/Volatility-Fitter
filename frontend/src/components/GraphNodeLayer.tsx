// Node layer of the smile-universe canvas (GRAPH ERGONOMICS ARC, E3 — moved
// out of GraphNetworkChart.helpers).
//
// Node states (the visual language shared with the legacy lattice chart):
//   dark            slate fill, subtle border (no information yet)
//   lit (observed)  amber ring + glow, carries a user dAtmVol observation
//   solved          fill on the diverging blue → slate → red shift scale plus
//                   an outer halo whose radius / fade encode the posterior sd
//   collapsed pod   one larger dashed-ring node standing for a whole ticker
//                   (its aggregated shift / lit state, member count inside)
//   connect source  accent ring while a connect gesture is in flight
//
// Reveal-wave gating: with `wave`, a node's posterior rendering only applies
// once the wave has reached its BFS hop. Interaction is delegated upward: a
// mousedown / mouseup pair (for the connect gesture), click (toggle), double
// click (drill-in) and hover.
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import { nodeKey } from "../state/useGraph";
import { clamp } from "../lib/chartScale";
import { shiftColor } from "../lib/graphColor";
import { isCollapsedKey } from "../lib/graphCollapse";
import type { GraphLayout } from "../lib/graphLayout";
import { COLLAPSED_R, HALO_MAX, NODE_R, type WaveState } from "./GraphNetworkChart.helpers";

export interface GraphNodeLayerProps {
  nodes: GraphNodeBase[];
  layout: GraphLayout;
  lit: Record<string, number>;
  results: Record<string, GraphSolveNode> | null;
  maxAbsShift: number;
  maxSd: number;
  focusKeep: ReadonlySet<string> | null;
  wave: WaveState | undefined;
  /** Collapsed key → member keys (the count badge). */
  members: Map<string, string[]>;
  /** Source node of the connect gesture in flight, or null. */
  connectFrom: string | null;
  onToggle: (key: string) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
  onHover: (key: string | null) => void;
  onNodeMouseDown: (key: string, e: React.MouseEvent) => void;
  onNodeMouseUp: (key: string, e: React.MouseEvent) => void;
}

export default function GraphNodeLayer({
  nodes,
  layout,
  lit,
  results,
  maxAbsShift,
  maxSd,
  focusKeep,
  wave,
  members,
  connectFrom,
  onToggle,
  onOpenSmile,
  onHover,
  onNodeMouseDown,
  onNodeMouseUp,
}: GraphNodeLayerProps) {
  return (
    <>
      {nodes.map((n) => {
        const key = nodeKey(n.ticker, n.expiry);
        const p = layout.nodePos.get(key);
        if (!p) return null;
        const collapsed = isCollapsedKey(key);
        const r = collapsed ? COLLAPSED_R : NODE_R;
        const isLit = key in lit;
        const isSource = connectFrom === key;
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
        // Centre label: lit pre-solve (or pre-reveal) → observation in vol
        // pts; revealed → posterior shift in whole bp; collapsed idle → count.
        const count = members.get(key)?.length ?? 0;
        const label = result
          ? `${result.shiftBp >= 0 ? "+" : ""}${Math.round(result.shiftBp)}`
          : isLit
            ? `${(lit[key] ?? 0) >= 0 ? "+" : ""}${((lit[key] ?? 0) * 100).toFixed(1)}`
            : collapsed
              ? `${count}`
              : null;
        const stroke = isSource
          ? "var(--color-accent-400)"
          : isLit
            ? "#fbbf24"
            : "rgb(148 163 184 / 0.35)";
        return (
          <g
            key={key}
            className="cursor-pointer"
            opacity={focusKeep === null || focusKeep.has(key) ? 1 : 0.15}
            data-node={key}
            onMouseDown={(e) => onNodeMouseDown(key, e)}
            onMouseUp={(e) => onNodeMouseUp(key, e)}
            onClick={() => onToggle(key)}
            onDoubleClick={() => {
              if (!collapsed) onOpenSmile(n.ticker, n.expiry);
            }}
            onMouseEnter={() => onHover(key)}
            onMouseLeave={() => onHover(null)}
          >
            {raw && sdFrac > 0 && (
              <circle
                cx={p.x} cy={p.y}
                r={r + sdFrac * HALO_MAX}
                fill={shiftColor(raw.shiftBp, maxAbsShift)}
                style={{
                  opacity: revealed ? 0.3 - 0.18 * sdFrac : 0,
                  transition: "opacity 400ms ease-out",
                }}
              />
            )}
            <circle
              cx={p.x} cy={p.y} r={r}
              className={
                wave !== undefined && wave.animating && isLit
                  ? "gnc-lit-pulse"
                  : undefined
              }
              stroke={stroke}
              strokeWidth={isLit || isSource ? 2 : 1}
              strokeDasharray={collapsed ? "4 3" : undefined}
              style={{
                fill,
                transition: "fill 400ms ease-out",
                ...(isLit
                  ? { filter: "drop-shadow(0 0 6px rgb(251 191 36 / 0.55))" }
                  : isSource
                    ? { filter: "drop-shadow(0 0 6px rgb(56 189 248 / 0.6))" }
                    : undefined),
              }}
            />
            {label !== null && (
              <text
                x={p.x} y={p.y} dy="0.34em" textAnchor="middle"
                pointerEvents="none"
                className={[
                  "font-mono font-medium",
                  collapsed ? "text-[10px]" : "text-[9px]",
                  result ? "fill-slate-100" : isLit ? "fill-amber-300" : "fill-slate-400",
                ].join(" ")}
              >
                {label}
              </text>
            )}
            {/* Expiry shorthand beside the node (MM-DD of an ISO date); a
                collapsed pod reads "n exp" instead. */}
            <text
              x={p.x + r + 4} y={p.y} dy="0.32em"
              pointerEvents="none"
              className="fill-slate-500 font-mono text-[8px]"
            >
              {collapsed ? `${count} exp` : n.expiry.slice(5)}
            </text>
          </g>
        );
      })}
    </>
  );
}

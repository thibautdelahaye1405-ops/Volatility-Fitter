// Arrow layer of the smile-universe canvas (GRAPH ERGONOMICS ARC, E3).
//
// Every relation is an ARROW drawn from the informer to the receiver, with
// the encoders of lib/edgeStyle: stroke width = relationship confidence
// (fixed σ anchors, so widths compare across sessions) and colour = β (cool
// below 1, slate at 1, warm above, rose when negative). Heads are computed
// polygons (SVG markers cannot take a per-use colour). Three families:
//
//   bundles   one Bézier per ticker pair (Σp width, p-weighted mean β);
//             heads on the ends information flows INTO; hovered OR expanded
//             (sticky, click) bundles also draw their individual arrows;
//   arrows    the individual cross relations of an expanded bundle, offset
//             sideways when the mirror direction exists, selectable;
//   calendar  one hop per adjacent expiry pair of a spine, heads on the
//             receiver end(s); fillers (no relation) stay dashed slate.
//
// Engine truth for the chart's LayoutEdgeIn: `from` is the RECEIVER and `to`
// the INFORMER (state/useGraphTopology); the relation key read back to the
// draft is therefore `${to}>${from}`.
import { arrowHeadPoints, betaColor, bezierHeadPoints, bundleWidth, edgeWidth } from "../lib/edgeStyle";
import type { CalendarEdge, GraphLayout, PairEdgeDetail } from "../lib/graphLayout";
import { NODE_R, SLATE_400, type BundleGeo, type FocusSet } from "./GraphNetworkChart.helpers";

/** Relation key (source|sExp>target|tExp) of a chart edge / pair detail. */
export const detailKey = (d: {
  fromTicker: string; fromExpiry: string; toTicker: string; toExpiry: string;
}): string => `${d.toTicker}|${d.toExpiry}>${d.fromTicker}|${d.fromExpiry}`;

/** Relation keys a calendar hop can stand for (earlier ← later, later ← earlier). */
export function calendarKeys(c: CalendarEdge): { toEarlier: string; toLater: string } {
  return {
    toEarlier: `${c.ticker}|${c.toExpiry}>${c.ticker}|${c.fromExpiry}`,
    toLater: `${c.ticker}|${c.fromExpiry}>${c.ticker}|${c.toExpiry}`,
  };
}

export interface RelationHover {
  key: string;
  label: string;
  beta: number;
  precision: number;
  x: number;
  y: number;
}

export interface GraphEdgeLayerProps {
  layout: GraphLayout;
  bundleGeos: BundleGeo[];
  focus: FocusSet | null;
  hovTicker: string;
  hovExpiry: string;
  hoverBundleKey: string | null;
  /** Bundle keys expanded by click (sticky). */
  expanded: ReadonlySet<string>;
  selectedKey: string | null;
  hoverRelationKey: string | null;
  interactive: boolean;
  onBundleEnter: (g: BundleGeo) => void;
  onBundleLeave: () => void;
  onBundleClick: (g: BundleGeo) => void;
  onRelationEnter: (h: RelationHover) => void;
  onRelationLeave: () => void;
  onRelationClick: (key: string) => void;
  onCalendarClick: (c: CalendarEdge) => void;
}

const GLOW = "var(--color-accent-400)";

/** Shorten a segment at both ends so heads touch the node circles. */
function trimmed(x1: number, y1: number, x2: number, y2: number, rStart: number, rEnd: number) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  return {
    x1: x1 + ux * rStart, y1: y1 + uy * rStart,
    x2: x2 - ux * rEnd, y2: y2 - uy * rEnd,
    // perpendicular unit (for the mirror offset)
    px: -uy, py: ux,
  };
}

const short = (ticker: string, expiry: string) => `${ticker} ${expiry.slice(5)}`;

export default function GraphEdgeLayer({
  layout,
  bundleGeos,
  focus,
  hovTicker,
  hovExpiry,
  hoverBundleKey,
  expanded,
  selectedKey,
  hoverRelationKey,
  interactive,
  onBundleEnter,
  onBundleLeave,
  onBundleClick,
  onRelationEnter,
  onRelationLeave,
  onRelationClick,
  onCalendarClick,
}: GraphEdgeLayerProps) {
  /** One individual cross arrow (informer → receiver), selectable. */
  const arrow = (d: PairEdgeDetail, i: number, mirrored: boolean) => {
    const key = detailKey(d);
    const seg = trimmed(d.x2, d.y2, d.x1, d.y1, NODE_R, NODE_R + 2);
    const off = mirrored ? 3 : 0;
    const x1 = seg.x1 + seg.px * off;
    const y1 = seg.y1 + seg.py * off;
    const x2 = seg.x2 + seg.px * off;
    const y2 = seg.y2 + seg.py * off;
    const color = betaColor(d.beta);
    const w = edgeWidth(Math.abs(d.weight));
    const selected = selectedKey === key;
    const hovered = hoverRelationKey === key;
    return (
      <g key={`pd-${i}`} data-relation={key}>
        {selected && (
          <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={GLOW} strokeWidth={w + 6} opacity={0.35} strokeLinecap="round" />
        )}
        <line
          x1={x1} y1={y1} x2={x2} y2={y2}
          stroke={color}
          strokeWidth={hovered ? w + 1 : w}
          opacity={selected || hovered ? 1 : 0.8}
          strokeLinecap="round"
          pointerEvents="none"
        />
        <polygon points={arrowHeadPoints(x1, y1, x2, y2)} fill={color} pointerEvents="none" />
        {/* Hit twin */}
        <line
          x1={x1} y1={y1} x2={x2} y2={y2}
          stroke="transparent"
          strokeWidth={w + 10}
          pointerEvents="stroke"
          className={interactive ? "cursor-pointer" : undefined}
          onMouseEnter={() =>
            onRelationEnter({
              key,
              label: `${short(d.toTicker, d.toExpiry)} → ${short(d.fromTicker, d.fromExpiry)}`,
              beta: d.beta,
              precision: Math.abs(d.weight),
              x: (x1 + x2) / 2,
              y: (y1 + y2) / 2,
            })
          }
          onMouseLeave={onRelationLeave}
          onClick={(e) => {
            e.stopPropagation();
            if (interactive) onRelationClick(key);
          }}
        />
      </g>
    );
  };

  return (
    <>
      {/* Cross-ticker bundles: one Bézier per ticker pair */}
      {bundleGeos.map((g) => {
        const hovered = hoverBundleKey === g.key;
        const isExpanded = expanded.has(g.key);
        const dimmed = focus !== null && !focus.bundles.has(g.key);
        const color = betaColor(g.b.meanBeta);
        const w = bundleWidth(g.b.totalWeight);
        const p0 = { x: g.b.x1, y: g.b.y1 };
        const c = { x: g.cx, y: g.cy };
        const p2 = { x: g.b.x2, y: g.b.y2 };
        return (
          <g key={g.key} opacity={dimmed ? 0.15 : 1} data-bundle={g.key}>
            <path
              d={g.d}
              fill="none"
              stroke={color}
              strokeWidth={w}
              opacity={hovered || isExpanded ? 0.55 : 0.28}
              strokeLinecap="round"
            />
            {/* Heads show INFORMATION FLOW: an (a → b) edge means b informs
                a, so flow arrives at the a / path-start end. */}
            {g.b.hasAb && (
              <polygon points={bezierHeadPoints(p0, c, p2, "start", 10, 4.5)} fill={color} opacity={hovered || isExpanded ? 0.9 : 0.5} />
            )}
            {g.b.hasBa && (
              <polygon points={bezierHeadPoints(p0, c, p2, "end", 10, 4.5)} fill={color} opacity={hovered || isExpanded ? 0.9 : 0.5} />
            )}
            {/* Hover/click twin: hoverable width; click = expand + pair card */}
            <path
              d={g.d}
              fill="none"
              stroke="transparent"
              strokeWidth={w + 10}
              pointerEvents="stroke"
              className={interactive ? "cursor-pointer" : undefined}
              onMouseEnter={() => onBundleEnter(g)}
              onMouseLeave={onBundleLeave}
              onClick={(e) => {
                e.stopPropagation();
                onBundleClick(g);
              }}
            />
          </g>
        );
      })}

      {/* Expanded bundles: the individual relations as arrows */}
      {bundleGeos
        .filter((g) => expanded.has(g.key) || hoverBundleKey === g.key)
        .map((g) => {
          const details = layout.pairDetails(g.b.fromTicker, g.b.toTicker);
          const keys = new Set(
            details.map((d) => `${d.fromTicker}|${d.fromExpiry}>${d.toTicker}|${d.toExpiry}`),
          );
          return (
            <g key={`x-${g.key}`}>
              {details.map((d, i) =>
                arrow(
                  d,
                  i,
                  keys.has(`${d.toTicker}|${d.toExpiry}>${d.fromTicker}|${d.fromExpiry}`),
                ),
              )}
            </g>
          );
        })}

      {/* Calendar hops (non-filler = real relations; heads at the receiver) */}
      {layout.calendar.map((c) => {
        const touches =
          focus === null ||
          (c.ticker === hovTicker && (c.fromExpiry === hovExpiry || c.toExpiry === hovExpiry));
        const filler = c.weight === 0;
        const keys = calendarKeys(c);
        const selected =
          selectedKey !== null && (selectedKey === keys.toEarlier || selectedKey === keys.toLater);
        const hovered =
          hoverRelationKey !== null &&
          (hoverRelationKey === keys.toEarlier || hoverRelationKey === keys.toLater);
        const color = filler ? SLATE_400 : betaColor(c.beta);
        const w = filler ? 1.2 : edgeWidth(c.weight);
        // Earlier expiry sits at (x1, y1) — the spine is sorted by t.
        const seg = trimmed(c.x1, c.y1, c.x2, c.y2, NODE_R + 1, NODE_R + 1);
        const id = `cal-${c.ticker}-${c.fromExpiry}-${c.toExpiry}`;
        return (
          <g key={id} opacity={touches ? 1 : 0.15} data-calendar={id}>
            {selected && (
              <line x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2} stroke={GLOW} strokeWidth={w + 6} opacity={0.35} strokeLinecap="round" />
            )}
            <line
              x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2}
              stroke={color}
              strokeWidth={hovered ? w + 1 : w}
              strokeDasharray={filler ? "3 3" : undefined}
              opacity={filler ? 0.3 : selected || hovered ? 1 : 0.75}
              strokeLinecap="round"
            />
            {!filler && c.toEarlier && (
              <polygon points={arrowHeadPoints(seg.x2, seg.y2, seg.x1, seg.y1, 7, 3.2)} fill={color} />
            )}
            {!filler && c.toLater && (
              <polygon points={arrowHeadPoints(seg.x1, seg.y1, seg.x2, seg.y2, 7, 3.2)} fill={color} />
            )}
            {!filler && interactive && (
              <line
                x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2}
                stroke="transparent"
                strokeWidth={12}
                pointerEvents="stroke"
                className="cursor-pointer"
                onMouseEnter={() =>
                  onRelationEnter({
                    key: c.toEarlier ? keys.toEarlier : keys.toLater,
                    label: c.toEarlier
                      ? `${short(c.ticker, c.toExpiry)} → ${short(c.ticker, c.fromExpiry)}`
                      : `${short(c.ticker, c.fromExpiry)} → ${short(c.ticker, c.toExpiry)}`,
                    beta: c.beta,
                    precision: c.weight,
                    x: (c.x1 + c.x2) / 2,
                    y: (c.y1 + c.y2) / 2,
                  })
                }
                onMouseLeave={onRelationLeave}
                onClick={(e) => {
                  e.stopPropagation();
                  onCalendarClick(c);
                }}
              />
            )}
          </g>
        );
      })}
    </>
  );
}

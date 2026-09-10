// The Smile chart's LANES overlay slot (SERIES ARC S4, roadmap §3.4): N
// named curves drawn through the chart's own k → x transform and y scale,
// each with its colour / dash / width / opacity — the Series stage's other
// lanes and the production lane's ghost trail (previous frames, fading).
// Split out of SmileChart.tsx (file-size policy): the chart mounts this
// with its pixel maps and lists `LaneLegendItems` in its legend row.
import type { SmilePoint } from "../../lib/mockData";

/** One overlaid curve in the market frame's moneyness. */
export interface LaneCurve {
  /** Stable key (a lane id, or "ghost-<n>"). */
  id: string;
  /** Legend text; empty = drawn but not listed (ghost frames). */
  label: string;
  points: SmilePoint[];
  /** SVG stroke colour. */
  colour: string;
  /** SVG stroke-dasharray ("" = solid). */
  dash: string;
  /** Stroke width (px); 1.5 by default. */
  width?: number;
  /** Stroke opacity in [0, 1]; 1 by default. */
  opacity?: number;
}

/** "M…L…" path of a curve through the chart's pixel maps ("" when < 2 points). */
export function laneCurvePath(
  points: readonly SmilePoint[],
  toX: (k: number) => number,
  toY: (v: number) => number,
): string {
  if (points.length < 2) return "";
  let d = "";
  for (const p of points) {
    const x = toX(p.k);
    const y = toY(p.vol);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    d += d === "" ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`;
  }
  return d;
}

interface LaneCurvesLayerProps {
  lanes: readonly LaneCurve[];
  /** k → pixel x of the market frame (the chart's `toX`). */
  toX: (k: number) => number;
  /** vol → pixel y (the chart's `toY`). */
  toY: (v: number) => number;
}

/** The paths, in the given order (put the faintest first). Inert to the
 *  pointer so the chart's hover / quote clicks pass through. */
export default function LaneCurvesLayer({ lanes, toX, toY }: LaneCurvesLayerProps) {
  return (
    <g pointerEvents="none" data-testid="lane-curves">
      {lanes.map((lane) => {
        const d = laneCurvePath(lane.points, toX, toY);
        if (d === "") return null;
        return (
          <path
            key={lane.id}
            data-lane={lane.id}
            d={d}
            fill="none"
            stroke={lane.colour}
            strokeWidth={lane.width ?? 1.5}
            strokeOpacity={lane.opacity ?? 1}
            strokeDasharray={lane.dash !== "" ? lane.dash : undefined}
            strokeLinejoin="round"
          />
        );
      })}
    </g>
  );
}

/** Legend entries (swatch with the lane's dash + label) for the labelled
 *  lanes, on the chart legend's own idiom. */
export function LaneLegendItems({ lanes }: { lanes: readonly LaneCurve[] }) {
  return (
    <>
      {lanes
        .filter((lane) => lane.label !== "")
        .map((lane) => (
          <span key={lane.id} className="flex items-center gap-1.5" data-lane-legend={lane.id}>
            <svg width={20} height={6} aria-hidden="true">
              <line
                x1={0}
                x2={20}
                y1={3}
                y2={3}
                stroke={lane.colour}
                strokeWidth={2}
                strokeOpacity={lane.opacity ?? 1}
                strokeDasharray={lane.dash !== "" ? lane.dash : undefined}
              />
            </svg>
            {lane.label}
          </span>
        ))}
    </>
  );
}

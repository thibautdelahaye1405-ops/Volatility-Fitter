// The Term chart's LANES overlay slot (SERIES ARC S5, roadmap §3.4): N
// named term structures drawn through the chart's own maturity → x and
// vol → y maps — each lane's per-expiry ATM vols as a polyline with small
// markers, and its var-swap vols thinner and dashed — the Series stage's
// other lanes beside the production lane's fit. The points sit on the
// CALENDAR clock whatever the chart's axis clock (a series carries no event
// dilation). Split out of TermChart.tsx (file-size policy): the chart
// mounts this with its pixel maps and lists `LaneTermLegendItems` in its
// legend row.

/** One expiry of an overlaid lane (null = not fitted at that expiry). */
export interface TermLanePoint {
  expiry: string;
  /** Calendar year-fraction to expiry. */
  t: number;
  atmVol: number | null;
  varSwapVol: number | null;
}

/** One overlaid term structure. */
export interface TermLane {
  /** Stable key (the lane id). */
  id: string;
  /** Legend text. */
  label: string;
  /** SVG stroke colour. */
  colour: string;
  /** SVG stroke-dasharray of the ATM line ("" = solid). */
  dash: string;
  points: TermLanePoint[];
}

/** Dash of every lane's var-swap line (thinner, always dashed). */
export const VARSWAP_DASH = "2 3";

/** "M…L…" path through the finite (t, pick(p)) pairs of a lane, ascending
 *  in t, through the chart's pixel maps ("" with fewer than two). */
export function laneTermPath(
  points: readonly TermLanePoint[],
  pick: (p: TermLanePoint) => number | null,
  toX: (t: number) => number,
  toY: (v: number) => number,
): string {
  const pairs: { t: number; v: number }[] = [];
  for (const p of points) {
    const v = pick(p);
    if (v !== null && Number.isFinite(v) && Number.isFinite(p.t)) pairs.push({ t: p.t, v });
  }
  if (pairs.length < 2) return "";
  pairs.sort((a, b) => a.t - b.t);
  let d = "";
  for (const { t, v } of pairs) {
    const x = toX(t);
    const y = toY(v);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    d += `${d === "" ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
  }
  return d;
}

/** Extent of the lanes' points — the maturities and the vols (ATM and
 *  var-swap) — what the chart adds to its domains; null with no finite point. */
export function laneTermExtent(
  lanes: readonly TermLane[],
): { tLo: number; tHi: number; vLo: number; vHi: number } | null {
  let tLo = Infinity;
  let tHi = -Infinity;
  let vLo = Infinity;
  let vHi = -Infinity;
  for (const lane of lanes) {
    for (const p of lane.points) {
      if (!Number.isFinite(p.t)) continue;
      for (const v of [p.atmVol, p.varSwapVol]) {
        if (v === null || !Number.isFinite(v)) continue;
        tLo = Math.min(tLo, p.t);
        tHi = Math.max(tHi, p.t);
        vLo = Math.min(vLo, v);
        vHi = Math.max(vHi, v);
      }
    }
  }
  return Number.isFinite(tLo) && Number.isFinite(vLo) ? { tLo, tHi, vLo, vHi } : null;
}

interface LaneTermLayerProps {
  lanes: readonly TermLane[];
  /** Calendar maturity t (years) → pixel x (the chart's `X`). */
  toX: (t: number) => number;
  /** Vol → pixel y (the chart's vol scale). */
  toY: (v: number) => number;
}

/** The lanes' ATM polylines (+ markers) and var-swap polylines, in the
 *  given order. Inert to the pointer so the chart's hover passes through. */
export default function LaneTermLayer({ lanes, toX, toY }: LaneTermLayerProps) {
  return (
    <g pointerEvents="none" data-testid="lane-term">
      {lanes.map((lane) => {
        const atm = laneTermPath(lane.points, (p) => p.atmVol, toX, toY);
        const vs = laneTermPath(lane.points, (p) => p.varSwapVol, toX, toY);
        return (
          <g key={lane.id} data-lane-group={lane.id}>
            {vs !== "" && (
              <path data-lane-vs={lane.id} d={vs} fill="none" stroke={lane.colour} strokeWidth={1}
                strokeOpacity={0.6} strokeDasharray={VARSWAP_DASH} strokeLinejoin="round" />
            )}
            {atm !== "" && (
              <path data-lane={lane.id} d={atm} fill="none" stroke={lane.colour} strokeWidth={1.5}
                strokeDasharray={lane.dash !== "" ? lane.dash : undefined} strokeLinejoin="round" />
            )}
            {lane.points.map((p) => {
              if (p.atmVol === null || !Number.isFinite(p.atmVol) || !Number.isFinite(p.t)) return null;
              const x = toX(p.t);
              const y = toY(p.atmVol);
              if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
              return (
                <circle key={p.expiry} data-lane-marker={lane.id} cx={x} cy={y} r={2.5}
                  fill={lane.colour} stroke="var(--color-surface-900)" strokeWidth={1} />
              );
            })}
          </g>
        );
      })}
    </g>
  );
}

/** Legend entries (swatch with the lane's dash + label), on the Term
 *  chart legend's own idiom. */
export function LaneTermLegendItems({ lanes }: { lanes: readonly TermLane[] }) {
  return (
    <>
      {lanes.map((lane) => (
        <span key={lane.id} className="flex items-center gap-1.5" data-lane-legend={lane.id}>
          <svg width={20} height={6} aria-hidden="true">
            <line x1={0} x2={20} y1={3} y2={3} stroke={lane.colour} strokeWidth={2}
              strokeDasharray={lane.dash !== "" ? lane.dash : undefined} />
          </svg>
          {lane.label}
        </span>
      ))}
    </>
  );
}

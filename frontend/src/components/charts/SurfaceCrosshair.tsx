// Crosshair of the 3D surface charts (UI SHELL v2 wave 3, B2): for the
// snapped grid vertex (i, j) it draws
//   (a) the two iso-curves LIFTED onto the surface — the SMILE at T_i (row
//       i) and the TERM curve at k_j (column j),
//   (b) their dashed projections on the floor (z = 0),
//   (c) a marker at the surface point,
// and the parent renders the readout badge. Drawn LAST (above the painter-
// sorted facets). Pure SVG from pre-projected pixel points.
import { CrosshairBadge } from "../CrosshairOverlay";

export interface PixelPoint { x: number; y: number }

interface SurfaceCrosshairProps {
  /** Projected surface vertices [row][col]. */
  pts: PixelPoint[][];
  /** Projected FLOOR points of row i and column j (z = 0). */
  floorRow: PixelPoint[];
  floorCol: PixelPoint[];
  i: number;
  j: number;
  /** Muted when the hit comes from a LINKED chart (not this pointer). */
  linked?: boolean;
}

const path = (ps: PixelPoint[]) => ps.map((p, n) => `${n === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("");

export default function SurfaceCrosshair({ pts, floorRow, floorCol, i, j, linked = false }: SurfaceCrosshairProps) {
  const row = pts[i];
  if (!row || !row[j]) return null;
  const col = pts.map((r) => r[j]).filter(Boolean);
  const hit = row[j];
  const smile = linked ? "rgb(203 213 225 / 0.6)" : "rgb(248 250 252)";
  const term = linked ? "rgb(56 189 248 / 0.6)" : "rgb(56 189 248)";
  const floor = "rgb(148 163 184 / 0.55)";
  return (
    <g pointerEvents="none">
      {/* Floor projections */}
      <path d={path(floorRow)} fill="none" stroke={floor} strokeWidth={1} strokeDasharray="3 3" />
      <path d={path(floorCol)} fill="none" stroke={floor} strokeWidth={1} strokeDasharray="3 3" />
      {/* Drop line from the surface point to the floor */}
      {floorRow[j] && (
        <line x1={hit.x} y1={hit.y} x2={floorRow[j].x} y2={floorRow[j].y} stroke={floor} strokeDasharray="2 3" />
      )}
      {/* Lifted iso-curves: the smile at T_i and the term curve at k_j */}
      <path d={path(row)} fill="none" stroke="rgb(2 6 23 / 0.7)" strokeWidth={3.5} strokeLinejoin="round" />
      <path d={path(row)} fill="none" stroke={smile} strokeWidth={1.6} strokeLinejoin="round" />
      <path d={path(col)} fill="none" stroke="rgb(2 6 23 / 0.7)" strokeWidth={3.5} strokeLinejoin="round" />
      <path d={path(col)} fill="none" stroke={term} strokeWidth={1.6} strokeLinejoin="round" />
      {/* Marker */}
      <circle cx={hit.x} cy={hit.y} r={4.5} fill="rgb(15 23 42)" stroke={smile} strokeWidth={1.5} />
      <circle cx={hit.x} cy={hit.y} r={1.8} fill={term} />
    </g>
  );
}

/** Readout badge text: `T 0.50y · 24-Feb-27 · k −0.12 · σ 21.3%` (units follow
 *  the axis mode through the formatters). */
export function surfaceReadout(
  tLabel: string,
  expiryLabel: string | null,
  xLabel: string,
  valueLabel: string,
): string {
  return [tLabel, expiryLabel, xLabel, valueLabel].filter((s) => s !== null && s !== "").join(" · ");
}

export { CrosshairBadge };

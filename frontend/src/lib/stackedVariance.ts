// Pure helpers for the Stacked-Variance arb evidence (roadmap V3.3, item 10):
// the "levels / Δ" difference mode's series algebra and the calendar-cross
// marker mapping (quality-node row → adjacent series pair → circle position).
// Pure data → data so vitest covers the logic without an SVG in sight.

/** The exact calendar certificate's own gate (backend quality._CAL_TOL):
 *  a ledger gap is flagged iff min gap < -CAL_TOL — never a new threshold. */
export const CAL_TOL = 1e-6;

/** Shared-grid total-variance rows (one per expiry, nearest first). */
export interface VarianceGrid {
  expiries: string[];
  k: number[];
  /** w[i][j] = total variance of expiry i at k[j]. */
  w: number[][];
}

/** The quality fields the marker mapping consumes (a structural subset of
 *  useQuality's QualityNode — the certificate location on the wire). */
export interface CalendarEvidenceNode {
  expiry: string;
  ledgerGapMin?: number | null;
  ledgerGapK?: number | null;
}

/** Marker in DATA coordinates (k, w or Δw) — the chart maps to pixels. */
export interface CalendarMarker {
  /** Log-moneyness of the certificate's minimizing strike. */
  k: number;
  y: number;
  label: string;
  /** Index of the far expiry's row (its axis context transforms the x). */
  farIndex: number;
}

/** Linear interpolation of ys over an ascending xs grid; null off an empty grid. */
export function interpOnGrid(xs: number[], ys: number[], x: number): number | null {
  const n = Math.min(xs.length, ys.length);
  if (n === 0) return null;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[n - 1]) return ys[n - 1];
  for (let i = 1; i < n; i++) {
    if (x <= xs[i]) {
      const t = (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
      return ys[i - 1] + t * (ys[i] - ys[i - 1]);
    }
  }
  return ys[n - 1];
}

/** Δ mode: adjacent-pair difference rows w_far(k) − w_near(k) on the SHARED
 *  k grid (client-side subtraction — the series already share the grid).
 *  Sub-zero excursions are the calendar violations; the chart fills them red. */
export function deltaRows(grid: VarianceGrid): { label: string; ys: number[] }[] {
  const rows: { label: string; ys: number[] }[] = [];
  for (let i = 1; i < grid.w.length; i++) {
    rows.push({
      label: `${grid.expiries[i - 1]}→${grid.expiries[i]}`,
      ys: grid.k.map((_, j) => grid.w[i][j] - grid.w[i - 1][j]),
    });
  }
  return rows;
}

/** Map certificate-refuted quality rows onto the chart: one circle per
 *  far-expiry node with ledgerGapMin < -CAL_TOL, at x = ledgerGapK and
 *  y = the two curves' midpoint ("levels") or their gap ("delta"),
 *  interpolated on the shared grid. Certified rows and the first expiry
 *  (no previous slice ⇒ null fields) produce nothing. */
export function calendarMarkers(
  nodes: CalendarEvidenceNode[],
  grid: VarianceGrid,
  mode: "levels" | "delta",
): CalendarMarker[] {
  const markers: CalendarMarker[] = [];
  for (const node of nodes) {
    const gap = node.ledgerGapMin;
    const kStar = node.ledgerGapK;
    if (gap == null || kStar == null || !(gap < -CAL_TOL)) continue;
    const far = grid.expiries.indexOf(node.expiry);
    if (far <= 0) continue; // unknown expiry or the ladder's first (no pair)
    const wNear = interpOnGrid(grid.k, grid.w[far - 1], kStar);
    const wFar = interpOnGrid(grid.k, grid.w[far], kStar);
    if (wNear === null || wFar === null) continue;
    markers.push({
      k: kStar,
      y: mode === "levels" ? 0.5 * (wNear + wFar) : wFar - wNear,
      label:
        `ΔG min ${(gap * 1e4).toFixed(1)}bp · ` +
        `${grid.expiries[far - 1]}→${grid.expiries[far]} · certified: no`,
      farIndex: far,
    });
  }
  return markers;
}

/** LV variant (item 10, LV side): the affine fit reports the worst PDE-lattice
 *  crossing as (pair index, k). Returns the circle in data coordinates on the
 *  stacked-IV total-variance axes, or null when clean / degenerate. */
export function lvCalendarMarker(
  smiles: {
    expiry: string;
    t: number;
    tau?: number;
    model: { k: number; vol: number }[];
    modelExt?: { k: number; vol: number }[];
  }[],
  pair: number | null | undefined,
  kStar: number | null | undefined,
): { k: number; y: number; label: string } | null {
  if (pair == null || kStar == null) return null;
  const near = smiles[pair];
  const far = smiles[pair + 1];
  if (!near || !far) return null;
  const wAt = (s: (typeof smiles)[number]): number | null => {
    const pts = s.modelExt && s.modelExt.length > 1 ? s.modelExt : s.model;
    const vol = interpOnGrid(
      pts.map((p) => p.k),
      pts.map((p) => p.vol),
      kStar,
    );
    if (vol === null) return null;
    const tau = s.tau !== undefined && s.tau > 0 ? s.tau : s.t;
    return vol * vol * tau;
  };
  const wNear = wAt(near);
  const wFar = wAt(far);
  if (wNear === null || wFar === null) return null;
  return {
    k: kStar,
    y: 0.5 * (wNear + wFar),
    label: `worst cal. crossing · ${near.expiry}→${far.expiry} at k ${kStar.toFixed(2)}`,
  };
}

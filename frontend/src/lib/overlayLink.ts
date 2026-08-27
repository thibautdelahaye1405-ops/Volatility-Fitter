// Linked-hover helpers for the overlay curve charts (UI SHELL v2 wave 3, B2)
// — pure. A Stacked IV / Densities overlay is many expiry curves on shared
// axes; linking it to the 3D surfaces needs (a) which curve the pointer is
// on (→ its maturity T, published with the pointer's x = k) and (b) where a
// point (k, T) published elsewhere lands here (→ the curve with the nearest
// T, and its y at k, interpolated along the polyline).

export interface CurveLike { xs: number[]; ys: number[] }

/** Index of the curve nearest to the pointer in PIXEL space (each curve
 *  sampled at the pointer's x by interpolation). Null when no curve covers x. */
export function nearestCurveAt(
  curves: CurveLike[],
  x: number,
  y: number,
  mapY: (v: number) => number,
): number | null {
  let best: number | null = null;
  let bestD = Infinity;
  const py = mapY(y);
  for (let i = 0; i < curves.length; i++) {
    const yi = interpolateY(curves[i], x);
    if (yi === null) continue;
    const d = Math.abs(mapY(yi) - py);
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

/** Linear interpolation of a curve's y at x (null outside its x-range or on
 *  a non-finite sample). Curves are x-sorted (ascending or descending). */
export function interpolateY(curve: CurveLike, x: number): number | null {
  const { xs, ys } = curve;
  const n = xs.length;
  if (n === 0) return null;
  if (n === 1) return xs[0] === x ? ys[0] : null;
  const asc = xs[n - 1] >= xs[0];
  const lo = asc ? xs[0] : xs[n - 1];
  const hi = asc ? xs[n - 1] : xs[0];
  if (x < lo || x > hi) return null;
  for (let i = 1; i < n; i++) {
    const a = xs[i - 1], b = xs[i];
    const inside = asc ? x >= a && x <= b : x <= a && x >= b;
    if (!inside) continue;
    const ya = ys[i - 1], yb = ys[i];
    if (!Number.isFinite(ya) || !Number.isFinite(yb)) return null;
    const f = b === a ? 0 : (x - a) / (b - a);
    return ya + f * (yb - ya);
  }
  return null;
}

/** Index of the maturity nearest to t (null on an empty list). */
export function nearestByT(ts: number[], t: number): number | null {
  if (ts.length === 0) return null;
  let best = 0;
  for (let i = 1; i < ts.length; i++) if (Math.abs(ts[i] - t) < Math.abs(ts[best] - t)) best = i;
  return best;
}

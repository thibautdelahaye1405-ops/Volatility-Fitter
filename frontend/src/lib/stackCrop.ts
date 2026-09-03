// Stacked-IV display crop (Options ▸ stackCrop / stackCropTailProb, 2026-09-03).
//
// Each expiry's payload carries a crop table: at fixed tail-probability levels
// u (1e-2 … 1e-12, both tails) the realistic log-moneyness range [lo, hi] =
// the slice's own [Q(u), Q(1 − u)] widened to its quoted range (backend
// volfit.api.crop). With the option on, a curve is drawn only inside the
// range at the chosen ε: a pricer sampling the fitted distribution never reads
// the smile beyond with probability 1 − O(ε), so arbitrage-freeness inside
// the crop is the computational statement and nothing is computed outside.
// Quotes are always drawn (the range contains the quoted range by
// construction, and quote markers are never filtered).
// Pure data → data so vitest covers the logic without an SVG in sight.

/** One slice's crop table (the wire shape). */
export interface CropRanges {
  u: number[];
  lo: number[];
  hi: number[];
}

/** [lo, hi] at tail probability `eps`, interpolated linearly in log10(u)
 *  between the table's levels and clamped to its ends; null without a table
 *  or for a non-positive eps. */
export function cropRangeAt(
  table: CropRanges | null | undefined,
  eps: number,
): [number, number] | null {
  if (!table || table.u.length === 0 || !(eps > 0)) return null;
  const n = Math.min(table.u.length, table.lo.length, table.hi.length);
  if (n === 0) return null;
  // Levels are stored from the largest u (narrowest range) to the smallest.
  const x = Math.log10(eps);
  const xs = table.u.slice(0, n).map((u) => Math.log10(u));
  if (x >= xs[0]) return [table.lo[0], table.hi[0]];
  if (x <= xs[n - 1]) return [table.lo[n - 1], table.hi[n - 1]];
  for (let i = 1; i < n; i++) {
    if (x >= xs[i]) {
      const t = (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
      return [
        table.lo[i - 1] + t * (table.lo[i] - table.lo[i - 1]),
        table.hi[i - 1] + t * (table.hi[i] - table.hi[i - 1]),
      ];
    }
  }
  return [table.lo[n - 1], table.hi[n - 1]];
}

/** Intersection of two ranges (the Δ-pair mode draws where BOTH expiries are
 *  realistic); null when either is null or they do not overlap. */
export function intersectRanges(
  a: [number, number] | null,
  b: [number, number] | null,
): [number, number] | null {
  if (!a || !b) return null;
  const lo = Math.max(a[0], b[0]);
  const hi = Math.min(a[1], b[1]);
  return lo < hi ? [lo, hi] : null;
}

/** Keep the points whose log-moneyness lies inside the range; a null range
 *  or a crop leaving fewer than two points returns the input unchanged (a
 *  curve is never reduced to nothing by the display option). */
export function cropPoints<T>(
  pts: T[],
  kOf: (p: T) => number,
  range: [number, number] | null,
): T[] {
  if (!range) return pts;
  const kept = pts.filter((p) => {
    const k = kOf(p);
    return k >= range[0] && k <= range[1];
  });
  return kept.length >= 2 ? kept : pts;
}

/** Crop a shared-grid row: the (k, y) pairs inside the range, as parallel
 *  arrays for an OverlaySeries. */
export function cropRow(
  k: number[],
  ys: number[],
  range: [number, number] | null,
): { k: number[]; ys: number[] } {
  const n = Math.min(k.length, ys.length);
  const idx: number[] = [];
  for (let j = 0; j < n; j++) idx.push(j);
  const kept = cropPoints(idx, (j) => k[j], range);
  return { k: kept.map((j) => k[j]), ys: kept.map((j) => ys[j]) };
}

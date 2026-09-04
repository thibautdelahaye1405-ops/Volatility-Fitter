// Pure geometry helpers of the overlay chart (OverlayCurvesChart): the data
// extents, the y-domain auto-fitted to the points inside the x view (the base
// the Y center / Y fit policy rides on — same rule as the Smile chart), the
// NaN-splitting polyline path and the sub-zero fill path. No React, no DOM.

/** The minimal curve shape the helpers read. */
export interface XYSeries {
  xs: number[];
  ys: number[];
}

export interface Domain {
  lo: number;
  hi: number;
}

/** Min/max across all series for one accessor, or null when there's no data. */
export function fullDomain(series: readonly XYSeries[], pick: (s: XYSeries) => number[]): Domain | null {
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of series) {
    for (const v of pick(s)) {
      if (!Number.isFinite(v)) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return lo <= hi ? { lo, hi } : null;
}

/** Y BASE domain: the y extent of every point whose x lies inside [xLo, xHi]
 *  (either order), padded 6 % each side; with `zeroBaseline` the floor is
 *  pinned at 0 unless the data dips below it (Δ-pair rows, signed densities).
 *  Falls back to the full-data extent when nothing is in view (a window
 *  beyond the data), and to [0, 1] with no data at all — so the scale is
 *  always finite. */
export function inViewYDomain(
  series: readonly XYSeries[],
  xLo: number,
  xHi: number,
  zeroBaseline = false,
): Domain {
  const a = Math.min(xLo, xHi);
  const b = Math.max(xLo, xHi);
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of series) {
    const n = Math.min(s.xs.length, s.ys.length);
    for (let i = 0; i < n; i++) {
      const x = s.xs[i];
      const y = s.ys[i];
      if (!Number.isFinite(x) || !Number.isFinite(y) || x < a || x > b) continue;
      if (y < lo) lo = y;
      if (y > hi) hi = y;
    }
  }
  if (!(lo <= hi)) {
    const full = fullDomain(series, (s) => s.ys);
    if (full === null) return { lo: 0, hi: 1 };
    lo = full.lo;
    hi = full.hi;
  }
  const pad = Math.max(1e-9, (hi - lo) * 0.06);
  const floor = zeroBaseline ? (lo < 0 ? lo - pad : 0) : lo - pad;
  return { lo: floor, hi: hi + pad };
}

/** SVG polyline of a series; a non-finite point breaks the line (a crop gap
 *  stays a gap instead of being bridged). */
export function seriesPath(s: XYSeries, xMap: (x: number) => number, yMap: (y: number) => number): string {
  let d = "";
  let started = false;
  for (let i = 0; i < s.xs.length; i++) {
    const x = s.xs[i];
    const y = s.ys[i];
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      started = false;
      continue;
    }
    d += `${started ? "L" : "M"}${xMap(x).toFixed(1)},${yMap(y).toFixed(1)}`;
    started = true;
  }
  return d;
}

/** Sub-zero fill of a series: the polyline of min(y, 0) closed along y = 0 —
 *  regions with y >= 0 collapse onto the baseline (zero area), so only the
 *  negative excursions read as red. Empty when the series has no points. */
export function negativeFillPath(s: XYSeries, xMap: (x: number) => number, yMap: (y: number) => number): string {
  const y0 = yMap(0);
  let d = "";
  let firstPx: number | null = null;
  let lastPx: number | null = null;
  for (let i = 0; i < s.xs.length; i++) {
    const x = s.xs[i];
    const y = s.ys[i];
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const px = xMap(x);
    const py = yMap(Math.min(y, 0));
    d += `${d === "" ? "M" : "L"}${px.toFixed(1)},${py.toFixed(1)}`;
    if (firstPx === null) firstPx = px;
    lastPx = px;
  }
  if (d === "" || firstPx === null || lastPx === null) return "";
  return `${d}L${lastPx.toFixed(1)},${y0.toFixed(1)}L${firstPx.toFixed(1)},${y0.toFixed(1)}Z`;
}

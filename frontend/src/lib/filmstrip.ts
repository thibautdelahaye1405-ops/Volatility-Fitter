// Pure scale helpers of the Series filmstrip (roadmap §3.4): three stacked
// sparklines over ALL frames — spot, ATM vol per lane, rms per lane — with
// the playhead crossing them. The x axis is FRAME-INDEX-LINEAR (like the
// scrubber): frame i sits at i/(n−1) of the width, whatever the wall-clock
// gaps. Null values (a lane with no fit at a frame) break the polyline.
// No React, no DOM — components/series/Filmstrip.tsx draws with these.

/** Fraction of the width for frame i of n (0.5 for a single frame). */
export function fracOf(i: number, n: number): number {
  if (!(n > 1)) return 0.5;
  return Math.min(1, Math.max(0, i / (n - 1)));
}

/** Pixel x of frame i of n across `width`. */
export function xOf(i: number, n: number, width: number): number {
  return fracOf(i, n) * width;
}

/** The frame nearest to pixel x (clamped into [0, n−1]; 0 when empty). */
export function nearestIndex(x: number, n: number, width: number): number {
  if (!(n > 1) || !(width > 0)) return 0;
  const i = Math.round((x / width) * (n - 1));
  return Math.min(n - 1, Math.max(0, i));
}

export interface YScale {
  lo: number;
  hi: number;
}

/** Vertical domain of a row: the finite values' extent padded by `pad` of
 *  the span (a flat / single-value row gets a ±5 % band around the level, a
 *  row without values the unit interval). */
export function yScale(values: readonly (number | null | undefined)[], pad = 0.1): YScale {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v == null || !Number.isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!Number.isFinite(lo)) return { lo: 0, hi: 1 };
  if (hi - lo <= Math.abs(hi) * 1e-9) {
    const band = Math.abs(hi) > 0 ? Math.abs(hi) * 0.05 : 0.5;
    return { lo: lo - band, hi: hi + band };
  }
  const p = (hi - lo) * pad;
  return { lo: lo - p, hi: hi + p };
}

/** Pixel y of a value on a row of `height` (lo at the bottom, hi at the top). */
export function yOf(v: number, scale: YScale, height: number): number {
  const span = scale.hi - scale.lo;
  if (!(span > 0)) return height / 2;
  return height - ((v - scale.lo) / span) * height;
}

/** SVG path of a sparkline: one "M…L…" run per stretch of finite values,
 *  a new run after every null (no bridging across a missing fit). */
export function sparkPath(
  values: readonly (number | null | undefined)[],
  scale: YScale,
  width: number,
  height: number,
): string {
  const n = values.length;
  let d = "";
  let open = false;
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v == null || !Number.isFinite(v)) {
      open = false;
      continue;
    }
    const x = xOf(i, n, width).toFixed(1);
    const y = yOf(v, scale, height).toFixed(1);
    d += open ? `L${x},${y}` : `M${x},${y}`;
    open = true;
  }
  return d;
}

/** The value at frame i as a finite number, else null. */
export function valueAt(values: readonly (number | null | undefined)[] | undefined, i: number): number | null {
  const v = values?.[i];
  return v != null && Number.isFinite(v) ? v : null;
}

// Minimal linear-scale and tick utilities for hand-rolled SVG charts.
// Kept dependency-free on purpose (no d3): just the pieces our charts need.

/** Two-way linear mapping between a data domain and a pixel range. */
export interface LinearScale {
  /** Map a domain value to a pixel coordinate. */
  map: (value: number) => number;
  /** Map a pixel coordinate back to a domain value. */
  invert: (px: number) => number;
  domain: readonly [number, number];
  range: readonly [number, number];
}

/** Build a linear scale. Degenerate domains map to the range midpoint. */
export function linearScale(
  domain: readonly [number, number],
  range: readonly [number, number],
): LinearScale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  const slope = span === 0 ? 0 : (r1 - r0) / span;
  return {
    map: (v) => (span === 0 ? (r0 + r1) / 2 : r0 + (v - d0) * slope),
    invert: (px) => (slope === 0 ? d0 : d0 + (px - r0) / slope),
    domain,
    range,
  };
}

/**
 * Generate "nice" tick values covering [min, max], aiming for `target` ticks.
 * Steps are restricted to 1 / 2 / 2.5 / 5 multiples of a power of ten.
 */
export function niceTicks(min: number, max: number, target = 6): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return [];
  const rawStep = (max - min) / Math.max(1, target);
  const power = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const candidates = [1, 2, 2.5, 5, 10];
  let step = candidates[candidates.length - 1] * power;
  for (const c of candidates) {
    if (c * power >= rawStep) {
      step = c * power;
      break;
    }
  }
  const ticks: number[] = [];
  const first = Math.ceil(min / step) * step;
  for (let v = first; v <= max + step * 1e-9; v += step) {
    // Snap to the step grid to avoid 0.30000000000000004-style labels.
    ticks.push(Number((Math.round(v / step) * step).toPrecision(12)));
  }
  return ticks;
}

/** Clamp a value into [lo, hi]. */
export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Format a decimal vol as a percentage label, e.g. 0.206 -> "20.6%". */
export function formatPct(v: number, digits = 1): string {
  return `${(v * 100).toFixed(digits)}%`;
}

/** Compact numeric label for the strike axis (k or fixed strike). */
export function formatAxisNumber(v: number): string {
  if (Math.abs(v) >= 100) return v.toFixed(0);
  return Number(v.toPrecision(4)).toString();
}

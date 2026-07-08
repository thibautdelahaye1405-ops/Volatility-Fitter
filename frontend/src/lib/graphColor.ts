// Diverging shift colour scale + basis-point label for the graph views.
// Extracted verbatim from GraphChart.tsx so the lattice and node-link charts
// paint posterior shifts identically. Pure functions — no React, no DOM.
import { clamp } from "./chartScale";

type Rgb = readonly [number, number, number];
const NEG: Rgb = [59, 130, 246]; // blue-500: vols marked down
const MID: Rgb = [71, 85, 105]; //  slate-600: no shift
const POS: Rgb = [239, 68, 68]; //  red-500: vols marked up

/**
 * Map a posterior shift (bp) to a colour: blue -> slate -> red, clamped at
 * ±maxAbs (the largest |shift| of the current solve). Plain RGB lerp.
 */
export function shiftColor(shiftBp: number, maxAbs: number): string {
  const t = maxAbs > 0 ? clamp(shiftBp / maxAbs, -1, 1) : 0;
  const end = t < 0 ? NEG : POS;
  const a = Math.abs(t);
  const ch = (i: number) => Math.round(MID[i] + (end[i] - MID[i]) * a);
  return `rgb(${ch(0)} ${ch(1)} ${ch(2)})`;
}

/** Signed basis-point label, e.g. "+12.3 bp". */
export function formatBp(bp: number): string {
  return `${bp >= 0 ? "+" : ""}${bp.toFixed(1)} bp`;
}

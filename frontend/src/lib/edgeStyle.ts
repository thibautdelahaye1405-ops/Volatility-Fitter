// Arrow encoders for the Graph Ergonomics canvas (E1, roadmap "GRAPH
// ERGONOMICS ARC", ruling "the canvas is the editor"): thickness reads
// relationship CONFIDENCE off FIXED sigma anchors (so widths compare across
// sessions, unlike a per-frame min/max scale), colour reads beta (cool below
// 1, slate at 1, warm above 1, rose when negative). Pure math — no React, no
// DOM — plus small SVG geometry helpers for arrow heads, since SVG markers
// can't inherit a per-edge stroke colour.
import { clamp } from "./chartScale";
import { precisionFromSigmaPts, sigmaPtsFromPrecision } from "./precisionUnits";

/* --------------------------------- width ---------------------------------- */

/** Relationship uncertainty (vol points) at/above which a relation reads at
 *  its thinnest (least confident). */
export const SIGMA_WIDE_PTS = 10;
/** Relationship uncertainty (vol points) at/below which a relation reads at
 *  its thickest (most confident). */
export const SIGMA_TIGHT_PTS = 0.25;
export const WIDTH_MIN = 0.8;
export const WIDTH_MAX = 4.5;

const LOG_WIDE = Math.log(SIGMA_WIDE_PTS);
const LOG_TIGHT = Math.log(SIGMA_TIGHT_PTS);

/**
 * Stroke width from a relation precision p (1/vol², decimal vol): linear in
 * log(sigma_edge) between the two fixed anchors, clamped beyond them.
 * p <= 0 or non-finite (a dead/undefined relation) draws at WIDTH_MIN.
 */
export function edgeWidth(precision: number): number {
  if (!(precision > 0) || !Number.isFinite(precision)) return WIDTH_MIN;
  const sigma = sigmaPtsFromPrecision(precision);
  if (!Number.isFinite(sigma)) return WIDTH_MIN;
  const frac = clamp((Math.log(sigma) - LOG_TIGHT) / (LOG_WIDE - LOG_TIGHT), 0, 1);
  return WIDTH_MAX + frac * (WIDTH_MIN - WIDTH_MAX);
}

/** Same encoder applied to a bundle's total incoming precision Sigma-p, so a
 *  pile of weak relations reads exactly as thick as the receiver conditional
 *  q = Sigma-p they jointly produce (spec §7.6). */
export function bundleWidth(totalPrecision: number): number {
  return edgeWidth(totalPrecision);
}

/* --------------------------------- colour --------------------------------- */

type Rgb = readonly [number, number, number];

const ROSE: Rgb = [251, 113, 133]; // rose-400 #fb7185 — negative beta
const SKY: Rgb = [56, 189, 248]; // sky-400   #38bdf8 — beta = 0
const SLATE: Rgb = [148, 163, 184]; // slate-400 #94a3b8 — beta = 1 (no amplification)
const AMBER: Rgb = [251, 191, 36]; // amber-400 #fbbf24 — beta = 1.75
const ORANGE: Rgb = [249, 115, 22]; // orange-500 #f97316 — beta >= 2.5

/** β at which the warm ramp reaches amber, and where it saturates orange. */
const BETA_AMBER = 1.75;
const BETA_ORANGE = 2.5;

const rgbStr = (c: Rgb): string => `rgb(${c[0]} ${c[1]} ${c[2]})`;

function lerpRgb(a: Rgb, b: Rgb, t: number): string {
  const k = clamp(t, 0, 1);
  const ch = (i: number) => Math.round(a[i] + (b[i] - a[i]) * k);
  return `rgb(${ch(0)} ${ch(1)} ${ch(2)})`;
}

/**
 * Directed amplitude β -> colour: rose below zero (a corrective / inverse
 * relation), a cool ramp from sky (β=0) to slate (β=1, no amplification), then
 * a warm ramp from slate through amber (β=1.75) to orange (β>=2.5, clamped).
 * Non-finite β (an undefined relation) reads slate.
 */
export function betaColor(beta: number): string {
  if (!Number.isFinite(beta)) return rgbStr(SLATE);
  if (beta < 0) return rgbStr(ROSE);
  if (beta < 1) return lerpRgb(SKY, SLATE, beta);
  if (beta <= BETA_AMBER) return lerpRgb(SLATE, AMBER, (beta - 1) / (BETA_AMBER - 1));
  return lerpRgb(AMBER, ORANGE, (beta - BETA_AMBER) / (BETA_ORANGE - BETA_AMBER));
}

/** Legend stops for a beta gradient strip, ascending. */
export const BETA_LEGEND: readonly { beta: number; label: string }[] = [
  { beta: 0, label: "0" },
  { beta: 0.5, label: "½" },
  { beta: 1, label: "1" },
  { beta: 1.75, label: "1¾" },
  { beta: 2.5, label: "2½+" },
];

/** Legend stops for a width strip, with widths precomputed via the real
 *  precision -> width pipeline (so the strip never drifts from edgeWidth). */
export const WIDTH_LEGEND: readonly { sigmaPts: number; label: string; width: number }[] = [
  { sigmaPts: 10, label: "10 pt", width: edgeWidth(precisionFromSigmaPts(10)) },
  { sigmaPts: 2, label: "2 pt", width: edgeWidth(precisionFromSigmaPts(2)) },
  { sigmaPts: 0.5, label: "½ pt", width: edgeWidth(precisionFromSigmaPts(0.5)) },
];

/* ------------------------------- arrow heads ------------------------------- */

const HEAD_LEN = 9;
const HEAD_HALF = 4;

/**
 * Arrow-head polygon points for a straight segment (x1,y1) -> (x2,y2): a
 * triangle of length `len` / half-width `half`, tip at the end. SVG `points`
 * string ready for a `<polygon>` (so the head can take the stroke colour —
 * marker-end can't be recoloured per edge). Degenerate (zero-length)
 * segments return "" (nothing to draw).
 */
export function arrowHeadPoints(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  len: number = HEAD_LEN,
  half: number = HEAD_HALF,
): string {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const d = Math.hypot(dx, dy);
  if (d < 1e-9) return "";
  const ux = dx / d;
  const uy = dy / d;
  const px = -uy; // unit perpendicular
  const py = ux;
  const baseX = x2 - ux * len;
  const baseY = y2 - uy * len;
  const tip = `${x2},${y2}`;
  const left = `${baseX + px * half},${baseY + py * half}`;
  const right = `${baseX - px * half},${baseY - py * half}`;
  return `${tip} ${left} ${right}`;
}

/**
 * Tangent-aware arrow head for a quadratic Bezier `M P0 Q C P2` at t=1 (tip
 * at P2, direction P2 - C) or t=0 (tip at P0, direction P0 - C) — used to cap
 * the curved bundle/calendar edges honestly instead of the chord direction.
 */
export function bezierHeadPoints(
  p0: { x: number; y: number },
  c: { x: number; y: number },
  p2: { x: number; y: number },
  end: "start" | "end",
  len: number = HEAD_LEN,
  half: number = HEAD_HALF,
): string {
  return end === "end"
    ? arrowHeadPoints(c.x, c.y, p2.x, p2.y, len, half)
    : arrowHeadPoints(c.x, c.y, p0.x, p0.y, len, half);
}

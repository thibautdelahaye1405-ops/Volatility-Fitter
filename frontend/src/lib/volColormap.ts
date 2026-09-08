// Shared vol colormap of the surface charts (3D SurfaceMesh + the LV vertex
// heatmap): blue → cyan → amber → red over the value range. One place so the
// two renderers can never drift apart.

const STOPS: { u: number; rgb: [number, number, number] }[] = [
  { u: 0, rgb: [59, 130, 246] },
  { u: 0.34, rgb: [34, 211, 238] },
  { u: 0.67, rgb: [251, 191, 36] },
  { u: 1, rgb: [239, 68, 68] },
];

/** Piecewise-linear colormap lookup, u in [0, 1] (clamped). */
export function volColor(u: number): string {
  const x = Math.min(1, Math.max(0, u));
  for (let i = 1; i < STOPS.length; i++) {
    if (x <= STOPS[i].u) {
      const a = STOPS[i - 1];
      const b = STOPS[i];
      const f = (x - a.u) / (b.u - a.u);
      const c = a.rgb.map((v, j) => Math.round(v + f * (b.rgb[j] - v)));
      return `rgb(${c[0]} ${c[1]} ${c[2]})`;
    }
  }
  return "rgb(239 68 68)";
}

/** CSS gradient of the same ramp (the legend swatch). */
export const VOL_GRADIENT_CSS =
  "linear-gradient(90deg, rgb(59 130 246), rgb(34 211 238), rgb(251 191 36), rgb(239 68 68))";

// ---- Diverging ramp for SIGNED sheets (the Local Vol Compare tab's twin −
// affine difference): blue below zero, a neutral slate AT zero, red above —
// symmetric, so equal magnitudes of either sign read equally strong.
const DIV_NEG: [number, number, number] = [59, 130, 246]; // blue-500
const DIV_MID: [number, number, number] = [51, 65, 85]; // slate-700 (the card's ground)
const DIV_POS: [number, number, number] = [239, 68, 68]; // red-500

/** Diverging colormap lookup, u in [-1, 1] (clamped): -1 blue · 0 slate · +1 red. */
export function divergingColor(u: number): string {
  const x = Math.min(1, Math.max(-1, Number.isFinite(u) ? u : 0));
  const to = x < 0 ? DIV_NEG : DIV_POS;
  const f = Math.abs(x);
  const c = DIV_MID.map((v, j) => Math.round(v + f * (to[j] - v)));
  return `rgb(${c[0]} ${c[1]} ${c[2]})`;
}

/** CSS gradient of the diverging ramp (the legend swatch), −max → 0 → +max. */
export const DIVERGING_GRADIENT_CSS =
  "linear-gradient(90deg, rgb(59 130 246), rgb(51 65 85), rgb(239 68 68))";

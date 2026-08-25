// Shared crosshair ("haircross") logic for the hand-rolled 2D SVG charts.
//
// Pure pointer -> plot mapping: a chart hands over the pointer's client
// position, its own margins / plot box and its inverse scales; back come
// plot-local pixel coordinates (for the two dashed guides) and domain values
// (for the readout badge), or null when the pointer sits outside the plot box.
// The SVG guides and the badge themselves live in components/CrosshairOverlay;
// margins and scales differ per chart, so everything arrives as arguments.

export interface CrosshairPoint {
  /** Pointer position in PLOT-LOCAL pixels (origin = the plot's top-left). */
  px: number;
  py: number;
  /** Pointer position in domain units (through the chart's inverse scales). */
  x: number;
  y: number;
}

/** Map a pointer event's client coordinates into the plot. `rect` is the
 *  chart SVG's bounding rect; `invertX`/`invertY` take PLOT-LOCAL pixels
 *  (charts whose scales run in full-SVG pixels wrap them, adding the margin
 *  back). Returns null outside the plot box or on a degenerate/non-finite
 *  mapping. */
export function crosshairPoint(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number },
  margin: { left: number; top: number },
  plotW: number,
  plotH: number,
  invertX: (px: number) => number,
  invertY: (py: number) => number,
): CrosshairPoint | null {
  if (plotW <= 0 || plotH <= 0) return null;
  const px = clientX - rect.left - margin.left;
  const py = clientY - rect.top - margin.top;
  if (px < 0 || px > plotW || py < 0 || py > plotH) return null;
  const x = invertX(px);
  const y = invertY(py);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { px, py, x, y };
}

/** Compact "x · y" badge text, each side through its own domain formatter. */
export function crosshairLabel(
  pt: CrosshairPoint,
  formatX: (x: number) => string,
  formatY: (y: number) => string,
): string {
  return `${formatX(pt.x)} · ${formatY(pt.y)}`;
}

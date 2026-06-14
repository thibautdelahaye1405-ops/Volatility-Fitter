// Reusable wheel-zoom / drag-pan / double-click-reset for the hand-rolled SVG
// charts. Dependency-free.
//
// Zoom is stored as *fractions of a base domain* — [lo, hi] start at [0, 1] and
// the wheel/pan move them, possibly outside [0, 1] (zoom-out reveals beyond the
// data). Because the state is base-relative, the chart can recompute its base
// domain every render (auto-fit y, a moved brush, a switched axis mode) and the
// zoom rides along. `viewX/viewY` turn a base domain into the current view
// domain in data units; the chart builds its linear scale from that.
import { useCallback, useState } from "react";

export interface ZoomFractions {
  xLo: number;
  xHi: number;
  yLo: number;
  yHi: number;
}

const IDENTITY: ZoomFractions = { xLo: 0, xHi: 1, yLo: 0, yHi: 1 };
/** Wheel step: one notch zooms to 85% (in) or ~118% (out) of the span. */
const STEP = 0.85;

export interface ZoomController {
  /** Map a base domain to the current view domain in data units. */
  viewX: (base: readonly [number, number]) => [number, number];
  viewY: (base: readonly [number, number]) => [number, number];
  /** Zoom about a plot-fraction cursor (fx across, fy from TOP). dir<0 = in. */
  zoomAt: (fx: number, fy: number, dir: number, axis: "x" | "y" | "both") => void;
  /** Pan by plot-fraction deltas (drag). */
  panBy: (dfx: number, dfy: number, axis: "x" | "y" | "both") => void;
  reset: () => void;
  zoomed: boolean;
}

function interp(base: readonly [number, number], lo: number, hi: number): [number, number] {
  const span = base[1] - base[0];
  return [base[0] + lo * span, base[0] + hi * span];
}

export function useZoom(): ZoomController {
  const [f, setF] = useState<ZoomFractions>(IDENTITY);

  const viewX = useCallback((base: readonly [number, number]) => interp(base, f.xLo, f.xHi), [f]);
  const viewY = useCallback((base: readonly [number, number]) => interp(base, f.yLo, f.yHi), [f]);

  const zoomAt = useCallback(
    (fx: number, fy: number, dir: number, axis: "x" | "y" | "both") => {
      const z = dir < 0 ? STEP : 1 / STEP;
      setF((p) => {
        const next = { ...p };
        if (axis === "x" || axis === "both") {
          const c = p.xLo + fx * (p.xHi - p.xLo); // cursor in base fractions
          next.xLo = c - (c - p.xLo) * z;
          next.xHi = c + (p.xHi - c) * z;
        }
        if (axis === "y" || axis === "both") {
          const fyb = 1 - fy; // pixels grow downward; value grows upward
          const c = p.yLo + fyb * (p.yHi - p.yLo);
          next.yLo = c - (c - p.yLo) * z;
          next.yHi = c + (p.yHi - c) * z;
        }
        return next;
      });
    },
    [],
  );

  const panBy = useCallback((dfx: number, dfy: number, axis: "x" | "y" | "both") => {
    setF((p) => {
      const next = { ...p };
      if (axis === "x" || axis === "both") {
        const d = -dfx * (p.xHi - p.xLo);
        next.xLo = p.xLo + d;
        next.xHi = p.xHi + d;
      }
      if (axis === "y" || axis === "both") {
        const d = dfy * (p.yHi - p.yLo); // drag down -> view moves up
        next.yLo = p.yLo + d;
        next.yHi = p.yHi + d;
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => setF(IDENTITY), []);
  const zoomed = f.xLo !== 0 || f.xHi !== 1 || f.yLo !== 0 || f.yHi !== 1;

  return { viewX, viewY, zoomAt, panBy, reset, zoomed };
}

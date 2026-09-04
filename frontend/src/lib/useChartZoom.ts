// The ONE interaction grammar of the 2-D charts (Smile, Local-Vol smile,
// Compare, Stacked IV / Densities overlays): wheel-zoom, drag-pan, double-
// click / ⌂ reset and the Y auto-scale policy (lib/autoScaleY) on top of the
// base-relative zoom fractions of lib/useZoom. Extracted from SmileChart so
// every chart behaves identically:
//   wheel          zoom x AND y about the cursor; +Shift = x only; +Alt = y only
//   with Y center / Y fit lit, the policy OWNS y: a wheel or an x-pan zooms /
//                  moves x, then the y window is re-fitted (fit) or recentred
//                  (center) on the data in the x view; Alt+wheel (manual y)
//                  bypasses the policy by design
//   drag           pan both axes — x only while the policy is lit (y is its
//                  to place; a pan with dx ≠ 0 re-applies it)
//   xBaseKey       anything that moves the x BASE outside these handlers — the
//                  coarse brush window, an axis-mode switch — re-applies it too
// The chart keeps ownership of its scales, hover readout and layers; it feeds
// pointer events through `dragMove` / `endDrag` and attaches the wheel
// listener through the SVG ref (native, non-passive so preventDefault works).
import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";
import { clamp } from "./chartScale";
import { useZoom } from "./useZoom";
import type { ZoomController } from "./useZoom";
import { autoScaleYWindow, DEFAULT_AUTOSCALE } from "./autoScaleY";
import type { AutoScaleToggles } from "./autoScaleY";

export interface ChartZoomOptions {
  /** Plot-area size in px (0 while unmeasured: interactions are inert). */
  plotW: number;
  plotH: number;
  /** Plot-area offset inside the SVG (the chart's MARGIN). */
  marginLeft: number;
  marginTop: number;
  /** Y auto-scale toggles (Y center / Y fit); both ON by default. */
  autoScaleY?: AutoScaleToggles;
  /** A string that changes whenever the x BASE moves outside the zoom
   *  handlers (brush window, axis mode): the policy re-applies on change. */
  xBaseKey: string;
}

/** A pointer position (React or native pointer events both fit). */
interface PointerLike {
  clientX: number;
  clientY: number;
}

export interface ChartZoom {
  zoom: ZoomController;
  /** True when Y center or Y fit is lit (the policy owns y). */
  autoActive: boolean;
  /** Arm a drag-pan at the pointer (pointer down). */
  beginDrag: (e: PointerLike) => void;
  /** Feed a pointer move: pans when a drag is armed. Returns true once the
   *  pointer has moved past a click (charts hide their crosshair then). */
  dragMove: (e: PointerLike) => boolean;
  /** Disarm the drag (pointer up): `moved` false = a plain click; null when
   *  no drag was armed. */
  endDrag: () => { moved: boolean } | null;
  /** Disarm without a verdict (pointer leave). */
  cancelDrag: () => void;
  /** Remount key for layers rebuilt per zoom / pan / resize step (the quote
   *  beams): fractions + plot size. Charts append their own axis keys. */
  viewKey: string;
}

export function useChartZoom(
  svgRef: RefObject<SVGSVGElement | null>,
  { plotW, plotH, marginLeft, marginTop, autoScaleY = DEFAULT_AUTOSCALE, xBaseKey }: ChartZoomOptions,
): ChartZoom {
  const zoom = useZoom();
  const autoCenter = autoScaleY.center;
  const autoFit = autoScaleY.fit;
  const autoActive = autoCenter || autoFit;

  // The policy reads the CURRENT fractions / toggles through refs so the
  // wheel listener (subscribed once per size change) never goes stale.
  const fracRef = useRef(zoom.fractions);
  fracRef.current = zoom.fractions;
  const togglesRef = useRef({ center: autoCenter, fit: autoFit });
  togglesRef.current = { center: autoCenter, fit: autoFit };
  const { setYWindow, zoomAt, panBy } = zoom;
  /** Rewrite the y fractions per the policy (a satisfied window is a no-op). */
  const applyAutoY = useCallback(() => {
    const w = autoScaleYWindow(fracRef.current, togglesRef.current);
    if (w !== null) setYWindow(w.yLo, w.yHi);
  }, [setYWindow]);

  /* ---------------- wheel zoom (native, non-passive) ---------------- */
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      if (plotW <= 0 || plotH <= 0) return;
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const fx = clamp((e.clientX - rect.left - marginLeft) / plotW, 0, 1);
      const fy = clamp((e.clientY - rect.top - marginTop) / plotH, 0, 1);
      const axis = e.shiftKey ? "x" : e.altKey ? "y" : "both";
      if (autoActive && axis !== "y") {
        // The policy owns y: zoom x only, then re-apply it. Alt+wheel — the
        // manual y-only zoom — falls through untouched (no policy).
        zoomAt(fx, fy, e.deltaY, "x");
        applyAutoY();
      } else {
        zoomAt(fx, fy, e.deltaY, axis);
      }
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [svgRef, plotW, plotH, marginLeft, marginTop, autoActive, zoomAt, applyAutoY]);

  // Re-apply the policy when the x base moves OUTSIDE the handlers (brush,
  // axis mode) and when a chip flips on (so enabling one takes effect at
  // once). Reset is already the identity, so no trigger is needed there. No
  // loop: the deps exclude the fractions, and a satisfied window is a no-op.
  useEffect(() => {
    if (!autoActive) return;
    applyAutoY();
  }, [xBaseKey, autoCenter, autoFit, autoActive, applyAutoY]);

  /* ---------------- drag-pan ---------------- */
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const beginDrag = (e: PointerLike) => {
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  };
  const dragMove = (e: PointerLike): boolean => {
    const d = drag.current;
    if (!d || plotW <= 0 || plotH <= 0) return false;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) {
      // With the policy lit, y is ITS to place: pan x only, then re-apply
      // (fit = stay on the base, center = keep the manual span centred).
      panBy(dx / plotW, dy / plotH, autoActive ? "x" : "both");
      if (autoActive && dx !== 0) applyAutoY();
      drag.current = { x: e.clientX, y: e.clientY, moved: true };
      return true;
    }
    return d.moved;
  };
  const endDrag = () => {
    const d = drag.current;
    drag.current = null;
    return d === null ? null : { moved: d.moved };
  };
  const cancelDrag = () => {
    drag.current = null;
  };

  const f = zoom.fractions;
  const viewKey = `${f.xLo},${f.xHi},${f.yLo},${f.yHi},${plotW},${plotH}`;

  return { zoom, autoActive, beginDrag, dragMove, endDrag, cancelDrag, viewKey };
}

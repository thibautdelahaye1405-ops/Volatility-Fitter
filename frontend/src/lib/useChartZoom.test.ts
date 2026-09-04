// The shared chart interaction grammar: the Y auto-scale policy owning y on
// x-pans / x-base moves, Alt-style manual y left alone, the drag verdicts and
// the remount key.
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useChartZoom } from "./useChartZoom";
import type { ChartZoomOptions } from "./useChartZoom";

const base = (over: Partial<ChartZoomOptions> = {}): ChartZoomOptions => ({
  plotW: 100,
  plotH: 100,
  marginLeft: 10,
  marginTop: 5,
  xBaseKey: "a",
  ...over,
});
const ref = { current: null as SVGSVGElement | null };

describe("useChartZoom", () => {
  it("a drag pans x, and with Y fit lit the y window snaps back to the base", () => {
    const { result } = renderHook(() => useChartZoom(ref, base()));
    act(() => result.current.beginDrag({ clientX: 50, clientY: 50 }));
    let moved = false;
    act(() => {
      moved = result.current.dragMove({ clientX: 70, clientY: 80 });
    });
    expect(moved).toBe(true);
    const f = result.current.zoom.fractions;
    expect(f.xLo).toBeCloseTo(-0.2, 12); // dragged right: view moves left
    expect(f.xHi).toBeCloseTo(0.8, 12);
    expect(f.yLo).toBe(0); // fit: y re-pinned to the auto-fitted base
    expect(f.yHi).toBe(1);
    expect(result.current.endDrag()).toEqual({ moved: true });
    expect(result.current.endDrag()).toBeNull(); // nothing armed any more
  });

  it("with both chips off, a drag pans y too and a short move is a click", () => {
    const { result } = renderHook(() =>
      useChartZoom(ref, base({ autoScaleY: { center: false, fit: false } })),
    );
    expect(result.current.autoActive).toBe(false);
    act(() => result.current.beginDrag({ clientX: 0, clientY: 0 }));
    act(() => {
      result.current.dragMove({ clientX: 1, clientY: 0 }); // within the click slack
    });
    expect(result.current.zoom.zoomed).toBe(false);
    expect(result.current.endDrag()).toEqual({ moved: false });
    act(() => result.current.beginDrag({ clientX: 0, clientY: 0 }));
    act(() => {
      result.current.dragMove({ clientX: 0, clientY: 30 });
    });
    expect(result.current.zoom.fractions.yLo).toBeCloseTo(0.3, 12);
  });

  it("Y center keeps the manual y span and recentres it when the x base moves", () => {
    const { result, rerender } = renderHook((o: ChartZoomOptions) => useChartZoom(ref, o), {
      initialProps: base({ autoScaleY: { center: true, fit: false } }),
    });
    act(() => result.current.zoom.setYWindow(0.5, 0.9)); // manual y zoom (span 0.4)
    rerender(base({ autoScaleY: { center: true, fit: false }, xBaseKey: "b" })); // brush moved
    const f = result.current.zoom.fractions;
    expect(f.yHi - f.yLo).toBeCloseTo(0.4, 12);
    expect((f.yLo + f.yHi) / 2).toBeCloseTo(0.5, 12);
  });

  it("flipping Y fit on takes effect immediately; the viewKey tracks the fractions and size", () => {
    const { result, rerender } = renderHook((o: ChartZoomOptions) => useChartZoom(ref, o), {
      initialProps: base({ autoScaleY: { center: false, fit: false } }),
    });
    act(() => result.current.zoom.setYWindow(0.2, 0.4));
    const before = result.current.viewKey;
    rerender(base({ autoScaleY: { center: false, fit: true } }));
    expect(result.current.zoom.fractions.yLo).toBe(0);
    expect(result.current.viewKey).not.toBe(before);
    expect(result.current.viewKey).toBe("0,1,0,1,100,100");
  });
});

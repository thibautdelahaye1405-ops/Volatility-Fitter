import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { clampWindow, useZoom } from "./useZoom";

describe("clampWindow — the explicit-setter guard", () => {
  it("orders swapped bounds and passes a healthy window through unchanged", () => {
    expect(clampWindow(0.8, 0.2)).toEqual([0.2, 0.8]);
    expect(clampWindow(0, 1)).toEqual([0, 1]);
    expect(clampWindow(-0.5, 1.5)).toEqual([-0.5, 1.5]);
  });

  it("grows a sub-minimum span about its midpoint (1e-3 guard, like the wheel)", () => {
    const w = clampWindow(0.5, 0.5)!;
    expect(w[1] - w[0]).toBeCloseTo(1e-3, 12);
    expect((w[0] + w[1]) / 2).toBeCloseTo(0.5, 12);
  });

  it("rejects non-finite bounds", () => {
    expect(clampWindow(NaN, 1)).toBeNull();
    expect(clampWindow(0, Infinity)).toBeNull();
  });
});

describe("useZoom.setYWindow — explicit y-fraction setter for the auto-scale policy", () => {
  it("rewrites only the y fractions and flows through viewY", () => {
    const { result } = renderHook(() => useZoom());
    act(() => result.current.setYWindow(0.25, 0.75));
    expect(result.current.fractions).toEqual({ xLo: 0, xHi: 1, yLo: 0.25, yHi: 0.75 });
    expect(result.current.zoomed).toBe(true);
    expect(result.current.viewY([0, 100])).toEqual([25, 75]);
    expect(result.current.viewX([0, 100])).toEqual([0, 100]);
  });

  it("keeps the SAME fractions object on a no-op call (viewKey must not churn)", () => {
    const { result } = renderHook(() => useZoom());
    const before = result.current.fractions;
    act(() => result.current.setYWindow(0, 1));
    expect(result.current.fractions).toBe(before);
    act(() => result.current.setYWindow(NaN, 1)); // rejected, also a no-op
    expect(result.current.fractions).toBe(before);
  });

  it("reset returns to the identity after an explicit window", () => {
    const { result } = renderHook(() => useZoom());
    act(() => result.current.setYWindow(0.3, 0.6));
    act(() => result.current.reset());
    expect(result.current.fractions).toEqual({ xLo: 0, xHi: 1, yLo: 0, yHi: 1 });
    expect(result.current.zoomed).toBe(false);
  });
});

// Overlay-chart geometry helpers: in-view y auto-fit (the Y fit base),
// NaN-splitting paths and the sub-zero fill.
import { describe, expect, it } from "vitest";
import { fullDomain, inViewYDomain, negativeFillPath, seriesPath } from "./overlayPaths";

const id = (v: number) => v;
const s1 = { xs: [-1, 0, 1, 2], ys: [0.3, 0.2, 0.25, 0.4] };
const s2 = { xs: [-1, 0, 1, 2], ys: [0.1, 0.15, 0.12, 0.9] };

describe("fullDomain", () => {
  it("spans every finite value across series and ignores NaN", () => {
    expect(fullDomain([s1, s2], (s) => s.ys)).toEqual({ lo: 0.1, hi: 0.9 });
    expect(fullDomain([{ xs: [NaN], ys: [NaN] }], (s) => s.xs)).toBeNull();
  });
});

describe("inViewYDomain", () => {
  it("fits only the points inside the x window (either bound order), padded 6 %", () => {
    const d = inViewYDomain([s1, s2], 1, -1); // swapped bounds are fine
    const pad = (0.3 - 0.1) * 0.06;
    expect(d.lo).toBeCloseTo(0.1 - pad, 12);
    expect(d.hi).toBeCloseTo(0.3 + pad, 12);
    // x = 2 (the 0.4 / 0.9 points) is outside the window
    expect(d.hi).toBeLessThan(0.4);
  });

  it("pins the floor at 0 with zeroBaseline unless the data dips below it", () => {
    expect(inViewYDomain([s1], -1, 2, true).lo).toBe(0);
    const dip = { xs: [0, 1], ys: [0.5, -0.2] };
    const d = inViewYDomain([dip], 0, 1, true);
    expect(d.lo).toBeLessThan(-0.2);
  });

  it("falls back to the full extent when nothing is in view, and to [0, 1] with no data", () => {
    const d = inViewYDomain([s1], 10, 11);
    expect(d.lo).toBeLessThan(0.2);
    expect(d.hi).toBeGreaterThan(0.4);
    expect(inViewYDomain([], 0, 1)).toEqual({ lo: 0, hi: 1 });
  });
});

describe("paths", () => {
  it("breaks the polyline at a non-finite point instead of bridging it", () => {
    const p = seriesPath({ xs: [0, 1, NaN, 3], ys: [0, 1, 2, 3] }, id, id);
    expect(p).toBe("M0.0,0.0L1.0,1.0M3.0,3.0");
  });

  it("fills only the sub-zero excursion, closed along y = 0", () => {
    const p = negativeFillPath({ xs: [0, 1, 2], ys: [1, -1, 1] }, id, (y) => -y);
    // y >= 0 collapses onto the baseline (mapped 0), the dip reads at 1
    expect(p).toBe("M0.0,0.0L1.0,1.0L2.0,0.0L2.0,0.0L0.0,0.0Z");
    expect(negativeFillPath({ xs: [], ys: [] }, id, id)).toBe("");
  });
});

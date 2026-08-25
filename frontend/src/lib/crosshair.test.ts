import { describe, expect, it } from "vitest";

import { linearScale } from "./chartScale";
import { crosshairLabel, crosshairPoint } from "./crosshair";

// A realistic chart setup: SVG at client (100, 50), 40/10 margins, a
// 200x100 plot box, x in [0, 2] and y (drawn downward) in [0.1, 0.3].
const rect = { left: 100, top: 50 };
const margin = { left: 40, top: 10 };
const plotW = 200;
const plotH = 100;
const xs = linearScale([0, 2], [0, plotW]);
const ys = linearScale([0.1, 0.3], [plotH, 0]);

const at = (clientX: number, clientY: number) =>
  crosshairPoint(clientX, clientY, rect, margin, plotW, plotH, xs.invert, ys.invert);

describe("crosshairPoint — pointer to plot-local pixels and domain units", () => {
  it("maps a pointer inside the plot box", () => {
    const pt = at(240, 110); // plot-local (100, 50): both midpoints
    expect(pt).not.toBeNull();
    expect(pt!.px).toBe(100);
    expect(pt!.py).toBe(50);
    expect(pt!.x).toBeCloseTo(1, 12);
    expect(pt!.y).toBeCloseTo(0.2, 12);
  });

  it("maps the plot corners inclusively (y-range runs downward)", () => {
    const tl = at(140, 60); // plot-local (0, 0): x lo, y HI
    expect(tl).toMatchObject({ px: 0, py: 0, x: 0, y: 0.3 });
    const br = at(340, 160); // plot-local (plotW, plotH): x hi, y LO
    expect(br).toMatchObject({ px: plotW, py: plotH, x: 2 });
    expect(br!.y).toBeCloseTo(0.1, 12);
  });

  it("returns null outside the plot box, on every side", () => {
    expect(at(139, 110)).toBeNull(); // left of the plot
    expect(at(341, 110)).toBeNull(); // right
    expect(at(240, 59)).toBeNull(); // above
    expect(at(240, 161)).toBeNull(); // below
  });

  it("returns null on a degenerate plot or a non-finite inversion", () => {
    expect(crosshairPoint(240, 110, rect, margin, 0, plotH, xs.invert, ys.invert)).toBeNull();
    expect(crosshairPoint(240, 110, rect, margin, plotW, plotH, () => NaN, ys.invert)).toBeNull();
    expect(crosshairPoint(240, 110, rect, margin, plotW, plotH, xs.invert, () => Infinity)).toBeNull();
  });
});

describe("crosshairLabel — the badge text", () => {
  it("joins the two formatted domain values with the badge separator", () => {
    const pt = at(240, 110)!;
    expect(crosshairLabel(pt, (v) => `k ${v.toFixed(2)}`, (v) => `σ ${(v * 100).toFixed(1)}%`)).toBe(
      "k 1.00 · σ 20.0%",
    );
  });
});

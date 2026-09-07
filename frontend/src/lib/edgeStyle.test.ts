// Arrow encoders: width is monotone + anchored in relationship uncertainty
// (vol points), colour is exact at the beta stops, and the SVG head geometry
// puts the tip at the segment end with the base offset by +/- half.
import { describe, expect, it } from "vitest";
import {
  arrowHeadPoints,
  BETA_LEGEND,
  betaColor,
  bezierHeadPoints,
  bundleWidth,
  edgeWidth,
  SIGMA_TIGHT_PTS,
  SIGMA_WIDE_PTS,
  WIDTH_LEGEND,
  WIDTH_MAX,
  WIDTH_MIN,
} from "./edgeStyle";
import { precisionFromSigmaPts } from "./precisionUnits";

describe("edgeWidth", () => {
  it("is monotone decreasing in sigma (increasing in precision)", () => {
    const sigmas = [20, 10, 5, 2, 1, 0.5, 0.25, 0.1];
    const widths = sigmas.map((s) => edgeWidth(precisionFromSigmaPts(s)));
    for (let i = 1; i < widths.length; i++) {
      expect(widths[i]).toBeGreaterThanOrEqual(widths[i - 1]);
    }
  });

  it("hits the anchors exactly", () => {
    expect(edgeWidth(precisionFromSigmaPts(SIGMA_WIDE_PTS))).toBeCloseTo(WIDTH_MIN, 12);
    expect(edgeWidth(precisionFromSigmaPts(SIGMA_TIGHT_PTS))).toBeCloseTo(WIDTH_MAX, 12);
    // Beyond the anchors: clamped, not extrapolated.
    expect(edgeWidth(precisionFromSigmaPts(50))).toBeCloseTo(WIDTH_MIN, 12);
    expect(edgeWidth(precisionFromSigmaPts(0.05))).toBeCloseTo(WIDTH_MAX, 12);
  });

  it("hits the geometric-mean sigma (~1.58 pt) at the midpoint width", () => {
    const midSigma = Math.sqrt(SIGMA_TIGHT_PTS * SIGMA_WIDE_PTS);
    expect(midSigma).toBeCloseTo(1.5811, 3);
    expect(edgeWidth(precisionFromSigmaPts(midSigma))).toBeCloseTo((WIDTH_MIN + WIDTH_MAX) / 2, 9);
  });

  it("draws a dead or undefined relation at WIDTH_MIN", () => {
    expect(edgeWidth(0)).toBe(WIDTH_MIN);
    expect(edgeWidth(-5)).toBe(WIDTH_MIN);
    expect(edgeWidth(NaN)).toBe(WIDTH_MIN);
    expect(edgeWidth(Infinity)).toBe(WIDTH_MIN);
  });

  it("bundleWidth is the same encoder applied to Sigma-p", () => {
    const p = precisionFromSigmaPts(2);
    expect(bundleWidth(p)).toBe(edgeWidth(p));
  });
});

describe("betaColor", () => {
  it("matches the exact stops", () => {
    expect(betaColor(1)).toBe("rgb(148 163 184)");
    expect(betaColor(0)).toBe("rgb(56 189 248)");
    expect(betaColor(1.75)).toBe("rgb(251 191 36)");
    expect(betaColor(2.5)).toBe("rgb(249 115 22)");
    expect(betaColor(10)).toBe("rgb(249 115 22)"); // clamped past 2.5
    expect(betaColor(-1)).toBe("rgb(251 113 133)");
    expect(betaColor(-0.001)).toBe("rgb(251 113 133)");
  });

  it("falls back to slate for a non-finite beta", () => {
    expect(betaColor(NaN)).toBe("rgb(148 163 184)");
    expect(betaColor(Infinity)).toBe("rgb(148 163 184)");
  });

  it("BETA_LEGEND stops are ascending and match the model's anchors", () => {
    const betas = BETA_LEGEND.map((s) => s.beta);
    for (let i = 1; i < betas.length; i++) expect(betas[i]).toBeGreaterThan(betas[i - 1]);
    expect(betas).toEqual([0, 0.5, 1, 1.75, 2.5]);
  });
});

describe("WIDTH_LEGEND", () => {
  it("precomputes widths via the real precision pipeline, descending as sigma tightens", () => {
    expect(WIDTH_LEGEND.map((s) => s.sigmaPts)).toEqual([10, 2, 0.5]);
    for (let i = 1; i < WIDTH_LEGEND.length; i++) {
      expect(WIDTH_LEGEND[i].width).toBeGreaterThan(WIDTH_LEGEND[i - 1].width);
    }
    expect(WIDTH_LEGEND[0].width).toBeCloseTo(WIDTH_MIN, 12);
  });
});

describe("arrowHeadPoints", () => {
  it("puts the tip at the end and the base at +/- half, `len` back, for an axis-aligned segment", () => {
    const points = arrowHeadPoints(0, 0, 10, 0, 9, 4);
    expect(points).toBe("10,0 1,4 1,-4");
  });

  it("rotates correctly for a vertical segment", () => {
    const points = arrowHeadPoints(0, 0, 0, 10, 9, 4);
    expect(points).toBe("0,10 -4,1 4,1");
  });

  it("returns empty for a degenerate (zero-length) segment", () => {
    expect(arrowHeadPoints(5, 5, 5, 5)).toBe("");
  });
});

describe("bezierHeadPoints", () => {
  const p0 = { x: 0, y: 0 };
  const c = { x: 5, y: 0 };
  const p2 = { x: 10, y: 0 };

  it("end: tip at P2, direction P2 - C", () => {
    expect(bezierHeadPoints(p0, c, p2, "end", 9, 4)).toBe(arrowHeadPoints(c.x, c.y, p2.x, p2.y, 9, 4));
  });

  it("start: tip at P0, direction P0 - C", () => {
    expect(bezierHeadPoints(p0, c, p2, "start", 9, 4)).toBe(arrowHeadPoints(c.x, c.y, p0.x, p0.y, 9, 4));
  });
});

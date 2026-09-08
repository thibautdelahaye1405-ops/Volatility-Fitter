// lib/volColormap: the sequential vol ramp's ends and the diverging ramp used
// by signed sheets (blue below zero, the neutral slate at zero, red above;
// symmetric and clamped).
import { describe, expect, it } from "vitest";
import { DIVERGING_GRADIENT_CSS, divergingColor, volColor } from "./volColormap";

describe("volColor", () => {
  it("runs blue → red over [0, 1]", () => {
    expect(volColor(0)).toBe("rgb(59 130 246)");
    expect(volColor(1)).toBe("rgb(239 68 68)");
    expect(volColor(-1)).toBe(volColor(0));
    expect(volColor(2)).toBe(volColor(1));
  });
});

describe("divergingColor", () => {
  it("is the neutral slate at zero, blue at −1, red at +1", () => {
    expect(divergingColor(0)).toBe("rgb(51 65 85)");
    expect(divergingColor(-1)).toBe("rgb(59 130 246)");
    expect(divergingColor(1)).toBe("rgb(239 68 68)");
  });
  it("clamps beyond ±1 and treats NaN as zero", () => {
    expect(divergingColor(5)).toBe(divergingColor(1));
    expect(divergingColor(-5)).toBe(divergingColor(-1));
    expect(divergingColor(Number.NaN)).toBe(divergingColor(0));
  });
  it("is symmetric in magnitude: ±u interpolate the same fraction |u| toward their end", () => {
    const parse = (s: string) => s.match(/\d+/g)!.map(Number);
    const mid = parse(divergingColor(0));
    const red = parse(divergingColor(1));
    const blue = parse(divergingColor(-1));
    const halfway = (a: number[], b: number[]) => a.map((v, i) => Math.round(v + 0.5 * (b[i] - v)));
    expect(parse(divergingColor(0.5))).toEqual(halfway(mid, red));
    expect(parse(divergingColor(-0.5))).toEqual(halfway(mid, blue));
  });
  it("the legend gradient names the same three stops", () => {
    expect(DIVERGING_GRADIENT_CSS).toContain("rgb(59 130 246)");
    expect(DIVERGING_GRADIENT_CSS).toContain("rgb(51 65 85)");
    expect(DIVERGING_GRADIENT_CSS).toContain("rgb(239 68 68)");
  });
});

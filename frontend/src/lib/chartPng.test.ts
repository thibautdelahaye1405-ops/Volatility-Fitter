// Chart-as-PNG helpers (UI SHELL v2 wave 3, A3): filename, chart lookup and
// the style inlining (jsdom has no real layout, so only the mechanics).
import { describe, expect, it } from "vitest";
import { CHART_CARD_ATTR, chartPngFilename, findActiveChartSvg, inlineSvgStyles } from "./chartPng";

describe("chartPngFilename", () => {
  it("is <ticker>_<expiry>_<view>.png with safe characters", () => {
    expect(chartPngFilename("SPY", "2026-12-18", "smile")).toBe("SPY_2026-12-18_smile.png");
    expect(chartPngFilename("^SPX", "2026-12-18", "stacked iv")).toBe("SPX_2026-12-18_stacked-iv.png");
    expect(chartPngFilename("", "", "")).toBe("chart_node_chart.png");
  });
});

describe("findActiveChartSvg / inlineSvgStyles", () => {
  it("finds the first svg inside the marked chart card and inlines styles on a clone", () => {
    document.body.innerHTML = `
      <div><svg id="other"></svg></div>
      <div ${CHART_CARD_ATTR}=""><div><svg id="chart" width="300" height="200">
        <text class="fill-slate-500" style="fill: rgb(1, 2, 3)">x</text></svg></div></div>`;
    const svg = findActiveChartSvg();
    expect(svg?.id).toBe("chart");
    const clone = inlineSvgStyles(svg!);
    expect(clone).not.toBe(svg);
    expect(clone.getAttribute("xmlns")).toBe("http://www.w3.org/2000/svg");
    expect(clone.getAttribute("width")).toBe("300");
    const text = clone.querySelector("text")!;
    expect(text.getAttribute("class")).toBeNull();
    expect(text.getAttribute("style")).toContain("fill:rgb(1, 2, 3)");
    // The live SVG is untouched.
    expect(svg!.querySelector("text")!.getAttribute("class")).toBe("fill-slate-500");
  });

  it("returns null without a marked card", () => {
    document.body.innerHTML = "<svg></svg>";
    expect(findActiveChartSvg()).toBeNull();
  });
});

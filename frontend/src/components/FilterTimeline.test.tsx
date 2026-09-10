// FilterTimeline render lock (SERIES ARC S5 rider): the optional `cursor`
// prop draws one violet line at the step's x (the linear step scale over the
// inner width, offset by the left margin) and is absent by default — the
// live Filter view is untouched. The element size is stubbed (jsdom has no
// layout) so the SVG renders.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FilterTimeline } from "./FilterTimeline";
import type { FilterStepWire } from "../lib/filterTimeline";

vi.mock("../lib/useElementSize", () => ({
  useElementSize: () => ({ ref: { current: null }, size: { width: 400, height: 300 } }),
}));

const step = (ts: number): FilterStepWire => ({
  ts, dtDays: 0.02,
  prediction: [0.2, -0.3, 0.1], predictionStd: [0.01, 0.02, 0.05],
  observation: [0.21, -0.29, 0.12], observationStd: [0.005, 0.01, 0.02],
  innovation: [0.01, 0.01, 0.02], zeta: [0.9, 0.4, 0.3], gain: [0.8, 0.6, 0.4],
  posterior: [0.208, -0.292, 0.115], posteriorStd: [0.004, 0.009, 0.018],
  processBreakdown: { clock: [1e-6, 2e-6, 3e-6] }, transportDistance: 0.001,
  provenance: "update", resetReason: null, contaminated: false,
});
const steps = [step(1_760_000_000), step(1_760_000_900), step(1_760_001_800)];

afterEach(cleanup);

describe("FilterTimeline cursor", () => {
  it("draws no cursor by default", () => {
    const { container } = render(<FilterTimeline steps={steps} handle={0} />);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelector("[data-testid=filter-cursor]")).toBeNull();
  });

  it("draws the cursor at the step's x: margin + i/(n−1) of the inner width", () => {
    const { container } = render(<FilterTimeline steps={steps} handle={0} cursor={1} />);
    const line = container.querySelector("[data-testid=filter-cursor]");
    expect(line).not.toBeNull();
    // ML = 46, MR = 6 → inner width 348; step 1 of 3 sits at its midpoint.
    expect(Number(line?.getAttribute("x1"))).toBeCloseTo(46 + 174, 6);
  });

  it("ignores a cursor outside the ring", () => {
    const { container } = render(<FilterTimeline steps={steps} handle={0} cursor={7} />);
    expect(container.querySelector("[data-testid=filter-cursor]")).toBeNull();
  });
});

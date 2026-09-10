// The Term chart's lanes slot: the layer draws one ATM path per lane (by
// `data-lane`) with markers, the var-swap path thinner and dashed, and the
// chart lists the lanes in its legend. jsdom has no ResizeObserver, so the
// chart's plot stays unmeasured (no SVG) — the legend row is what the
// TermChart render checks.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import LaneTermLayer, { VARSWAP_DASH, laneTermExtent, laneTermPath } from "./LaneTermLayer";
import type { TermLane } from "./LaneTermLayer";
import TermChart from "../TermChart";

beforeAll(() => {
  class RO {
    observe() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});
afterEach(cleanup);

const toX = (t: number) => t * 100;
const toY = (v: number) => 100 - v * 100;

const lanes: TermLane[] = [
  {
    id: "svi", label: "SVI free", colour: "#3b82f6", dash: "6 3",
    points: [
      { expiry: "b", t: 0.2, atmVol: 0.25, varSwapVol: 0.26 },
      { expiry: "a", t: 0.1, atmVol: 0.3, varSwapVol: 0.31 },
      { expiry: "c", t: 0.3, atmVol: null, varSwapVol: 0.24 },
    ],
  },
  { id: "lv", label: "Local Vol", colour: "#f97316", dash: "", points: [{ expiry: "a", t: 0.1, atmVol: 0.28, varSwapVol: null }] },
];

describe("laneTermPath / laneTermExtent", () => {
  it("sorts by t and skips the unfitted rungs; fewer than two points draw nothing", () => {
    expect(laneTermPath(lanes[0].points, (p) => p.atmVol, toX, toY)).toBe("M10.00,70.00L20.00,75.00");
    expect(laneTermPath(lanes[0].points, (p) => p.varSwapVol, toX, toY)).toBe("M10.00,69.00L20.00,74.00L30.00,76.00");
    expect(laneTermPath(lanes[1].points, (p) => p.atmVol, toX, toY)).toBe("");
  });
  it("the extent spans both vols and every finite rung", () => {
    expect(laneTermExtent(lanes)).toEqual({ tLo: 0.1, tHi: 0.3, vLo: 0.24, vHi: 0.31 });
    expect(laneTermExtent([])).toBeNull();
    expect(laneTermExtent([{ ...lanes[1], points: [{ expiry: "x", t: 0.1, atmVol: null, varSwapVol: null }] }])).toBeNull();
  });
});

describe("LaneTermLayer", () => {
  it("one ATM path per drawable lane, markers per fitted rung, the var-swap path thinner and dashed", () => {
    const { container } = render(
      <svg>
        <LaneTermLayer lanes={lanes} toX={toX} toY={toY} />
      </svg>,
    );
    expect(container.querySelectorAll("path[data-lane]").length).toBe(1);
    const atm = container.querySelector('path[data-lane="svi"]')!;
    expect(atm.getAttribute("stroke")).toBe("#3b82f6");
    expect(atm.getAttribute("stroke-dasharray")).toBe("6 3");
    expect(atm.getAttribute("stroke-width")).toBe("1.5");
    const vs = container.querySelector('path[data-lane-vs="svi"]')!;
    expect(vs.getAttribute("stroke-width")).toBe("1");
    expect(vs.getAttribute("stroke-dasharray")).toBe(VARSWAP_DASH);
    expect(container.querySelector('path[data-lane-vs="lv"]')).toBeNull();
    expect(container.querySelectorAll('circle[data-lane-marker="svi"]').length).toBe(2);
    expect(container.querySelectorAll('circle[data-lane-marker="lv"]').length).toBe(1);
  });
});

describe("TermChart lanes slot", () => {
  it("lists the lanes in the legend", () => {
    render(
      <TermChart
        points={[{ expiry: "a", t: 0.1, tau: 0.1, atmVol: 0.2, w0: 0.004, varSwapVol: 0.21, maxIvErrorBp: 3 }]}
        curve={{ t: [0.05, 0.1, 0.2], tau: [0.05, 0.1, 0.2], w: [0.002, 0.004, 0.008], vol: [0.2, 0.2, 0.2] }}
        events={[]}
        eventsEnabled={false}
        axisClock="real"
        dividends={[]}
        lanes={lanes}
      />,
    );
    expect(screen.getByText("SVI free")).toBeTruthy();
    expect(screen.getByText("Local Vol")).toBeTruthy();
    expect(document.querySelectorAll("[data-lane-legend]").length).toBe(2);
  });
});

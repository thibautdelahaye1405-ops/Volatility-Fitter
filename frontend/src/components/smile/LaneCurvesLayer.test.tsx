// The Smile chart's lanes slot: the layer draws one path per lane through
// the chart's pixel maps (by `data-lane`), faint / dashed as asked, and the
// chart lists the labelled lanes in its legend. jsdom has no
// ResizeObserver, so the chart's plot stays unmeasured (no SVG) — the
// legend row is what the SmileChart render checks.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import LaneCurvesLayer, { laneCurvePath } from "./LaneCurvesLayer";
import type { LaneCurve } from "./LaneCurvesLayer";
import SmileChart from "../SmileChart";

beforeAll(() => {
  class RO {
    observe() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});
afterEach(cleanup);

const lanes: LaneCurve[] = [
  { id: "svi", label: "SVI free", points: [{ k: -0.2, vol: 0.3 }, { k: 0, vol: 0.2 }, { k: 0.2, vol: 0.25 }], colour: "#3b82f6", dash: "6 3" },
  { id: "ghost-0", label: "", points: [{ k: -0.2, vol: 0.31 }, { k: 0.2, vol: 0.26 }], colour: "#22c55e", dash: "", width: 1, opacity: 0.35 },
  { id: "short", label: "one point", points: [{ k: 0, vol: 0.2 }], colour: "#fff", dash: "" },
];

describe("LaneCurvesLayer", () => {
  it("builds a path through the pixel maps; fewer than two points draw nothing", () => {
    const toX = (k: number) => 100 + 100 * k;
    const toY = (v: number) => 100 - 100 * v;
    expect(laneCurvePath(lanes[0].points, toX, toY)).toBe("M80.00,70.00L100.00,80.00L120.00,75.00");
    expect(laneCurvePath(lanes[2].points, toX, toY)).toBe("");
  });

  it("renders one path per drawable lane with its colour, dash and opacity", () => {
    const { container } = render(
      <svg>
        <LaneCurvesLayer lanes={lanes} toX={(k) => 100 + 100 * k} toY={(v) => 100 - 100 * v} />
      </svg>,
    );
    const paths = container.querySelectorAll("path[data-lane]");
    expect(paths.length).toBe(2);
    const svi = container.querySelector('path[data-lane="svi"]')!;
    expect(svi.getAttribute("stroke")).toBe("#3b82f6");
    expect(svi.getAttribute("stroke-dasharray")).toBe("6 3");
    expect(svi.getAttribute("stroke-width")).toBe("1.5");
    const ghost = container.querySelector('path[data-lane="ghost-0"]')!;
    expect(ghost.getAttribute("stroke-dasharray")).toBeNull();
    expect(ghost.getAttribute("stroke-opacity")).toBe("0.35");
    expect(ghost.getAttribute("stroke-width")).toBe("1");
  });
});

describe("SmileChart lanes slot", () => {
  it("lists the labelled lanes in the legend (ghosts stay unlisted)", () => {
    render(
      <SmileChart
        market={{ forward: 100, quotes: [], model: [{ k: -0.1, vol: 0.2 }, { k: 0.1, vol: 0.2 }], inferred: null, live: false, warming: false, spot: 100, timestamp: null }}
        calib={null}
        prior={[]}
        kWindow={[-0.3, 0.3]}
        onKWindowChange={() => {}}
        fullRange={[-0.3, 0.3]}
        lanes={lanes}
      />,
    );
    expect(screen.getByText("SVI free")).toBeTruthy();
    expect(screen.getByText("one point")).toBeTruthy();
    expect(document.querySelectorAll("[data-lane-legend]").length).toBe(2);
  });
});

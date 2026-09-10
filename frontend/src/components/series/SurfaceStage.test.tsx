// The Series lens's Surface stage: one sheet per visible lane under ONE
// camera / window key (compact when several), the difference mode's
// production sheet beside a diverging lane − production heatmap in vol bp,
// the empty states and the loading veil over the last drawn frame. The mesh
// and the heatmap are stubbed (they need a measured plot) — their props are
// what this locks.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SurfaceStage from "./SurfaceStage";
import { gridColumns } from "./SurfaceStage";
import type { FramePayload, LaneFrameDoc, LaneSpec, SurfaceGridDoc } from "../../lib/seriesTypes";

interface MeshStubProps {
  data: { t: number[] };
  legendLabel?: string;
  axisMode?: string;
  cameraKey?: string;
  windowKey?: string;
  chartId?: string;
  compact?: boolean;
}
interface HeatStubProps {
  xNodes: number[];
  legendLabel?: string;
  diverging?: boolean;
  formatValue: (v: number) => string;
  chartId?: string;
}

vi.mock("../SurfaceMesh", async () => {
  const React = await import("react");
  return {
    default: (p: MeshStubProps) =>
      React.createElement("div", {
        "data-testid": "mesh", "data-chart": p.chartId, "data-camera": p.cameraKey, "data-window": p.windowKey,
        "data-legend": p.legendLabel, "data-axis": p.axisMode, "data-compact": String(p.compact === true),
        "data-rows": p.data.t.length,
      }),
  };
});
vi.mock("../LocalVolHeatmap", async () => {
  const React = await import("react");
  return {
    default: (p: HeatStubProps) =>
      React.createElement("div", {
        "data-testid": "heat", "data-chart": p.chartId, "data-legend": p.legendLabel,
        "data-diverging": String(p.diverging === true), "data-lo": p.formatValue(-0.0012),
        "data-x0": p.xNodes[0].toFixed(3), "data-cols": p.xNodes.length,
      }),
  };
});

afterEach(cleanup);

const K = [-0.2, -0.1, 0, 0.1];
const grid = (expiries: string[], tau: number[], level: number): SurfaceGridDoc => ({
  k: K, tau, expiries, sigma: expiries.map(() => K.map(() => level)),
});
const laneDoc = (laneId: string, surface: SurfaceGridDoc | null): LaneFrameDoc =>
  ({ laneId, slices: [], surface, term: [], metrics: {}, status: "done" });
const spec = (id: string, patch: Partial<LaneSpec> = {}): LaneSpec => ({
  id, name: id.toUpperCase(), family: "lqd", colour: null, fitMode: null,
  patchFit: {}, patchOptions: {}, production: false, seed: "cold", ...patch,
});
const EXP = ["2026-09-18", "2026-10-16", "2026-12-18"];
const frame: FramePayload = {
  seriesId: "S1", idx: 0, ts: "2026-09-08T15:45:00", quoteKind: "quotes", spot: 100,
  expiries: EXP, forwards: {}, market: {},
  lanes: { a: laneDoc("a", grid(EXP, [0.03, 0.1, 0.28], 0.2)), b: laneDoc("b", grid(EXP, [0.03, 0.1, 0.28], 0.21)), c: laneDoc("c", null) },
};
const lanes = [spec("a", { production: true }), spec("b"), spec("c")];

const stage = (over: Partial<Parameters<typeof SurfaceStage>[0]> = {}) => (
  <SurfaceStage frame={frame} lanes={lanes} hidden={new Set()} seriesId="S1" ticker="SPY" mode="sheets" axisMode="k" loading={false} {...over} />
);

describe("gridColumns", () => {
  it("1 · 2 (two to four) · 3", () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(gridColumns)).toEqual([1, 1, 2, 2, 2, 3, 3]);
  });
});

describe("SurfaceStage sheets", () => {
  it("one compact sheet per visible lane with a surface, under one camera + window key", () => {
    render(stage());
    const meshes = screen.getAllByTestId("mesh");
    expect(meshes.map((m) => m.getAttribute("data-chart"))).toEqual(["series:a", "series:b"]);
    expect(meshes.every((m) => m.getAttribute("data-camera") === "series:S1")).toBe(true);
    expect(meshes.every((m) => m.getAttribute("data-window") === "series:S1")).toBe(true);
    expect(meshes.every((m) => m.getAttribute("data-compact") === "true")).toBe(true);
    expect(meshes[0].getAttribute("data-legend")).toBe("A σ(k, τ)");
    expect(meshes[0].getAttribute("data-axis")).toBe("logmoneyness");
    expect(meshes[0].getAttribute("data-rows")).toBe("3");
    expect(screen.getAllByText("production").length).toBe(1);
    expect(screen.getByTestId("series-surface-stage").getAttribute("data-mode")).toBe("sheets");
  });
  it("a hidden lane is not drawn; a single sheet is not compact; the axis word maps", () => {
    render(stage({ hidden: new Set(["b"]), axisMode: "kf" }));
    const meshes = screen.getAllByTestId("mesh");
    expect(meshes.length).toBe(1);
    expect(meshes[0].getAttribute("data-compact")).toBe("false");
    expect(meshes[0].getAttribute("data-axis")).toBe("pctatm");
  });
  it("empty states: no frame · no surface at the frame", () => {
    const { unmount } = render(stage({ frame: null }));
    expect(screen.getByTestId("series-stage-empty").textContent).toBe("no frame");
    unmount();
    render(stage({ frame: { ...frame, lanes: { c: laneDoc("c", null) } } }));
    expect(screen.getByTestId("series-stage-empty").textContent).toBe("no surface at this frame");
  });
  it("keeps the last drawn frame under the veil while the next one loads", () => {
    const { rerender } = render(stage());
    rerender(stage({ frame: null, loading: true }));
    expect(screen.getAllByTestId("mesh").length).toBe(2);
    expect(screen.getByTestId("series-stage-loading")).toBeTruthy();
  });
});

describe("SurfaceStage difference", () => {
  it("the production sheet beside a diverging lane − production heatmap in vol bp, x = K/F", () => {
    render(stage({ mode: "difference" }));
    const meshes = screen.getAllByTestId("mesh");
    expect(meshes.map((m) => m.getAttribute("data-chart"))).toEqual(["series:a"]);
    expect(meshes[0].getAttribute("data-compact")).toBe("true");
    const heats = screen.getAllByTestId("heat");
    expect(heats.length).toBe(1);
    expect(heats[0].getAttribute("data-chart")).toBe("series:b:diff");
    expect(heats[0].getAttribute("data-legend")).toBe("σ B − A");
    expect(heats[0].getAttribute("data-diverging")).toBe("true");
    expect(heats[0].getAttribute("data-lo")).toBe("−12 bp");
    expect(heats[0].getAttribute("data-x0")).toBe(Math.exp(-0.2).toFixed(3));
    expect(heats[0].getAttribute("data-cols")).toBe("4");
    expect(screen.getByText("B − A")).toBeTruthy();
  });
  it("the production sheet alone (not compact) with a cue when no other lane has a surface", () => {
    render(stage({ mode: "difference", hidden: new Set(["b"]) }));
    expect(screen.getAllByTestId("mesh").length).toBe(1);
    expect(screen.getAllByTestId("mesh")[0].getAttribute("data-compact")).toBe("false");
    expect(screen.queryAllByTestId("heat").length).toBe(0);
    expect(screen.getByTestId("series-surface-nodiff")).toBeTruthy();
  });
  it("says so when the production lane has no surface", () => {
    render(stage({ mode: "difference", frame: { ...frame, lanes: { ...frame.lanes, a: laneDoc("a", null) } } }));
    expect(screen.getByTestId("series-stage-empty").textContent).toBe("the production lane has no surface at this frame");
  });
});

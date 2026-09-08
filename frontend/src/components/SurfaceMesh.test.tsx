// SurfaceMesh: two meshes under one `windowKey` crop as one (the Compare
// sheets, 2026-09-08) — a drag on the first sheet's maturity handle moves the
// second sheet's handle to the same value; keyless meshes stay independent.
// jsdom gives the plot no size, so only the brushes and the top bar render —
// which is exactly what this locks.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import SurfaceMesh from "./SurfaceMesh";
import type { SurfaceMeshData } from "./SurfaceMesh";
import { resetSurfaceWindows } from "../state/surfaceWindows";

beforeAll(() => {
  // jsdom has no ResizeObserver; the mesh only needs it to size its plot.
  class RO {
    observe() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});

const DATA: SurfaceMeshData = {
  expiries: ["a", "b", "c", "d"],
  t: [0.1, 0.25, 0.5, 1.0],
  k: [-0.4, -0.2, 0, 0.2, 0.4],
  vol: [
    [0.3, 0.25, 0.2, 0.22, 0.26],
    [0.28, 0.24, 0.21, 0.22, 0.25],
    [0.27, 0.24, 0.22, 0.23, 0.25],
    [0.26, 0.24, 0.23, 0.23, 0.24],
  ],
};

beforeEach(resetSurfaceWindows);
afterEach(cleanup);

function dragLowerMaturity(handle: HTMLElement, toFrac: number) {
  const track = handle.parentElement!;
  vi.spyOn(track, "getBoundingClientRect").mockReturnValue({
    left: 0, top: 0, right: 20, bottom: 100, width: 20, height: 100, x: 0, y: 0, toJSON: () => ({}),
  } as DOMRect);
  handle.setPointerCapture = () => {};
  fireEvent.pointerDown(handle, { pointerId: 1, clientX: 10, clientY: 100 });
  fireEvent.pointerMove(track, { pointerId: 1, clientX: 10, clientY: (1 - toFrac) * 100 });
  fireEvent.pointerUp(track, { pointerId: 1 });
}

describe("SurfaceMesh shared windows", () => {
  it("two sheets under one windowKey crop together", () => {
    render(
      <div>
        <SurfaceMesh data={DATA} chartId="a" windowKey="shared" />
        <SurfaceMesh data={DATA} chartId="b" windowKey="shared" />
      </div>,
    );
    const lowers = screen.getAllByLabelText("Lower maturity bound") as HTMLElement[];
    expect(lowers).toHaveLength(2);
    expect(lowers.map((h) => h.getAttribute("aria-valuenow"))).toEqual(["0.1", "0.1"]);
    dragLowerMaturity(lowers[0], 0.5); // half-way up: 0.1 + 0.5 · 0.9 = 0.55 → snapped to the row at 0.5
    expect(lowers[1].getAttribute("aria-valuenow")).toBe("0.5");
    expect(lowers[0].getAttribute("aria-valuenow")).toBe("0.5");
    // The √T / T switch is shared too.
    const tButtons = screen.getAllByTitle("Linear T axis");
    fireEvent.click(tButtons[0]);
    expect(tButtons[1].className).toContain("text-accent-400");
  });

  it("keyless sheets keep their own windows", () => {
    render(
      <div>
        <SurfaceMesh data={DATA} chartId="a" />
        <SurfaceMesh data={DATA} chartId="b" />
      </div>,
    );
    const lowers = screen.getAllByLabelText("Lower maturity bound") as HTMLElement[];
    dragLowerMaturity(lowers[0], 0.5);
    expect(lowers[0].getAttribute("aria-valuenow")).toBe("0.5");
    expect(lowers[1].getAttribute("aria-valuenow")).toBe("0.1");
  });
});

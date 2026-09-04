// Overlay chart chrome: the x-range brush (internal in display units, or the
// caller's controlled window in its own units), the Y center / Y fit buttons
// and the brush opt-out. jsdom has no ResizeObserver, so a stub keeps the
// plot unmeasured (no SVG) — the chrome around it is what's under test.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import OverlayCurvesChart from "./OverlayCurvesChart";
import type { OverlaySeries } from "./OverlayCurvesChart";

beforeAll(() => {
  class RO {
    observe() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});
afterEach(cleanup);

const series: OverlaySeries[] = [
  { label: "a", xs: [-1, 0, 1], ys: [0.3, 0.2, 0.25], color: "#fff" },
  { label: "b", xs: [-0.5, 0, 2], ys: [0.1, 0.15, 0.4], color: "#eee" },
];

const sliders = () => screen.getAllByRole("slider");

describe("OverlayCurvesChart", () => {
  it("shows an internal brush over the data extent in display units", () => {
    render(<OverlayCurvesChart series={series} xLabel="k" yLabel="σ" formatX={(v) => `x${v}`} />);
    const [lo, hi] = sliders();
    expect(lo.getAttribute("aria-valuemin")).toBe("-1");
    expect(hi.getAttribute("aria-valuemax")).toBe("2");
    expect(lo.getAttribute("aria-valuenow")).toBe("-1");
    expect(hi.getAttribute("aria-valuenow")).toBe("2");
    expect(screen.getByText("x-1")).toBeTruthy(); // the handle labels use formatX
    expect(screen.getByText("x2")).toBeTruthy();
  });

  it("a controlled brush lives in the caller's units with its own labels", () => {
    const onChange = vi.fn();
    render(
      <OverlayCurvesChart
        series={series} xLabel="K" yLabel="σ"
        xBrush={{ min: -1.5, max: 1.5, value: [-0.5, 0.5], onChange, toX: (k) => 100 * Math.exp(k), format: (v) => v.toFixed(2) }}
      />,
    );
    const [lo, hi] = sliders();
    expect(lo.getAttribute("aria-valuemin")).toBe("-1.5");
    expect(lo.getAttribute("aria-valuenow")).toBe("-0.5");
    expect(hi.getAttribute("aria-valuenow")).toBe("0.5");
    expect(screen.getByText("-0.50")).toBeTruthy();
    expect(screen.getByText("0.50")).toBeTruthy();
  });

  it("xBrush={false} hides the brush; the Y buttons need a toggler", () => {
    render(<OverlayCurvesChart series={series} xLabel="k" yLabel="σ" xBrush={false} />);
    expect(screen.queryAllByRole("slider").length).toBe(0);
    expect(screen.queryByRole("button", { name: /Y fit/ })).toBeNull();
  });

  it("renders Y center / Y fit with the toggles' state and flips them on click", () => {
    const onToggle = vi.fn();
    render(
      <OverlayCurvesChart series={series} xLabel="k" yLabel="σ"
        autoScaleY={{ center: false, fit: true }} onToggleAutoScale={onToggle} />,
    );
    const fit = screen.getByRole("button", { name: /Y fit/ });
    const center = screen.getByRole("button", { name: /Y center/ });
    expect(fit.getAttribute("aria-pressed")).toBe("true");
    expect(center.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(center);
    expect(onToggle).toHaveBeenCalledWith("center");
  });

  it("says so when there is nothing to draw", () => {
    render(<OverlayCurvesChart series={[]} xLabel="k" yLabel="σ" />);
    expect(screen.getByText("No curves to display.")).toBeTruthy();
    expect(screen.queryAllByRole("slider").length).toBe(0);
  });
});

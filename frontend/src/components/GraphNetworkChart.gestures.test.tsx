// Canvas gestures after the 2026-09-08 report: a PLAIN drag from node to
// node connects once it moves past the threshold (no tool, no Shift), a
// press without movement stays a click, the framing re-fits when the
// container resizes (Focus), a selected cross relation expands its bundle,
// and the readouts flip to the left near the toolbar corner.
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import GraphNetworkChart from "./GraphNetworkChart";
import { anchorStyle } from "./GraphNetworkChart.tooltips";
import { rowsToLayoutEdges } from "../lib/relationRows";
import type { GraphNodeBase } from "../state/useGraph";
import type { MessageEdgeRow } from "../state/useMessageEdges";

/** ResizeObserver stub whose callbacks the tests can fire. */
const observers: (() => void)[] = [];
beforeAll(() => {
  class RO {
    cb: () => void;
    constructor(cb: () => void) {
      this.cb = cb;
      observers.push(cb);
    }
    observe() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});
afterEach(() => {
  cleanup();
  observers.length = 0;
});

const E1 = "2026-07-17";
const E2 = "2026-10-16";
const NODES: GraphNodeBase[] = [
  { ticker: "SPY", expiry: E1, t: 0.02, atmVol: 0.2, skew: 0, curvature: 0, lit: true },
  { ticker: "SPY", expiry: E2, t: 0.25, atmVol: 0.2, skew: 0, curvature: 0, lit: false },
  { ticker: "AAPL", expiry: E1, t: 0.02, atmVol: 0.3, skew: 0, curvature: 0, lit: false },
];
const ROWS: MessageEdgeRow[] = [
  { sourceTicker: "SPY", sourceExpiry: E1, targetTicker: "AAPL", targetExpiry: E1,
    messagePrecision: 13000, betaAtmVol: 0.5, betaSkew: 0.5, betaCurv: 0.5,
    relationClass: "broad_index", precisionRule: "explicit", relationSemantics: null },
];

function mount(over: Partial<React.ComponentProps<typeof GraphNetworkChart>> = {}) {
  const onConnect = vi.fn();
  const onToggle = vi.fn();
  const utils = render(
    <GraphNetworkChart
      nodes={NODES}
      edges={rowsToLayoutEdges(ROWS)}
      lit={{}}
      results={null}
      onToggle={onToggle}
      onOpenSmile={vi.fn()}
      onEdgeClick={vi.fn()}
      onConnect={onConnect}
      {...over}
    />,
  );
  return { ...utils, onConnect, onToggle };
}

describe("GraphNetworkChart gestures (2026-09-08)", () => {
  it("a plain drag past the threshold connects; a still press stays a click", () => {
    const { container, onConnect, onToggle } = mount();
    const from = container.querySelector(`[data-node="SPY|${E2}"]`) as SVGGElement;
    const to = container.querySelector(`[data-node="AAPL|${E1}"]`) as SVGGElement;
    const svg = container.querySelector("svg") as SVGSVGElement;
    // Press, wiggle 2 px (below the threshold): no band, click toggles.
    fireEvent.mouseDown(from, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(svg, { clientX: 102, clientY: 101 });
    expect(container.querySelector('[data-testid="connect-band"]')).toBeNull();
    fireEvent.mouseUp(from, { button: 0 });
    fireEvent.click(from);
    expect(onToggle).toHaveBeenCalledWith(`SPY|${E2}`);
    // Press and drag 20 px: the band appears; release on another node connects.
    fireEvent.mouseDown(from, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(svg, { clientX: 120, clientY: 100 });
    expect(container.querySelector('[data-testid="connect-band"]')).toBeTruthy();
    fireEvent.mouseUp(to, { button: 0 });
    expect(onConnect).toHaveBeenCalledWith({ ticker: "SPY", expiry: E2 }, { ticker: "AAPL", expiry: E1 });
    // The ancestor click that follows a cross-node gesture clears the swallow flag.
    fireEvent.click(svg);
    fireEvent.click(to);
    expect(onToggle).toHaveBeenLastCalledWith(`AAPL|${E1}`);
  });

  it("re-fits the framing when the container resizes", () => {
    const { container } = mount();
    const el = container.querySelector('[data-testid="graph-canvas"]') as HTMLDivElement;
    Object.defineProperty(el, "clientWidth", { value: 400, configurable: true });
    Object.defineProperty(el, "clientHeight", { value: 300, configurable: true });
    act(() => observers.forEach((cb) => cb()));
    const t1 = container.querySelector("svg > g")?.getAttribute("transform") ?? "";
    Object.defineProperty(el, "clientWidth", { value: 1600, configurable: true });
    Object.defineProperty(el, "clientHeight", { value: 900, configurable: true });
    act(() => observers.forEach((cb) => cb()));
    const t2 = container.querySelector("svg > g")?.getAttribute("transform") ?? "";
    expect(t1).not.toBe("");
    expect(t2).not.toBe(t1); // a bigger canvas → a bigger fit
  });

  it("a selected cross relation expands its bundle so the arrow shows", () => {
    const { container } = mount({ selectedRelationKey: `SPY|${E1}>AAPL|${E1}` });
    expect(container.querySelectorAll("[data-relation]")).toHaveLength(1);
  });

  it("readouts flip left of the anchor near the toolbar corner", () => {
    const t = { k: 1, tx: 0, ty: 0 };
    expect(anchorStyle(100, 50, t, { w: 1000, h: 600 })).toEqual({ left: 108, top: 36 });
    const flipped = anchorStyle(900, 50, t, { w: 1000, h: 600 });
    expect(flipped).toHaveProperty("right");
    expect(flipped).not.toHaveProperty("left");
  });
});

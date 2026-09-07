// The canvas as a relation editor (GRAPH ERGONOMICS ARC, E3): arrows carry
// the β colour and the confidence width, a calendar hop click selects its
// relation, a bundle click expands the pair into arrows, the Shift-drag
// connect gesture reports informer → receiver, a ticker label collapses its
// pod, and the toolbar's Focus routes to the shell.
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import GraphNetworkChart from "./GraphNetworkChart";
import { betaColor, edgeWidth } from "../lib/edgeStyle";
import { rowsToLayoutEdges } from "../lib/relationRows";
import type { GraphNodeBase } from "../state/useGraph";
import type { MessageEdgeRow } from "../state/useMessageEdges";

beforeAll(() => {
  // jsdom has no ResizeObserver; the chart only needs it for the initial fit.
  class RO {
    observe() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});
afterEach(cleanup);

const E1 = "2026-07-17";
const E2 = "2026-10-16";
const NODES: GraphNodeBase[] = [
  { ticker: "SPY", expiry: E1, t: 0.02, atmVol: 0.2, skew: 0, curvature: 0, lit: true },
  { ticker: "SPY", expiry: E2, t: 0.25, atmVol: 0.2, skew: 0, curvature: 0, lit: false },
  { ticker: "AAPL", expiry: E1, t: 0.02, atmVol: 0.3, skew: 0, curvature: 0, lit: false },
  { ticker: "AAPL", expiry: E2, t: 0.25, atmVol: 0.3, skew: 0, curvature: 0, lit: false },
];
const ROWS: MessageEdgeRow[] = [
  { sourceTicker: "SPY", sourceExpiry: E2, targetTicker: "SPY", targetExpiry: E1,
    messagePrecision: 1700, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
    relationClass: "calendar", precisionRule: "calendar_distance", relationSemantics: null },
  { sourceTicker: "SPY", sourceExpiry: E1, targetTicker: "AAPL", targetExpiry: E1,
    messagePrecision: 13000, betaAtmVol: 0.5, betaSkew: 0.5, betaCurv: 0.5,
    relationClass: "broad_index", precisionRule: "explicit", relationSemantics: null },
];

function mount(over: Partial<React.ComponentProps<typeof GraphNetworkChart>> = {}) {
  const onEdgeClick = vi.fn();
  const onConnect = vi.fn();
  const onToggle = vi.fn();
  const onToggleFocus = vi.fn();
  const utils = render(
    <GraphNetworkChart
      nodes={NODES}
      edges={rowsToLayoutEdges(ROWS)}
      lit={{ [`SPY|${E1}`]: 0 }}
      results={null}
      onToggle={onToggle}
      onOpenSmile={vi.fn()}
      onEdgeClick={onEdgeClick}
      onConnect={onConnect}
      onToggleFocus={onToggleFocus}
      {...over}
    />,
  );
  return { ...utils, onEdgeClick, onConnect, onToggle, onToggleFocus };
}

describe("GraphNetworkChart (E3)", () => {
  it("draws the calendar hop with the β colour, the confidence width and a head at the receiver", () => {
    const { container } = mount();
    const hop = container.querySelector(`[data-calendar="cal-SPY-${E1}-${E2}"]`) as SVGGElement;
    expect(hop).toBeTruthy();
    const visible = hop.querySelectorAll("line")[0] as SVGLineElement;
    expect(visible.getAttribute("stroke")).toBe(betaColor(2));
    expect(Number(visible.getAttribute("stroke-width"))).toBeCloseTo(edgeWidth(1700), 6);
    // Receiver = the earlier expiry → exactly one head.
    expect(hop.querySelectorAll("polygon")).toHaveLength(1);
  });

  it("a calendar hop click selects its ONE relation; a bundle click expands the pair", () => {
    const { container, onEdgeClick } = mount();
    const hop = container.querySelector(`[data-calendar="cal-SPY-${E1}-${E2}"]`) as SVGGElement;
    const hit = hop.querySelectorAll("line")[1] as SVGLineElement; // the transparent twin
    fireEvent.click(hit);
    expect(onEdgeClick).toHaveBeenCalledWith({ kind: "relation", key: `SPY|${E2}>SPY|${E1}` });

    const bundle = container.querySelector('[data-bundle="AAPL→SPY"]') as SVGGElement;
    expect(bundle.querySelector("path")?.getAttribute("stroke")).toBe(betaColor(0.5));
    expect(container.querySelectorAll("[data-relation]")).toHaveLength(0);
    fireEvent.click(bundle.querySelectorAll("path")[1] as SVGPathElement);
    expect(onEdgeClick).toHaveBeenCalledWith({ kind: "cross", a: "AAPL", b: "SPY" });
    const arrows = container.querySelectorAll("[data-relation]");
    expect(arrows).toHaveLength(1);
    expect(arrows[0]?.getAttribute("data-relation")).toBe(`SPY|${E1}>AAPL|${E1}`);
    // Clicking the expanded arrow selects that relation.
    fireEvent.click(arrows[0]?.querySelectorAll("line")[1] as SVGLineElement);
    expect(onEdgeClick).toHaveBeenLastCalledWith({ kind: "relation", key: `SPY|${E1}>AAPL|${E1}` });
  });

  it("Shift-drag from a node to another reports informer → receiver and does not toggle", () => {
    const { container, onConnect, onToggle } = mount();
    const from = container.querySelector(`[data-node="SPY|${E1}"]`) as SVGGElement;
    const to = container.querySelector(`[data-node="AAPL|${E2}"]`) as SVGGElement;
    fireEvent.mouseDown(from, { shiftKey: true, button: 0, clientX: 10, clientY: 10 });
    expect(container.querySelector('[data-testid="connect-band"]')).toBeTruthy();
    fireEvent.mouseUp(to, { button: 0 });
    expect(onConnect).toHaveBeenCalledWith({ ticker: "SPY", expiry: E1 }, { ticker: "AAPL", expiry: E2 });
    fireEvent.click(to); // the click that follows the gesture is swallowed
    expect(onToggle).not.toHaveBeenCalled();
    fireEvent.click(to);
    expect(onToggle).toHaveBeenCalledWith(`AAPL|${E2}`);
  });

  it("a plain node click still toggles; without onConnect Shift-drag does nothing", () => {
    const { container, onToggle } = mount({ onConnect: undefined });
    const from = container.querySelector(`[data-node="SPY|${E1}"]`) as SVGGElement;
    fireEvent.mouseDown(from, { shiftKey: true, button: 0 });
    expect(container.querySelector('[data-testid="connect-band"]')).toBeNull();
    fireEvent.click(from);
    expect(onToggle).toHaveBeenCalledWith(`SPY|${E1}`);
  });

  it("a ticker label collapses the pod into one node; the toolbar expands all", () => {
    const { container } = mount();
    fireEvent.click(container.querySelector('[data-pod="SPY"]') as SVGTextElement);
    expect(container.querySelector(`[data-node="SPY|${E1}"]`)).toBeNull();
    expect(container.querySelector('[data-node="SPY|*"]')).toBeTruthy();
    expect(container.querySelector(`[data-node="AAPL|${E1}"]`)).toBeTruthy();
    fireEvent.click(container.querySelector('[data-testid="tool-collapse"]') as HTMLButtonElement);
    expect(container.querySelector('[data-node="AAPL|*"]')).toBeTruthy();
    fireEvent.click(container.querySelector('[data-testid="tool-collapse"]') as HTMLButtonElement);
    expect(container.querySelector(`[data-node="SPY|${E1}"]`)).toBeTruthy();
  });

  it("the Focus button routes to the shell; the selected relation glows", () => {
    const { container, onToggleFocus } = mount({ selectedRelationKey: `SPY|${E2}>SPY|${E1}` });
    fireEvent.click(container.querySelector('[data-testid="tool-focus"]') as HTMLButtonElement);
    expect(onToggleFocus).toHaveBeenCalled();
    const hop = container.querySelector(`[data-calendar="cal-SPY-${E1}-${E2}"]`) as SVGGElement;
    expect(hop.querySelectorAll("line")).toHaveLength(3); // glow + visible + hit twin
  });
});

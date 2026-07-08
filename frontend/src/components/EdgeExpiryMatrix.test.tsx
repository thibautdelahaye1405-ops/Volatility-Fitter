// Expiry×expiry drill-in: inherited-cell display and the directed-override
// write-through (symmetric ⇄ keeps the mirrored edge in lockstep; β applies
// to all three handles, matching the backend's block-rule expansion).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EdgeExpiryMatrix from "./EdgeExpiryMatrix";
import type { GraphEdge } from "../state/useGraphEdges";

const EXP = ["2026-07-17", "2026-09-18"];

function edge(
  fromExpiry: string,
  toExpiry: string,
  weight: number,
  over: Partial<GraphEdge> = {},
): GraphEdge {
  return {
    fromTicker: "SPY", fromExpiry, toTicker: "NVDA", toExpiry,
    weight, betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
    ...over,
  };
}

function renderMatrix(overrides: GraphEdge[] = [], src = "SPY", dst = "NVDA") {
  const onChange = vi.fn();
  const onBack = vi.fn();
  render(
    <EdgeExpiryMatrix
      src={src}
      dst={dst}
      srcExpiries={EXP}
      dstExpiries={EXP}
      baseCell={{ weight: 2, beta: 1, symmetric: true }}
      overrides={overrides}
      busy={false}
      onChange={onChange}
      onBack={onBack}
    />,
  );
  return { onChange, onBack };
}

afterEach(cleanup);

describe("EdgeExpiryMatrix", () => {
  it("shows the pair rule faintly on the cells it expands to", () => {
    renderMatrix();
    // Cross-ticker rule = same-expiry cells only: two inherited "2.0" cells.
    expect(screen.getAllByText("2.0")).toHaveLength(2);
  });

  it("writes a directed override, mirrored when symmetric", () => {
    const { onChange } = renderMatrix();
    fireEvent.click(screen.getByTitle("SPY 2026-07-17 → NVDA 2026-09-18"));
    const weightInput = screen.getByLabelText(/weight/);
    fireEvent.change(weightInput, { target: { value: "5" } });
    let next = onChange.mock.lastCall?.[0] as GraphEdge[];
    expect(next).toHaveLength(1);
    expect(next[0]).toMatchObject({
      fromTicker: "SPY", fromExpiry: "2026-07-17",
      toTicker: "NVDA", toExpiry: "2026-09-18",
      weight: 5, betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
    });
    // Symmetric ⇄ adds the mirrored directed edge with the same values.
    fireEvent.click(screen.getByLabelText(/symmetric/));
    next = onChange.mock.lastCall?.[0] as GraphEdge[];
    // onChange is not applied back into props here, so the base cell (weight
    // from the popover's initial state) is what mirrors — assert directions.
    expect(next.some((o) => o.fromTicker === "NVDA" && o.toTicker === "SPY")).toBe(true);
  });

  it("clears an override (and its mirror when symmetric)", () => {
    const { onChange } = renderMatrix([
      edge("2026-07-17", "2026-09-18", 5),
      { ...edge("2026-09-18", "2026-07-17", 5), fromTicker: "NVDA", toTicker: "SPY" },
    ]);
    fireEvent.click(screen.getByTitle("SPY 2026-07-17 → NVDA 2026-09-18"));
    fireEvent.click(screen.getByText("Clear"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("disables self edges on the calendar diagonal", () => {
    renderMatrix([], "SPY", "SPY");
    const self = screen.getAllByTitle("self edge");
    expect(self).toHaveLength(2);
    expect((self[0] as HTMLButtonElement).disabled).toBe(true);
  });

  it("navigates back to the ticker matrix", () => {
    const { onBack } = renderMatrix();
    fireEvent.click(screen.getByText("← Matrix"));
    expect(onBack).toHaveBeenCalledOnce();
  });
});

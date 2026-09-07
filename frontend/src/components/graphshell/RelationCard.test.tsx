// Relation card (GRAPH ERGONOMICS ARC, E5): the slider edits patch the row,
// the distance rule shows as "auto" and locks explicit on a drag, ↺ returns
// to the rule, the linked-handles switch fans a β change out (or not), and
// flip / delete route to the shell.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RelationCard from "./RelationCard";
import type { SolverParams } from "../../state/useGraph";
import type { MessageEdgeRow } from "../../state/useMessageEdges";

const params: SolverParams = {
  etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
  calendarWeight: null, crossWeight: null, crossExpiryToleranceDays: 0,
  propagationMode: "layered_dynamic_harmonic", alphaT: 1, ampCal: 1, ampCross: 1,
  calPrecision: 1700, calEpsilon: 0.97, calDecay: "inverse_sqrt_gap", crossPrecision: 13000,
  calendarEnabled: true, calendarOverrides: {},
};
const ROW: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-10-16",
  targetTicker: "SPY", targetExpiry: "2026-07-17",
  messagePrecision: 1700, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
  relationClass: "calendar", precisionRule: "calendar_distance", relationSemantics: null,
};
const tOf = (_t: string, e: string) => (e === "2026-07-17" ? 0.25 : 0.5);

function mount(row: MessageEdgeRow = ROW, layered = true) {
  const onChange = vi.fn();
  const onFlip = vi.fn();
  const onDelete = vi.fn();
  render(
    <RelationCard row={row} params={params} layered={layered} raw={false} tOf={tOf} onChange={onChange} onFlip={onFlip} onDelete={onDelete} onClose={vi.fn()} />,
  );
  return { onChange, onFlip, onDelete };
}

afterEach(cleanup);

describe("RelationCard", () => {
  it("shows the distance-derived confidence as auto; a drag locks it explicit; ↺ restores the rule", () => {
    const { onChange } = mount();
    expect(screen.getByText("auto")).toBeTruthy();
    // Derived under the receiver's policy: 1700 / (0.97 + √0.25) = 1156.46… → σ 2.94 pt
    expect(screen.getByTestId("slider-sigma-readout").textContent).toBe("σ 2.94 pt");
    fireEvent.change(screen.getByTestId("slider-sigma"), { target: { value: "0" } }); // conf 1 → σ 1 pt
    expect(onChange).toHaveBeenCalledWith({ messagePrecision: 10000, precisionRule: "explicit" });
    fireEvent.click(screen.getByTitle("Back to the maturity-distance rule"));
    expect(onChange).toHaveBeenCalledWith({ precisionRule: "calendar_distance" });
  });

  it("β drives all three handles while linked, only ATM once unlinked", () => {
    const { onChange } = mount();
    fireEvent.change(screen.getByTestId("slider-beta"), { target: { value: "1.5" } });
    expect(onChange).toHaveBeenLastCalledWith({ betaAtmVol: 1.5, betaSkew: 1.5, betaCurv: 1.5 });
    fireEvent.click(screen.getByLabelText("link handles"));
    expect(screen.getByTestId("slider-beta-skew")).toBeTruthy();
    fireEvent.change(screen.getByTestId("slider-beta"), { target: { value: "0.8" } });
    expect(onChange).toHaveBeenLastCalledWith({ betaAtmVol: 0.8 });
    fireEvent.change(screen.getByTestId("slider-beta-curv"), { target: { value: "1.1" } });
    expect(onChange).toHaveBeenLastCalledWith({ betaCurv: 1.1 });
  });

  it("starts unlinked when the handles differ, and the exact input patches too", () => {
    const { onChange } = mount({ ...ROW, betaSkew: 1 });
    expect(screen.getByTestId("slider-beta-skew")).toBeTruthy();
    fireEvent.change(screen.getByTitle("β ATM (exact)"), { target: { value: "2.25" } });
    expect(onChange).toHaveBeenLastCalledWith({ betaAtmVol: 2.25 });
  });

  it("class, semantics, flip and delete route to the shell; the implied reverse reads 1/β", () => {
    const { onChange, onFlip, onDelete } = mount();
    fireEvent.change(screen.getByTitle(/Relation class/), { target: { value: "sector_peer" } });
    expect(onChange).toHaveBeenLastCalledWith({ relationClass: "sector_peer" });
    fireEvent.change(screen.getByTitle(/recip ⇄: information flows/), { target: { value: "directed_state" } });
    expect(onChange).toHaveBeenLastCalledWith({ relationSemantics: "directed_state" });
    expect(screen.getByText(/⇐ β 0\.50/)).toBeTruthy();
    fireEvent.click(screen.getByTestId("relation-flip"));
    expect(onFlip).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByTestId("relation-delete"));
    expect(onDelete).toHaveBeenCalledOnce();
  });
});

// Relations drawer tab (GRAPH ERGONOMICS ARC, E5): rows list with search /
// class filter / sort, selection routes to the shell, × removes through the
// draft, undo / redo follow the draft flags, templates replace the list.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RelationsTab from "./RelationsTab";
import type { SolverParams } from "../../state/useGraph";
import type { MessageEdgeRow } from "../../state/useMessageEdges";
import type { RelationDraft } from "../../state/useRelationDraft";

const params: SolverParams = {
  etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
  calendarWeight: null, crossWeight: null, crossExpiryToleranceDays: 0,
  propagationMode: "layered_dynamic_harmonic", alphaT: 1, ampCal: 1, ampCross: 1,
  calPrecision: 1700, calEpsilon: 0.97, calDecay: "inverse_sqrt_gap", crossPrecision: 13000,
  calendarEnabled: true, calendarOverrides: {},
};
const CAL: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-10-16", targetTicker: "SPY", targetExpiry: "2026-07-17",
  messagePrecision: 1700, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
  relationClass: "calendar", precisionRule: "calendar_distance", relationSemantics: null,
};
const CROSS: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-07-17", targetTicker: "AAPL", targetExpiry: "2026-07-17",
  messagePrecision: 13000, betaAtmVol: 1.2, betaSkew: 1.2, betaCurv: 1.2,
  relationClass: "broad_index", precisionRule: "explicit", relationSemantics: null,
};
const NODES = [
  { ticker: "SPY", expiry: "2026-07-17" }, { ticker: "SPY", expiry: "2026-10-16" },
  { ticker: "AAPL", expiry: "2026-07-17" },
];

function draftStub(over: Partial<RelationDraft> = {}): RelationDraft {
  return {
    rows: [CAL, CROSS], source: "draft", loading: false, saving: false, error: null,
    canUndo: true, canRedo: false,
    add: vi.fn(), update: vi.fn(), remove: vi.fn(), removeMany: vi.fn(), flip: vi.fn(() => null),
    replaceAll: vi.fn(), seedAuto: vi.fn().mockResolvedValue(undefined),
    resetAuto: vi.fn().mockResolvedValue(undefined), undo: vi.fn(), redo: vi.fn(), reload: vi.fn(),
    byKey: () => undefined,
    ...over,
  };
}

function mount(draft = draftStub(), selectedKey: string | null = null) {
  const onSelect = vi.fn();
  const onOpenFullEditor = vi.fn();
  render(
    <RelationsTab draft={draft} params={params} raw={false} selectedKey={selectedKey} onSelect={onSelect} nodes={NODES} onOpenFullEditor={onOpenFullEditor} />,
  );
  return { onSelect, onOpenFullEditor };
}

afterEach(cleanup);

describe("RelationsTab", () => {
  it("lists the rows with σ / β / rule and filters by class and search", () => {
    mount();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2
    expect(screen.getByText("2.43")).toBeTruthy(); // σ of p = 1700
    expect(screen.getByText("auto")).toBeTruthy();
    fireEvent.click(screen.getByText("index 1"));
    expect(screen.getAllByRole("row")).toHaveLength(2);
    fireEvent.click(screen.getByText("all 2"));
    fireEvent.change(screen.getByTestId("relations-search"), { target: { value: "aapl" } });
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText(/AAPL 07-17/)).toBeTruthy();
  });

  it("row click selects; × removes through the draft; the selected row is highlighted", () => {
    const draft = draftStub();
    const { onSelect } = mount(draft, "SPY|2026-10-16>SPY|2026-07-17");
    const row = screen.getByText(/SPY 10-16/).closest("tr") as HTMLElement;
    expect(row.className).toContain("bg-accent-600/15");
    fireEvent.click(row);
    expect(onSelect).toHaveBeenCalledWith("SPY|2026-10-16>SPY|2026-07-17");
    fireEvent.click(row.querySelector('button[title="Remove relation"]') as HTMLElement);
    expect(draft.remove).toHaveBeenCalledWith("SPY|2026-10-16>SPY|2026-07-17");
    expect(onSelect).toHaveBeenCalledTimes(1); // the × click does not re-select
  });

  it("undo / redo follow the draft flags; seed, reset and the full editor route", () => {
    const draft = draftStub();
    const { onOpenFullEditor } = mount(draft);
    fireEvent.click(screen.getByTestId("relations-undo"));
    expect(draft.undo).toHaveBeenCalled();
    expect((screen.getByTestId("relations-redo") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Seed auto"));
    expect(draft.seedAuto).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Reset to auto"));
    expect(draft.resetAuto).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Full editor"));
    expect(onOpenFullEditor).toHaveBeenCalled();
  });

  it("a template replaces the whole list (Calendar only drops the cross rows)", () => {
    const draft = draftStub();
    mount(draft);
    fireEvent.click(screen.getByTestId("templates-menu"));
    fireEvent.click(screen.getByTestId("template-calendar_only"));
    expect(draft.replaceAll).toHaveBeenCalledWith([CAL]);
  });
});

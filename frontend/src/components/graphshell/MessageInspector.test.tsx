// U4 message inspector: the incoming-messages table + the exact local
// conditional vs the solved global (divergence explainer), and the edge-click
// relation card.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EdgeInspectorCard, MessageInspector } from "./MessageInspector";
import type { SolverParams } from "../../state/useGraph";
import type { ExtrapolateNode } from "../../state/useGraphExtrapolation";
import type { MessageEdgeRow } from "../../state/useMessageEdges";

function params(over: Partial<SolverParams> = {}): SolverParams {
  return {
    etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
    calendarWeight: null, crossWeight: null,
    propagationMode: "precision_messages", alphaT: 1, ampCal: 1, ampCross: 1,
    calPrecision: 1700, calEpsilon: 0.97,
    calDecay: "inverse_sqrt_gap", crossPrecision: 13000,
    calendarEnabled: true, calendarOverrides: {},
    ...over,
  };
}

function node(
  ticker: string, expiry: string, t: number, shift = 0, over: Partial<ExtrapolateNode> = {},
): ExtrapolateNode {
  return {
    ticker, expiry, t, lit: false, calibrated: false, priorSource: "stored",
    priorAsOf: null, transportDistance: 0, validForValidation: true,
    priorAtmVol: 0.2, priorSkew: 0, priorCurv: 0,
    postAtmVol: 0.2 + shift, postSkew: 0, postCurv: 0,
    shiftBp: shift * 1e4, sd: 0.005, bandLo: 0.19, bandHi: 0.21,
    innovationBp: null, baselinePrecision: [1, 1, 1], obsPrecision: null,
    precisionFactors: {}, qIncoming: 4, noLitPath: false,
    ...over,
  };
}

/** §21.1: 12-18 informs 09-18 at β=2, p=4; the informer moved +1pt. */
const ROW: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-12-18",
  targetTicker: "SPY", targetExpiry: "2026-09-18",
  messagePrecision: 4, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
  relationClass: "calendar", precisionRule: "explicit",
};
const RECEIVER = node("SPY", "2026-09-18", 0.25, 0.015); // solved +150bp
const INFORMER = node("SPY", "2026-12-18", 0.5, 0.01);

afterEach(cleanup);

describe("MessageInspector", () => {
  it("shows the incoming table and local-vs-final with the divergence note", () => {
    render(
      <MessageInspector
        receiver={RECEIVER}
        rows={[ROW]}
        nodes={[RECEIVER, INFORMER]}
        params={params()}
      />,
    );
    expect(screen.getByText(/Incoming messages · 1/)).toBeTruthy();
    // Informer row: z +1.00, β 2.00, mapped +2.00pt.
    expect(screen.getByText(/\+2\.00pt/)).toBeTruthy();
    // Local conditional = exact §21.1 transmission (+200 bp, q 4)…
    expect(screen.getByText("+200.0 bp")).toBeTruthy();
    expect(screen.getByText("4", { selector: "span" })).toBeTruthy();
    // …vs the solved final (+150 bp) → the divergence explainer shows.
    expect(screen.getByText("+150.0 bp")).toBeTruthy();
    expect(screen.getByText(/marginal folds in informer/)).toBeTruthy();
  });

  it("renders nothing without incoming relations", () => {
    const { container } = render(
      <MessageInspector
        receiver={node("NVDA", "2026-09-18", 0.25)}
        rows={[ROW]}
        nodes={[RECEIVER, INFORMER]}
        params={params()}
      />,
    );
    expect(container.textContent).toBe("");
  });
});

describe("EdgeInspectorCard", () => {
  it("resolves a calendar pair (persisted row) and drills into the editor", () => {
    const onEdit = vi.fn();
    render(
      <EdgeInspectorCard
        edge={{ kind: "calendar", ticker: "SPY", aExpiry: "2026-12-18", bExpiry: "2026-09-18" }}
        rows={[ROW]}
        nodes={[RECEIVER, INFORMER]}
        params={params()}
        messages={true}
        onClose={vi.fn()}
        onEditRelations={onEdit}
      />,
    );
    expect(screen.getByText(/Relation · SPY calendar/)).toBeTruthy();
    expect(screen.getByText(/β 2\.00/)).toBeTruthy();
    expect(screen.getByText(/persisted/)).toBeTruthy();
    fireEvent.click(screen.getByText("Edit relations"));
    expect(onEdit).toHaveBeenCalledOnce();
  });

  it("shows both directions of a cross pair via the matrix resolution", () => {
    render(
      <EdgeInspectorCard
        edge={{ kind: "cross", a: "SPY", b: "NVDA" }}
        rows={[]}
        nodes={[]}
        params={params()}
        messages={true}
        onClose={vi.fn()}
        onEditRelations={vi.fn()}
      />,
    );
    // No persisted rows → both directions show the auto default β 1.
    expect(screen.getAllByText(/β 1\.00/)).toHaveLength(2);
    expect(screen.getAllByText(/auto/)).toHaveLength(2);
  });
});

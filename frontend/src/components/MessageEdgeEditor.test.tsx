// Message relation editor: seed-from-auto, informer→receiver direction
// labels, inherited-vs-explicit provenance, save payload, and the scenario
// preview showing the exact §21.1 conditional mean before saving (the
// Phase-5 exit gate). The data hook is mocked — the endpoint contracts are
// locked by backend/tests/test_graph_message_production.py.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MessageEdgeEditor from "./MessageEdgeEditor";
import type { MessageEdgeRow } from "../state/useMessageEdges";
import type { SolverParams } from "../state/useGraph";

const fetchEdges = vi.fn();
const fetchAuto = vi.fn();
const putEdges = vi.fn();
vi.mock("../state/useMessageEdges", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/useMessageEdges")>()),
  useMessageEdges: () => ({ fetchEdges, fetchAuto, putEdges }),
}));

const PARAMS: SolverParams = {
  etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
  calendarWeight: null, crossWeight: null,
  propagationMode: "precision_messages",
  alphaT: 1, ampCal: 1, ampCross: 1,
  calPrecision: 1700, calEpsilon: 0.97,
  calDecay: "inverse_sqrt_gap", crossPrecision: 13000,
  calendarEnabled: true, calendarOverrides: {},
};

const NODES = [
  { ticker: "SPY", expiry: "2026-09-18" },
  { ticker: "SPY", expiry: "2026-12-18" },
  { ticker: "AAPL", expiry: "2026-09-18" },
];

/** §21.1 shape: the 6M node informs the 3M node at β=2, p=4 (calendar). */
function calRow(over: Partial<MessageEdgeRow> = {}): MessageEdgeRow {
  return {
    sourceTicker: "SPY", sourceExpiry: "2026-12-18",
    targetTicker: "SPY", targetExpiry: "2026-09-18",
    messagePrecision: 4, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
    relationClass: "calendar", precisionRule: "calendar_distance",
    ...over,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderEditor(rows: MessageEdgeRow[]) {
  fetchEdges.mockResolvedValue(rows);
  fetchAuto.mockResolvedValue([calRow()]);
  putEdges.mockImplementation((e: MessageEdgeRow[]) => Promise.resolve(e));
  const onSaved = vi.fn();
  render(
    <MessageEdgeEditor
      nodes={NODES}
      params={PARAMS}
      onSaved={onSaved}
      onClose={vi.fn()}
    />,
  );
  return { onSaved };
}

describe("MessageEdgeEditor", () => {
  it("renders rows with the U1 sentence tooltip (direction + transfer + σ)", async () => {
    renderEditor([calRow()]);
    // The row label's title is the full relation sentence: +1pt through this
    // factor transfers ρβ = 2.00 pt; σ_edge = 1/√4 = 50.00 vol pts.
    const row = await screen.findByTitle(
      "SPY 12-18 informs SPY 09-18: +1.00 pt → +2.00 pt message · relationship uncertainty 50.00 pt",
    );
    expect(row.textContent).toContain("SPY 12-18");
    expect(row.textContent).toContain("SPY 09-18");
    expect(screen.getByText("source (informer) → target (receiver) · one factor per relation")).toBeTruthy();
    expect(screen.getByText(/calendar · 1/)).toBeTruthy(); // class group header
  });

  it("defaults to the σ-pts lens and stores raw precision behind it", async () => {
    const { onSaved } = renderEditor([calRow()]);
    await screen.findByText(/calendar · 1/);
    // p=4 reads as σ = 50 pts in the default lens…
    const sigma = screen.getByTitle(/Distance-derived relationship uncertainty/);
    expect((sigma as HTMLInputElement).value).toBe("50");
    // …typing σ = 2 pts stores p = (100/2)² = 2500, locked explicit.
    fireEvent.change(sigma, { target: { value: "2" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(putEdges).toHaveBeenCalled());
    const saved = putEdges.mock.lastCall?.[0] as MessageEdgeRow[];
    expect(saved[0]?.messagePrecision).toBeCloseTo(2500, 8);
    expect(saved[0]?.precisionRule).toBe("explicit");
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("shows the raw precision behind the units toggle", async () => {
    renderEditor([calRow()]);
    await screen.findByText(/calendar · 1/);
    fireEvent.click(screen.getByText("units: σ pts"));
    const rawInput = screen.getByTitle(/Distance-derived precision/);
    expect((rawInput as HTMLInputElement).value).toBe("4");
    expect(screen.getByText("units: raw p")).toBeTruthy();
  });

  it("seeds from the auto relations and marks rows inherited until touched", async () => {
    renderEditor([]);
    fireEvent.click(await screen.findByText("Seed from auto relations"));
    expect(await screen.findByText("auto")).toBeTruthy();
    // Editing any field drops the inherited badge.
    const beta = screen.getByTitle("β ATM vol");
    fireEvent.change(beta, { target: { value: "1.5" } });
    expect(screen.queryByText("auto")).toBeNull();
  });

  it("saves the edited rows through PUT and notifies the parent", async () => {
    const { onSaved } = renderEditor([calRow()]);
    await screen.findByText(/calendar · 1/);
    fireEvent.change(screen.getByTitle("β skew"), { target: { value: "1.25" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(putEdges).toHaveBeenCalled());
    const saved = putEdges.mock.lastCall?.[0] as MessageEdgeRow[];
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({
      sourceTicker: "SPY", sourceExpiry: "2026-12-18",
      targetTicker: "SPY", targetExpiry: "2026-09-18",
      betaSkew: 1.25,
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("scenario preview shows the exact §21.1 full-transmission mean", async () => {
    renderEditor([calRow()]);
    await screen.findByText(/calendar · 1/);
    // One incoming message at the receiver: z = +1.0 vol pt, β = 2, ρ = 1
    // → conditional mean EXACTLY +2.000 pts, q = 4 (the golden contract).
    const zInputs = screen
      .getAllByRole("spinbutton")
      .filter((el) => (el as HTMLInputElement).step === "0.5");
    fireEvent.change(zInputs[zInputs.length - 1], { target: { value: "1" } });
    const out = screen.getByTestId("preview-out");
    expect(out.textContent).toContain("2.000 pts");
    expect(out.textContent).toContain("q 4");
  });

  it("reset to auto persists an empty list (back to auto relations)", async () => {
    renderEditor([calRow()]);
    await screen.findByText(/calendar · 1/);
    fireEvent.click(screen.getByText("Reset to auto"));
    await waitFor(() => expect(putEdges).toHaveBeenCalledWith([]));
  });
});

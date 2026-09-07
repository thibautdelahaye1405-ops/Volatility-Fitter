// Graph shell (P5b U0 → GRAPH ERGONOMICS ARC) locks: the source fork
// (calibrations vs manual), Run/Validate routing, the manual observation
// rows, — regression 2026-07-09 — that the legacy Edges matrix is fed by the
// SELECTED universe (GET /universe), the drawer tabs and the inspector
// selection flow; plus the arc's rulings: the operator order, "what you see
// is what runs" (useDraftConfig follows the dirty draft, Apply / Discard),
// the relation card + Delete chord, the connect gesture, Live preview and
// Focus. The stub's default operator is the legacy smooth field so the
// legacy locks stay meaningful; message-family tests set the mode.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import GraphViewer from "./GraphViewer";
import type { UseGraphResult } from "../state/useGraph";
import type {
  ExtrapolateNode,
  UseGraphExtrapolationResult,
} from "../state/useGraphExtrapolation";
import type { PreflightReport, UsePreflightResult } from "../state/usePreflight";
import type { GraphTopologyResult } from "../state/useGraphTopology";
import type { UseLooComparisonResult } from "../state/useLooComparison";
import type { MessageConfigEnvelope } from "../state/useMessageConfig";
import type { MessageEdgeRow } from "../state/useMessageEdges";
import type { RelationDraft } from "../state/useRelationDraft";

const apiGet = vi.fn();
vi.mock("../state/api", () => ({
  API_BASE_URL: "http://localhost:8000",
  api: { get: (...args: unknown[]) => apiGet(...args) },
}));

// Hook stubs: each test assigns graphState/extraState before render.
let graphState: UseGraphResult;
let extraState: UseGraphExtrapolationResult;
let preflightState: UsePreflightResult;
vi.mock("../state/usePreflight", () => ({
  usePreflight: () => preflightState,
}));
vi.mock("../state/useGraph", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/useGraph")>()),
  useGraph: () => graphState,
}));
vi.mock("../state/useGraphExtrapolation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/useGraphExtrapolation")>()),
  useGraphExtrapolation: () => extraState,
}));

// Topology + U6 config: the hook is stubbed wholesale (its fetch internals
// have their own contracts); lifecycle ACTIONS are spied, diff math real.
let topologyState: GraphTopologyResult;
vi.mock("../state/useGraphTopology", () => ({
  useGraphTopology: () => topologyState,
}));
const activateMock = vi.fn((_notes: string) =>
  Promise.resolve({ draft: null, active: null }),
);
const revertMock = vi.fn(() => Promise.resolve({ draft: null, active: null }));
vi.mock("../state/useMessageConfig", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/useMessageConfig")>()),
  activateMessageConfig: (notes: string) => activateMock(notes),
  revertMessageConfig: () => revertMock(),
}));
const emptyMsgEdges = { fetchEdges: vi.fn(() => Promise.resolve([])), fetchAuto: vi.fn(() => Promise.resolve([])) };
vi.mock("../state/useMessageEdges", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/useMessageEdges")>()),
  useMessageEdges: () => emptyMsgEdges,
}));
let looState: UseLooComparisonResult;
vi.mock("../state/useLooComparison", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/useLooComparison")>()),
  useLooComparison: () => looState,
}));
// The relation draft (E2): rows on screen + spied edit operations.
let draftState: RelationDraft;
vi.mock("../state/useRelationDraft", () => ({
  useRelationDraft: () => draftState,
}));
vi.mock("../state/useLivePreview", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../state/useLivePreview")>()),
  LIVE_PREVIEW_DEBOUNCE_MS: 0,
}));

// Shared-session contexts + cinematics: inert stubs.
vi.mock("../state/smileSession", () => ({
  useSmileSession: () => ({ setTicker: vi.fn(), setExpiry: vi.fn() }),
}));
vi.mock("../state/graphFocus", () => ({ useGraphFocus: () => ({ setFocus: vi.fn() }) }));
const timeline = { revealedHop: Infinity, animating: false, skip: () => undefined };
vi.mock("../state/useWaveTimeline", () => ({ useWaveTimeline: () => timeline }));
vi.mock("../state/useAttributionParticles", () => ({ useAttributionParticles: () => [] }));

// Heavy leaves: the canvas and the drill-in cards have their own tests. The
// mock exposes an edge-click trigger for the U4 relation-card lock.
vi.mock("../components/GraphNetworkChart", () => ({
  default: ({
    onEdgeClick,
    onConnect,
    selectedRelationKey,
    onToggleFocus,
  }: {
    onEdgeClick?: (s: unknown) => void;
    onConnect?: (a: { ticker: string; expiry: string }, b: { ticker: string; expiry: string }) => void;
    selectedRelationKey?: string | null;
    onToggleFocus?: () => void;
  }) => (
    <div data-testid="chart" data-selected={selectedRelationKey ?? ""}>
      <button
        data-testid="chart-edge"
        onClick={() =>
          onEdgeClick?.({ kind: "calendar", ticker: "SPY", aExpiry: "2026-10-16", bExpiry: "2026-07-17" })
        }
      />
      <button
        data-testid="chart-relation"
        onClick={() => onEdgeClick?.({ kind: "relation", key: "SPY|2026-10-16>SPY|2026-07-17" })}
      />
      <button
        data-testid="chart-connect"
        disabled={onConnect === undefined}
        onClick={() => onConnect?.({ ticker: "SPY", expiry: "2026-07-17" }, { ticker: "SPY", expiry: "2026-10-16" })}
      />
      <button data-testid="chart-focus" onClick={onToggleFocus} />
    </div>
  ),
}));
vi.mock("../components/GraphAttributionCard", () => ({
  default: () => <div data-testid="attribution" />,
}));
// The matrix editor has its own data flow (blocks endpoints); here we only
// assert the shell hands it the right universe.
vi.mock("../components/EdgeMatrixEditor", () => ({
  default: ({ tickers }: { tickers: string[] }) => (
    <div data-testid="edge-matrix">{tickers.join(",")}</div>
  ),
}));

function graphStub(over: Partial<UseGraphResult> = {}): UseGraphResult {
  return {
    nodes: [
      { ticker: "SPY", expiry: "2026-07-17", t: 0.02, atmVol: 0.2, skew: 0, curvature: 0, lit: true },
      { ticker: "SPY", expiry: "2026-10-16", t: 0.25, atmVol: 0.2, skew: 0, curvature: 0, lit: false },
    ],
    loading: false,
    error: null,
    reload: vi.fn(),
    lit: {},
    toggleLit: vi.fn(),
    setShift: vi.fn(),
    lightMany: vi.fn(),
    unlight: vi.fn(),
    replaceLit: vi.fn(),
    params: {
      etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
      calendarWeight: null, crossWeight: null, crossExpiryToleranceDays: 0,
      propagationMode: "smooth_field", alphaT: 1, ampCal: 1, ampCross: 1,
      calPrecision: 1700, calEpsilon: 0.97,
      calDecay: "inverse_sqrt_gap", crossPrecision: 13000,
      calendarEnabled: true, calendarOverrides: {},
    },
    setParam: vi.fn(),
    resetParams: vi.fn(),
    autotune: vi.fn(),
    autotuning: false,
    autotuneResult: null,
    autotuneError: null,
    ...over,
  } as UseGraphResult;
}

function extraStub(
  over: Partial<UseGraphExtrapolationResult> = {},
): UseGraphExtrapolationResult {
  return {
    nodes: null,
    results: null,
    running: false,
    error: null,
    cycles: [],
    preview: false,
    backtest: null,
    backtesting: false,
    backtestError: null,
    run: vi.fn().mockResolvedValue(undefined),
    runBacktest: vi.fn().mockResolvedValue(undefined),
    clear: vi.fn(),
    ...over,
  };
}

/** A production posterior node for the diagnostics/inspector tests. */
function extraNode(over: Partial<ExtrapolateNode> = {}): ExtrapolateNode {
  return {
    ticker: "SPY", expiry: "2026-07-17", t: 0.02, lit: true, calibrated: true,
    priorSource: "stored", priorAsOf: "2026-07-16", transportDistance: 0,
    validForValidation: true,
    priorAtmVol: 0.2, priorSkew: 0, priorCurv: 0,
    postAtmVol: 0.21, postSkew: 0, postCurv: 0,
    shiftBp: 100, sd: 0.005, bandLo: 0.2, bandHi: 0.22, innovationBp: 100,
    baselinePrecision: [1, 1, 1], obsPrecision: null, precisionFactors: {},
    qIncoming: null, noLitPath: false,
    ...over,
  };
}

/** The default request body the shell builds (untouched knobs, no flags). */
const BODY = { etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1, flatAtm: false };

function renderShell() {
  render(<GraphViewer onNavigateToSmile={vi.fn()} />);
}

function preflightReport(over: Partial<PreflightReport> = {}): PreflightReport {
  return {
    universeNodes: 2, litCount: 1, darkCount: 1, observationCount: 1,
    propagationMode: "smooth_field", ok: true, issues: [],
    ...over,
  };
}

const CONFIG_ROW: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-10-16",
  targetTicker: "SPY", targetExpiry: "2026-07-17",
  messagePrecision: 1700, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
  relationClass: "calendar", precisionRule: "explicit",
};

function draftStub(rows: MessageEdgeRow[] = []): RelationDraft {
  const byKey = (key: string) =>
    rows.find((r) => `${r.sourceTicker}|${r.sourceExpiry}>${r.targetTicker}|${r.targetExpiry}` === key);
  return {
    rows, source: rows.length > 0 ? "draft" : "auto", loading: false, saving: false, error: null,
    canUndo: false, canRedo: false,
    add: vi.fn(), update: vi.fn(), remove: vi.fn(), removeMany: vi.fn(),
    flip: vi.fn(() => null), replaceAll: vi.fn(),
    seedAuto: vi.fn().mockResolvedValue(undefined), resetAuto: vi.fn().mockResolvedValue(undefined),
    undo: vi.fn(), redo: vi.fn(), reload: vi.fn(), byKey,
  };
}

function envelope(over: Partial<MessageConfigEnvelope> = {}): MessageConfigEnvelope {
  return {
    name: "default", version: 1, createdAt: "2026-07-19T10:00:00+00:00",
    author: "desk", parentVersion: null, notes: "", rows: [CONFIG_ROW],
    ...over,
  };
}

beforeEach(() => {
  graphState = graphStub();
  extraState = extraStub();
  preflightState = { report: null, loading: false, error: null };
  // Default /universe payload (messages-mode pane fetch); tests override.
  apiGet.mockResolvedValue({ asOf: "", tickers: [], expiries: {} });
  topologyState = {
    edges: [], msgRows: [], persistedRows: [], config: null, refresh: vi.fn(),
  };
  looState = { columns: null, running: null, error: null, run: vi.fn().mockResolvedValue(undefined) };
  draftState = draftStub();
  activateMock.mockClear();
  revertMock.mockClear();
});

afterEach(() => {
  cleanup();
  apiGet.mockReset();
});

describe("Graph shell (U0)", () => {
  it("routes Run to the production solve with the request body", async () => {
    renderShell();
    fireEvent.click(screen.getByText("Run"));
    // Calibrations source: the knobs only — no synthetic pulses on the body.
    expect(extraState.run).toHaveBeenCalledWith(BODY);
    // The run reveals Diagnostics once the attempt settles.
    await waitFor(() => expect(screen.getByText(/Press Run to transport/)).toBeTruthy());
  });

  it("manual what-if ships the pulses as syntheticObservations (U3)", async () => {
    graphState = graphStub({ lit: { "SPY|2026-07-17": 0.02 } });
    renderShell();
    fireEvent.click(screen.getByText("Manual what-if"));
    fireEvent.click(screen.getByText("Run"));
    // ONE solve either way — the production endpoint with the typed pulses.
    expect(extraState.run).toHaveBeenCalledWith({
      ...BODY,
      syntheticObservations: [
        { ticker: "SPY", expiry: "2026-07-17", dAtmVol: 0.02 },
      ],
    });
    await waitFor(() => expect(screen.getByText(/Press Run to transport/)).toBeTruthy());
  });

  it("scenario shortcuts replace the pulse set (calendar pulse)", () => {
    renderShell();
    fireEvent.click(screen.getByText("Manual what-if"));
    fireEvent.click(screen.getByText("Calendar pulse"));
    // Two SPY rungs in the stub ladder → mid rung = the 0.25y expiry, +1pt.
    expect(graphState.replaceLit).toHaveBeenCalledWith({ "SPY|2026-10-16": 0.01 });
    // Cross basket needs a second ticker — disabled on this universe.
    expect((screen.getByText("Cross basket") as HTMLButtonElement).disabled).toBe(true);
  });

  it("disables Run in manual mode with no pulses", () => {
    renderShell();
    fireEvent.click(screen.getByText("Manual what-if"));
    expect(screen.getByText(/No pulses/)).toBeTruthy();
    expect((screen.getByText("Run") as HTMLButtonElement).disabled).toBe(true);
  });

  it("edits and removes a manual observation in the Preview tab", () => {
    graphState = graphStub({ lit: { "SPY|2026-07-17": 0.02 } });
    renderShell();
    fireEvent.click(screen.getByText("Manual what-if"));
    // +2.0 vol pts -> dAtmVol 0.02; typing 3 updates the shift.
    fireEvent.change(screen.getByDisplayValue("2"), { target: { value: "3" } });
    expect(graphState.setShift).toHaveBeenCalledWith("SPY|2026-07-17", 0.03);
    fireEvent.click(screen.getByTitle("Remove observation"));
    expect(graphState.unlight).toHaveBeenCalledWith("SPY|2026-07-17");
  });

  it("Validation runs the side-by-side LOO with mode-forced bodies (U7)", () => {
    renderShell();
    fireEvent.click(screen.getByText("Validation"));
    fireEvent.click(screen.getByText("Compare operators (LOO)"));
    const [smooth, messages] = (looState.run as ReturnType<typeof vi.fn>).mock
      .lastCall as [Record<string, unknown>, Record<string, unknown>];
    expect(smooth.propagationMode ?? "smooth_field").toBe("smooth_field");
    expect(messages.propagationMode).toBe("precision_messages");
    cleanup();
    looState = { ...looState, running: "messages" };
    renderShell();
    fireEvent.click(screen.getByText("Validation"));
    expect(
      (screen.getByText(/Scoring messages…/) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("feeds the Edges matrix from the SELECTED universe, not the sandbox", async () => {
    apiGet.mockResolvedValue({
      asOf: "2026-07-09",
      tickers: ["SPY", "NVDA", "AAPL"],
      expiries: {
        SPY: [{ expiry: "2026-07-17", t: 0.02 }],
        NVDA: [{ expiry: "2026-07-17", t: 0.02 }],
        AAPL: [{ expiry: "2026-07-17", t: 0.02 }],
      },
    });
    renderShell();
    fireEvent.click(screen.getByText("Edges"));
    expect(apiGet).toHaveBeenCalledWith("/universe");
    await waitFor(() =>
      expect(screen.getByTestId("edge-matrix").textContent).toBe("SPY,NVDA,AAPL"),
    );
  });

  it("falls back to the sandbox nodes when the universe fetch fails", async () => {
    apiGet.mockRejectedValue(new Error("offline"));
    renderShell();
    fireEvent.click(screen.getByText("Edges"));
    await waitFor(() =>
      expect(screen.getByTestId("edge-matrix").textContent).toBe("SPY"),
    );
  });

  it("selects a diagnostics row into the inspector (facts + attribution)", () => {
    const n = extraNode();
    extraState = extraStub({
      nodes: [n],
      results: { "SPY|2026-07-17": {
        ticker: n.ticker, expiry: n.expiry, t: n.t, baseAtmVol: n.priorAtmVol,
        postAtmVol: n.postAtmVol, shiftBp: n.shiftBp, sd: n.sd,
        bandLo: n.bandLo, bandHi: n.bandHi, observed: true,
      } },
    });
    renderShell();
    fireEvent.click(screen.getByText("Diagnostics"));
    fireEvent.click(
      screen.getByTitle(
        "Inspect this node (attribution of its move to the lit observations)",
      ),
    );
    expect(screen.getByText("Prior source")).toBeTruthy();
    expect(screen.getByTestId("attribution")).toBeTruthy();
    // Non-layered run: the wire carried no V0 fields → no decomposition card.
    expect(screen.queryByTestId("decomposition")).toBeNull();
  });

  it("layered run surfaces the decomposition card in the inspector (P6 V2)", () => {
    const n = extraNode({
      boundaryClass: "fresh_certified",
      systematicAtmVol: 0.001, residualAtmVol: -0.0003,
      residualAgeDays: 0.5, harmonicAtmVol: 0.0001,
      residualSurpriseAtm: -2.1,
    });
    graphState = graphStub();
    graphState.params.propagationMode = "layered_dynamic_harmonic";
    extraState = extraStub({
      nodes: [n],
      results: { "SPY|2026-07-17": {
        ticker: n.ticker, expiry: n.expiry, t: n.t, baseAtmVol: n.priorAtmVol,
        postAtmVol: n.postAtmVol, shiftBp: n.shiftBp, sd: n.sd,
        bandLo: n.bandLo, bandHi: n.bandHi, observed: true,
      } },
    });
    renderShell();
    // P6 V3 layered surfaces: the Dynamics policy card (left pane) and the
    // §5 A/B timeline fixture (Preview tab, the default open tab).
    expect(screen.getByTestId("dynamics-policy")).toBeTruthy();
    expect(screen.getByTestId("timeline-preview")).toBeTruthy();
    fireEvent.click(screen.getByText("Diagnostics"));
    // |χ| = 2.1 > 2 → the loud-surprise banner above the results table.
    expect(screen.getByText(/1 loud residual surprise/)).toBeTruthy();
    expect(screen.getByText(/worst χ -2\.1/)).toBeTruthy();
    fireEvent.click(
      screen.getByTitle(
        "Inspect this node (attribution of its move to the lit observations)",
      ),
    );
    const card = screen.getByTestId("decomposition");
    expect(screen.getByText("clamped boundary")).toBeTruthy();
    // Scoped to the card — the diagnostics banner also cites the worst χ.
    expect(card.textContent).toContain("χ -2.1");
  });

  it("preflight blockers gate Run; the chip lists the finding (U5)", () => {
    preflightState = {
      report: preflightReport({
        ok: false,
        issues: [
          { severity: "blocker", code: "empty_universe",
            message: "The selected universe is empty.", count: 1 },
        ],
      }),
      loading: false,
      error: null,
    };
    renderShell();
    expect((screen.getByText("Run") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("1 blocker"));
    expect(screen.getByText("The selected universe is empty.")).toBeTruthy();
  });

  it("preflight warnings never gate Run (U5)", () => {
    preflightState = {
      report: preflightReport({
        issues: [
          { severity: "warning", code: "no_lit_path",
            message: "3 node(s) stranded.", count: 3 },
          { severity: "warning", code: "beta_extreme",
            message: "1 relation beyond the cap.", count: 1 },
        ],
      }),
      loading: false,
      error: null,
    };
    renderShell();
    expect(screen.getByText("2 warnings")).toBeTruthy();
    expect((screen.getByText("Run") as HTMLButtonElement).disabled).toBe(false);
  });

  it("config chip: dirty draft shows the diff and Activate routes (U6)", async () => {
    topologyState.config = {
      active: envelope(),
      draft: envelope({
        version: 2, parentVersion: 1,
        rows: [{ ...CONFIG_ROW, betaAtmVol: 1.5 }],
      }),
    };
    renderShell();
    // Pill = active name·version + the staged-edit count; popover = diff + Apply.
    fireEvent.click(screen.getByText("1 edit"));
    expect(screen.getByText(/\+0 −0 ~1/)).toBeTruthy();
    expect(screen.getByText(/the draft \(staged edits\)/)).toBeTruthy();
    fireEvent.click(screen.getByText("Apply"));
    expect(activateMock).toHaveBeenCalledWith("");
    await waitFor(() => expect(topologyState.refresh).toHaveBeenCalled());
  });

  it("what you see is what runs: a dirty draft ships useDraftConfig by itself", async () => {
    graphState = graphStub();
    graphState.params.propagationMode = "precision_messages";
    topologyState.config = {
      active: envelope(),
      draft: envelope({ version: 2, rows: [{ ...CONFIG_ROW, betaAtmVol: 1.5 }] }),
    };
    renderShell();
    fireEvent.click(screen.getByText("Run"));
    await waitFor(() => expect(extraState.run).toHaveBeenCalled());
    const body = (extraState.run as ReturnType<typeof vi.fn>).mock
      .lastCall?.[0] as Record<string, unknown>;
    expect(body.useDraftConfig).toBe(true);
    expect(body.propagationMode).toBe("precision_messages");
    // A clean draft (identical rows) runs the active config.
    cleanup();
    extraState = extraStub();
    topologyState.config = { active: envelope(), draft: envelope({ version: 2 }) };
    renderShell();
    fireEvent.click(screen.getByText("Run"));
    await waitFor(() => expect(extraState.run).toHaveBeenCalled());
    const clean = (extraState.run as ReturnType<typeof vi.fn>).mock
      .lastCall?.[0] as Record<string, unknown>;
    expect(clean.useDraftConfig).toBeUndefined();
  });

  it("layered segment sets the dynamic-harmonic operator (P6 V1)", () => {
    renderShell();
    fireEvent.click(screen.getByText("Layered"));
    expect(graphState.setParam).toHaveBeenCalledWith(
      "propagationMode",
      "layered_dynamic_harmonic",
    );
  });

  it("layered mode ships propagationMode on the run body and uses the message surfaces", async () => {
    graphState = graphStub();
    graphState.params.propagationMode = "layered_dynamic_harmonic";
    renderShell();
    // Message-family policy pane (layered reuses the relation config); the
    // legacy operator is NOT a segment until it is selected.
    expect(screen.getByText(/How each smile informs its neighbors/)).toBeTruthy();
    expect(screen.queryByText("Smooth field")).toBeNull();
    expect(screen.getByText("Precision")).toBeTruthy();
    fireEvent.click(screen.getByText("Run"));
    await waitFor(() => expect(extraState.run).toHaveBeenCalled());
    const body = (extraState.run as ReturnType<typeof vi.fn>).mock
      .lastCall?.[0] as Record<string, unknown>;
    expect(body.propagationMode).toBe("layered_dynamic_harmonic");
    // The relation knobs ride with the operator (same §9.2 policy family).
    expect(body.calendarPrecisionScale).toBe(1700);
  });

  it("edge click opens the relation card in the inspector (U4)", () => {
    renderShell();
    fireEvent.click(screen.getByTestId("chart-edge"));
    expect(screen.getByText(/Relation · SPY calendar/)).toBeTruthy();
    // Smooth-field mode: the minimal coupling note (message card needs the
    // message operator).
    expect(screen.getByText(/Smooth-field coupling/)).toBeTruthy();
    fireEvent.click(screen.getByTitle("Close relation card"));
    expect(screen.queryByText(/Relation · SPY calendar/)).toBeNull();
  });

  it("collapses the drawer on an active-tab re-click", () => {
    renderShell();
    // Preview is the default open tab: its calibrations blurb is visible.
    expect(screen.getByText(/transported priors drive the field/)).toBeTruthy();
    fireEvent.click(screen.getByText("Preview"));
    expect(screen.queryByText(/transported priors drive the field/)).toBeNull();
  });
});

describe("Graph shell (GRAPH ERGONOMICS ARC)", () => {
  const messages = () => {
    graphState = graphStub();
    graphState.params.propagationMode = "layered_dynamic_harmonic";
    draftState = draftStub([CONFIG_ROW]);
  };

  it("the legacy operator lives under Advanced and comes back as a segment", () => {
    messages();
    renderShell();
    fireEvent.click(screen.getByText("Smooth field (legacy)"));
    expect(graphState.setParam).toHaveBeenCalledWith("propagationMode", "smooth_field");
    cleanup();
    graphState = graphStub(); // smooth_field → the third segment + Back button
    renderShell();
    expect(screen.getByText("Smooth field")).toBeTruthy();
    fireEvent.click(screen.getByText("← Back to Layered"));
    expect(graphState.setParam).toHaveBeenCalledWith("propagationMode", "layered_dynamic_harmonic");
  });

  it("an arrow click opens the relation card; sliders and Delete edit the draft", () => {
    messages();
    renderShell();
    fireEvent.click(screen.getByTestId("chart-relation"));
    expect(screen.getByTestId("relation-card")).toBeTruthy();
    expect(screen.getByTestId("chart").getAttribute("data-selected")).toBe(
      "SPY|2026-10-16>SPY|2026-07-17",
    );
    // β slider → linked handles patch on the selected key.
    fireEvent.change(screen.getByTestId("slider-beta"), { target: { value: "1.5" } });
    expect(draftState.update).toHaveBeenCalledWith("SPY|2026-10-16>SPY|2026-07-17", {
      betaAtmVol: 1.5, betaSkew: 1.5, betaCurv: 1.5,
    });
    // Delete chord removes it and clears the selection.
    fireEvent.keyDown(window, { key: "Delete" });
    expect(draftState.remove).toHaveBeenCalledWith("SPY|2026-10-16>SPY|2026-07-17");
    expect(screen.queryByTestId("relation-card")).toBeNull();
  });

  it("the connect gesture adds a draft row and selects it", () => {
    messages();
    renderShell();
    fireEvent.click(screen.getByTestId("chart-connect"));
    expect(draftState.add).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceTicker: "SPY", sourceExpiry: "2026-07-17",
        targetTicker: "SPY", targetExpiry: "2026-10-16",
        relationClass: "calendar", precisionRule: "calendar_distance",
      }),
    );
    expect(screen.getByTestId("chart").getAttribute("data-selected")).toBe(
      "SPY|2026-07-17>SPY|2026-10-16",
    );
    // Smooth field: no connect handler (read-only canvas).
    cleanup();
    graphState = graphStub();
    renderShell();
    expect((screen.getByTestId("chart-connect") as HTMLButtonElement).disabled).toBe(true);
  });

  it("Ctrl+Z / Ctrl+Y route to the draft's undo / redo", () => {
    messages();
    renderShell();
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    expect(draftState.undo).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "y", ctrlKey: true });
    expect(draftState.redo).toHaveBeenCalled();
  });

  it("the Relations tab lists the draft rows and a row click selects the arrow", () => {
    messages();
    renderShell();
    fireEvent.click(screen.getByTestId("open-relations"));
    expect(screen.getByTestId("relations-tab")).toBeTruthy();
    fireEvent.click(screen.getByText(/SPY 10-16/));
    expect(screen.getByTestId("relation-card")).toBeTruthy();
  });

  it("Live re-solves as a non-persisting preview; Run commits", async () => {
    messages();
    renderShell();
    fireEvent.click(screen.getByTestId("live-toggle"));
    await waitFor(() => expect(extraState.run).toHaveBeenCalled());
    const body = (extraState.run as ReturnType<typeof vi.fn>).mock
      .lastCall?.[0] as Record<string, unknown>;
    expect(body.preview).toBe(true);
    fireEvent.click(screen.getByText("Run"));
    const committed = (extraState.run as ReturnType<typeof vi.fn>).mock
      .lastCall?.[0] as Record<string, unknown>;
    expect(committed.preview).toBeUndefined();
  });

  it("Focus hides the side panes and the drawer; Esc restores them", () => {
    messages();
    renderShell();
    expect(screen.getByTestId("policy-pane")).toBeTruthy();
    fireEvent.click(screen.getByTestId("chart-focus"));
    expect(screen.queryByTestId("policy-pane")).toBeNull();
    expect(screen.queryByTestId("inspector-pane")).toBeNull();
    expect(screen.queryByText("Diagnostics")).toBeNull();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByTestId("policy-pane")).toBeTruthy();
  });

  it("Level 0 sliders write the calendar / cross confidence as precisions", () => {
    messages();
    renderShell();
    fireEvent.change(screen.getByTestId("slider-cross"), { target: { value: String(Math.log10(1)) } });
    // conf = 1/σ = 1 → σ = 1 pt → p = 10 000
    expect(graphState.setParam).toHaveBeenCalledWith("crossPrecision", 10000);
  });
});

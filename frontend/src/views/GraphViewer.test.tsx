// Graph shell (P5b U0) feature-parity locks, ported from the dissolved
// PropagatePanel: the source fork (calibrations vs manual), Run/Validate
// routing, the manual observation rows, and — regression 2026-07-09 — that
// the Edges matrix is fed by the SELECTED universe (GET /universe), not the
// sandbox lattice (empty on the gated server until mid-mode calibrations
// exist). Plus the new shell surfaces: drawer tabs and the inspector
// selection flow.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import GraphViewer from "./GraphViewer";
import type { UseGraphResult } from "../state/useGraph";
import type {
  ExtrapolateNode,
  UseGraphExtrapolationResult,
} from "../state/useGraphExtrapolation";
import type { PreflightReport, UsePreflightResult } from "../state/usePreflight";

const apiGet = vi.fn();
vi.mock("../state/api", () => ({
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

// Topology fetchers: stable refs (the viewer's edge effect depends on them).
const emptyEdges = { fetchEdges: vi.fn(() => Promise.resolve([])), fetchLattice: vi.fn(() => Promise.resolve([])) };
vi.mock("../state/useGraphEdges", () => ({ useGraphEdges: () => emptyEdges }));
const emptyMsgEdges = { fetchEdges: vi.fn(() => Promise.resolve([])), fetchAuto: vi.fn(() => Promise.resolve([])) };
vi.mock("../state/useMessageEdges", () => ({ useMessageEdges: () => emptyMsgEdges }));

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
  default: ({ onEdgeClick }: { onEdgeClick?: (s: unknown) => void }) => (
    <button
      data-testid="chart-edge"
      onClick={() =>
        onEdgeClick?.({
          kind: "calendar",
          ticker: "SPY",
          aExpiry: "2026-10-16",
          bExpiry: "2026-07-17",
        })
      }
    />
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
      calendarWeight: null, crossWeight: null,
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

beforeEach(() => {
  graphState = graphStub();
  extraState = extraStub();
  preflightState = { report: null, loading: false, error: null };
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

  it("runs the LOO backtest with the same body and shows progress", () => {
    renderShell();
    fireEvent.click(screen.getByText("Validation"));
    fireEvent.click(screen.getByText("Validate (LOO)"));
    expect(extraState.runBacktest).toHaveBeenCalledWith(BODY);
    cleanup();
    extraState = extraStub({ backtesting: true });
    renderShell();
    fireEvent.click(screen.getByText("Validation"));
    expect((screen.getByText("Backtesting…") as HTMLButtonElement).disabled).toBe(true);
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

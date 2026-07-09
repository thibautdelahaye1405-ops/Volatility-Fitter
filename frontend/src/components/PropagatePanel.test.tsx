// Propagate panel: the Graph workspace's single control panel. Locks the
// source fork (calibrations vs manual), the Propagate/Validate routing, and —
// regression 2026-07-09 — that the Edges matrix is fed by the SELECTED
// universe (GET /universe), not the sandbox lattice (empty on the gated
// server until mid-mode calibrations exist).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PropagatePanel from "./PropagatePanel";
import type { UseGraphResult } from "../state/useGraph";
import type { UseGraphExtrapolationResult } from "../state/useGraphExtrapolation";

const apiGet = vi.fn();
vi.mock("../state/api", () => ({
  api: { get: (...args: unknown[]) => apiGet(...args) },
}));

// The matrix editor has its own data flow (blocks endpoints); here we only
// assert the panel hands it the right universe.
vi.mock("./EdgeMatrixEditor", () => ({
  default: ({ tickers }: { tickers: string[] }) => (
    <div data-testid="edge-matrix">{tickers.join(",")}</div>
  ),
}));
vi.mock("./SolverPanel", () => ({ default: () => <div data-testid="solver" /> }));

function graphStub(over: Partial<UseGraphResult> = {}): UseGraphResult {
  return {
    nodes: [
      { ticker: "SPY", expiry: "2026-07-17", t: 0.02, atmVol: 0.2, skew: 0, curvature: 0, lit: true },
    ],
    loading: false,
    error: null,
    reload: vi.fn(),
    lit: {},
    toggleLit: vi.fn(),
    setShift: vi.fn(),
    lightMany: vi.fn(),
    unlight: vi.fn(),
    params: {
      etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
      calendarWeight: null, crossWeight: null,
    },
    setParam: vi.fn(),
    resetParams: vi.fn(),
    solve: vi.fn().mockResolvedValue(undefined),
    solving: false,
    solveError: null,
    results: null,
    clear: vi.fn(),
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
    backtest: null,
    backtesting: false,
    backtestError: null,
    run: vi.fn().mockResolvedValue(undefined),
    runBacktest: vi.fn().mockResolvedValue(undefined),
    clear: vi.fn(),
    ...over,
  };
}

const BODY = { etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1, flatAtm: false };

function renderPanel(opts: {
  source?: "calibrations" | "manual";
  graph?: UseGraphResult;
  extra?: UseGraphExtrapolationResult;
} = {}) {
  const graph = opts.graph ?? graphStub();
  const extra = opts.extra ?? extraStub();
  render(
    <PropagatePanel
      source={opts.source ?? "calibrations"}
      graph={graph}
      extra={extra}
      body={BODY}
      flatAtm={false}
      setFlatAtm={vi.fn()}
      crossBeta={1}
      setCrossBeta={vi.fn()}
      onOpenSmile={vi.fn()}
    />,
  );
  return { graph, extra };
}

afterEach(() => {
  cleanup();
  apiGet.mockReset();
});

describe("PropagatePanel", () => {
  it("routes Propagate to the production solve with the request body", () => {
    const { extra, graph } = renderPanel();
    fireEvent.click(screen.getByText("Propagate"));
    expect(extra.run).toHaveBeenCalledWith(BODY);
    expect(graph.solve).not.toHaveBeenCalled();
  });

  it("routes Propagate to the sandbox solve for manual what-if", () => {
    const { extra, graph } = renderPanel({
      source: "manual",
      graph: graphStub({ lit: { "SPY|2026-07-17": 0.02 } }),
    });
    fireEvent.click(screen.getByText("Propagate"));
    expect(graph.solve).toHaveBeenCalledOnce();
    expect(extra.run).not.toHaveBeenCalled();
  });

  it("disables Propagate in manual mode with no lit nodes", () => {
    renderPanel({ source: "manual" });
    expect(screen.getByText(/No lit nodes/)).toBeTruthy();
    expect((screen.getByText("Propagate") as HTMLButtonElement).disabled).toBe(true);
  });

  it("edits and removes a manual observation", () => {
    const { graph } = renderPanel({
      source: "manual",
      graph: graphStub({ lit: { "SPY|2026-07-17": 0.02 } }),
    });
    // +2.0 vol pts -> dAtmVol 0.02; typing 3 updates the shift.
    fireEvent.change(screen.getByDisplayValue("2"), { target: { value: "3" } });
    expect(graph.setShift).toHaveBeenCalledWith("SPY|2026-07-17", 0.03);
    fireEvent.click(screen.getByTitle("Remove observation"));
    expect(graph.unlight).toHaveBeenCalledWith("SPY|2026-07-17");
  });

  it("runs the LOO backtest with the same body and shows progress", () => {
    const { extra } = renderPanel();
    fireEvent.click(screen.getByText("Validate (LOO)"));
    expect(extra.runBacktest).toHaveBeenCalledWith(BODY);
    cleanup();
    renderPanel({ extra: extraStub({ backtesting: true }) });
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
    renderPanel();
    fireEvent.click(screen.getByText("Edges"));
    expect(apiGet).toHaveBeenCalledWith("/universe");
    await waitFor(() =>
      expect(screen.getByTestId("edge-matrix").textContent).toBe("SPY,NVDA,AAPL"),
    );
  });

  it("falls back to the sandbox nodes when the universe fetch fails", async () => {
    apiGet.mockRejectedValue(new Error("offline"));
    renderPanel();
    fireEvent.click(screen.getByText("Edges"));
    await waitFor(() =>
      expect(screen.getByTestId("edge-matrix").textContent).toBe("SPY"),
    );
  });
});

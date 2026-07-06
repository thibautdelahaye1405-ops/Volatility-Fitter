// Quality workspace: tiles, exception filtering and the offline card, with
// the data hook mocked (the /quality contract is locked by
// backend/tests/test_quality.py).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import QualityViewer from "./QualityViewer";
import type { QualityNode, QualityReport } from "../state/useQuality";

const mockUse = vi.fn();
vi.mock("../state/useQuality", () => ({
  useQuality: () => mockUse(),
}));

function node(over: Partial<QualityNode>): QualityNode {
  return {
    ticker: "ALPHA", expiry: "2026-07-10", tau: 0.1, hasFit: true, stale: false,
    model: "lqd", nQuotes: 9, rmsBp: 8.2, maxIvBp: 16.3, atmVol: 0.21, skew: -0.1,
    leeLeft: 0.02, leeRight: 0.01, leeOk: true, calendarViolation: 0,
    calendarOk: true, varSwapQuoted: false, filterActive: false,
    filterContaminated: false, ready: true, issues: [],
    ...over,
  };
}

function report(): QualityReport {
  const ready = node({});
  const stale = node({
    expiry: "2026-09-09", stale: true, ready: false, issues: ["stale"], rmsBp: 3.0,
  });
  return {
    fitMode: "mid",
    rmsBudgetBp: 50,
    summary: {
      tickers: 1, litNodes: 2, darkNodes: 0, fitted: 2, stale: 1, noFit: 0,
      readyNodes: 1, arbFlags: 0, medianRmsBp: 5.6, worstRmsBp: 8.2,
      filterMode: "off", priorMode: "hybrid", lvTickers: 1, lvArbFree: 1,
    },
    tickers: [
      {
        ticker: "ALPHA", nodes: 2, fitted: 2, stale: 1, surfaceRmsBp: 5.0,
        worstNodeRmsBp: 8.2, arbFlags: 0, ready: 1,
        lv: {
          hasFit: true, stale: false, rmsIvErrorBp: 0.0086, maxIvErrorBp: 0.03,
          surfaceRmsBp: 0.0086, arbitrageFree: true, calendarViolations: 0,
          worstMinDensity: 0.001,
        },
      },
    ],
    nodes: [ready, stale],
  };
}

afterEach(() => {
  cleanup();
  mockUse.mockReset();
});

describe("QualityViewer", () => {
  it("renders the headline tiles and both tables", () => {
    mockUse.mockReturnValue({ report: report(), loading: false, error: null, reload: vi.fn() });
    render(<QualityViewer />);
    expect(screen.getByText("Publish ready")).toBeTruthy();
    expect(screen.getAllByText("1/2").length).toBe(2); // ready tile + ticker rollup
    expect(screen.getByText("5.6 bp")).toBeTruthy(); // median RMS tile
    // The sub-0.1bp LV RMS renders with sig figs, not a fake 0.0.
    expect(screen.getByText(/0\.0086 bp/)).toBeTruthy();
    expect(screen.getAllByText("stale").length).toBeGreaterThan(0); // exception status
  });

  it("filters to exceptions only", () => {
    mockUse.mockReturnValue({ report: report(), loading: false, error: null, reload: vi.fn() });
    render(<QualityViewer />);
    expect(screen.getAllByText("ALPHA").length).toBeGreaterThan(2); // rollup + 2 rows
    fireEvent.click(screen.getByLabelText(/exceptions only/i));
    // Only the stale node's row remains in the node table.
    expect(screen.getByText("2026-09-09")).toBeTruthy();
    expect(screen.queryByText("2026-07-10")).toBeNull();
  });

  it("shows the live-only offline card with retry", () => {
    const reload = vi.fn();
    mockUse.mockReturnValue({ report: null, loading: false, error: "backend down", reload });
    render(<QualityViewer />);
    expect(screen.getByText(/requires the live backend/i)).toBeTruthy();
    fireEvent.click(screen.getByText("Retry"));
    expect(reload).toHaveBeenCalledOnce();
  });
});

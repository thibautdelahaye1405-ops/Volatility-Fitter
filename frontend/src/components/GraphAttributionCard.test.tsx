// Graph attribution card: renders the exact per-lit-node decomposition the
// backend computed (contribution rows, others fold, shift header) and wires
// the close / open-smile actions. The hook is mocked — the endpoint contract
// itself is locked by backend/tests/test_graph_attribution.py.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GraphAttributionCard from "./GraphAttributionCard";
import type { GraphNodeSmile } from "../state/useGraphNodeSmile";

const mockUse = vi.fn();
vi.mock("../state/useGraphNodeSmile", () => ({
  useGraphNodeSmile: (...args: unknown[]) => mockUse(...args),
}));

function nodeSmile(over: Partial<GraphNodeSmile> = {}): GraphNodeSmile {
  return {
    ticker: "AAPL",
    expiry: "2026-09-18",
    t: 0.2,
    model: "lqd",
    lit: false,
    calibrated: false,
    priorSource: "saved",
    priorAtmVol: 0.25,
    postAtmVol: 0.2512, // +12 bp shift
    sd: 0.01,
    sdSkew: 0.02,
    sdCurv: 0.15,
    bandKind: "functional",
    varSwapVol: 0.26,
    varSwapVolSd: 0.012,
    tailMassLeft: 0.01,
    tailMassLeftSd: 0.002,
    tailMassRight: 0.008,
    tailMassRightSd: 0.001,
    post: [],
    postBandLo: [],
    postBandHi: [],
    prior: [],
    litCalibration: [],
    metrics: null,
    attribution: [
      {
        ticker: "SPX", expiry: "2026-09-18",
        innovationBp: 96.0, gain: 0.12, contributionBp: 11.52, edgeBeta: 0.7,
      },
      {
        ticker: "QQQ", expiry: "2026-09-18",
        innovationBp: -10.0, gain: 0.05, contributionBp: -0.5, edgeBeta: null,
      },
    ],
    attributionOthersBp: 0.98,
    ...over,
  };
}

function renderCard(node: GraphNodeSmile | null, extras: Partial<{ loading: boolean }> = {}) {
  mockUse.mockReturnValue({ node, loading: extras.loading ?? false, error: null });
  const onClose = vi.fn();
  const onOpenSmile = vi.fn();
  render(
    <GraphAttributionCard
      ticker="AAPL"
      expiry="2026-09-18"
      body={{}}
      onClose={onClose}
      onOpenSmile={onOpenSmile}
    />,
  );
  return { onClose, onOpenSmile };
}

afterEach(() => {
  cleanup();
  mockUse.mockReset();
});

describe("GraphAttributionCard", () => {
  it("shows the shift and each contributor with sign and edge beta", () => {
    renderCard(nodeSmile());
    expect(screen.getByText("+12.0bp")).toBeTruthy(); // header shift
    expect(screen.getByText("SPX")).toBeTruthy();
    expect(screen.getByText("+11.5bp")).toBeTruthy(); // dominant contribution
    expect(screen.getByText("-0.5bp")).toBeTruthy(); // negative contributor
    expect(screen.getByText("β0.70")).toBeTruthy(); // direct-edge context chip
    expect(screen.getByText("+ others")).toBeTruthy();
    expect(screen.getByText("+1.0bp")).toBeTruthy(); // folded remainder
  });

  it("explains the arithmetic in the tooltip", () => {
    renderCard(nodeSmile());
    const row = screen.getByTitle(/gain 0\.120 × innovation \+96\.0bp/);
    expect(row.title).toContain("direct edge β 0.70");
  });

  it("handles a solve with no lit observations", () => {
    renderCard(nodeSmile({ attribution: [], attributionOthersBp: 0 }));
    expect(screen.getByText(/nothing to attribute/i)).toBeTruthy();
  });

  it("wires close and open-smile", () => {
    const { onClose, onOpenSmile } = renderCard(nodeSmile());
    fireEvent.click(screen.getByTitle("Close attribution"));
    expect(onClose).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByTitle("Open the reconstructed smile"));
    expect(onOpenSmile).toHaveBeenCalledWith("AAPL", "2026-09-18");
  });
});

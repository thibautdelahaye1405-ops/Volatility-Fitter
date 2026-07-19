// U2 policy surfaces: the calendar policy card's LIVE example (exact §8.2 /
// §9.2 numbers), enable switch, per-ticker overrides, ladder + |β|-cap
// warnings; the cross matrix's cell resolution (persisted / implied reverse /
// auto), sentence hover, and editor drill-in.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CalendarPolicyCard from "./CalendarPolicyCard";
import CrossMatrixCard, { crossCell } from "./CrossMatrixCard";
import type { SolverParams } from "../../state/useGraph";
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

const EXPIRIES = {
  SPY: [
    { expiry: "2026-07-24", t: 0.02 },
    { expiry: "2026-10-16", t: 0.25 },
    { expiry: "2027-01-15", t: 0.5 },
  ],
};

afterEach(cleanup);

describe("CalendarPolicyCard", () => {
  it("shows the LIVE +1pt example with the exact §8.2/§9.2 numbers", () => {
    render(
      <CalendarPolicyCard
        params={params()}
        setParam={vi.fn()}
        raw={false}
        tickers={["SPY"]}
        expiries={EXPIRIES}
      />,
    );
    // β = (0.5/0.25)^1 = 2; p = 1700/(0.97+√0.25) = 1156.46 → σ = 2.94 pt.
    expect(screen.getByTestId("cal-live-example").textContent).toBe(
      "6M informs 3M: +1.00 pt → +2.00 pt message · relationship uncertainty 2.94 pt",
    );
  });

  it("routes the policy switch and per-ticker override adds to params", () => {
    const setParam = vi.fn();
    render(
      <CalendarPolicyCard
        params={params()}
        setParam={setParam}
        raw={false}
        tickers={["SPY", "NVDA"]}
        expiries={EXPIRIES}
      />,
    );
    fireEvent.click(screen.getByLabelText("Calendar messages"));
    expect(setParam).toHaveBeenCalledWith("calendarEnabled", false);
    fireEvent.change(screen.getByTitle("Add a per-ticker calendar-policy override"), {
      target: { value: "NVDA" },
    });
    expect(setParam).toHaveBeenCalledWith("calendarOverrides", {
      NVDA: { enabled: true, precisionScale: null, betaExponent: null },
    });
  });

  it("renders the ladder with β/σ chips and flags |β| beyond the cap", () => {
    render(
      <CalendarPolicyCard
        params={params()}
        setParam={vi.fn()}
        raw={false}
        tickers={["SPY"]}
        expiries={EXPIRIES}
      />,
    );
    // 0.02y → 0.25y amplifies β = 12.5 — one capped rung out of two.
    expect(screen.getByText(/1 rung with/)).toBeTruthy();
    expect(screen.getByText(/β 12.50/)).toBeTruthy();
    expect(screen.getByText(/β 2.00/)).toBeTruthy();
  });
});

const ROW: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-10-16",
  targetTicker: "NVDA", targetExpiry: "2026-10-16",
  messagePrecision: 10000, betaAtmVol: 2, betaSkew: 1, betaCurv: 1,
  relationClass: "broad_index", precisionRule: "explicit",
};

describe("crossCell", () => {
  it("resolves persisted, implied-reverse, and auto cells", () => {
    // Direct orientation: the persisted factor itself.
    expect(crossCell([ROW], "NVDA", "SPY", 13000)).toMatchObject({
      beta: 2, precision: 10000, provenance: "persisted",
    });
    // Mirror orientation: §7.6/§8.3 reverse identities 1/β and p·β².
    expect(crossCell([ROW], "SPY", "NVDA", 13000)).toMatchObject({
      beta: 0.5, precision: 40000, provenance: "implied",
    });
    // No rows: the auto relation at the cross precision scale.
    expect(crossCell([], "SPY", "NVDA", 13000)).toMatchObject({
      beta: 1, precision: 13000, provenance: "auto",
    });
  });
});

describe("CrossMatrixCard", () => {
  it("renders sentence hovers and drills into the editor on cell click", () => {
    const onDrillIn = vi.fn();
    render(
      <CrossMatrixCard
        params={params()}
        setParam={vi.fn()}
        raw={false}
        tickers={["NVDA", "SPY"]}
        rows={[ROW]}
        onDrillIn={onDrillIn}
      />,
    );
    const cell = screen.getByTitle(/SPY informs NVDA: \+1\.00 pt → \+2\.00 pt message/);
    fireEvent.click(cell);
    expect(onDrillIn).toHaveBeenCalledOnce();
  });
});

// Pure Quality-workspace helpers: bp formatting + table ordering.
import { describe, expect, it } from "vitest";
import { fmtBp, sortNodes } from "./qualityFormat";
import type { QualityNode } from "../state/useQuality";

function node(over: Partial<QualityNode>): QualityNode {
  return {
    ticker: "ALPHA",
    expiry: "2026-07-10",
    tau: 0.1,
    hasFit: true,
    stale: false,
    model: "lqd",
    nQuotes: 10,
    rmsBp: 5,
    maxIvBp: 10,
    atmVol: 0.2,
    skew: -0.1,
    leeLeft: 0.5,
    leeRight: 0.5,
    leeOk: true,
    calendarViolation: 0,
    calendarOk: true,
    varSwapQuoted: false,
    filterActive: false,
    filterContaminated: false,
    ready: true,
    issues: [],
    ...over,
  };
}

describe("fmtBp", () => {
  it("renders normal figures with one decimal", () => {
    expect(fmtBp(12.34)).toBe("12.3");
    expect(fmtBp(0.1)).toBe("0.1");
  });

  it("renders an exact zero as 0.0", () => {
    expect(fmtBp(0)).toBe("0.0");
  });

  it("keeps sub-0.1 figures visible instead of a fake hard zero", () => {
    expect(fmtBp(0.0086)).toBe("0.0086");
    expect(fmtBp(0.043)).toBe("0.043");
  });
});

describe("sortNodes", () => {
  const ready = node({ expiry: "a", rmsBp: 30 });
  const worseReady = node({ expiry: "b", rmsBp: 40 });
  const exception = node({ expiry: "c", rmsBp: 5, ready: false, issues: ["stale"] });

  it("puts exceptions first, then worst RMS", () => {
    const out = sortNodes([ready, worseReady, exception], "exceptions");
    expect(out.map((n) => n.expiry)).toEqual(["c", "b", "a"]);
  });

  it("sorts by RMS descending", () => {
    const out = sortNodes([ready, exception, worseReady], "rms");
    expect(out.map((n) => n.rmsBp)).toEqual([40, 30, 5]);
  });

  it("keeps backend order for node mode and never mutates the input", () => {
    const input = [worseReady, ready];
    const out = sortNodes(input, "node");
    expect(out.map((n) => n.expiry)).toEqual(["b", "a"]);
    sortNodes(input, "exceptions");
    expect(input.map((n) => n.expiry)).toEqual(["b", "a"]); // untouched
  });
});

// Pure edge-matrix codecs: rule↔grid round trip, TSV parse, symmetric
// collapse, CSV shape and deterministic ordering.
import { describe, expect, it } from "vitest";
import {
  cellAt,
  cellKey,
  collapseSymmetric,
  gridToRule,
  parseTsv,
  ruleToGrid,
  toCsv,
} from "./edgeMatrix";
import type { MatrixCell } from "./edgeMatrix";
import type { GraphEdge } from "../state/useGraphEdges";
import type { GraphBlockRule } from "../state/useGraphBlocks";

const TICKERS = ["AAPL", "QQQ", "SPY"];

const cell = (over: Partial<MatrixCell> = {}): MatrixCell => ({
  weight: 1,
  beta: 1,
  symmetric: false,
  ...over,
});

const override: GraphEdge = {
  fromTicker: "SPY",
  fromExpiry: "2026-08-21",
  toTicker: "QQQ",
  toExpiry: "2026-08-21",
  weight: 4,
  betaAtmVol: 1.2,
  betaSkew: 1.2,
  betaCurv: 1.2,
};

// Constructed in sorted-key order (AAPL|QQQ < QQQ|SPY < SPY|SPY) so the
// round trip is a strict identity.
const rule: GraphBlockRule = {
  pairs: [
    { a: "AAPL", b: "QQQ", weight: 2, beta: 0.8, symmetric: false },
    { a: "QQQ", b: "SPY", weight: 3, beta: 1, symmetric: true },
  ],
  calendar: [{ ticker: "SPY", weight: 5, beta: 1 }],
  overrides: [override],
};

describe("ruleToGrid / gridToRule", () => {
  it("round-trips a rule through the grid unchanged", () => {
    const grid = ruleToGrid(rule);
    expect(grid.size).toBe(3);
    expect(gridToRule(grid, rule.overrides)).toEqual(rule);
  });

  it("keys the diagonal from calendar entries, symmetric by construction", () => {
    const grid = ruleToGrid(rule);
    expect(grid.get(cellKey("SPY", "SPY"))).toEqual(cell({ weight: 5, symmetric: true }));
  });

  it("emits deterministic sorted order regardless of insertion order", () => {
    const a = new Map<string, MatrixCell>([
      [cellKey("SPY", "SPY"), cell({ weight: 5, symmetric: true })],
      [cellKey("QQQ", "SPY"), cell({ weight: 3, symmetric: true })],
      [cellKey("AAPL", "QQQ"), cell({ weight: 2, beta: 0.8 })],
    ]);
    const b = new Map([...a.entries()].reverse());
    expect(gridToRule(a, [])).toEqual(gridToRule(b, []));
    expect(gridToRule(a, []).pairs.map((p) => `${p.a}|${p.b}`)).toEqual([
      "AAPL|QQQ",
      "QQQ|SPY",
    ]);
  });

  it("drops zero-weight cells (0 = no rule, same as blank)", () => {
    const grid = new Map([[cellKey("AAPL", "SPY"), cell({ weight: 0 })]]);
    expect(gridToRule(grid, [])).toEqual({ pairs: [], calendar: [], overrides: [] });
  });
});

describe("cellAt", () => {
  it("resolves the mirrored cell only when symmetric", () => {
    const grid = new Map([
      [cellKey("QQQ", "SPY"), cell({ weight: 3, symmetric: true })],
      [cellKey("AAPL", "QQQ"), cell({ weight: 2 })],
    ]);
    expect(cellAt(grid, "SPY", "QQQ")?.weight).toBe(3); // mirror of a symmetric pair
    expect(cellAt(grid, "QQQ", "AAPL")).toBeUndefined(); // one-way rule
  });
});

describe("parseTsv", () => {
  it("parses a tab matrix: corner header, diagonal symmetric, blanks skipped", () => {
    const text = "\tSPY\tQQQ\nSPY\t5\t2\nQQQ\t\t1\n";
    const { grid, errors } = parseTsv(text, TICKERS);
    expect(errors).toEqual([]);
    expect(grid.size).toBe(3);
    expect(grid.get(cellKey("SPY", "SPY"))).toEqual(cell({ weight: 5, symmetric: true }));
    expect(grid.get(cellKey("SPY", "QQQ"))).toEqual(cell({ weight: 2 }));
    expect(grid.get(cellKey("QQQ", "QQQ"))).toEqual(cell({ weight: 1, symmetric: true }));
  });

  it("reports unknown tickers in errors and keeps the rest, never throws", () => {
    const text = "\tSPY\tZZZ\nSPY\t1\t9\nYYY\t2\t3\n";
    const { grid, errors } = parseTsv(text, TICKERS);
    expect(errors).toHaveLength(2);
    expect(errors[0]).toContain("ZZZ");
    expect(errors[1]).toContain("YYY");
    expect([...grid.keys()]).toEqual([cellKey("SPY", "SPY")]);
  });

  it("treats 0 as no rule and flags non-numeric cells", () => {
    const text = "\tSPY\tQQQ\nSPY\t0\tx\n";
    const { grid, errors } = parseTsv(text, TICKERS);
    expect(grid.size).toBe(0);
    expect(errors).toEqual(['SPY→QQQ: not a number "x"']);
  });

  it("collapses equal mirrored cells into one symmetric cell", () => {
    const text = "\tSPY\tQQQ\nSPY\t\t2\nQQQ\t2\t\n";
    const { grid, errors } = parseTsv(text, TICKERS);
    expect(errors).toEqual([]);
    expect([...grid.entries()]).toEqual([
      [cellKey("QQQ", "SPY"), cell({ weight: 2, symmetric: true })],
    ]);
  });
});

describe("collapseSymmetric", () => {
  it("merges equal mirrored cells under the first sorted key", () => {
    const grid = new Map([
      [cellKey("SPY", "QQQ"), cell({ weight: 2 })],
      [cellKey("QQQ", "SPY"), cell({ weight: 2 })],
    ]);
    expect([...collapseSymmetric(grid).entries()]).toEqual([
      [cellKey("QQQ", "SPY"), cell({ weight: 2, symmetric: true })],
    ]);
  });

  it("leaves unequal mirrored cells and the diagonal alone", () => {
    const grid = new Map([
      [cellKey("SPY", "QQQ"), cell({ weight: 2 })],
      [cellKey("QQQ", "SPY"), cell({ weight: 3 })],
      [cellKey("SPY", "SPY"), cell({ weight: 5, symmetric: true })],
    ]);
    expect(collapseSymmetric(grid).size).toBe(3);
  });
});

describe("toCsv", () => {
  const grid = new Map([
    [cellKey("QQQ", "SPY"), cell({ weight: 3, symmetric: true })],
    [cellKey("SPY", "SPY"), cell({ weight: 5, symmetric: true })],
  ]);

  it("emits the square matrix, symmetric pairs in both mirrored cells", () => {
    expect(toCsv(grid, TICKERS)).toBe(
      ",AAPL,QQQ,SPY\nAAPL,,,\nQQQ,,,3\nSPY,,3,5\n",
    );
  });

  it("round-trips through parseTsv (comma fallback delimiter)", () => {
    const { grid: parsed, errors } = parseTsv(toCsv(grid, TICKERS), TICKERS);
    expect(errors).toEqual([]);
    expect(parsed).toEqual(grid);
  });
});

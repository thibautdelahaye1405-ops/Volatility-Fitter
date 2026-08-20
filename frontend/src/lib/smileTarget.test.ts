// Fit-target overlay geometry (V3.4 item 4): mid polyline + band ribbons.
import { describe, expect, it } from "vitest";
import { midLinePath, ribbonPath } from "./smileTarget";
import type { QuoteBand } from "./mockData";

/** Identity-ish display transforms: x = 100k, y = 100 - 100·vol (pixels). */
const toX = (k: number) => k * 100;
const toY = (v: number) => 100 - v * 100;

function quote(k: number, over: Partial<QuoteBand> = {}): QuoteBand {
  const mid = 0.2;
  return {
    k,
    bid: mid - 0.01,
    ask: mid + 0.01,
    mid,
    index: Math.round(k * 100),
    excluded: false,
    amended: false,
    targetLo: mid - 0.005,
    targetHi: mid + 0.005,
    ...over,
  };
}

const bid = (q: QuoteBand) => q.bid;
const ask = (q: QuoteBand) => q.ask;
const tLo = (q: QuoteBand) => q.targetLo;
const tHi = (q: QuoteBand) => q.targetHi;

describe("midLinePath", () => {
  it("draws one polyline through the mids in ascending k", () => {
    const qs = [quote(0.2, { mid: 0.3 }), quote(0.0, { mid: 0.2 }), quote(0.1, { mid: 0.25 })];
    // Unsorted input is sorted by k before drawing.
    expect(midLinePath(qs, toX, toY)).toBe("M0.00,80.00L10.00,75.00L20.00,70.00");
  });

  it("skips excluded quotes and connects across the gap", () => {
    const qs = [quote(0.0), quote(0.1, { excluded: true }), quote(0.2)];
    expect(midLinePath(qs, toX, toY)).toBe("M0.00,80.00L20.00,80.00");
  });

  it("yields nothing for empty or single-quote inputs", () => {
    expect(midLinePath([], toX, toY)).toBe("");
    expect(midLinePath([quote(0.0)], toX, toY)).toBe("");
    // Two quotes with one excluded: still a single point — nothing to draw.
    expect(midLinePath([quote(0.0), quote(0.1, { excluded: true })], toX, toY)).toBe("");
  });
});

describe("ribbonPath", () => {
  it("builds one closed subpath: forward along hi, back along lo", () => {
    const qs = [quote(0.0), quote(0.1)];
    // hi = ask = 0.21 → y 79; lo = bid = 0.19 → y 81.
    expect(ribbonPath(qs, bid, ask, toX, toY)).toBe(
      "M0.00,79.00L10.00,79.00L10.00,81.00L0.00,81.00Z",
    );
  });

  it("breaks the ribbon at an excluded strike (visible gap)", () => {
    const qs = [quote(0.0), quote(0.1), quote(0.2, { excluded: true }), quote(0.3), quote(0.4)];
    const d = ribbonPath(qs, bid, ask, toX, toY);
    const subpaths = d.split(" ");
    expect(subpaths).toHaveLength(2);
    expect(subpaths.every((s) => s.startsWith("M") && s.endsWith("Z"))).toBe(true);
    // Neither subpath touches the excluded strike's x = 20.
    expect(d).not.toContain("20.00,");
  });

  it("treats missing target edges as gaps (mid-mode payloads draw nothing)", () => {
    const bare = [quote(0.0, { targetLo: null, targetHi: null }), quote(0.1, { targetLo: undefined, targetHi: undefined })];
    expect(ribbonPath(bare, tLo, tHi, toX, toY)).toBe("");
    // One missing edge inside a run splits it like an exclusion.
    const qs = [quote(0.0), quote(0.1), quote(0.2, { targetHi: null }), quote(0.3), quote(0.4)];
    expect(ribbonPath(qs, tLo, tHi, toX, toY).split(" ")).toHaveLength(2);
  });

  it("skips single-quote runs (no drawable area)", () => {
    const qs = [
      quote(0.0, { excluded: true }),
      quote(0.1), // lone included quote between exclusions
      quote(0.2, { excluded: true }),
      quote(0.3),
      quote(0.4),
    ];
    const d = ribbonPath(qs, bid, ask, toX, toY);
    expect(d.split(" ")).toHaveLength(1); // only the [0.3, 0.4] run survives
    expect(d).not.toContain("10.00,");
    expect(ribbonPath([quote(0.0)], bid, ask, toX, toY)).toBe("");
    expect(ribbonPath([], bid, ask, toX, toY)).toBe("");
  });

  it("degenerates cleanly when the band collapses to the mid (lo == hi)", () => {
    const qs = [
      quote(0.0, { targetLo: 0.2, targetHi: 0.2 }),
      quote(0.1, { targetLo: 0.2, targetHi: 0.2 }),
    ];
    // Zero-area ribbon along the mid line: top edge == bottom edge reversed.
    expect(ribbonPath(qs, tLo, tHi, toX, toY)).toBe(
      "M0.00,80.00L10.00,80.00L10.00,80.00L0.00,80.00Z",
    );
  });

  it("sorts unsorted quotes so the ribbon stays monotone in x", () => {
    const qs = [quote(0.2), quote(0.0), quote(0.1)];
    const d = ribbonPath(qs, bid, ask, toX, toY);
    const xs = [...d.matchAll(/[ML](-?\d+\.\d+),/g)].map((m) => Number(m[1]));
    expect(xs.slice(0, 3)).toEqual([0, 10, 20]); // top edge ascending
    expect(xs.slice(3)).toEqual([20, 10, 0]); // bottom edge descending
  });
});

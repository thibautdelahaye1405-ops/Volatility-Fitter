// Locks for the filter-replay artifact helpers (V3.9 rider).
import { describe, expect, it } from "vitest";

import {
  newestPart,
  partForExpiry,
  replayChipLabel,
  stepsForExpiry,
  type FilterReplayPart,
  type FilterReplayPartMeta,
} from "./filterReplay";
import type { FilterStepWire } from "./filterTimeline";

const meta = (over: Partial<FilterReplayPartMeta>): FilterReplayPartMeta => ({
  ticker: "SPY",
  day: "2026-06-10",
  nInstants: 13,
  fitMode: "mid",
  filterMode: "overlay",
  expiries: ["2026-07-17"],
  mtime: 1_760_000_000,
  ...over,
});

const step = (ts: number): FilterStepWire => ({
  ts,
  dtDays: 0.02,
  prediction: [0.2, -0.3, 0.1],
  predictionStd: [0.01, 0.02, 0.05],
  observation: [0.21, -0.29, 0.12],
  observationStd: [0.005, 0.01, 0.02],
  innovation: [0.01, 0.01, 0.02],
  zeta: [0.9, 0.4, 0.3],
  gain: [0.8, 0.6, 0.4],
  posterior: [0.208, -0.292, 0.115],
  posteriorStd: [0.004, 0.009, 0.018],
  processBreakdown: { clock: [1e-6, 2e-6, 3e-6] },
  transportDistance: 0.001,
  provenance: "update",
  resetReason: null,
  contaminated: false,
});

describe("newestPart", () => {
  it("returns null on an empty list", () => {
    expect(newestPart([])).toBeNull();
  });

  it("picks the latest replayed day regardless of list order", () => {
    const a = meta({ day: "2026-06-09" });
    const b = meta({ day: "2026-06-11" });
    const c = meta({ day: "2026-06-10" });
    expect(newestPart([a, b, c])).toBe(b);
    expect(newestPart([b, a, c])).toBe(b);
  });

  it("breaks a same-day tie on mtime (a missing mtime counts as oldest)", () => {
    const older = meta({ mtime: 10 });
    const newer = meta({ mtime: 20 });
    expect(newestPart([older, newer])).toBe(newer);
    expect(newestPart([newer, older])).toBe(newer);
    const bare: { day: string; mtime?: number }[] = [
      { day: "2026-06-10" },
      { day: "2026-06-10", mtime: 1 },
    ];
    expect(newestPart(bare)).toEqual({ day: "2026-06-10", mtime: 1 });
  });
});

describe("partForExpiry", () => {
  const spy1 = meta({ day: "2026-06-09", expiries: ["2026-07-17", "2026-09-18"] });
  const spy2 = meta({ day: "2026-06-10", expiries: ["2026-07-17"] });

  it("returns the newest part carrying the expiry, else null", () => {
    expect(partForExpiry([spy1, spy2], "2026-07-17")).toBe(spy2);
    expect(partForExpiry([spy1, spy2], "2026-09-18")).toBe(spy1);
    expect(partForExpiry([spy1, spy2], "2026-12-18")).toBeNull();
  });

  it("never matches an empty expiry", () => {
    expect(partForExpiry([meta({ expiries: [""] })], "")).toBeNull();
  });
});

describe("stepsForExpiry", () => {
  const part: FilterReplayPart = {
    meta: { ticker: "SPY", day: "2026-06-10" },
    nodes: { "2026-07-17": [step(1), step(2)] },
  };

  it("returns the node's steps oldest first", () => {
    expect(stepsForExpiry(part, "2026-07-17").map((s) => s.ts)).toEqual([1, 2]);
  });

  it("is [] for an absent part, an unknown node or a malformed node", () => {
    expect(stepsForExpiry(null, "2026-07-17")).toEqual([]);
    expect(stepsForExpiry(undefined, "2026-07-17")).toEqual([]);
    expect(stepsForExpiry(part, "2026-09-18")).toEqual([]);
    const bad = { meta: part.meta, nodes: { x: "nope" } } as unknown as FilterReplayPart;
    expect(stepsForExpiry(bad, "x")).toEqual([]);
  });
});

describe("replayChipLabel", () => {
  it("labels the chip with the replayed day", () => {
    expect(replayChipLabel({ day: "2026-06-10" })).toBe("Replay 2026-06-10");
  });
});

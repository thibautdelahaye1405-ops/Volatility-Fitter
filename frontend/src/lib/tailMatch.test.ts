// Tail-matching helpers: chip state from the selection + the backend report,
// and the table pill of a constrained row.
import { describe, expect, it } from "vitest";
import type { CompareTailInfo } from "./mockData";
import { TAIL_FLAG_ORDER, tailChipState, tailMatchedLabel } from "./tailMatch";

const info = (over: Partial<CompareTailInfo>): CompareTailInfo => ({
  requested: ["varswap", "lee", "edge"],
  applied: ["varswap", "lee", "edge"],
  target: "lqd",
  leeAvailable: true,
  leeClamped: false,
  ...over,
});

describe("tailChipState", () => {
  it("is off and plain without a selection or a report", () => {
    const s = tailChipState("varswap", new Set(), null);
    expect(s).toMatchObject({ on: false, dropped: false, clamped: false });
    expect(s.title).toContain("var-swap");
  });

  it("flags a lit toggle the backend dropped, with its reason", () => {
    const s = tailChipState(
      "lee", new Set(["lee", "edge"]),
      info({ requested: ["lee", "edge"], applied: ["edge"], leeAvailable: false, note: "alpha > 0" }),
    );
    expect(s.on).toBe(true);
    expect(s.dropped).toBe(true);
    expect(s.title).toContain("Not applied: alpha > 0");
    expect(tailChipState("edge", new Set(["lee", "edge"]), info({ applied: ["edge"] })).dropped).toBe(false);
  });

  it("marks a clamped Lee target and ignores a report about other flags", () => {
    const s = tailChipState("lee", new Set(["lee"]), info({ requested: ["lee"], applied: ["lee"], leeClamped: true, note: "cap 1.95" }));
    expect(s.clamped).toBe(true);
    expect(s.title).toContain("cap 1.95");
    // A stale report that never asked for this flag says nothing about it.
    const t = tailChipState("varswap", new Set(["varswap"]), info({ requested: ["lee"], applied: [] }));
    expect(t.dropped).toBe(false);
  });
});

describe("tailMatchedLabel", () => {
  it("lists the constraints in wire order, short names, or null when plain", () => {
    expect(tailMatchedLabel({ tailMatched: ["edge", "varswap"] })).toBe("= var-swap · edge");
    expect(tailMatchedLabel({ tailMatched: [] })).toBeNull();
    expect(tailMatchedLabel({})).toBeNull();
    expect(TAIL_FLAG_ORDER).toEqual(["varswap", "lee", "edge"]);
  });
});

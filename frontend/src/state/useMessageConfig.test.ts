// U6 config diff: the dirty badge must count added/removed/changed relations
// exactly (a clean draft copy is NOT dirty). P6 V3 adds the policy dials to
// the dirty computation and closes the V1 semantics-equality gap.
import { describe, expect, it } from "vitest";
import { configDirty, diffRows, policyDirty } from "./useMessageConfig";
import type { MessageEdgeRow } from "./useMessageEdges";

function row(over: Partial<MessageEdgeRow> = {}): MessageEdgeRow {
  return {
    sourceTicker: "SPY", sourceExpiry: "2026-12-18",
    targetTicker: "SPY", targetExpiry: "2026-09-18",
    messagePrecision: 4, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
    relationClass: "calendar", precisionRule: "explicit",
    ...over,
  };
}

const ENV = {
  name: "default", version: 1, createdAt: "", author: "desk",
  parentVersion: null, notes: "",
};

describe("diffRows / configDirty", () => {
  it("counts added, removed and changed relations by directed identity", () => {
    const active = [row(), row({ targetExpiry: "2026-06-19" })];
    const draft = [
      row({ betaAtmVol: 1.5 }), // changed
      row({ sourceTicker: "QQQ", targetTicker: "QQQ" }), // added
      // the 06-19 row is gone → removed
    ];
    expect(diffRows(draft, active)).toEqual({ added: 1, removed: 1, changed: 1 });
  });

  it("a clean draft copy is not dirty; staging against no active is", () => {
    const rows = [row()];
    expect(
      configDirty({ draft: { ...ENV, rows }, active: { ...ENV, rows } }),
    ).toBe(false);
    expect(configDirty({ draft: { ...ENV, rows }, active: null })).toBe(true);
    expect(configDirty(null)).toBe(false);
  });

  it("a semantics-only edit counts as changed (V1 gap closed in V3)", () => {
    const d = diffRows([row({ relationSemantics: "directed_state" })], [row()]);
    expect(d).toEqual({ added: 0, removed: 0, changed: 1 });
    // null and absent semantics are the same thing (auto).
    expect(diffRows([row({ relationSemantics: null })], [row()]).changed).toBe(0);
  });

  it("policy participates in dirtiness; null compares as schema defaults", () => {
    const rows = [row()];
    expect(
      policyDirty({
        draft: { ...ENV, rows, policy: null },
        active: { ...ENV, rows },
      }),
    ).toBe(false); // null vs absent = both the schema defaults
    const staged = {
      draft: {
        ...ENV, rows,
        policy: {
          clampMaxAgeDays: 2.5,
          residualHalfLifeDays: 5,
          semanticsDefaults: {},
        },
      },
      active: { ...ENV, rows },
    };
    expect(policyDirty(staged)).toBe(true);
    expect(configDirty(staged)).toBe(true); // rows identical — policy alone
  });
});

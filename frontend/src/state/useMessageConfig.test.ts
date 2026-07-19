// U6 config diff: the dirty badge must count added/removed/changed relations
// exactly (a clean draft copy is NOT dirty).
import { describe, expect, it } from "vitest";
import { configDirty, diffRows } from "./useMessageConfig";
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
});

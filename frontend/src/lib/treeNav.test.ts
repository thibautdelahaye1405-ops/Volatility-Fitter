// Nodes-tree keyboard algebra (UI SHELL v2 wave 3, C1).
import { describe, expect, it } from "vitest";
import { EMPTY_TYPEAHEAD, TYPEAHEAD_MS, treeKeyAction, typeAheadTarget } from "./treeNav";
import type { TreeRow } from "./treeNav";

const rows: TreeRow[] = [
  { id: "g:AAPL", kind: "group", ticker: "AAPL", expanded: true },
  { id: "AAPL|2026-12-18", kind: "node", ticker: "AAPL", expiry: "2026-12-18" },
  { id: "AAPL|2027-03-19", kind: "node", ticker: "AAPL", expiry: "2027-03-19" },
  { id: "g:NVDA", kind: "group", ticker: "NVDA", expanded: false },
  { id: "g:SPY", kind: "group", ticker: "SPY", expanded: true },
  { id: "SPY|2026-12-18", kind: "node", ticker: "SPY", expiry: "2026-12-18" },
];
const act = (id: string | null, key: string, mods: Partial<Parameters<typeof treeKeyAction>[2]> = {}) =>
  treeKeyAction(rows, id, { key, ...mods }).action;

describe("arrow navigation", () => {
  it("moves down / up across visible rows and clamps at the ends", () => {
    expect(act(null, "ArrowDown")).toEqual({ type: "focus", id: "g:AAPL" });
    expect(act("g:AAPL", "ArrowDown")).toEqual({ type: "focus", id: "AAPL|2026-12-18" });
    expect(act("SPY|2026-12-18", "ArrowDown")).toEqual({ type: "focus", id: "SPY|2026-12-18" });
    expect(act("g:AAPL", "ArrowUp")).toEqual({ type: "focus", id: "g:AAPL" });
    expect(act("g:NVDA", "ArrowUp")).toEqual({ type: "focus", id: "AAPL|2027-03-19" });
    expect(act("g:NVDA", "Home")).toEqual({ type: "focus", id: "g:AAPL" });
    expect(act("g:NVDA", "End")).toEqual({ type: "focus", id: "SPY|2026-12-18" });
  });

  it("→ expands a collapsed group, enters an expanded one; ← collapses or climbs", () => {
    expect(act("g:NVDA", "ArrowRight")).toEqual({ type: "expand", ticker: "NVDA", expanded: true });
    expect(act("g:AAPL", "ArrowRight")).toEqual({ type: "focus", id: "AAPL|2026-12-18" });
    expect(act("AAPL|2026-12-18", "ArrowRight")).toBeNull();
    expect(act("g:AAPL", "ArrowLeft")).toEqual({ type: "expand", ticker: "AAPL", expanded: false });
    expect(act("g:NVDA", "ArrowLeft")).toBeNull();
    expect(act("AAPL|2027-03-19", "ArrowLeft")).toEqual({ type: "focus", id: "g:AAPL" });
  });
});

describe("open / toggle / filter", () => {
  it("Enter previews, Shift+Enter and Space pin, Ctrl+Enter opens in the other split", () => {
    expect(act("SPY|2026-12-18", "Enter")).toEqual({ type: "open", ticker: "SPY", expiry: "2026-12-18", mode: "preview" });
    expect(act("SPY|2026-12-18", "Enter", { shiftKey: true })).toMatchObject({ mode: "pin" });
    expect(act("SPY|2026-12-18", " ")).toMatchObject({ mode: "pin" });
    expect(act("SPY|2026-12-18", "Enter", { ctrlKey: true })).toMatchObject({ mode: "split" });
    expect(act("g:NVDA", "Enter")).toEqual({ type: "expand", ticker: "NVDA", expanded: true });
  });

  it("L toggles lit/dark on a node row only; Tab hands over to the filter", () => {
    expect(act("SPY|2026-12-18", "l")).toEqual({ type: "lit", ticker: "SPY", expiry: "2026-12-18" });
    expect(act("g:SPY", "L")).toBeNull(); // no L-ticker → no type-ahead hit either
    expect(act("g:SPY", "Tab")).toEqual({ type: "filter" });
    expect(act("g:SPY", "Tab", { shiftKey: true })).toBeNull();
    expect(act("g:SPY", "ArrowDown", { altKey: true })).toBeNull();
  });
});

describe("type-ahead", () => {
  it("jumps to the next ticker with the prefix, wrapping, and chains letters within the window", () => {
    expect(typeAheadTarget(rows, null, "s")).toBe("g:SPY");
    expect(typeAheadTarget(rows, "g:SPY", "a")).toBe("g:AAPL");
    expect(typeAheadTarget(rows, "AAPL|2026-12-18", "n")).toBe("g:NVDA");
    expect(typeAheadTarget(rows, null, "zz")).toBeNull();
    const r1 = treeKeyAction(rows, "g:AAPL", { key: "s" }, EMPTY_TYPEAHEAD, 1000);
    expect(r1.action).toEqual({ type: "focus", id: "g:SPY" });
    expect(r1.typeahead).toEqual({ buffer: "s", at: 1000 });
    // "s" then "p" within the window → prefix "sp" (still SPY); "n" later → fresh "n".
    const r2 = treeKeyAction(rows, "g:SPY", { key: "p" }, r1.typeahead, 1000 + TYPEAHEAD_MS / 2);
    expect(r2.typeahead.buffer).toBe("sp");
    expect(r2.action).toEqual({ type: "focus", id: "g:SPY" });
    const r3 = treeKeyAction(rows, "g:SPY", { key: "n" }, r2.typeahead, 1000 + 3 * TYPEAHEAD_MS);
    expect(r3.typeahead.buffer).toBe("n");
    expect(r3.action).toEqual({ type: "focus", id: "g:NVDA" });
  });

  it("a chained prefix beats the L shortcut", () => {
    const r1 = treeKeyAction(rows, "SPY|2026-12-18", { key: "a" }, EMPTY_TYPEAHEAD, 10);
    const r2 = treeKeyAction(rows, r1.action && r1.action.type === "focus" ? r1.action.id : null, { key: "l" }, r1.typeahead, 20);
    expect(r2.typeahead.buffer).toBe("al");
    expect(r2.action).toBeNull(); // no "AL…" ticker
  });
});

// Locks for the workbench tab algebra (UI SHELL v2, S1): VS Code preview
// semantics, close/activate/cycle bookkeeping, pruning and persistence.
import { describe, expect, it } from "vitest";
import {
  EMPTY_TABS,
  activateTab,
  activeTab,
  closeAllTabs,
  closeOtherTabs,
  closeTab,
  cycleTab,
  moveTab,
  openTab,
  openTabWithMemory,
  parseTabKey,
  pinTab,
  pruneTabs,
  pruneViewMemory,
  restoreTabs,
  restoreViewMemory,
  setViewMemory,
  tabKey,
} from "./workbenchTabs";

const spyDec = { ticker: "SPY", expiry: "2026-12-18" };
const spyMar = { ticker: "SPY", expiry: "2027-03-19" };
const nvda = { ticker: "NVDA", expiry: "2026-12-18" };

describe("tabKey / parseTabKey", () => {
  it("round-trips a node", () => {
    expect(tabKey("SPY", "2026-12-18")).toBe("SPY|2026-12-18");
    expect(parseTabKey("SPY|2026-12-18")).toEqual(spyDec);
    expect(parseTabKey("garbage")).toEqual({ ticker: "garbage", expiry: "" });
  });
});

describe("openTab", () => {
  it("opens a pinned tab and activates it", () => {
    const s = openTab(EMPTY_TABS, spyDec);
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0].preview).toBe(false);
    expect(s.activeKey).toBe("SPY|2026-12-18");
    expect(activeTab(s)).toEqual(s.tabs[0]);
  });

  it("a preview open REPLACES the existing preview tab in place", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, spyMar, { preview: true });
    s = openTab(s, nvda, { preview: true });
    expect(s.tabs.map((t) => t.key)).toEqual(["SPY|2026-12-18", "NVDA|2026-12-18"]);
    expect(s.tabs[1].preview).toBe(true);
    expect(s.activeKey).toBe("NVDA|2026-12-18");
  });

  it("re-opening an open node just activates it; pinned open pins a preview", () => {
    let s = openTab(EMPTY_TABS, spyDec, { preview: true });
    s = openTab(s, nvda);
    s = openTab(s, spyDec, { preview: true });
    expect(s.tabs).toHaveLength(2);
    expect(s.activeKey).toBe("SPY|2026-12-18");
    expect(s.tabs[0].preview).toBe(true);
    s = openTab(s, spyDec);
    expect(s.tabs[0].preview).toBe(false);
  });

  it("inserts a new pinned tab right after the active one", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, nvda);
    s = activateTab(s, "SPY|2026-12-18");
    s = openTab(s, spyMar);
    expect(s.tabs.map((t) => t.ticker + t.expiry.slice(5, 7))).toEqual(["SPY12", "SPY03", "NVDA12"]);
  });
});

describe("pin / close / activate / cycle / move", () => {
  it("pinTab flips preview off and is a no-op otherwise", () => {
    const s = openTab(EMPTY_TABS, spyDec, { preview: true });
    const p = pinTab(s, "SPY|2026-12-18");
    expect(p.tabs[0].preview).toBe(false);
    expect(pinTab(p, "SPY|2026-12-18")).toBe(p);
    expect(pinTab(p, "nope")).toBe(p);
  });

  it("closing the active tab activates the right neighbour, else the left", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, spyMar);
    s = openTab(s, nvda);
    s = activateTab(s, "SPY|2027-03-19");
    s = closeTab(s, "SPY|2027-03-19");
    expect(s.activeKey).toBe("NVDA|2026-12-18");
    s = closeTab(s, "NVDA|2026-12-18");
    expect(s.activeKey).toBe("SPY|2026-12-18");
    s = closeTab(s, "SPY|2026-12-18");
    expect(s).toEqual(EMPTY_TABS);
  });

  it("closing an inactive tab keeps the active key", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, nvda);
    s = closeTab(s, "SPY|2026-12-18");
    expect(s.activeKey).toBe("NVDA|2026-12-18");
    expect(closeTab(s, "missing")).toBe(s);
  });

  it("closeOtherTabs / closeAllTabs", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, nvda);
    s = openTab(s, spyMar);
    const o = closeOtherTabs(s, "NVDA|2026-12-18");
    expect(o.tabs.map((t) => t.key)).toEqual(["NVDA|2026-12-18"]);
    expect(o.activeKey).toBe("NVDA|2026-12-18");
    expect(closeOtherTabs(s, "missing")).toBe(s);
    expect(closeAllTabs()).toEqual(EMPTY_TABS);
  });

  it("cycleTab wraps in both directions and ignores an empty strip", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, nvda);
    expect(cycleTab(s, 1).activeKey).toBe("SPY|2026-12-18");
    expect(cycleTab(s, -1).activeKey).toBe("SPY|2026-12-18");
    expect(cycleTab(cycleTab(s, -1), -1).activeKey).toBe("NVDA|2026-12-18");
    expect(cycleTab(EMPTY_TABS, 1)).toBe(EMPTY_TABS);
  });

  it("moveTab reorders and clamps the target index", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, nvda);
    s = openTab(s, spyMar);
    const m = moveTab(s, "SPY|2026-12-18", 99);
    expect(m.tabs.map((t) => t.key)).toEqual(["NVDA|2026-12-18", "SPY|2027-03-19", "SPY|2026-12-18"]);
    expect(m.activeKey).toBe(s.activeKey);
    expect(moveTab(s, "missing", 0)).toBe(s);
  });
});

describe("pruneTabs / restoreTabs", () => {
  it("drops tabs outside the universe and re-activates sensibly", () => {
    let s = openTab(EMPTY_TABS, spyDec);
    s = openTab(s, nvda);
    const pruned = pruneTabs(s, (t) => t === "SPY");
    expect(pruned.tabs.map((t) => t.key)).toEqual(["SPY|2026-12-18"]);
    expect(pruned.activeKey).toBe("SPY|2026-12-18");
    expect(pruneTabs(s, () => true)).toBe(s);
  });

  it("restoreTabs validates a persisted blob (dedupe, drop malformed, fix active)", () => {
    const r = restoreTabs({
      tabs: [
        { ticker: "SPY", expiry: "2026-12-18", preview: true },
        { ticker: "SPY", expiry: "2026-12-18" },
        { ticker: "", expiry: "2026-12-18" },
        "junk",
        { ticker: "NVDA", expiry: "2026-12-18", preview: "yes" },
      ],
      activeKey: "missing|x",
    });
    expect(r.tabs.map((t) => [t.key, t.preview])).toEqual([
      ["SPY|2026-12-18", true],
      ["NVDA|2026-12-18", false],
    ]);
    expect(r.activeKey).toBe("SPY|2026-12-18");
    expect(restoreTabs(null)).toEqual(EMPTY_TABS);
    expect(restoreTabs({ tabs: "x" })).toEqual(EMPTY_TABS);
  });
});

// ---- per-tab view memory (wave 3, C2) --------------------------------------
describe("view memory", () => {
  const A = { ticker: "SPY", expiry: "2026-12-18" };
  const B = { ticker: "NVDA", expiry: "2027-03-19" };

  it("writes per tab and lens without clobbering the other lens", () => {
    let m = setViewMemory({}, "SPY|2026-12-18", "parametric", { view: "term" });
    m = setViewMemory(m, "SPY|2026-12-18", "localvol", { view: "table" });
    expect(m["SPY|2026-12-18"]).toEqual({ parametric: { view: "term" }, localvol: { view: "table" } });
    m = setViewMemory(m, "SPY|2026-12-18", "parametric", { view: "smile" });
    expect(m["SPY|2026-12-18"].parametric).toEqual({ view: "smile" });
  });

  it("prunes memory of closed tabs and keeps the object when nothing changed", () => {
    const tabs = openTab(EMPTY_TABS, A);
    const m = { "SPY|2026-12-18": { parametric: 1 }, "GONE|2026-01-01": { parametric: 2 } };
    expect(pruneViewMemory(m, tabs)).toEqual({ "SPY|2026-12-18": { parametric: 1 } });
    const kept = { "SPY|2026-12-18": { parametric: 1 } };
    expect(pruneViewMemory(kept, tabs)).toBe(kept);
  });

  it("a new tab inherits the active tab's memory; an existing tab keeps its own", () => {
    const tabsA = openTab(EMPTY_TABS, A);
    const memA = setViewMemory({}, "SPY|2026-12-18", "parametric", { view: "density" });
    const r1 = openTabWithMemory(tabsA, memA, B);
    expect(r1.tabs.activeKey).toBe("NVDA|2027-03-19");
    expect(r1.memory["NVDA|2027-03-19"]).toEqual({ parametric: { view: "density" } });
    const memB = setViewMemory(r1.memory, "NVDA|2027-03-19", "parametric", { view: "table" });
    const r2 = openTabWithMemory(r1.tabs, memB, A);
    expect(r2.memory["SPY|2026-12-18"]).toEqual({ parametric: { view: "density" } });
    expect(r2.memory["NVDA|2027-03-19"]).toEqual({ parametric: { view: "table" } });
  });

  it("a replaced preview tab loses its memory (the new one inherits it first)", () => {
    const tabs = openTab(EMPTY_TABS, A, { preview: true });
    const mem = setViewMemory({}, "SPY|2026-12-18", "parametric", { view: "term" });
    const r = openTabWithMemory(tabs, mem, B, { preview: true });
    expect(r.tabs.tabs.map((t) => t.key)).toEqual(["NVDA|2027-03-19"]);
    expect(Object.keys(r.memory)).toEqual(["NVDA|2027-03-19"]);
    expect(r.memory["NVDA|2027-03-19"]).toEqual({ parametric: { view: "term" } });
  });

  it("restores only object-of-object blobs", () => {
    expect(restoreViewMemory({ a: { parametric: { view: "x" } }, b: 3, c: [1] })).toEqual({
      a: { parametric: { view: "x" } },
    });
    expect(restoreViewMemory("nope")).toEqual({});
  });
});

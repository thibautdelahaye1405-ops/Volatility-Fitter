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
  parseTabKey,
  pinTab,
  pruneTabs,
  restoreTabs,
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

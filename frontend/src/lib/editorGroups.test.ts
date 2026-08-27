// Editor-group algebra (UI SHELL v2 wave 3, C3): split / focus / move /
// close-unsplits / prune / restore (legacy blob migration).
import { describe, expect, it } from "vitest";
import {
  EMPTY_GROUPS, allTabs, closeIn, focusGroup, groupOf, moveToGroup, openIn, otherGroup, pruneGroups,
  restoreGroups, setGroupActivity, split, unsplit, updateFocused,
} from "./editorGroups";
import { activateTab } from "./workbenchTabs";

const A = { ticker: "SPY", expiry: "2026-12-18" };
const B = { ticker: "NVDA", expiry: "2027-03-19" };
const C = { ticker: "AAPL", expiry: "2026-12-18" };

describe("split / unsplit", () => {
  it("split duplicates the active tab into a focused right group; a second split is a no-op", () => {
    const s0 = openIn(EMPTY_GROUPS, 0, A);
    const s1 = split(s0);
    expect(s1.groups).toHaveLength(2);
    expect(s1.focused).toBe(1);
    expect(s1.groups[1].tabs.tabs.map((t) => t.key)).toEqual(["SPY|2026-12-18"]);
    expect(s1.groups[1].tabs.tabs[0].preview).toBe(false);
    expect(split(s1)).toBe(s1);
    expect(otherGroup(s1, 1)).toBe(0);
    expect(otherGroup(s0, 0)).toBe(-1);
  });

  it("split with nothing open makes an empty focused group", () => {
    const s = split(EMPTY_GROUPS);
    expect(s.groups[1].tabs.tabs).toEqual([]);
    expect(s.focused).toBe(1);
  });

  it("unsplit folds the right tabs into the left (left active tab wins)", () => {
    let s = openIn(EMPTY_GROUPS, 0, A);
    s = split(s);
    s = openIn(s, 1, B);
    s = openIn(s, 1, C, { preview: true });
    const u = unsplit(s);
    expect(u.groups).toHaveLength(1);
    expect(u.focused).toBe(0);
    expect(u.groups[0].tabs.tabs.map((t) => t.key)).toEqual(["SPY|2026-12-18", "NVDA|2027-03-19", "AAPL|2026-12-18"]);
    expect(u.groups[0].tabs.activeKey).toBe("SPY|2026-12-18");
    expect(u.groups[0].tabs.tabs[2].preview).toBe(true);
  });
});

describe("open / close / move", () => {
  it("closing the last tab of a side group unsplits; closing elsewhere keeps the split", () => {
    let s = split(openIn(EMPTY_GROUPS, 0, A));
    s = openIn(s, 1, B);
    expect(groupOf(s, "NVDA|2027-03-19")).toBe(1);
    s = closeIn(s, "SPY|2026-12-18"); // the duplicate in group 1 goes first (left-first lookup finds group 0!)
    // groupOf finds group 0 first: SPY closed on the left; the left group is empty → unsplit.
    expect(s.groups).toHaveLength(1);
    expect(s.groups[0].tabs.tabs.map((t) => t.key).sort()).toEqual(["NVDA|2027-03-19", "SPY|2026-12-18"]);
  });

  it("moveToGroup pins the tab in the target, focuses it, and unsplits an emptied source", () => {
    let s = split(openIn(EMPTY_GROUPS, 0, A));
    s = openIn(s, 0, B, { preview: true });
    s = focusGroup(s, 0);
    s = moveToGroup(s, "NVDA|2027-03-19", 1);
    expect(s.focused).toBe(1);
    expect(s.groups[1].tabs.tabs.map((t) => t.key)).toEqual(["SPY|2026-12-18", "NVDA|2027-03-19"]);
    expect(s.groups[1].tabs.tabs[1].preview).toBe(false);
    expect(s.groups[0].tabs.tabs.map((t) => t.key)).toEqual(["SPY|2026-12-18"]);
    s = moveToGroup(s, "SPY|2026-12-18", 1); // empties group 0 → unsplit
    expect(s.groups).toHaveLength(1);
    expect(s.focused).toBe(0);
  });

  it("updateFocused / activateTab act on the focused group only", () => {
    let s = split(openIn(EMPTY_GROUPS, 0, A));
    s = openIn(s, 1, B);
    s = updateFocused(s, (t) => activateTab(t, "SPY|2026-12-18"));
    expect(s.groups[1].tabs.activeKey).toBe("SPY|2026-12-18");
    expect(s.groups[0].tabs.activeKey).toBe("SPY|2026-12-18");
    expect(allTabs(s).map((t) => t.key)).toEqual(["SPY|2026-12-18", "NVDA|2027-03-19"]);
  });

  it("group activity overrides are per group", () => {
    let s = split(openIn(EMPTY_GROUPS, 0, A));
    s = setGroupActivity(s, 1, "localvol");
    expect(s.groups[1].activity).toBe("localvol");
    expect(s.groups[0].activity).toBeNull();
    expect(setGroupActivity(s, 1, "localvol")).toBe(s);
  });
});

describe("prune / restore", () => {
  it("prunes every group and unsplits an emptied side", () => {
    let s = split(openIn(EMPTY_GROUPS, 0, A));
    s = openIn(s, 1, B);
    const p = pruneGroups(s, (t) => t !== "NVDA");
    expect(p.groups).toHaveLength(2); // group 1 still holds the SPY duplicate
    const q = pruneGroups(s, (t) => t === "NVDA");
    expect(q.groups).toHaveLength(1);
    expect(q.groups[0].tabs.tabs.map((t) => t.key)).toEqual(["NVDA|2027-03-19"]);
    expect(pruneGroups(s, () => true)).toBe(s);
  });

  it("restores a groups blob, migrates a legacy tabs blob, drops junk", () => {
    const legacy = restoreGroups({ tabs: { tabs: [{ ticker: "SPY", expiry: "2026-12-18", preview: false }], activeKey: "SPY|2026-12-18" } });
    expect(legacy.groups).toHaveLength(1);
    expect(legacy.groups[0].tabs.activeKey).toBe("SPY|2026-12-18");
    const two = restoreGroups({
      groups: [
        { tabs: { tabs: [{ ticker: "SPY", expiry: "2026-12-18" }], activeKey: "SPY|2026-12-18" }, activity: "parametric" },
        { tabs: { tabs: [{ ticker: "NVDA", expiry: "2027-03-19" }], activeKey: null }, activity: "bogus" },
      ],
      focused: 1,
    }, (a) => a === "parametric" || a === "localvol");
    expect(two.groups).toHaveLength(2);
    expect(two.focused).toBe(1);
    expect(two.groups[0].activity).toBe("parametric");
    expect(two.groups[1].activity).toBeNull();
    // An empty right group in the blob unsplits on restore; junk → empty.
    expect(restoreGroups({ groups: [{ tabs: { tabs: [{ ticker: "SPY", expiry: "x" }] } }, { tabs: {} }], focused: 1 }).groups).toHaveLength(1);
    expect(restoreGroups("nope")).toEqual(EMPTY_GROUPS);
  });
});

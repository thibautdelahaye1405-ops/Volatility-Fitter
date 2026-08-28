// Editor-group algebra (UI SHELL v2 wave 3, C3): split / focus / move /
// close-unsplits / prune / restore (legacy blob migration).
import { describe, expect, it } from "vitest";
import {
  EMPTY_GROUPS, MAX_GROUPS, allTabs, closeIn, focusGroup, groupOf, moveToGroup, nextGroup, openIn, otherGroup,
  pruneGroups, restoreGroups, setGroupActivity, split, unsplit, updateFocused,
} from "./editorGroups";
import type { GroupsState } from "./editorGroups";
import { EMPTY_TABS, activateTab, openTab } from "./workbenchTabs";

const A = { ticker: "SPY", expiry: "2026-12-18" };
const B = { ticker: "NVDA", expiry: "2027-03-19" };
const C = { ticker: "AAPL", expiry: "2026-12-18" };

describe("split / unsplit", () => {
  it("split duplicates the active tab into a focused right group; a split at the cap is a no-op", () => {
    const s0 = openIn(EMPTY_GROUPS, 0, A);
    const s1 = split(s0);
    expect(s1.groups).toHaveLength(2);
    expect(s1.focused).toBe(1);
    expect(s1.groups[1].tabs.tabs.map((t) => t.key)).toEqual(["SPY|2026-12-18"]);
    expect(s1.groups[1].tabs.tabs[0].preview).toBe(false);
    const s2 = split(s1);
    expect(s2.groups).toHaveLength(MAX_GROUPS);
    expect(split(s2)).toBe(s2);
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

// Third group / vertical split (the workbench follow-on): N ≤ 3 along ONE axis.
const g = (...nodes: { ticker: string; expiry: string }[]) =>
  ({ tabs: nodes.reduce((t, n) => openTab(t, n), EMPTY_TABS), activity: null });
const three: GroupsState = { groups: [g(A), g(B), g(C)], focused: 1, direction: "row" };
const keys = (s: GroupsState) => s.groups.map((x) => x.tabs.tabs.map((t) => t.key));

describe("three groups / direction", () => {
  it("a second split inserts AFTER the focused group and caps at MAX_GROUPS", () => {
    expect(MAX_GROUPS).toBe(3);
    expect(EMPTY_GROUPS.direction).toBe("row");
    let s = openIn(split(openIn(EMPTY_GROUPS, 0, A)), 1, B); // [A] [A, B*]
    s = focusGroup(s, 0);
    s = split(s); // the copy of A lands BETWEEN the two
    expect(s.groups).toHaveLength(3);
    expect(s.focused).toBe(1);
    expect(keys(s)).toEqual([["SPY|2026-12-18"], ["SPY|2026-12-18"], ["SPY|2026-12-18", "NVDA|2027-03-19"]]);
    expect(s.direction).toBe("row");
    expect(split(s)).toBe(s);
  });

  it("the axis is chosen only from a single group", () => {
    const one = openIn(EMPTY_GROUPS, 0, A);
    const col = split(one, { direction: "column" });
    expect(col.direction).toBe("column");
    expect(split(col).direction).toBe("column"); // a third group keeps the axis
    expect(split(split(one), { direction: "column" }).direction).toBe("row"); // a 2-group row never becomes a column
    expect(split(one).direction).toBe("row");
  });

  it("unsplit folds three groups into the first (its active tab wins) and resets the axis", () => {
    const u = unsplit({ ...three, direction: "column", focused: 2 });
    expect(u.groups).toHaveLength(1);
    expect(u.focused).toBe(0);
    expect(u.direction).toBe("row");
    expect(keys(u)).toEqual([["SPY|2026-12-18", "NVDA|2027-03-19", "AAPL|2026-12-18"]]);
    expect(u.groups[0].tabs.activeKey).toBe("SPY|2026-12-18");
  });

  it("closing the last tab of the middle group focuses the neighbour that slid into its place", () => {
    const c = closeIn(three, "NVDA|2027-03-19");
    expect(keys(c)).toEqual([["SPY|2026-12-18"], ["AAPL|2026-12-18"]]);
    expect(c.focused).toBe(1);
    expect(c.direction).toBe("row");
    expect(closeIn({ ...three, focused: 2 }, "NVDA|2027-03-19").focused).toBe(1);
    expect(closeIn({ ...three, focused: 0 }, "NVDA|2027-03-19").focused).toBe(0);
    // Dropping the LAST group while it is focused: the new last group takes the focus.
    expect(closeIn({ ...three, focused: 2 }, "AAPL|2026-12-18").focused).toBe(1);
  });

  it("nextGroup cycles along the axis; otherGroup is its two-group face", () => {
    expect(nextGroup(three, 2)).toBe(0);
    expect(nextGroup(three, 0, -1)).toBe(2);
    expect(nextGroup(three, 1)).toBe(2);
    expect(nextGroup(openIn(EMPTY_GROUPS, 0, A), 0)).toBe(-1);
    const two = split(openIn(EMPTY_GROUPS, 0, A));
    expect(nextGroup(two, 1)).toBe(otherGroup(two, 1));
  });

  it("restores a legacy 2-group blob verbatim (row), reads direction leniently, caps at 3, prunes any empty index", () => {
    const legacy = restoreGroups({ groups: three.groups.slice(0, 2), focused: 1 });
    expect(keys(legacy)).toEqual([["SPY|2026-12-18"], ["NVDA|2027-03-19"]]);
    expect(legacy.focused).toBe(1);
    expect(legacy.direction).toBe("row");
    const col = restoreGroups({ groups: three.groups, focused: 2, direction: "column" });
    expect(col.groups).toHaveLength(3);
    expect(col.direction).toBe("column");
    expect(col.focused).toBe(2);
    expect(restoreGroups({ groups: [...three.groups, g(A)], focused: 3, direction: "bogus" })).toMatchObject({ focused: 2, direction: "row" });
    // An empty MIDDLE group is dropped too; a single survivor is always a row.
    const mid = restoreGroups({ groups: [g(A), { tabs: {} }, g(C)], focused: 2, direction: "column" });
    expect(keys(mid)).toEqual([["SPY|2026-12-18"], ["AAPL|2026-12-18"]]);
    expect(mid.focused).toBe(1);
    expect(mid.direction).toBe("column");
    expect(restoreGroups({ groups: [g(A)], focused: 0, direction: "column" }).direction).toBe("row");
  });
});

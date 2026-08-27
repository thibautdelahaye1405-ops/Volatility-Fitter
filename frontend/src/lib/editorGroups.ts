// Editor GROUPS of the main pane (UI SHELL v2 wave 3, C3) — pure algebra.
//
// The main pane holds ONE or TWO editor groups side by side (VS Code's split
// editor). Each group has its own tab strip (a TabsState from
// lib/workbenchTabs) and an optional LENS override (`activity`; null =
// follows the global lens — phase 3b: Parametric left, Local Vol right). The
// smile session follows the FOCUSED group's active tab. Closing the last tab
// of a group unsplits; `split` duplicates the focused group's active tab into
// a new right-hand group. Locked in editorGroups.test.ts.
import {
  EMPTY_TABS,
  activeTab,
  closeTab,
  openTab,
  pruneTabs,
  restoreTabs,
  tabKey,
} from "./workbenchTabs";
import type { NodeRef, TabsState, WorkbenchTab } from "./workbenchTabs";

export interface EditorGroup {
  tabs: TabsState;
  /** Lens override for this group (null = the global lens). */
  activity: string | null;
}

export interface GroupsState {
  /** One or two groups, left to right. */
  groups: EditorGroup[];
  /** Index of the focused group (drives the smile session). */
  focused: number;
}

export const MAX_GROUPS = 2;

const emptyGroup = (): EditorGroup => ({ tabs: EMPTY_TABS, activity: null });

export const EMPTY_GROUPS: GroupsState = { groups: [emptyGroup()], focused: 0 };

const clampFocus = (s: GroupsState): GroupsState =>
  s.focused >= 0 && s.focused < s.groups.length ? s : { ...s, focused: Math.max(0, s.groups.length - 1) };

function withGroup(s: GroupsState, i: number, tabs: TabsState): GroupsState {
  return { ...s, groups: s.groups.map((g, j) => (j === i ? { ...g, tabs } : g)) };
}

/** The focused group (always present). */
export function focusedGroup(s: GroupsState): EditorGroup {
  return s.groups[s.focused] ?? s.groups[0];
}

/** Index of the group holding a tab key, or -1. */
export function groupOf(s: GroupsState, key: string): number {
  return s.groups.findIndex((g) => g.tabs.tabs.some((t) => t.key === key));
}

/** Every open tab across the groups (deduped by key, left group first). */
export function allTabs(s: GroupsState): WorkbenchTab[] {
  const seen = new Set<string>();
  const out: WorkbenchTab[] = [];
  for (const g of s.groups) for (const t of g.tabs.tabs) if (!seen.has(t.key)) { seen.add(t.key); out.push(t); }
  return out;
}

export function focusGroup(s: GroupsState, i: number): GroupsState {
  return i >= 0 && i < s.groups.length && i !== s.focused ? { ...s, focused: i } : s;
}

/** Split: a second group to the right holding a copy of the focused group's
 *  active tab (pinned), focused. No-op when already split. */
export function split(s: GroupsState): GroupsState {
  if (s.groups.length >= MAX_GROUPS) return s;
  const cur = activeTab(focusedGroup(s).tabs);
  const tabs = cur ? openTab(EMPTY_TABS, { ticker: cur.ticker, expiry: cur.expiry }) : EMPTY_TABS;
  return { groups: [...s.groups, { tabs, activity: null }], focused: s.groups.length };
}

/** Unsplit: fold the right group's tabs (those not already open on the left)
 *  into the left group; the left group's active tab wins. */
export function unsplit(s: GroupsState): GroupsState {
  if (s.groups.length < 2) return s;
  const [left, right] = s.groups;
  const extra = right.tabs.tabs.filter((t) => !left.tabs.tabs.some((x) => x.key === t.key));
  const tabs: TabsState = {
    tabs: [...left.tabs.tabs, ...extra.map((t) => ({ ...t }))],
    activeKey: left.tabs.activeKey ?? right.tabs.activeKey,
  };
  return { groups: [{ ...left, tabs }], focused: 0 };
}

/** Drop a group that became empty (only when split); focus moves to the survivor. */
export function unsplitIfEmpty(s: GroupsState, i: number): GroupsState {
  if (s.groups.length < 2 || !s.groups[i] || s.groups[i].tabs.tabs.length > 0) return s;
  const groups = s.groups.filter((_, j) => j !== i);
  return clampFocus({ groups: groups.map((g, j) => (j === 0 ? { ...g } : g)), focused: 0 });
}

/** Open a node in group `i` (focuses it). */
export function openIn(s: GroupsState, i: number, node: NodeRef, opts: { preview?: boolean } = {}): GroupsState {
  if (!s.groups[i]) return s;
  return { ...withGroup(s, i, openTab(s.groups[i].tabs, node, opts)), focused: i };
}

/** Index of the group "beside" `i` (the other one; -1 when not split). */
export function otherGroup(s: GroupsState, i: number): number {
  return s.groups.length < 2 ? -1 : i === 0 ? 1 : 0;
}

/** Close a tab wherever it is; an emptied side group unsplits. */
export function closeIn(s: GroupsState, key: string): GroupsState {
  const i = groupOf(s, key);
  if (i < 0) return s;
  return unsplitIfEmpty(withGroup(s, i, closeTab(s.groups[i].tabs, key)), i);
}

/** Move a tab to another group (pinned there, active); the source unsplits when emptied. */
export function moveToGroup(s: GroupsState, key: string, to: number): GroupsState {
  const from = groupOf(s, key);
  if (from < 0 || !s.groups[to] || from === to) return s;
  const tab = s.groups[from].tabs.tabs.find((t) => t.key === key)!;
  let next = withGroup(s, from, closeTab(s.groups[from].tabs, key));
  next = withGroup(next, to, openTab(next.groups[to].tabs, { ticker: tab.ticker, expiry: tab.expiry }));
  next = { ...next, focused: to };
  return unsplitIfEmpty(next, from);
}

export function setGroupActivity(s: GroupsState, i: number, activity: string | null): GroupsState {
  if (!s.groups[i] || s.groups[i].activity === activity) return s;
  return { ...s, groups: s.groups.map((g, j) => (j === i ? { ...g, activity } : g)) };
}

/** Apply a TabsState transform to the group holding `key` (activate / pin / …). */
export function updateGroupOf(s: GroupsState, key: string, fn: (t: TabsState) => TabsState): GroupsState {
  const i = groupOf(s, key);
  return i < 0 ? s : withGroup(s, i, fn(s.groups[i].tabs));
}

/** Apply a transform to the focused group's tabs. */
export function updateFocused(s: GroupsState, fn: (t: TabsState) => TabsState): GroupsState {
  return withGroup(s, s.focused, fn(focusedGroup(s).tabs));
}

/** Drop tabs whose node left the universe (every group); empty side unsplits. */
export function pruneGroups(s: GroupsState, has: (ticker: string, expiry: string) => boolean): GroupsState {
  let next: GroupsState = { ...s, groups: s.groups.map((g) => ({ ...g, tabs: pruneTabs(g.tabs, has) })) };
  for (let i = next.groups.length - 1; i >= 0; i--) next = unsplitIfEmpty(next, i);
  return next.groups.every((g, i) => g.tabs === s.groups[i]?.tabs) && next.groups.length === s.groups.length ? s : next;
}

/** Validate a persisted blob; a legacy `{tabs}` blob becomes group 0. */
export function restoreGroups(raw: unknown, isActivity: (a: unknown) => boolean = () => true): GroupsState {
  if (typeof raw !== "object" || raw === null) return EMPTY_GROUPS;
  const r = raw as { groups?: unknown; focused?: unknown; tabs?: unknown };
  if (!Array.isArray(r.groups)) {
    return r.tabs !== undefined ? { groups: [{ tabs: restoreTabs(r.tabs), activity: null }], focused: 0 } : EMPTY_GROUPS;
  }
  const groups: EditorGroup[] = r.groups.slice(0, MAX_GROUPS).map((g) => {
    const gg = (typeof g === "object" && g !== null ? g : {}) as { tabs?: unknown; activity?: unknown };
    return { tabs: restoreTabs(gg.tabs), activity: typeof gg.activity === "string" && isActivity(gg.activity) ? gg.activity : null };
  });
  if (groups.length === 0) return EMPTY_GROUPS;
  const focused = typeof r.focused === "number" ? r.focused : 0;
  return clampFocus(unsplitIfEmpty({ groups, focused }, 1));
}

export { tabKey };

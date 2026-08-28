// Editor GROUPS of the main pane (UI SHELL v2 wave 3, C3 + the third-group /
// vertical-split follow-on) — pure algebra.
//
// The main pane holds ONE to MAX_GROUPS (3) editor groups along ONE axis
// (VS Code's split editor): `direction` "row" lays them out left to right,
// "column" top to bottom. Each group has its own tab strip (a TabsState from
// lib/workbenchTabs) and an optional LENS override (`activity`; null =
// follows the global lens). The smile session follows the FOCUSED group's
// active tab. `split` inserts a new group right AFTER the focused one holding
// a copy of its active tab; the axis can only be chosen while there is a
// single group — a two-group row never turns into a column (the groups are a
// flat list, not a tree, so mixing axes has no meaning here). Closing the last
// tab of a group drops that group; `unsplit` folds EVERY group into the
// first. Invariant: a single group always has direction "row" and no lens
// override (it renders the global lens). Locked in editorGroups.test.ts.
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

/** Layout axis of the groups: side by side ("row") or stacked ("column"). */
export type SplitDirection = "row" | "column";

export interface GroupsState {
  /** One to MAX_GROUPS groups in layout order (left→right or top→bottom). */
  groups: EditorGroup[];
  /** Index of the focused group (drives the smile session). */
  focused: number;
  /** Layout axis ("row" whenever there is a single group). */
  direction: SplitDirection;
}

export const MAX_GROUPS = 3;

const emptyGroup = (): EditorGroup => ({ tabs: EMPTY_TABS, activity: null });

export const EMPTY_GROUPS: GroupsState = { groups: [emptyGroup()], focused: 0, direction: "row" };

const clampFocus = (s: GroupsState): GroupsState =>
  s.focused >= 0 && s.focused < s.groups.length ? s : { ...s, focused: Math.max(0, Math.min(s.focused, s.groups.length - 1)) };

/** The single-group invariant: axis "row", no lens override (module comment). */
const normalizeSingle = (s: GroupsState): GroupsState =>
  s.groups.length !== 1 || (s.direction === "row" && s.groups[0].activity === null)
    ? s
    : { ...s, direction: "row", groups: [{ ...s.groups[0], activity: null }] };

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

/** Split: a new group right AFTER the focused one (or at `opts.at`) holding
 *  a copy of the focused group's active tab (pinned), focused. `direction`
 *  picks the axis and is honoured only from a single group (module comment);
 *  otherwise the existing axis stays. No-op at MAX_GROUPS. */
export function split(s: GroupsState, opts: { direction?: SplitDirection; at?: number } = {}): GroupsState {
  if (s.groups.length >= MAX_GROUPS) return s;
  const cur = activeTab(focusedGroup(s).tabs);
  const tabs = cur ? openTab(EMPTY_TABS, { ticker: cur.ticker, expiry: cur.expiry }) : EMPTY_TABS;
  const at = Math.max(0, Math.min(s.groups.length, opts.at ?? s.focused + 1));
  const direction = s.groups.length === 1 ? (opts.direction ?? "row") : s.direction;
  return { groups: [...s.groups.slice(0, at), { tabs, activity: null }, ...s.groups.slice(at)], focused: at, direction };
}

/** Unsplit: fold every group's tabs (those not already open in an earlier
 *  group) into the first group, in layout order; the first group's active
 *  tab wins, then the first later group that has one. Axis back to "row". */
export function unsplit(s: GroupsState): GroupsState {
  if (s.groups.length < 2) return s;
  const [first, ...rest] = s.groups;
  const tabs = [...first.tabs.tabs];
  let activeKey = first.tabs.activeKey;
  for (const g of rest) {
    for (const t of g.tabs.tabs) if (!tabs.some((x) => x.key === t.key)) tabs.push({ ...t });
    if (activeKey === null) activeKey = g.tabs.activeKey;
  }
  const merged: TabsState = { tabs, activeKey };
  return { groups: [{ tabs: merged, activity: null }], focused: 0, direction: "row" };
}

/** Drop a group that became empty (only when split). The focus follows the
 *  layout: a focused group past the dropped one slides back by one; when the
 *  dropped group WAS the focused one, the neighbour that took its place gets
 *  the focus (the last group when it was last). Two groups → always group 0. */
export function unsplitIfEmpty(s: GroupsState, i: number): GroupsState {
  if (s.groups.length < 2 || !s.groups[i] || s.groups[i].tabs.tabs.length > 0) return s;
  const groups = s.groups.filter((_, j) => j !== i);
  const focused = s.focused > i ? s.focused - 1 : s.focused;
  return normalizeSingle(clampFocus({ groups, focused, direction: s.direction }));
}

/** Open a node in group `i` (focuses it). */
export function openIn(s: GroupsState, i: number, node: NodeRef, opts: { preview?: boolean } = {}): GroupsState {
  if (!s.groups[i]) return s;
  return { ...withGroup(s, i, openTab(s.groups[i].tabs, node, opts)), focused: i };
}

/** Cyclic neighbour of group `i`, `delta` steps along the axis (-1 when not split). */
export function nextGroup(s: GroupsState, i: number, delta = 1): number {
  const n = s.groups.length;
  return n < 2 ? -1 : (((i + delta) % n) + n) % n;
}

/** Index of the group "beside" `i` — the next one along the axis, i.e. the
 *  other one while two groups are open (-1 when not split). */
export function otherGroup(s: GroupsState, i: number): number {
  return nextGroup(s, i, 1);
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

/** Validate a persisted blob: a legacy `{tabs}` blob becomes group 0; a blob
 *  without `direction` (pre-third-group) restores as a row; the count is
 *  capped at MAX_GROUPS and an empty group is dropped at ANY index. */
export function restoreGroups(raw: unknown, isActivity: (a: unknown) => boolean = () => true): GroupsState {
  if (typeof raw !== "object" || raw === null) return EMPTY_GROUPS;
  const r = raw as { groups?: unknown; focused?: unknown; direction?: unknown; tabs?: unknown };
  if (!Array.isArray(r.groups)) {
    return r.tabs !== undefined ? { ...EMPTY_GROUPS, groups: [{ tabs: restoreTabs(r.tabs), activity: null }] } : EMPTY_GROUPS;
  }
  const groups: EditorGroup[] = r.groups.slice(0, MAX_GROUPS).map((g) => {
    const gg = (typeof g === "object" && g !== null ? g : {}) as { tabs?: unknown; activity?: unknown };
    return { tabs: restoreTabs(gg.tabs), activity: typeof gg.activity === "string" && isActivity(gg.activity) ? gg.activity : null };
  });
  if (groups.length === 0) return EMPTY_GROUPS;
  const focused = typeof r.focused === "number" ? r.focused : 0;
  let next: GroupsState = { groups, focused, direction: r.direction === "column" ? "column" : "row" };
  for (let i = next.groups.length - 1; i >= 0; i--) next = unsplitIfEmpty(next, i);
  return normalizeSingle(clampFocus(next));
}

export { tabKey };

// Workbench shell state (UI SHELL v2, S1): the activity lens, the editor
// GROUPS of node tabs (wave 3, C3: one or two, side by side), the layout
// toggles, the open dialog, the per-tab view memory and the file blob.
//
// The FOCUSED group's active tab IS the shared smile-session selection:
// activating it pushes (ticker, expiry) into the root session (so the focused
// group's lens renders that node), and any selection made from inside a
// workspace (forward-ladder row, LV table row, graph canvas, quality row,
// drill-in) flows back through openNode() — or, when a workspace still writes
// the session directly, is picked up by the session→tab reconciliation and
// opens a PREVIEW tab in the focused group. A push guard (pushRef) keeps the
// two directions from fighting on the commit where the universe first loads
// (restored tabs win over the session's mid-ladder default). The OTHER group
// renders its own node through a node scope (state/nodeScope).
//
// Persistence + the pure algebra live in state/workbenchPersist,
// lib/editorGroups and lib/workbenchTabs so this provider stays a thin shell.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRootSmileSession } from "./smileSession";
import {
  activateTab as activateTabPure, closeAllTabs, closeOtherTabs, cycleTab as cycleTabPure,
  moveTab as moveTabPure, openTabWithMemory, pinTab as pinTabPure, pruneViewMemory,
  setViewMemory as setViewMemoryPure, tabKey,
} from "../lib/workbenchTabs";
import type { NodeRef, TabsState, ViewMemory, WorkbenchTab } from "../lib/workbenchTabs";
import {
  EMPTY_GROUPS, allTabs, closeIn, focusGroup as focusGroupPure, focusedGroup, groupOf, moveToGroup,
  openIn, otherGroup, pruneGroups, setGroupActivity as setGroupActivityPure, split as splitPure,
  unsplit as unsplitPure, updateFocused, updateGroupOf,
} from "../lib/editorGroups";
import type { EditorGroup, GroupsState } from "../lib/editorGroups";
import {
  DEFAULT_LAYOUT, UNIVERSE_ACTIVITIES, defaultNodesWidth, isActivity, loadPersisted, persist,
  restoreLayout, restorePersisted,
} from "./workbenchPersist";
import type { Activity, LayoutState } from "./workbenchPersist";

export { ACTIVITIES, NODES_WIDTH, UNIVERSE_ACTIVITIES, defaultNodesWidth } from "./workbenchPersist";
export type { Activity, LayoutState } from "./workbenchPersist";

/** Modal dialogs owned by the shell. */
export type DialogId = "universe" | "options" | "shortcuts" | "about" | "quickopen" | "commands";

/** Workbench part of the workspace-file shell blob. */
export interface ShellShellBlob {
  activity: Activity;
  groups: GroupsState;
  layout: LayoutState;
  viewMemory: ViewMemory;
}

export interface WorkbenchValue {
  activity: Activity;
  setActivity: (a: Activity) => void;
  /** The FOCUSED group's tabs / active tab (the session selection). */
  tabs: WorkbenchTab[];
  activeTab: WorkbenchTab | null;
  /** Editor groups (wave 3, C3). */
  groups: EditorGroup[];
  focusedGroup: number;
  focusGroup: (i: number) => void;
  /** The lens a group shows (its override, else the global lens). */
  activityOf: (i: number) => Activity;
  split: () => void;
  unsplit: () => void;
  toggleSplit: () => void;
  /** Open a node in a given group (pinned unless preview). */
  openNodeIn: (group: number, node: NodeRef, opts?: { preview?: boolean }) => void;
  /** Open in the group beside the focused one (splitting first if needed). */
  openBeside: (node: NodeRef) => void;
  moveTabToGroup: (key: string, to: number) => void;
  /** Tab being dragged from a strip (the split drop zone reads it). */
  draggingTab: string | null;
  setDraggingTab: (key: string | null) => void;
  /** Open (or focus) a node's tab in the focused group; optionally switch the lens. */
  openNode: (node: NodeRef, opts?: { preview?: boolean; activity?: Activity }) => void;
  pinTab: (key: string) => void;
  closeTab: (key: string) => void;
  closeOthers: (key: string) => void;
  closeAll: () => void;
  activateTab: (key: string) => void;
  cycleTab: (delta: number) => void;
  moveTab: (key: string, toIndex: number) => void;
  layout: LayoutState;
  setLayout: (patch: Partial<LayoutState>) => void;
  resetLayout: () => void;
  dialog: DialogId | null;
  openDialog: (id: DialogId) => void;
  closeDialog: () => void;
  /** Show the Nodes pane and hand it the keyboard focus (Ctrl+B; wave 3, C1). */
  focusNodesPane: () => void;
  nodesFocusSeq: number;
  /** Per-tab view memory (wave 3, C2) — read + written via useLensViewMemory. */
  viewMemory: ViewMemory;
  setViewMemory: (key: string, lens: string, value: unknown) => void;
  /** The shell's share of a workspace FILE (wave 3, A1), in and out. */
  exportShell: () => ShellShellBlob;
  importShell: (blob: Partial<ShellShellBlob> | null | undefined) => void;
}

const Ctx = createContext<WorkbenchValue | null>(null);

/** Mount inside SmileSessionProvider (it reconciles the session selection). */
export function WorkbenchProvider({ children }: { children: ReactNode }) {
  const { universe, ticker, expiry, setTicker, setExpiry } = useRootSmileSession();
  const [initial] = useState(loadPersisted);
  const [activity, setActivityState] = useState<Activity>(initial.activity);
  const [groups, setGroups] = useState<GroupsState>(initial.groups);
  const [layout, setLayoutState] = useState<LayoutState>(initial.layout);
  const [viewMemory, setViewMemoryState] = useState<ViewMemory>(initial.viewMemory);
  const [dialog, setDialog] = useState<DialogId | null>(null);
  const [draggingTab, setDraggingTab] = useState<string | null>(null);
  const [nodesFocusSeq, setNodesFocusSeq] = useState(0);
  const groupsRef = useRef(groups);
  groupsRef.current = groups;
  const memoryRef = useRef(viewMemory);
  memoryRef.current = viewMemory;

  useEffect(() => persist({ activity, groups, layout, viewMemory }), [activity, groups, layout, viewMemory]);
  // Memory follows the open tabs (any group); tabs follow the universe.
  useEffect(() => setViewMemoryState((m) => pruneViewMemory(m, { tabs: allTabs(groups), activeKey: null })), [groups]);
  useEffect(() => {
    if (universe === null) return;
    setGroups((g) => pruneGroups(g, (t, e) => (universe.expiries[t] ?? []).some((r) => r.expiry === e)));
  }, [universe]);

  const focusedTabs: TabsState = focusedGroup(groups).tabs;
  const active = focusedTabs.tabs.find((t) => t.key === focusedTabs.activeKey) ?? null;
  const activeKey = focusedTabs.activeKey;
  const universeLoaded = universe !== null && ticker !== "";

  // Open in a group; a brand-new tab inherits the focused tab's view memory.
  const openWithMemory = useCallback((group: number, node: NodeRef, preview: boolean) => {
    setGroups((g) => {
      const target = g.groups[group] ? group : g.focused;
      const r = openTabWithMemory(g.groups[target].tabs, memoryRef.current, node, { preview });
      if (r.memory !== memoryRef.current) { memoryRef.current = r.memory; setViewMemoryState(r.memory); }
      const opened = openIn(g, target, node, { preview });
      return { ...opened, groups: opened.groups.map((x, i) => (i === target ? { ...x, tabs: r.tabs } : x)) };
    });
  }, []);

  // Tab → session (focused group) / session → tab, guarded (module comment).
  const pushRef = useRef<string | null>(null);
  useEffect(() => {
    if (!universeLoaded || active === null) return;
    if (ticker === active.ticker && expiry === active.expiry) return;
    pushRef.current = active.key;
    setTicker(active.ticker);
    setExpiry(active.expiry);
  }, [universeLoaded, activeKey, groups.focused]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!universeLoaded) return;
    const key = tabKey(ticker, expiry);
    if (active !== null && active.key === key) { pushRef.current = null; return; }
    if (pushRef.current !== null && pushRef.current !== key) return; // push in flight
    pushRef.current = null;
    openWithMemory(groupsRef.current.focused, { ticker, expiry }, true);
  }, [universeLoaded, ticker, expiry]); // eslint-disable-line react-hooks/exhaustive-deps

  // A universe lens is single-group (global); a focused side group keeps its
  // own per-node lens override (phase 3b: Parametric left, Local Vol right).
  const setActivity = useCallback((a: Activity) => {
    const g = groupsRef.current;
    if (g.focused > 0 && !UNIVERSE_ACTIVITIES.has(a)) setGroups((s) => setGroupActivityPure(s, s.focused, a));
    else setActivityState(a);
  }, []);
  const activityOf = useCallback((i: number): Activity => {
    const own = groups.groups[i]?.activity;
    return i > 0 && isActivity(own) && !UNIVERSE_ACTIVITIES.has(own) ? own : activity;
  }, [groups, activity]);

  const openNode = useCallback((node: NodeRef, opts: { preview?: boolean; activity?: Activity } = {}) => {
    openWithMemory(groupsRef.current.focused, node, opts.preview ?? false);
    if (opts.activity) setActivity(opts.activity);
  }, [openWithMemory, setActivity]);
  const openNodeIn = useCallback((group: number, node: NodeRef, opts: { preview?: boolean } = {}) =>
    openWithMemory(group, node, opts.preview ?? false), [openWithMemory]);
  const split = useCallback(() => setGroups((g) => splitPure(g)), []);
  const unsplit = useCallback(() => setGroups((g) => unsplitPure(g)), []);
  const toggleSplit = useCallback(() => setGroups((g) => (g.groups.length > 1 ? unsplitPure(g) : splitPure(g))), []);
  const openBeside = useCallback((node: NodeRef) => {
    const g = groupsRef.current;
    if (g.groups.length < 2) { setGroups((s) => openIn(splitPure(s), 1, node)); return; }
    openWithMemory(otherGroup(g, g.focused), node, false);
  }, [openWithMemory]);
  const focusGroup = useCallback((i: number) => setGroups((g) => focusGroupPure(g, i)), []);
  const moveTabToGroup = useCallback((key: string, to: number) => setGroups((g) => moveToGroup(g, key, to)), []);
  const pinTab = useCallback((key: string) => setGroups((g) => updateGroupOf(g, key, (t) => pinTabPure(t, key))), []);
  const closeTab = useCallback((key: string) => setGroups((g) => closeIn(g, key)), []);
  const closeOthers = useCallback((key: string) => setGroups((g) => updateGroupOf(g, key, (t) => closeOtherTabs(t, key))), []);
  const closeAll = useCallback(() => setGroups(() => ({ ...EMPTY_GROUPS, groups: [{ tabs: closeAllTabs(), activity: null }] })), []);
  const activateTab = useCallback((key: string) => setGroups((g) => {
    const i = groupOf(g, key);
    return i < 0 ? g : focusGroupPure(updateGroupOf(g, key, (t) => activateTabPure(t, key)), i);
  }), []);
  const cycleTab = useCallback((delta: number) => setGroups((g) => updateFocused(g, (t) => cycleTabPure(t, delta))), []);
  const moveTab = useCallback((key: string, toIndex: number) => setGroups((g) => updateGroupOf(g, key, (t) => moveTabPure(t, key, toIndex))), []);
  const setViewMemory = useCallback((key: string, lens: string, value: unknown) =>
    setViewMemoryState((m) => setViewMemoryPure(m, key, lens, value)), []);

  const setLayout = useCallback((patch: Partial<LayoutState>) => setLayoutState((l) => ({ ...l, ...patch })), []);
  const resetLayout = useCallback(() => setLayoutState({ ...DEFAULT_LAYOUT, nodesWidth: defaultNodesWidth() }), []);
  const openDialog = useCallback((id: DialogId) => setDialog(id), []);
  const closeDialog = useCallback(() => setDialog(null), []);
  const focusNodesPane = useCallback(() => {
    setLayoutState((l) => (l.nodesPane ? l : { ...l, nodesPane: true }));
    setNodesFocusSeq((n) => n + 1);
  }, []);

  // Workspace-file shell blob (A1): the persisted state, in and out (lenient).
  const exportShell = useCallback((): ShellShellBlob => ({ activity, groups, layout, viewMemory }), [activity, groups, layout, viewMemory]);
  const importShell = useCallback((blob: Partial<ShellShellBlob> | null | undefined) => {
    if (!blob) return;
    const next = restorePersisted(blob, { activity, groups: groupsRef.current, layout: DEFAULT_LAYOUT, viewMemory: memoryRef.current });
    if (blob.activity !== undefined) setActivityState(next.activity);
    if (blob.groups !== undefined || (blob as { tabs?: unknown }).tabs !== undefined) {
      pushRef.current = focusedGroup(next.groups).tabs.activeKey; // restored tabs beat the session
      setGroups(next.groups);
      setViewMemoryState(next.viewMemory);
    }
    if (blob.layout) setLayoutState((l) => restoreLayout(blob.layout, l));
  }, [activity]);

  const value = useMemo<WorkbenchValue>(() => ({
    activity, setActivity, tabs: focusedTabs.tabs, activeTab: active,
    groups: groups.groups, focusedGroup: groups.focused, focusGroup, activityOf, split, unsplit, toggleSplit,
    openNodeIn, openBeside, moveTabToGroup, draggingTab, setDraggingTab,
    openNode, pinTab, closeTab, closeOthers, closeAll, activateTab, cycleTab, moveTab,
    layout, setLayout, resetLayout, dialog, openDialog, closeDialog, focusNodesPane, nodesFocusSeq,
    viewMemory, setViewMemory, exportShell, importShell,
  }), [
    activity, setActivity, focusedTabs, active, groups, focusGroup, activityOf, split, unsplit, toggleSplit,
    openNodeIn, openBeside, moveTabToGroup, draggingTab, openNode, pinTab, closeTab, closeOthers, closeAll,
    activateTab, cycleTab, moveTab, layout, setLayout, resetLayout, dialog, openDialog, closeDialog,
    focusNodesPane, nodesFocusSeq, viewMemory, setViewMemory, exportShell, importShell,
  ]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Consume the workbench shell state; throws outside a WorkbenchProvider. */
export function useWorkbench(): WorkbenchValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useWorkbench must be used within WorkbenchProvider");
  return ctx;
}

/** Optional consumer for components that also render outside the shell. */
export function useOptionalWorkbench(): WorkbenchValue | null {
  return useContext(Ctx);
}

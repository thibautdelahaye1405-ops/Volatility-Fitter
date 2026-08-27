// Workbench shell state (UI SHELL v2, S1): the activity lens, the node tabs,
// the layout toggles and the open dialog — one context for the whole chrome.
//
// The active tab IS the shared smile-session selection: activating a tab
// pushes (ticker, expiry) into the session (so every lens renders that node),
// and any selection made from inside a workspace (forward-ladder row, LV
// table row, graph canvas, quality row, drill-in) flows back through
// openNode() — or, when a workspace still writes the session directly, is
// picked up by the session→tab reconciliation and opens a PREVIEW tab. A
// push guard (pushRef) keeps the two directions from fighting on the commit
// where the universe first loads (restored tabs win over the session's
// mid-ladder default).
//
// Persistence: activity + tabs + layout + per-tab view memory in localStorage
// ("volfit.workbench") so a reload restores the workbench exactly (tabs and
// their memory are pruned against the universe once it loads).
//
// View memory (wave 3, C2): each lens stores what it showed per tab
// (lib/workbenchTabs ViewMemory; read + written through useLensViewMemory);
// Layout ▸ "Remember view per tab" switches it (OFF = per-lens view state).
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useSmileSession } from "./smileSession";
import {
  EMPTY_TABS,
  EMPTY_VIEW_MEMORY,
  activateTab as activateTabPure,
  activeTab as activeTabOf,
  closeAllTabs,
  closeOtherTabs as closeOthersPure,
  closeTab as closeTabPure,
  cycleTab as cycleTabPure,
  moveTab as moveTabPure,
  openTabWithMemory,
  pinTab as pinTabPure,
  pruneTabs,
  pruneViewMemory,
  restoreTabs,
  restoreViewMemory,
  setViewMemory as setViewMemoryPure,
  tabKey,
} from "../lib/workbenchTabs";
import type { NodeRef, TabsState, ViewMemory, WorkbenchTab } from "../lib/workbenchTabs";

/** The five activity-bar lenses, in bar order (user spec 2026-08-26). */
export type Activity = "graph" | "forwards" | "parametric" | "localvol" | "quality";

export const ACTIVITIES: { id: Activity; label: string; hint: string }[] = [
  { id: "graph", label: "Graph", hint: "Smile universe — propagate observations through the graph" },
  { id: "forwards", label: "Forwards", hint: "Forwards, dividends & borrow per ticker" },
  { id: "parametric", label: "Parametric", hint: "Per-node parametric smile fit (LQD / SVI-JW / MCS)" },
  { id: "localvol", label: "Local Vol", hint: "Direct local-volatility surface per ticker" },
  { id: "quality", label: "Quality", hint: "Fit-quality dashboard & publish readiness" },
];

/** Lenses that render the whole universe (no tab needed; the tab is highlighted). */
export const UNIVERSE_ACTIVITIES: ReadonlySet<Activity> = new Set(["graph", "quality"]);

/** Modal dialogs owned by the shell. */
export type DialogId = "universe" | "options" | "shortcuts" | "about" | "quickopen" | "commands";

export interface LayoutState {
  /** Nodes pane visible (Ctrl+B). */
  nodesPane: boolean;
  /** Nodes pane width in px (resizer; default = 1/5 of the viewport). */
  nodesWidth: number;
  /** Bottom status bar visible. */
  statusBar: boolean;
  /** Diagnostics / config asides inside the lenses. */
  aside: boolean;
  /** Per-tab view memory (wave 3, C2); false = one view state per lens. */
  rememberView: boolean;
}

export const NODES_WIDTH = { min: 200, max: 640 } as const;

/** 1/5 of the viewport (the spec), clamped; SSR-safe fallback. */
export function defaultNodesWidth(): number {
  const w = typeof window !== "undefined" ? window.innerWidth : 1400;
  return Math.max(NODES_WIDTH.min, Math.min(NODES_WIDTH.max, Math.round(w / 5)));
}

const DEFAULT_LAYOUT: LayoutState = {
  nodesPane: true,
  nodesWidth: defaultNodesWidth(),
  statusBar: true,
  aside: true,
  rememberView: true,
};

const STORAGE_KEY = "volfit.workbench.v1";
const ACTIVITY_IDS = ACTIVITIES.map((a) => a.id);

interface Persisted {
  activity: Activity;
  tabs: TabsState;
  layout: LayoutState;
  viewMemory: ViewMemory;
}

/** Lenient layout restore: unknown / malformed fields keep `base`. */
function restoreLayout(raw: unknown, base: LayoutState): LayoutState {
  const l = (raw ?? {}) as Partial<LayoutState>;
  return {
    nodesPane: typeof l.nodesPane === "boolean" ? l.nodesPane : base.nodesPane,
    nodesWidth: Number.isFinite(l.nodesWidth)
      ? Math.max(NODES_WIDTH.min, Math.min(NODES_WIDTH.max, Number(l.nodesWidth)))
      : base.nodesWidth,
    statusBar: typeof l.statusBar === "boolean" ? l.statusBar : base.statusBar,
    aside: typeof l.aside === "boolean" ? l.aside : base.aside,
    rememberView: typeof l.rememberView === "boolean" ? l.rememberView : base.rememberView,
  };
}

function loadPersisted(): Persisted {
  const fallback: Persisted = {
    activity: "parametric", tabs: EMPTY_TABS, layout: DEFAULT_LAYOUT, viewMemory: EMPTY_VIEW_MEMORY,
  };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const p = JSON.parse(raw) as Partial<Persisted>;
    const tabs = restoreTabs(p.tabs);
    return {
      activity: ACTIVITY_IDS.includes(p.activity as Activity) ? (p.activity as Activity) : "parametric",
      tabs,
      layout: restoreLayout(p.layout, DEFAULT_LAYOUT),
      viewMemory: pruneViewMemory(restoreViewMemory(p.viewMemory), tabs),
    };
  } catch {
    return fallback;
  }
}

function persist(p: Persisted): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* best-effort */
  }
}

export interface WorkbenchValue {
  activity: Activity;
  setActivity: (a: Activity) => void;
  tabs: WorkbenchTab[];
  activeTab: WorkbenchTab | null;
  /** Open (or focus) a node's tab; optionally switch the lens at the same time. */
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
  /** Show the Nodes pane and hand it the keyboard focus (Ctrl+B; wave 3, C1).
   *  `nodesFocusSeq` advances on every request — the pane focuses its tree. */
  focusNodesPane: () => void;
  nodesFocusSeq: number;
  /** Per-tab view memory (wave 3, C2) — read + written via useLensViewMemory. */
  viewMemory: ViewMemory;
  setViewMemory: (key: string, lens: string, value: unknown) => void;
  /** The shell's share of a workspace FILE (wave 3, A1): activity + tabs +
   *  layout + view memory as a plain blob, and its inverse (lenient —
   *  unknown values keep the current state; tabs are validated by restoreTabs). */
  exportShell: () => ShellShellBlob;
  importShell: (blob: Partial<ShellShellBlob> | null | undefined) => void;
}

/** Workbench part of the workspace-file shell blob. */
export interface ShellShellBlob {
  activity: Activity;
  tabs: TabsState;
  layout: LayoutState;
  viewMemory: ViewMemory;
}

const Ctx = createContext<WorkbenchValue | null>(null);

/** Mount inside SmileSessionProvider (it reconciles the session selection). */
export function WorkbenchProvider({ children }: { children: ReactNode }) {
  const { universe, ticker, expiry, setTicker, setExpiry } = useSmileSession();
  const [initial] = useState(loadPersisted);
  const [activity, setActivity] = useState<Activity>(initial.activity);
  const [tabs, setTabs] = useState<TabsState>(initial.tabs);
  const [layout, setLayoutState] = useState<LayoutState>(initial.layout);
  const [dialog, setDialog] = useState<DialogId | null>(null);
  const [viewMemory, setViewMemoryState] = useState<ViewMemory>(initial.viewMemory);

  // Persist on every change (small JSON; no debounce needed).
  useEffect(
    () => persist({ activity, tabs, layout, viewMemory }),
    [activity, tabs, layout, viewMemory],
  );
  // Memory follows the tabs: whatever closed / got pruned loses its entry.
  useEffect(() => setViewMemoryState((m) => pruneViewMemory(m, tabs)), [tabs]);

  const active = activeTabOf(tabs);
  const activeKey = tabs.activeKey;
  const universeLoaded = universe !== null && ticker !== "";

  // Prune tabs whose node left the universe (removed ticker / deselected expiry).
  useEffect(() => {
    if (universe === null) return;
    setTabs((prev) =>
      pruneTabs(prev, (t, e) => (universe.expiries[t] ?? []).some((r) => r.expiry === e)),
    );
  }, [universe]);

  // Key of a tab→session push in flight; the session→tab reconciliation skips
  // until the session lands on it (see the module comment).
  const pushRef = useRef<string | null>(null);

  // Tab → session: the active tab drives the shared selection.
  useEffect(() => {
    if (!universeLoaded || active === null) return;
    if (ticker === active.ticker && expiry === active.expiry) return;
    pushRef.current = active.key;
    setTicker(active.ticker);
    setExpiry(active.expiry);
    // Deliberately NOT keyed on ticker/expiry: a session change is handled by
    // the reconciliation below, never by re-pushing the tab.
  }, [universeLoaded, activeKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Session → tab: a selection made elsewhere opens / focuses a PREVIEW tab.
  useEffect(() => {
    if (!universeLoaded) return;
    const key = tabKey(ticker, expiry);
    if (active !== null && active.key === key) {
      pushRef.current = null;
      return;
    }
    if (pushRef.current !== null && pushRef.current !== key) return; // push in flight
    pushRef.current = null;
    openWithMemory({ ticker, expiry }, true);
  }, [universeLoaded, ticker, expiry]); // eslint-disable-line react-hooks/exhaustive-deps

  // Open a tab AND let a brand-new tab inherit the active tab's view memory
  // (lib/workbenchTabs.openTabWithMemory). Reads the memory ref so the two
  // state updates stay consistent without a combined reducer.
  const memoryRef = useRef(viewMemory);
  memoryRef.current = viewMemory;
  const openWithMemory = useCallback((node: NodeRef, preview: boolean) => {
    setTabs((prev) => {
      const r = openTabWithMemory(prev, memoryRef.current, node, { preview });
      if (r.memory !== memoryRef.current) {
        memoryRef.current = r.memory;
        setViewMemoryState(r.memory);
      }
      return r.tabs;
    });
  }, []);

  const openNode = useCallback(
    (node: NodeRef, opts: { preview?: boolean; activity?: Activity } = {}) => {
      openWithMemory(node, opts.preview ?? false);
      if (opts.activity) setActivity(opts.activity);
    },
    [openWithMemory],
  );
  const setViewMemory = useCallback(
    (key: string, lens: string, value: unknown) =>
      setViewMemoryState((m) => setViewMemoryPure(m, key, lens, value)),
    [],
  );
  const pinTab = useCallback((key: string) => setTabs((p) => pinTabPure(p, key)), []);
  const closeTab = useCallback((key: string) => setTabs((p) => closeTabPure(p, key)), []);
  const closeOthers = useCallback((key: string) => setTabs((p) => closeOthersPure(p, key)), []);
  const closeAll = useCallback(() => setTabs(closeAllTabs()), []);
  const activateTab = useCallback((key: string) => setTabs((p) => activateTabPure(p, key)), []);
  const cycleTab = useCallback((delta: number) => setTabs((p) => cycleTabPure(p, delta)), []);
  const moveTab = useCallback(
    (key: string, toIndex: number) => setTabs((p) => moveTabPure(p, key, toIndex)),
    [],
  );

  const setLayout = useCallback(
    (patch: Partial<LayoutState>) => setLayoutState((l) => ({ ...l, ...patch })),
    [],
  );
  const resetLayout = useCallback(
    () => setLayoutState({ ...DEFAULT_LAYOUT, nodesWidth: defaultNodesWidth() }),
    [],
  );
  const openDialog = useCallback((id: DialogId) => setDialog(id), []);
  const closeDialog = useCallback(() => setDialog(null), []);
  const [nodesFocusSeq, setNodesFocusSeq] = useState(0);
  const focusNodesPane = useCallback(() => {
    setLayoutState((l) => (l.nodesPane ? l : { ...l, nodesPane: true }));
    setNodesFocusSeq((n) => n + 1);
  }, []);

  // Workspace-file shell blob (A1): the persisted state, in and out.
  const exportShell = useCallback(
    (): ShellShellBlob => ({ activity, tabs, layout, viewMemory }),
    [activity, tabs, layout, viewMemory],
  );
  const importShell = useCallback((blob: Partial<ShellShellBlob> | null | undefined) => {
    if (!blob) return;
    if (ACTIVITY_IDS.includes(blob.activity as Activity)) setActivity(blob.activity as Activity);
    if (blob.tabs !== undefined) {
      const next = restoreTabs(blob.tabs);
      pushRef.current = next.activeKey; // restored tabs beat the session (see module doc)
      setTabs(next);
      setViewMemoryState(pruneViewMemory(restoreViewMemory(blob.viewMemory), next));
    }
    if (blob.layout) setLayoutState((cur) => restoreLayout(blob.layout, cur));
  }, []);

  const value = useMemo<WorkbenchValue>(
    () => ({
      activity, setActivity,
      tabs: tabs.tabs, activeTab: active,
      openNode, pinTab, closeTab, closeOthers, closeAll, activateTab, cycleTab, moveTab,
      layout, setLayout, resetLayout,
      dialog, openDialog, closeDialog,
      focusNodesPane, nodesFocusSeq,
      viewMemory, setViewMemory,
      exportShell, importShell,
    }),
    [
      activity, tabs, active, openNode, pinTab, closeTab, closeOthers, closeAll,
      activateTab, cycleTab, moveTab, layout, setLayout, resetLayout, dialog,
      openDialog, closeDialog, focusNodesPane, nodesFocusSeq, viewMemory, setViewMemory,
      exportShell, importShell,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Consume the workbench shell state; throws outside a WorkbenchProvider. */
export function useWorkbench(): WorkbenchValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useWorkbench must be used within WorkbenchProvider");
  return ctx;
}

/** Optional consumer for components that also render outside the shell
 *  (tests, legacy mounts): null when no provider is present. */
export function useOptionalWorkbench(): WorkbenchValue | null {
  return useContext(Ctx);
}

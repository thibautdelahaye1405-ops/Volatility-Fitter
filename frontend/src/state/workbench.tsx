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
// Persistence: activity + tabs + layout in localStorage ("volfit.workbench")
// so a reload restores the workbench exactly (tabs are pruned against the
// universe once it loads).
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
  activateTab as activateTabPure,
  activeTab as activeTabOf,
  closeAllTabs,
  closeOtherTabs as closeOthersPure,
  closeTab as closeTabPure,
  cycleTab as cycleTabPure,
  moveTab as moveTabPure,
  openTab as openTabPure,
  pinTab as pinTabPure,
  pruneTabs,
  restoreTabs,
  tabKey,
} from "../lib/workbenchTabs";
import type { NodeRef, TabsState, WorkbenchTab } from "../lib/workbenchTabs";

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
export type DialogId = "universe" | "options" | "shortcuts" | "about";

export interface LayoutState {
  /** Nodes pane visible (Ctrl+B). */
  nodesPane: boolean;
  /** Nodes pane width in px (resizer; default = 1/5 of the viewport). */
  nodesWidth: number;
  /** Bottom status bar visible. */
  statusBar: boolean;
  /** Diagnostics / config asides inside the lenses. */
  aside: boolean;
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
};

const STORAGE_KEY = "volfit.workbench.v1";
const ACTIVITY_IDS = ACTIVITIES.map((a) => a.id);

interface Persisted {
  activity: Activity;
  tabs: TabsState;
  layout: LayoutState;
}

function loadPersisted(): Persisted {
  const fallback: Persisted = { activity: "parametric", tabs: EMPTY_TABS, layout: DEFAULT_LAYOUT };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const p = JSON.parse(raw) as Partial<Persisted>;
    const l = (p.layout ?? {}) as Partial<LayoutState>;
    return {
      activity: ACTIVITY_IDS.includes(p.activity as Activity) ? (p.activity as Activity) : "parametric",
      tabs: restoreTabs(p.tabs),
      layout: {
        nodesPane: l.nodesPane !== false,
        nodesWidth: Math.max(
          NODES_WIDTH.min,
          Math.min(NODES_WIDTH.max, Number(l.nodesWidth) || DEFAULT_LAYOUT.nodesWidth),
        ),
        statusBar: l.statusBar !== false,
        aside: l.aside !== false,
      },
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

  // Persist on every change (small JSON; no debounce needed).
  useEffect(() => persist({ activity, tabs, layout }), [activity, tabs, layout]);

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
    setTabs((prev) => openTabPure(prev, { ticker, expiry }, { preview: true }));
  }, [universeLoaded, ticker, expiry]); // eslint-disable-line react-hooks/exhaustive-deps

  const openNode = useCallback(
    (node: NodeRef, opts: { preview?: boolean; activity?: Activity } = {}) => {
      setTabs((prev) => openTabPure(prev, node, { preview: opts.preview ?? false }));
      if (opts.activity) setActivity(opts.activity);
    },
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

  const value = useMemo<WorkbenchValue>(
    () => ({
      activity, setActivity,
      tabs: tabs.tabs, activeTab: active,
      openNode, pinTab, closeTab, closeOthers, closeAll, activateTab, cycleTab, moveTab,
      layout, setLayout, resetLayout,
      dialog, openDialog, closeDialog,
    }),
    [
      activity, tabs, active, openNode, pinTab, closeTab, closeOthers, closeAll,
      activateTab, cycleTab, moveTab, layout, setLayout, resetLayout, dialog,
      openDialog, closeDialog,
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
